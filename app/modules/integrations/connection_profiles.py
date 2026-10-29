"""Group-owned, versioned outbound connections. Public views never expose secrets."""
import json
import re
from contextlib import contextmanager

from peewee import IntegrityError, SqliteDatabase

from app.modules.common.time import utc_now
from app.modules.integrations.connection_options import (
    SECRET_FIELDS, ResolvedConnection, parse_input, merge_credentials, require_credentials_for_identity_change,
)
from app.modules.db.db_model import (
    ConnectionProfile, ConnectionProfileRevision, ConnectionProfileUse, Groups,
)
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.roxywi import logger
from app.modules.roxywi.exception import (
    RoxywiConflictError, RoxywiPermissionError, RoxywiResourceNotFound, RoxywiValidationError,
)


def _visible(group_id):
    return (ConnectionProfile.group_id == int(group_id)) | (ConnectionProfile.group_id == 0)


def get(profile_id, group_id):
    profile = ConnectionProfile.get_or_none((ConnectionProfile.id == profile_id) & _visible(group_id))
    if profile is None:
        raise RoxywiResourceNotFound('Connection profile not found in this group')
    return profile


def public(profile):
    credentials = deserialize_operation_payload(profile.credentials_encrypted)
    return dict(id=profile.id, group_id=profile.group_id, name=profile.name,
                enabled=bool(profile.enabled), revision=profile.revision,
                settings=json.loads(profile.settings),
                configured={key: bool(credentials.get(key)) for key in sorted(SECRET_FIELDS)})


def list_profiles(group_id):
    return [public(p) for p in ConnectionProfile.select().where(_visible(group_id)).order_by(ConnectionProfile.name)]


def _may_manage(profile_group, active_group, role):
    if int(role) == 1:
        return
    if int(role) != 2 or int(profile_group) == 0 or int(profile_group) != int(active_group):
        raise RoxywiPermissionError('Cannot manage this connection profile')


@contextmanager
def _write(profile_id=None, group_id=None, scope_group_id=None):
    database = ConnectionProfile._meta.database
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        scope = group_id if scope_group_id is None else scope_group_id
        if scope:
            parent = Groups.select().where(Groups.group_id == scope)
            if not isinstance(database, SqliteDatabase):
                parent = parent.for_update()
            if parent.first() is None:
                raise RoxywiValidationError('Group does not exist')
        if profile_id is not None:
            query = ConnectionProfile.select().where(
                (ConnectionProfile.id == profile_id) & _visible(group_id))
            if not isinstance(database, SqliteDatabase):
                query = query.for_update()
            if query.first() is None:
                raise RoxywiResourceNotFound('Connection profile not found in this group')
        yield


def save(data, *, group_id, role, actor_id, profile_id=None):
    body = parse_input(data)
    _may_manage(body.group_id, group_id, role)
    if body.group_id and not Groups.select().where(Groups.group_id == body.group_id).exists():
        raise RoxywiValidationError('Group does not exist')
    settings = body.model_dump(exclude={'name', 'group_id', 'enabled', 'revision', 'secrets', 'clear_secrets'})
    try:
        with _write(profile_id, group_id, scope_group_id=body.group_id):
            if profile_id is not None:
                old = get(profile_id, group_id)
                _may_manage(old.group_id, group_id, role)
                if body.group_id != old.group_id:
                    raise RoxywiValidationError('Create a new profile to change its group')
                if body.revision != old.revision:
                    raise RoxywiConflictError('The profile changed; reload before saving')
                previous = deserialize_operation_payload(old.credentials_encrypted)
                require_credentials_for_identity_change(body, json.loads(old.settings), previous)
                credentials = merge_credentials(body, previous)
                encrypted = serialize_operation_payload(credentials)
                changed = ConnectionProfile.update(
                    name=body.name, enabled=body.enabled, settings=json.dumps(settings),
                    credentials_encrypted=encrypted, revision=old.revision + 1, updated_at=utc_now(),
                ).where((ConnectionProfile.id == old.id) & (ConnectionProfile.revision == old.revision)).execute()
                if changed != 1:
                    raise RoxywiConflictError('The profile changed; reload before saving')
                profile = ConnectionProfile.get_by_id(old.id)
            else:
                credentials = merge_credentials(body, {})
                profile = ConnectionProfile.create(
                    group_id=body.group_id, scope_group=body.group_id or None, name=body.name, enabled=body.enabled,
                    settings=json.dumps(settings), credentials_encrypted=serialize_operation_payload(credentials),
                    created_by=actor_id,
                )
            ConnectionProfileRevision.create(
                profile_id=profile.id, revision=profile.revision, settings=profile.settings,
                credentials_encrypted=profile.credentials_encrypted, changed_by=actor_id,
            )
    except IntegrityError:
        raise RoxywiConflictError('A connection profile with this name already exists') from None
    logger.info('Connection profile saved', user_id=actor_id, group_id=profile.group_id,
                profile_id=profile.id, revision=profile.revision)
    return public(profile)


def resolve(profile_id, group_id, *, revision=None):
    profile = get(profile_id, group_id)
    if not profile.enabled:
        raise RoxywiConflictError('Connection profile is disabled')
    row = profile
    if revision is not None:
        row = ConnectionProfileRevision.get_or_none(
            (ConnectionProfileRevision.profile_id == profile.id) &
            (ConnectionProfileRevision.revision == revision))
        if row is None:
            raise RoxywiResourceNotFound('Connection profile revision not found')
    return ResolvedConnection(profile.id, row.revision, json.loads(row.settings),
                              deserialize_operation_payload(row.credentials_encrypted))


def delete(profile_id, *, group_id, role, actor_id, revision):
    with _write(profile_id, group_id):
        profile = get(profile_id, group_id)
        _may_manage(profile.group_id, group_id, role)
        if ConnectionProfileUse.select().where(ConnectionProfileUse.profile_id == profile.id).exists():
            raise RoxywiConflictError('This profile is in use; disable it instead')
        changed = ConnectionProfile.delete().where(
            (ConnectionProfile.id == profile.id) & (ConnectionProfile.revision == revision)).execute()
        if changed != 1:
            raise RoxywiConflictError('The profile changed; reload before deleting')
        ConnectionProfileRevision.delete().where(ConnectionProfileRevision.profile_id == profile.id).execute()
    logger.info('Connection profile deleted', user_id=actor_id, group_id=profile.group_id, profile_id=profile.id)


def bind_use(profile_id, group_id, *, consumer, consumer_id):
    """Consumers register their reference in the transaction creating that use."""
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', consumer) or not 1 <= len(str(consumer_id)) <= 128:
        raise RoxywiValidationError('Invalid connection profile reference')
    with _write(profile_id, group_id):
        connection = resolve(profile_id, group_id)
        existing = ConnectionProfileUse.get_or_none(
            (ConnectionProfileUse.consumer == consumer) & (ConnectionProfileUse.consumer_id == str(consumer_id)))
        if existing:
            existing.profile_id = profile_id
            existing.save()
        else:
            ConnectionProfileUse.create(profile_id=profile_id, consumer=consumer, consumer_id=str(consumer_id))
        return connection
