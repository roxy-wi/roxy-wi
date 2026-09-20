"""Let's Encrypt desired state, encrypted credentials and durable scheduling."""

import ast
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from peewee import SqliteDatabase

from app.modules.common.time import utc_now
from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, InstallationTasks, Server
from app.modules.operations.queue import serialize_operation_payload, deserialize_operation_payload
from app.modules.roxywi.class_models import LetsEncryptRequest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError, RoxywiResourceNotFound, RoxywiPublicError


ACTIVE = ('created', 'published', 'running')


@contextmanager
def transaction():
    db = LetsEncryptState._meta.database
    with db.atomic(*(('IMMEDIATE',) if isinstance(db, SqliteDatabase) else ())):
        yield


def locked(model, predicate):
    query = model.select().where(predicate)
    if not isinstance(model._meta.database, SqliteDatabase):
        query = query.for_update()
    return query.get()


def config_for(row, state):
    domains = row.domains
    if isinstance(domains, str):
        # Read both the old Python-list representation and new JSON.
        domains = ast.literal_eval(domains)
    data = dict(server_id=row.server_id_id, domains=domains, email=row.email or None,
                type=row.type, description=row.description or '')
    data.update(deserialize_operation_payload(state.credentials) if state.credentials else
                {'api_key': row.api_key, 'api_token': row.api_token})
    return data


def targets_for(server_id, group_id):
    server = Server.get_or_none((Server.server_id == server_id) & (Server.group_id == str(group_id)))
    if server is None:
        raise RoxywiResourceNotFound('Certificate server not found in this group')
    children = list(Server.select().where(Server.master == server_id))
    if any(str(child.group_id) != str(group_id) for child in children):
        raise RoxywiValidationError('HA certificate targets must belong to the same group')
    return [server, *children]


def validate_config(data, group_id, previous=None):
    data = dict(data)
    if previous and data['type'] == previous['type']:
        for field in ('api_key', 'api_token'):
            if data.get(field) is None:
                data[field] = previous.get(field)
    data = LetsEncryptRequest(**data).model_dump(mode='json')
    if data['type'] != 'standalone' and not data.get('api_token'):
        raise RoxywiValidationError('DNS provider token is required')
    if data['type'] == 'route53' and not data.get('api_key'):
        raise RoxywiValidationError('Route53 access key ID is required')
    targets_for(data['server_id'], group_id)
    return data


def write_config(row, state, data):
    for field in ('server_id', 'email', 'type', 'description'):
        setattr(row, field, data.get(field) or '')
    row.domains = json.dumps(data['domains'])
    # Secrets live only in the encrypted TextField, never the legacy varchar.
    row.api_key = row.api_token = ''
    state.credentials = serialize_operation_payload({key: data.get(key) for key in ('api_key', 'api_token')})
    row.save()


def get_owned(le_id, group_id):
    row = (LetsEncrypt.select().join(Server).where(
        (LetsEncrypt.id == le_id) & (Server.group_id == str(group_id))).get_or_none())
    if row is None:
        raise RoxywiResourceNotFound('Certificate not found')
    state = LetsEncryptState.get_or_none(le_id=le_id)
    if state is not None and state.status == 'deleted':
        raise RoxywiResourceNotFound('Certificate not found')
    return row


def editable(le_id):
    state = locked(LetsEncryptState, LetsEncryptState.le_id == le_id)
    if state.legacy_pending:
        raise RoxywiConflictError('Run migrate-le-cron on the original host before changing this certificate')
    if state.active_task_id:
        task = InstallationTasks.get_or_none(InstallationTasks.id == state.active_task_id)
        if task and task.status in ACTIVE:
            raise RoxywiConflictError('Certificate operation is queued or running')
    return state


def check_destination(data, pem_name, group_id, exclude=None):
    # Serialize owners of overlapping HA destinations, in a consistent order.
    targets = targets_for(data['server_id'], group_id)
    ids = {server.server_id for server in targets}
    for server_id in sorted(ids):
        locked(Server, Server.server_id == server_id)
    query = LetsEncryptState.select().where(LetsEncryptState.pem_name == pem_name)
    if not isinstance(LetsEncryptState._meta.database, SqliteDatabase):
        query = query.for_update()  # Current read after waiting on the server lock.
    for state in query:
        if state.le_id == exclude:
            continue
        if state.status == 'deleted':
            continue
        other = LetsEncrypt.get_or_none(LetsEncrypt.id == state.le_id)
        if other is None:
            continue
        other_ids = {other.server_id_id, *[s.server_id for s in Server.select().where(Server.master == other.server_id_id)]}
        if state.pending_config:
            requested = deserialize_operation_payload(state.pending_config)['server_id']
            other_ids |= {requested, *[s.server_id for s in Server.select().where(Server.master == requested)]}
        if ids & other_ids:
            raise RoxywiConflictError('Another certificate already manages this PEM on a target server')


def enqueue(state, data, action, group_id, user_id=None):
    now = utc_now()
    if not state.pending_config:
        state.targets = '{}'
    if data['type'] == 'standalone' and action != 'delete':
        issuers = json.loads(state.issuer_servers)
        if data['server_id'] not in issuers:
            issuers.append(data['server_id'])
        state.issuer_servers = json.dumps(issuers)
    state.pending_config = serialize_operation_payload(data)
    state.pending_action = action
    state.status = 'deleting' if action == 'delete' else 'queued'
    state.retry_at = None
    state.last_error = None
    task_id = InstallationTasks.insert(
        service_name=f"Let's Encrypt #{state.le_id}: {action}",
        server_ids=[s.server_id for s in targets_for(data['server_id'], group_id)],
        group_id=group_id, user_id=user_id, operation_id=str(uuid4()), operation_type='letsencrypt',
        operation_payload=serialize_operation_payload({'le_id': state.le_id, 'revision': state.revision,
                                                       'action': action}),
        status='created', start_date=now, updated_at=now,
    ).execute()
    state.active_task_id = state.last_task_id = task_id
    state.save()
    return task_id


def create(data, group_id, user_id=None):
    data = validate_config(data, group_id)
    pem_name = data['domains'][0].replace('*.', 'wildcard.') + '.pem'
    if len(pem_name) > 255:
        pem_name = data['domains'][0][:180] + '-' + hashlib.sha256(pem_name.encode()).hexdigest()[:32] + '.pem'
    with transaction():
        check_destination(data, pem_name, group_id)
        row = LetsEncrypt.create(server_id=data['server_id'], domains='[]', email='', type=data['type'],
                                 api_key='', api_token='', description='')
        state = LetsEncryptState.create(le_id=row.id, pem_name=pem_name)
        write_config(row, state, data)
        return row.id, enqueue(state, data, 'issue', group_id, user_id)


def update(le_id, data, group_id, user_id=None):
    with transaction():
        row = get_owned(le_id, group_id)
        state = editable(le_id)
        previous = config_for(row, state)
        data = validate_config(data, group_id, previous)
        check_destination(data, state.pem_name, group_id, le_id)
        if (state.revision != state.applied_revision or
                any(data[key] != previous[key] for key in ('server_id', 'type', 'domains'))):
            state.revision += 1
        state.targets = '{}'
        state.failures = 0
        # Keep the applied configuration until every target accepts the new PEM.
        return enqueue(state, data, 'issue', group_id, user_id)


def action(le_id, action, group_id, user_id=None):
    with transaction():
        row = get_owned(le_id, group_id)
        state = editable(le_id)
        if action == 'retry':
            if state.status != 'failed' or not state.pending_config:
                raise RoxywiConflictError('No failed certificate operation to retry')
            data = deserialize_operation_payload(state.pending_config)
            action = state.pending_action
        elif state.pending_config and action != 'delete':
            raise RoxywiConflictError('Retry the failed operation before starting another one')
        else:
            data = config_for(row, state)
        state.failures = 0
        return enqueue(state, data, action, group_id, user_id)


def record_failure(state, detail, now=None):
    now = now or utc_now()
    state.status = 'failed'
    state.failures += 1
    state.active_task_id = None
    state.retry_at = now + timedelta(minutes=5 * 2 ** (state.failures - 1)) if state.failures < 3 else None
    state.next_run_at = now + timedelta(hours=12)
    if state.pending_action == 'test':
        # Staging failures must not replace production renewals.
        state.pending_config = None
        state.pending_action = 'renew'
        state.retry_at = None
    elif state.pending_action == 'issue' and state.applied_revision and state.failures >= 3:
        state.pending_config = None
        state.pending_action = 'renew'
        state.targets = '{}'
        detail += '; replacement not applied. Edit to retry; the previous configuration will continue renewing'
    state.last_error = detail
    return detail


def dispatch_due(now=None, limit=100):
    now = now or utc_now()
    candidates = list(LetsEncryptState.select(LetsEncryptState.le_id).where(
        (LetsEncryptState.legacy_pending == False) &
        ((LetsEncryptState.next_run_at <= now) | (LetsEncryptState.retry_at <= now) |
         LetsEncryptState.active_task_id.is_null(False))))
    queued = 0
    for candidate in candidates:
        if queued >= limit:
            break
        with transaction():
            state = locked(LetsEncryptState, LetsEncryptState.le_id == candidate.le_id)
            if state.legacy_pending:
                continue
            task = InstallationTasks.get_or_none(InstallationTasks.id == state.active_task_id)
            if task and task.status in ACTIVE:
                continue
            if state.active_task_id:
                record_failure(state, task.error if task and task.error else
                               'Operation ended without confirming certificate deployment', now)
                state.save()
            if state.retry_at and state.retry_at > now:
                continue
            if not state.retry_at and (not state.next_run_at or state.next_run_at > now):
                continue
            row = LetsEncrypt.get_or_none(LetsEncrypt.id == state.le_id)
            if row is None or not row.server_id_id:
                continue
            server = Server.get_or_none(Server.server_id == row.server_id_id)
            if server is None:
                continue
            data = deserialize_operation_payload(state.pending_config) if state.pending_config else config_for(row, state)
            operation = state.pending_action if state.pending_config else 'renew'
            state.next_run_at = now + timedelta(hours=12)
            try:
                enqueue(state, data, operation, server.group_id)
            except RoxywiPublicError as error:
                state.status = 'failed'
                state.last_error = error.public_message
                state.retry_at = None
                state.save()
                continue
            queued += 1
    return queued


def public_config(row, recurse=False):
    state = LetsEncryptState.get(LetsEncryptState.le_id == row.id)
    data = config_for(row, state)
    data['has_api_key'] = bool(data.pop('api_key', None))
    data['has_api_token'] = bool(data.pop('api_token', None))
    data.update(id=row.id, api_key=None, api_token=None)
    if recurse:
        server = Server.get_or_none(Server.server_id == row.server_id_id)
        data['server_id'] = {'server_id': row.server_id_id, 'hostname': server.hostname if server else '(deleted)'}
    data['state'] = {key: getattr(state, key) for key in
                     ('status', 'legacy_pending', 'pem_name', 'last_task_id', 'last_error', 'fingerprint')}
    for key in ('not_after', 'next_run_at', 'retry_at'):
        value = getattr(state, key)
        data['state'][key] = value.isoformat() + 'Z' if value else None
    data['state']['targets'] = json.loads(state.targets)
    data['state']['can_retry'] = state.status == 'failed' and bool(state.pending_config)
    data['state']['history'] = [
        {'id': task.id, 'status': task.status, 'error': task.error,
         'started_at': task.start_date.isoformat() + 'Z' if task.start_date else None}
        for task in InstallationTasks.select().where(
            (InstallationTasks.operation_type == 'letsencrypt') &
            InstallationTasks.service_name.startswith(f"Let's Encrypt #{row.id}:"))
        .order_by(InstallationTasks.id.desc()).limit(10)
    ]
    return data


def cleanup_history(now=None, retention_days=None):
    days = int(os.environ.get('ROXYWI_LE_HISTORY_RETENTION_DAYS', '30')) if retention_days is None else retention_days
    if days < 0:
        raise ValueError('Certificate history retention must be non-negative')
    if days == 0:
        return 0
    active = LetsEncryptState.select(LetsEncryptState.active_task_id).where(LetsEncryptState.active_task_id.is_null(False))
    latest = LetsEncryptState.select(LetsEncryptState.last_task_id).where(LetsEncryptState.last_task_id.is_null(False))
    eligible = ((InstallationTasks.operation_type == 'letsencrypt') &
                InstallationTasks.status.in_(('completed', 'failed')) &
                (InstallationTasks.finish_date < (now or utc_now()) - timedelta(days=days)) &
                InstallationTasks.id.not_in(active) & InstallationTasks.id.not_in(latest))
    deleted = 0
    for _ in range(20):
        with transaction():
            ids = [task.id for task in InstallationTasks.select(InstallationTasks.id).where(eligible).limit(500)]
            if not ids:
                break
            deleted += InstallationTasks.delete().where(InstallationTasks.id.in_(ids) & eligible).execute()
    return deleted
