"""Versioned receivers with an optional adapter to shared connection profiles."""
import importlib.util
import json
import re

from peewee import IntegrityError, SqliteDatabase

from app.modules.audit.events import record, write_transaction, locked_state, TERMINAL_DELIVERY_STATES
from app.modules.db.db_model import AuditDestination, AuditDestinationRevision, AuditDelivery, Groups
from app.modules.integrations.connection_options import (
    SECRET_FIELDS, ResolvedConnection, parse_input, merge_credentials, require_credentials_for_identity_change,
)
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.roxywi.exception import (
    RoxywiConflictError, RoxywiPermissionError, RoxywiResourceNotFound, RoxywiValidationError,
)


def shared_profiles():
    if importlib.util.find_spec('app.modules.integrations.connection_profiles') is None:
        return None
    from app.modules.integrations import connection_profiles
    return connection_profiles


def get(destination_id, group_id, role):
    query = AuditDestination.select().where(AuditDestination.id == destination_id)
    if int(role) != 1:
        query = query.where(AuditDestination.group_id == int(group_id))
    destination = query.first()
    if destination is None:
        raise RoxywiResourceNotFound('Audit receiver not found')
    return destination


def revision(destination):
    return AuditDestinationRevision.get(
        (AuditDestinationRevision.destination_id == destination.id) &
        (AuditDestinationRevision.revision == destination.revision))


def public(destination):
    current = revision(destination)
    credentials = deserialize_operation_payload(current.credentials_encrypted)
    return dict(id=destination.id, group_id=destination.group_id, name=destination.name,
                enabled=bool(destination.enabled), revision=destination.revision,
                events=json.loads(destination.events), connection=json.loads(current.settings),
                configured={key: bool(credentials.get(key)) for key in sorted(SECRET_FIELDS)},
                profile_id=current.profile_id, profile_revision=current.profile_revision)


def list_destinations(group_id, role):
    query = AuditDestination.select()
    if int(role) != 1:
        query = query.where(AuditDestination.group_id == int(group_id))
    return [public(d) for d in query.order_by(AuditDestination.name)]


def _input(data, group_id, role):
    if not isinstance(data, dict) or set(data)-{
        'name', 'group_id', 'enabled', 'events', 'revision', 'connection', 'profile_id',
    }:
        raise RoxywiValidationError('Invalid audit receiver')
    name = data.get('name')
    scope = data.get('group_id', group_id)
    enabled = data.get('enabled', True)
    filters = data.get('events', ['*'])
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 128
            or type(scope) is not int or type(enabled) is not bool
            or not isinstance(filters, list) or not 1 <= len(filters) <= 100
            or any(not isinstance(v, str) or not re.fullmatch(r'\*|[a-z][a-z0-9_.-]{0,127}', v) for v in filters)):
        raise RoxywiValidationError('Invalid audit receiver settings')
    if int(role) != 1 and (int(role) != 2 or scope != int(group_id)):
        raise RoxywiPermissionError('Cannot manage this audit receiver scope')
    if scope < 0 or scope and not Groups.select().where(Groups.group_id == scope).exists():
        raise RoxywiValidationError('Group does not exist')
    return name.strip(), scope, enabled, list(dict.fromkeys(filters))


def save(data, *, group_id, role, actor_id, destination_id=None):
    name, scope, active, filters = _input(data, group_id, role)
    try:
        with write_transaction():
            locked_state()
            if scope:
                query = Groups.select().where(Groups.group_id == scope)
                if not isinstance(Groups._meta.database, SqliteDatabase):
                    query = query.for_update()
                if query.first() is None:
                    raise RoxywiValidationError('Group does not exist')
            old = get(destination_id, group_id, role) if destination_id else None
            if old and (scope != old.group_id or data.get('revision') != old.revision):
                raise RoxywiConflictError('Receiver scope or revision changed; reload before saving')
            previous = revision(old) if old else None
            profile_id = data.get('profile_id')
            profile_revision = None
            if profile_id is not None:
                if type(profile_id) is not int or profile_id < 1 or data.get('connection'):
                    raise RoxywiValidationError('Choose either a shared profile or inline receiver settings')
                adapter = shared_profiles()
                if adapter is None:
                    raise RoxywiValidationError('Shared connection profiles are not installed')
                resolved = adapter.resolve(profile_id, scope)
                settings, credentials, profile_revision = resolved.settings, resolved.credentials, resolved.revision
            else:
                inline = data.get('connection')
                if not isinstance(inline, dict):
                    raise RoxywiValidationError('Receiver connection settings are required')
                body = parse_input({**inline, 'name': name, 'group_id': scope})
                settings = body.model_dump(exclude={
                    'name', 'group_id', 'enabled', 'revision', 'secrets', 'clear_secrets',
                })
                # A group administrator may use a shared profile but must not
                # copy its hidden credentials into an editable inline endpoint.
                old_credentials = (deserialize_operation_payload(previous.credentials_encrypted)
                                   if previous and previous.profile_id is None else {})
                if previous and previous.profile_id is None:
                    require_credentials_for_identity_change(body, json.loads(previous.settings), old_credentials)
                credentials = merge_credentials(body, old_credentials)
            if old:
                changed = AuditDestination.update(
                    name=name, enabled=active, events=json.dumps(filters), revision=old.revision+1,
                    scope_group=scope if scope else None,
                ).where((AuditDestination.id == old.id) & (AuditDestination.revision == old.revision)).execute()
                if changed != 1:
                    raise RoxywiConflictError('Receiver changed; reload before saving')
                destination = AuditDestination.get_by_id(old.id)
            else:
                if AuditDestination.select().count() >= 20:
                    raise RoxywiConflictError('Audit receiver limit reached (20 per instance)')
                destination = AuditDestination.create(name=name, group_id=scope, enabled=active,
                    scope_group=scope if scope else None, events=json.dumps(filters), created_by=actor_id)
            if profile_id is not None:
                shared_profiles().bind_use(profile_id, scope, consumer='audit',
                                           consumer_id=f'{destination.id}:{destination.revision}')
            AuditDestinationRevision.create(
                destination_id=destination.id, revision=destination.revision,
                settings=json.dumps(settings), credentials_encrypted=serialize_operation_payload(credentials),
                profile_id=profile_id, profile_revision=profile_revision,
            )
            record('audit.receiver.saved', 'succeeded', user_id=actor_id, group_id=scope,
                   details={'subject_type': 'audit_receiver', 'subject_id': destination.id,
                            'revision': destination.revision}, force=True,
                   extra_revision_ids=(previous.id,) if previous and old.enabled else ())
    except IntegrityError:
        raise RoxywiConflictError('Receiver name or group changed; reload before saving') from None
    return public(destination)


def resolve_revision(row):
    if row.profile_id is not None:
        adapter = shared_profiles()
        if adapter is None:
            raise RoxywiConflictError('Shared connection profile adapter is unavailable')
        destination = AuditDestination.get_by_id(row.destination_id)
        # Recheck enabled state/visibility even for already pinned work.
        adapter.resolve(row.profile_id, destination.group_id, revision=row.profile_revision)
    return ResolvedConnection(row.destination_id, row.revision, json.loads(row.settings),
                              deserialize_operation_payload(row.credentials_encrypted))


def _release_profile_uses(rows):
    shared = [row for row in rows if row.profile_id is not None]
    if not shared:
        return
    if shared_profiles() is None:
        raise RoxywiConflictError('Restore the shared profile adapter before deleting this receiver')
    from app.modules.db.db_model import ConnectionProfileUse
    consumers = [f'{row.destination_id}:{row.revision}' for row in shared]
    ConnectionProfileUse.delete().where((ConnectionProfileUse.consumer == 'audit') &
                                       ConnectionProfileUse.consumer_id.in_(consumers)).execute()


def delete(destination_id, *, group_id, role, actor_id, expected_revision):
    """Delete disabled, fully delivered receiver data while preserving event history."""
    if type(expected_revision) is not int:
        raise RoxywiValidationError('A receiver revision is required')
    with write_transaction():
        locked_state()
        destination = get(destination_id, group_id, role)
        if destination.revision != expected_revision:
            raise RoxywiConflictError('Receiver changed; reload before deleting')
        if destination.enabled:
            raise RoxywiConflictError('Disable the receiver before deleting it')
        revisions = list(AuditDestinationRevision.select().where(
            AuditDestinationRevision.destination_id == destination.id))
        ids = [row.id for row in revisions]
        work = AuditDelivery.select().where(AuditDelivery.destination_revision_id.in_(ids))
        if work.where(~AuditDelivery.status.in_(TERMINAL_DELIVERY_STATES)).exists():
            raise RoxywiConflictError('Undelivered work must finish before deleting this receiver')
        _release_profile_uses(revisions)
        AuditDelivery.delete().where(AuditDelivery.destination_revision_id.in_(ids)).execute()
        AuditDestinationRevision.delete().where(AuditDestinationRevision.destination_id == destination.id).execute()
        changed = AuditDestination.delete().where((AuditDestination.id == destination.id) &
            (AuditDestination.revision == expected_revision) & (AuditDestination.enabled == False)).execute()
        if changed != 1:
            raise RoxywiConflictError('Receiver changed; reload before deleting')
        # The removed receiver is disabled and already absent from selection;
        # the deletion event goes only to other enabled receivers or local history.
        record('audit.receiver.deleted', 'succeeded', user_id=actor_id, group_id=destination.group_id,
               details={'subject_type': 'audit_receiver', 'subject_id': destination.id,
                        'revision': destination.revision}, force=True)
    return dict(status='deleted')


def retry_failed(destination_id, *, group_id, role, actor_id, expected_revision, include_pending=False):
    """Explicitly rebind selected undelivered work to the current revision."""
    if type(expected_revision) is not int or type(include_pending) is not bool:
        raise RoxywiValidationError('A receiver revision and boolean include_pending option are required')
    repairable = ('failed', 'pending') if include_pending else ('failed',)
    with write_transaction():
        locked_state()
        destination = get(destination_id, group_id, role)
        if destination.revision != expected_revision:
            raise RoxywiConflictError('Receiver changed; reload before retrying')
        current = revision(destination)
        resolve_revision(current)
        ids = AuditDestinationRevision.select(AuditDestinationRevision.id).where(
            AuditDestinationRevision.destination_id == destination.id)
        from app.modules.common.time import utc_now
        count = 0
        for item in AuditDelivery.select().where(
                (AuditDelivery.destination_revision_id.in_(ids)) & AuditDelivery.status.in_(repairable)):
            duplicate = AuditDelivery.get_or_none(
                (AuditDelivery.event_id == item.event_id) &
                (AuditDelivery.destination_revision_id == current.id) & (AuditDelivery.id != item.id))
            if duplicate:
                # The same UUID may have targeted both old/new revisions during
                # receiver reconfiguration. Preserve the existing current delivery.
                if duplicate.status in repairable:
                    AuditDelivery.update(status='pending', retry_at=utc_now(), last_error=None,
                                         claim_token=None, claim_expires_at=None).where(
                        AuditDelivery.id == duplicate.id).execute()
                AuditDelivery.delete().where(AuditDelivery.id == item.id).execute()
            else:
                AuditDelivery.update(destination_revision_id=current.id, status='pending',
                                     retry_at=utc_now(), last_error=None, claim_token=None,
                                     claim_expires_at=None).where(
                    AuditDelivery.id == item.id).execute()
            count += 1
        record('audit.delivery.retry_requested', 'requested', user_id=actor_id, group_id=destination.group_id,
               details={'subject_id': destination.id, 'revision': destination.revision,
                        'reason_code': 'requeue_undelivered' if include_pending else 'retry_failed'}, force=True)
        return count


def prune_unused_revisions():
    """Release shared-profile references only after all pinned work is removed."""
    with write_transaction():
        locked_state()
        used = AuditDelivery.select(AuditDelivery.destination_revision_id)
        for row in AuditDestinationRevision.select().where(AuditDestinationRevision.id.not_in(used)):
            destination = AuditDestination.get_or_none(AuditDestination.id == row.destination_id)
            if destination and destination.revision == row.revision:
                continue
            if row.profile_id is not None:
                adapter = shared_profiles()
                if adapter is not None:
                    from app.modules.db.db_model import ConnectionProfileUse
                    ConnectionProfileUse.delete().where(
                        (ConnectionProfileUse.consumer == 'audit') &
                        (ConnectionProfileUse.consumer_id == f'{row.destination_id}:{row.revision}')).execute()
            row.delete_instance()


def status(group_id, role):
    ids = AuditDestination.select(AuditDestination.id)
    if int(role) != 1:
        ids = ids.where(AuditDestination.group_id == int(group_id))
    revisions = AuditDestinationRevision.select(AuditDestinationRevision.id).where(
        AuditDestinationRevision.destination_id.in_(ids))
    counts = {}
    from peewee import fn
    for row in AuditDelivery.select(AuditDelivery.status, fn.COUNT(AuditDelivery.id).alias('total')).where(
            AuditDelivery.destination_revision_id.in_(revisions)).group_by(AuditDelivery.status):
        counts[row.status] = row.total
    # Receiver-controlled data and global activity are never exposed across groups.
    recent = [dict(id=row.id, status=row.status, attempts=row.attempts, error=row.last_error,
                   event_id=row.event_id, receiver_revision_id=row.destination_revision_id)
              for row in AuditDelivery.select().where(AuditDelivery.destination_revision_id.in_(revisions))
              .order_by(AuditDelivery.id.desc()).limit(30)]
    return dict(counts=counts, deliveries=recent)
