"""Atomically rotate the Fernet key used for stored Roxy-WI credentials."""

import os
from itertools import chain

from cryptography.fernet import Fernet, InvalidToken

from app.modules.db.db_model import Cred, InstallationTasks, LetsEncryptState, LetsEncryptDnsProfile, OidcProvider


SECRET_FIELDS = ('password', 'passphrase', 'private_key')


def _fernet_from_environment(variable_name: str) -> Fernet:
    value = os.environ.get(variable_name)
    if not value:
        raise RuntimeError(f'{variable_name} is required')
    if value == 'CHANGE_ME':
        raise RuntimeError(f'{variable_name} must not be CHANGE_ME')
    try:
        return Fernet(value.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(f'{variable_name} is not a valid Fernet key') from exc


def rotate_credentials() -> int:
    old_fernet = _fernet_from_environment('ROXYWI_OLD_SECRET_PHRASE')
    new_fernet = _fernet_from_environment('ROXYWI_SECRET_PHRASE')
    database = Cred._meta.database
    rotated_credentials = 0

    with database.atomic():
        for credential in Cred.select():
            updates = {}
            for field_name in SECRET_FIELDS:
                encrypted_value = getattr(credential, field_name)
                if encrypted_value in (None, '', 'None'):
                    continue
                token = encrypted_value.encode('utf-8') if isinstance(encrypted_value, str) else encrypted_value
                try:
                    plaintext = old_fernet.decrypt(token)
                except InvalidToken as exc:
                    try:
                        new_fernet.decrypt(token)
                    except InvalidToken:
                        raise RuntimeError(
                            f'Credential {credential.id} contains an invalid {field_name} token'
                        ) from exc
                    continue
                updates[field_name] = new_fernet.encrypt(plaintext).decode('ascii')

            if updates:
                Cred.update(**updates).where(Cred.id == credential.id).execute()
                rotated_credentials += 1

        for provider in OidcProvider.select().where(
            OidcProvider.client_secret_encrypted.is_null(False)
        ):
            encrypted_value = provider.client_secret_encrypted
            if encrypted_value in ('', 'None'):
                continue
            token = encrypted_value.encode('utf-8') if isinstance(encrypted_value, str) else encrypted_value
            try:
                plaintext = old_fernet.decrypt(token)
            except InvalidToken as exc:
                try:
                    new_fernet.decrypt(token)
                except InvalidToken:
                    raise RuntimeError(
                        f'OIDC provider {provider.id} contains an invalid client secret token'
                    ) from exc
                continue

            OidcProvider.update(
                client_secret_encrypted=new_fernet.encrypt(plaintext).decode('ascii')
            ).where(OidcProvider.id == provider.id).execute()
            rotated_credentials += 1

        for task in InstallationTasks.select().where(
            InstallationTasks.operation_payload.is_null(False)
        ):
            payload = task.operation_payload
            if not payload.startswith('fernet:'):
                continue
            token = payload.removeprefix('fernet:').encode('ascii')
            try:
                plaintext = old_fernet.decrypt(token)
            except InvalidToken as exc:
                try:
                    new_fernet.decrypt(token)
                except InvalidToken:
                    raise RuntimeError(
                        f'Operation task {task.id} contains an invalid encrypted payload'
                    ) from exc
                continue
            InstallationTasks.update(
                operation_payload='fernet:' + new_fernet.encrypt(plaintext).decode('ascii')
            ).where(InstallationTasks.id == task.id).execute()
            rotated_credentials += 1

        for state in chain(LetsEncryptState.select(), LetsEncryptDnsProfile.select()):
            updates = {}
            fields = ('credentials', 'pending_config') if isinstance(state, LetsEncryptState) else ('credentials',)
            for field in fields:
                value = getattr(state, field)
                if not value:
                    continue
                if not value.startswith('fernet:'):
                    raise RuntimeError(f'LE secret record {state.id} contains invalid encrypted state')
                token = value.removeprefix('fernet:').encode('ascii')
                try:
                    plaintext = old_fernet.decrypt(token)
                except InvalidToken as error:
                    try:
                        new_fernet.decrypt(token)
                    except InvalidToken:
                        raise RuntimeError(f'LE secret record {state.id} cannot be decrypted') from error
                    continue
                updates[field] = 'fernet:' + new_fernet.encrypt(plaintext).decode('ascii')
            if updates:
                type(state).update(**updates).where(type(state).id == state.id).execute()
                rotated_credentials += 1

    return rotated_credentials


if __name__ == '__main__':
    count = rotate_credentials()
    print(f'Rotated stored secrets: {count}')
