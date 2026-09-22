"""Tenant-owned reusable DNS credentials; public responses contain no secrets."""

from peewee import IntegrityError

from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, LetsEncryptDnsProfile, Server
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiValidationError, RoxywiConflictError


def get(profile_id, group_id):
    row = LetsEncryptDnsProfile.get_or_none((LetsEncryptDnsProfile.id == profile_id) &
                                           (LetsEncryptDnsProfile.group_id == int(str(group_id))))
    if row is None:
        raise RoxywiResourceNotFound('DNS profile not found in this group')
    return row


def public(row):
    credentials = deserialize_operation_payload(row.credentials)
    return dict(id=row.id, name=row.name, provider=row.provider, propagation_seconds=row.propagation_seconds,
                revision=row.revision, has_api_key=bool(credentials.get('api_key')),
                has_api_token=bool(credentials.get('api_token')))


def resolve(data, group_id):
    data = dict(data)
    if data.get('dns_profile_id'):
        profile = get(data['dns_profile_id'], group_id)
        if LetsEncryptDnsProfile._meta.database.in_transaction():
            from app.modules.service.le.le_store import locked
            profile = locked(LetsEncryptDnsProfile, LetsEncryptDnsProfile.id == profile.id)
        if profile.provider != data['type']:
            raise RoxywiValidationError('DNS profile provider does not match the certificate')
        data.update(deserialize_operation_payload(profile.credentials))
        data.update(propagation_seconds=profile.propagation_seconds, profile_revision=profile.revision)
    return data


def save(data, group_id, profile_id=None):
    from app.modules.service.le.le_store import transaction, locked
    with transaction():
        row = get(profile_id, group_id) if profile_id else None
        if row:
            row = locked(LetsEncryptDnsProfile, LetsEncryptDnsProfile.id == row.id)
            if row.provider != data['provider']:
                raise RoxywiValidationError('Create a separate DNS profile when changing provider')
        credentials = deserialize_operation_payload(row.credentials) if row else {}
        for key in ('api_key', 'api_token'):
            if data.get(key) is not None:
                credentials[key] = data[key]
        if not credentials.get('api_token') or (data['provider'] == 'route53' and not credentials.get('api_key')):
            raise RoxywiValidationError('DNS profile credentials are required')
        values = dict(name=data['name'], provider=data['provider'], group_id=int(str(group_id)),
                      credentials=serialize_operation_payload(credentials), propagation_seconds=data['propagation_seconds'])
        try:
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
                row.revision += 1
                row.save()
            else:
                row = LetsEncryptDnsProfile.create(**values)
        except IntegrityError:
            raise RoxywiConflictError('A DNS profile with this name already exists') from None
        return public(row)


def delete(profile_id, group_id):
    from app.modules.service.le.le_store import transaction, locked
    with transaction():
        row = get(profile_id, group_id)
        locked(LetsEncryptDnsProfile, LetsEncryptDnsProfile.id == row.id)
        # Current read after the profile lock, including concurrently committed attachments.
        query = (LetsEncryptState.select().join(LetsEncrypt, on=(LetsEncrypt.id == LetsEncryptState.le_id))
                 .join(Server).where((Server.group_id == str(group_id)) & (LetsEncryptState.status != 'deleted')))
        from peewee import SqliteDatabase
        if not isinstance(LetsEncryptState._meta.database, SqliteDatabase):
            query = query.for_update()
        for state in query:
            pending = deserialize_operation_payload(state.pending_config) if state.pending_config else {}
            if state.dns_profile_id == row.id or pending.get('dns_profile_id') == row.id:
                raise RoxywiConflictError('DNS profile is used by a certificate; detach it before deleting')
        row.delete_instance()
