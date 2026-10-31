"""Explicit audit schema; no request bodies, log exception strings or credentials."""
from contextlib import contextmanager
from datetime import timedelta
import json
import ipaddress
import os
import re
from uuid import uuid4

from peewee import SqliteDatabase

from app.modules.common.time import utc_now
from app.modules.db.db_model import AuditEvent, AuditDestination, AuditDestinationRevision, AuditDelivery, AuditState, User


class AuditStorageUnavailable(RuntimeError):
    pass


DETAIL_FIELDS = frozenset({
    'subject_type', 'subject_id', 'operation_id', 'task_id', 'change_id', 'target_id',
    'status', 'before_digest', 'after_digest', 'method', 'route', 'reason_code',
    'token_id', 'credential_id', 'request_id', 'http_status', 'profile_id', 'revision',
})
TERMINAL_DELIVERY_STATES = ('transport_handoff', 'receiver_accepted', 'datagram_sent')


@contextmanager
def write_transaction():
    database = AuditEvent._meta.database
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        yield


def locked_state():
    state, _ = AuditState.get_or_create(id=1)
    query = AuditState.select().where(AuditState.id == state.id)
    if not isinstance(AuditState._meta.database, SqliteDatabase):
        query = query.for_update()
    return query.get()


def enabled():
    return AuditDestination.select().where(AuditDestination.enabled == True).exists()


def actor_name(user_id):
    if user_id is None:
        return None
    user = User.get_or_none(User.user_id == user_id)
    return user.username if user else f'user:{user_id}'


def _details(values):
    result = {}
    for key in DETAIL_FIELDS:
        value = (values or {}).get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            result[key] = value
        elif isinstance(value, str):
            result[key] = value[:512]
    return result


def record(event_type, outcome, *, user_id=None, group_id=None, actor=None,
           source_ip=None, details=None, force=False, extra_revision_ids=()):
    try:
        if not force and not enabled():
            return None
    except Exception as error:
        raise AuditStorageUnavailable('Audit storage unavailable') from error
    if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}', event_type):
        raise ValueError('Invalid audit event type')
    if outcome not in {'requested', 'accepted', 'succeeded', 'failed', 'denied', 'unknown', 'pending'}:
        raise ValueError('Invalid audit outcome')
    user_id = int(user_id) if user_id is not None else None
    group_id = int(group_id) if group_id is not None else None
    try:
        source_ip = str(ipaddress.ip_address(source_ip)) if source_ip else None
    except ValueError:
        source_ip = None
    try:
        actor = actor if actor is not None else actor_name(user_id)
    except Exception as error:
        raise AuditStorageUnavailable('Audit actor storage unavailable') from error
    actor = str(actor)[:256] if actor is not None else None
    now = utc_now()
    event_id = str(uuid4())
    payload = dict(schema=1, id=event_id, type=event_type, outcome=outcome,
                   timestamp=now.isoformat()+'Z', actor_id=user_id,
                   actor_name=actor,
                   group_id=group_id, source_ip=source_ip, details=_details(details))
    encoded = json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > 8192:
        raise AuditStorageUnavailable('Audit record exceeds the storage limit')
    limit = max(100, min(100000, int(os.environ.get('ROXYWI_AUDIT_MAX_EVENTS', '10000'))))
    # A bounded reserve permits result records for started actions and
    # audited receiver repair. Ordinary request intents cannot consume it.
    if force:
        limit += 100
    try:
        with write_transaction():
            state = locked_state()
            if state.records >= limit:
                raise AuditStorageUnavailable('Audit storage limit reached; inspect queued deliveries')
            AuditEvent.create(event_id=event_id, group_id=group_id, event_type=event_type,
                              outcome=outcome, payload=encoded, created_at=now)
            selected = set(extra_revision_ids)
            for destination in AuditDestination.select().where(AuditDestination.enabled == True):
                if destination.group_id not in (0, group_id):
                    continue
                filters = json.loads(destination.events)
                if '*' not in filters and event_type not in filters:
                    continue
                revision = AuditDestinationRevision.get(
                    (AuditDestinationRevision.destination_id == destination.id) &
                    (AuditDestinationRevision.revision == destination.revision))
                selected.add(revision.id)
            for revision_id in selected:
                AuditDestinationRevision.get_by_id(revision_id)
                AuditDelivery.create(event_id=event_id, destination_revision_id=revision_id)
            AuditState.update(records=AuditState.records+1).where(AuditState.id == 1).execute()
    except AuditStorageUnavailable:
        raise
    except Exception as error:
        raise AuditStorageUnavailable('Audit storage unavailable') from error
    return event_id


def prune(retention_days=30):
    """Expired successful records can go; pending/failed delivery work survives."""
    cutoff = utc_now()-timedelta(days=max(1, retention_days))
    blocked = AuditDelivery.select(AuditDelivery.event_id).where(
        ~AuditDelivery.status.in_(TERMINAL_DELIVERY_STATES))
    with write_transaction():
        state = locked_state()
        ids = [row.event_id for row in AuditEvent.select(AuditEvent.event_id).where(
            (AuditEvent.created_at < cutoff) & AuditEvent.event_id.not_in(blocked)
        ).order_by(AuditEvent.created_at).limit(200)]
        if not ids:
            return 0
        AuditDelivery.delete().where(AuditDelivery.event_id.in_(ids)).execute()
        count = AuditEvent.delete().where(AuditEvent.event_id.in_(ids)).execute()
        AuditState.update(records=max(0, state.records-count)).where(AuditState.id == 1).execute()
        return count
