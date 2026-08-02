"""Atomically rotate the Fernet key used for stored SSH credentials."""

import os
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.modules.db.db_model import Cred, connect


KNOWN_INSECURE_SECRET_SHA256 = '81fd19ad32311ada4ffa54bfb9ebed03dc89632a853d0522e2498c420c4315c1'
SECRET_FIELDS = ('password', 'passphrase', 'private_key')


def _fernet_from_environment(variable_name: str, *, allow_known_key: bool) -> Fernet:
    value = os.environ.get(variable_name)
    if not value:
        raise RuntimeError(f'{variable_name} is required')
    if not allow_known_key and (
        value == 'CHANGE_ME' or hashlib.sha256(value.encode()).hexdigest() == KNOWN_INSECURE_SECRET_SHA256
    ):
        raise RuntimeError('The new credential key must be unique')
    try:
        return Fernet(value.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(f'{variable_name} is not a valid Fernet key') from exc


def rotate_credentials() -> int:
    old_fernet = _fernet_from_environment('ROXYWI_OLD_SECRET_PHRASE', allow_known_key=True)
    new_fernet = _fernet_from_environment('ROXYWI_SECRET_PHRASE', allow_known_key=False)
    database = connect()
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

    return rotated_credentials


if __name__ == '__main__':
    count = rotate_credentials()
    print(f'Rotated credentials: {count}')
