from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import uuid4

from peewee import IntegrityError

from app.modules.common.time import as_naive_utc, utc_now
from app.modules.db.service_event_storage import (
    METRIC_MODELS, advance_position, current_exists, event_key, event_order, has_identity,
    lock_position, lock_retention, write_transaction,
)
from app.modules.db.db_model import (
    Alerts,
    Metrics,
    MetricsHttpStatus,
    PortScannerHistory,
    PortScannerPorts,
    ServiceEvent,
    ServiceEventDelivery,
    ServiceNotification,
    WorkerState,
)


ACTIVE_WORKER_STATUSES = frozenset({'starting', 'running', 'degraded'})


def notification_payload(data: Mapping[str, Any]) -> str:
    """Store only delivery inputs, not a second copy of the scan/status envelope."""
    fields = ('server_address', 'group_id', 'service', 'level', 'message', 'alert_type')
    return json.dumps({key: data[key] for key in fields}, sort_keys=True, default=str)


def _enqueue_notification(data: Mapping[str, Any]) -> None:
    ServiceNotification.create(
        event_id=data['event_id'], event_key=event_key(data),
        category=data['source'], observed_at=as_naive_utc(data['observed_at']),
        payload=notification_payload(data),
    )


def record_worker_heartbeat(data: Mapping[str, Any]) -> None:
    values = {
        'service': data['service'],
        'instance_id': data.get('instance_id'),
        'status': data['status'],
        'hostname': data.get('hostname'),
        'version': data.get('version'),
        'started_at': as_naive_utc(data['started_at']) if data.get('started_at') else None,
        'last_heartbeat': as_naive_utc(data['heartbeat_at']),
        'expires_at': as_naive_utc(data['expires_at']),
        'active_assignments': data.get('active_assignments', 0),
        'capacity': data.get('capacity'),
        'group_ids': data.get('group_ids', []),
        'metadata': data.get('metadata', {}),
        'updated_at': utc_now(),
    }
    worker_id = data['worker_id']
    database = WorkerState._meta.database
    with database.atomic():
        updated = WorkerState.update(**values).where(
            (WorkerState.worker_id == worker_id)
            & (WorkerState.last_heartbeat <= values['last_heartbeat'])
        ).execute()
        if updated:
            return
        if WorkerState.get_or_none(WorkerState.worker_id == worker_id) is not None:
            # A delayed heartbeat must not roll current worker state backwards.
            return
        try:
            WorkerState.create(worker_id=worker_id, **values)
        except IntegrityError:
            # A concurrent heartbeat inserted the worker between UPDATE and INSERT.
            WorkerState.update(**values).where(
                (WorkerState.worker_id == worker_id)
                & (WorkerState.last_heartbeat <= values['last_heartbeat'])
            ).execute()


def _known_event(model, data):
    # Legacy diagnostics remain a dedup fallback during the data migration.
    return has_identity(model, data) or current_exists(ServiceEvent.select().where(
        (ServiceEvent.event_id == data['event_id'])
        | (
            (ServiceEvent.assignment_id == data['assignment_id'])
            & (ServiceEvent.assignment_revision == data['assignment_revision'])
            & (ServiceEvent.lease_epoch == data['lease_epoch'])
            & (ServiceEvent.sequence == data['sequence'])
        )
    ))


def _store_diagnostic(data):
    fields = (
        'assignment_id', 'assignment_revision', 'lease_epoch', 'sequence', 'server_id',
        'service', 'object_type', 'object_name', 'previous_status', 'current_status',
        'level', 'message',
    )
    ServiceEvent.create(
        event_id=data['event_id'], event_type=data['type'], source=data['source'],
        schema_version=data['schema_version'], user_group=data['group_id'],
        observed_at=as_naive_utc(data['observed_at']), received_at=utc_now(),
        payload=json.dumps(data, sort_keys=True, separators=(',', ':'), default=str),
        **{name: data.get(name) for name in fields},
    )


def store_status_event(data: Mapping[str, Any]) -> bool:
    """Store every unseen transition, including delayed ones, atomically with delivery."""
    with write_transaction():
        boundary = lock_retention('checker')
        observed_at = as_naive_utc(data['observed_at'])
        if observed_at < boundary.cutoff or _known_event(Alerts, data):
            return False
        position = lock_position(data)
        Alerts.create(
            event_id=data['event_id'], event_key=event_key(data),
            user_group=data['group_id'], level=data['level'],
            ip=data.get('server_address', ''), port=data.get('port', 0),
            message=data['message'], service=data.get('history_service', 'Checker'),
            date=observed_at,
        )
        advance_position(position, data)
        _store_diagnostic(data)
        if data.get('notify', True):
            _enqueue_notification(data)
    return True


def store_metric_sample(data: Mapping[str, Any]) -> bool:
    """Write graphs once without retaining a duplicate JSON event for every sample."""
    model = METRIC_MODELS[data['service']]
    with write_transaction():
        boundary = lock_retention('metrics')
        observed_at = as_naive_utc(data['observed_at'])
        if observed_at < boundary.cutoff or _known_event(model, data):
            return False
        position = lock_position(data)
        identity = {'event_id': data['event_id'], 'event_key': event_key(data)}
        common = {'serv': data['server_address'], 'date': observed_at, **identity}
        values = data['values']
        if data['service'] == 'haproxy':
            Metrics.create(
                **common, curr_con=values['curr_con'], cur_ssl_con=values['cur_ssl_con'],
                sess_rate=values['sess_rate'], max_sess_rate=values['max_sess_rate'],
            )
            MetricsHttpStatus.create(
                **common, ok_ans=values['http_2xx'], redir_ans=values['http_3xx'],
                not_found_ans=values['http_4xx'], err_ans=values['http_5xx'],
            )
        else:
            model.create(**common, conn=values['conn'])
        advance_position(position, data)
    return True


def _format_port_changes(changes: list[tuple[int, str]], limit: int = 20) -> str:
    visible = ', '.join(f'{port}/{service}' for port, service in changes[:limit])
    remaining = len(changes) - limit
    if remaining > 0:
        visible = f'{visible}, +{remaining} more'
    return visible


def store_portscanner_snapshot(data: Mapping[str, Any]) -> bool:
    """Keep producer-side changes regardless of arrival order; fence only current ports."""
    with write_transaction():
        boundary = lock_retention('portscanner')
        observed_at = as_naive_utc(data['observed_at'])
        if observed_at < boundary.cutoff:
            return False
        position = lock_position(data)
        if (position.event_id == data['event_id']
                or event_order(data) == (
                    position.assignment_revision, position.lease_epoch, position.sequence
                )
                or _known_event(PortScannerHistory, data)
                or has_identity(ServiceNotification, data)):
            return False

        opened = [(port['port'], port['service_name']) for port in data['opened']]
        closed = [(port['port'], port['service_name']) for port in data['closed']]
        parts = []
        if opened:
            parts.append(f'opened {_format_port_changes(opened)}')
        if closed:
            parts.append(f'closed {_format_port_changes(closed)}')
        message = (
            f'Port changes on server {data["server_address"]}: {"; ".join(parts)}'
            if parts else None
        )

        is_current = advance_position(position, data) and data.get('update_current', True)
        if is_current:
            new_ports = {port['port']: port['service_name'] for port in data['ports']}
            old_ports = {
                row.port: row.service_name for row in PortScannerPorts.select().where(
                    PortScannerPorts.serv == data['server_address']
                )
            }
            # Avoid rewriting the full current snapshot when nothing changed.
            if old_ports != new_ports:
                PortScannerPorts.delete().where(
                    PortScannerPorts.serv == data['server_address']
                ).execute()
                rows = [
                    {'serv': data['server_address'], 'user_group_id': data['group_id'],
                     'port': port, 'service_name': name, 'date': observed_at}
                    for port, name in sorted(new_ports.items())
                ]
                for start in range(0, len(rows), 100):
                    PortScannerPorts.insert_many(rows[start:start + 100]).execute()
            else:
                PortScannerPorts.update(date=observed_at).where(
                    PortScannerPorts.serv == data['server_address']
                ).execute()

        if data.get('history'):
            changes = [
                {'serv': data['server_address'], 'port': port, 'status': status,
                 'service_name': name, 'date': observed_at,
                 'event_id': data['event_id'], 'event_key': event_key(data)}
                for status, ports in (('opened', opened), ('closed', closed))
                for port, name in ports
            ]
            for start in range(0, len(changes), 100):
                PortScannerHistory.insert_many(changes[start:start + 100]).execute()

        if message:
            stored_payload = dict(data, level='info', message=message, alert_type='port')
            _store_diagnostic(stored_payload)
            if data.get('notify'):
                _enqueue_notification(stored_payload)
        return is_current or bool(message)


def pending_deliveries(limit: int = 100):
    return list(
        ServiceNotification.select()
        .where(ServiceNotification.status.in_(('pending', 'failed')))
        .order_by(ServiceNotification.created_at)
        .limit(limit)
    )


def claim_pending_deliveries(limit: int = 100):
    """Claim notification work so parallel HA schedulers do not send it together."""
    now = utc_now()
    abandoned_before = now - timedelta(minutes=5)
    retry_before = now - timedelta(seconds=30)
    eligible = (
        (ServiceNotification.status == 'pending')
        | ((ServiceNotification.status == 'failed') & (ServiceNotification.updated_at <= retry_before))
        | ((ServiceNotification.status == 'processing') & (ServiceNotification.updated_at < abandoned_before))
    )
    claimed_ids = []
    claim_token = str(uuid4())
    candidates = list(
        ServiceNotification.select(ServiceNotification.id, ServiceNotification.status)
        .where(eligible)
        .order_by(ServiceNotification.created_at)
        .limit(limit)
    )
    for candidate in candidates:
        updated = ServiceNotification.update(
            status='processing',
            updated_at=now,
            claim_token=claim_token,
        ).where(
            (ServiceNotification.id == candidate.id)
            & eligible
        ).execute()
        if updated:
            claimed_ids.append(candidate.id)
    if not claimed_ids:
        return []
    return list(
        ServiceNotification.select()
        .where(
            ServiceNotification.id.in_(claimed_ids)
            & (ServiceNotification.claim_token == claim_token)
        )
        .order_by(ServiceNotification.created_at)
    )


def prune_worker_states(retention_days: int = 7) -> int:
    cutoff = utc_now() - timedelta(days=retention_days)
    return WorkerState.delete().where(
        (WorkerState.expires_at < cutoff)
        | ((WorkerState.status == 'stopped') & (WorkerState.updated_at < cutoff))
    ).execute()


def prune_service_events(retention_days: int = 3) -> int:
    cutoff = utc_now() - timedelta(days=retention_days)
    # Protect unmigrated legacy deliveries as well. New notifications have no FK
    # to diagnostics and are retained until delivery succeeds (or is cancelled).
    protected = ServiceEventDelivery.select(ServiceEventDelivery.event_id).where(
        ~ServiceEventDelivery.status.in_(('delivered', 'cancelled'))
        & ServiceEventDelivery.event_id.not_in(
            ServiceNotification.select(ServiceNotification.event_id)
        )
    )
    deleted = 0
    while True:
        ids = [row.event_id for row in ServiceEvent.select(ServiceEvent.event_id).where(
            (ServiceEvent.received_at < cutoff) & ServiceEvent.event_id.not_in(protected)
        ).limit(500)]
        if not ids:
            return deleted
        with ServiceEvent._meta.database.atomic():
            ServiceEventDelivery.delete().where(ServiceEventDelivery.event_id.in_(ids)).execute()
            deleted += ServiceEvent.delete().where(ServiceEvent.event_id.in_(ids)).execute()


def prune_notifications(retention_days: int = 3) -> int:
    deleted = 0
    for category in ('checker', 'portscanner'):
        with write_transaction():
            boundary = lock_retention(category)
            terminal = (
                ServiceNotification.status.in_(('delivered', 'cancelled'))
                & (ServiceNotification.category == category)
            )
            deleted += ServiceNotification.delete().where(
                terminal & (ServiceNotification.observed_at < boundary.cutoff)
            ).execute()
            # Keep only the compact identity until history's replay boundary has
            # passed. Otherwise a history-disabled scan could notify twice.
            ServiceNotification.update(payload=None, last_error=None).where(
                terminal & ServiceNotification.payload.is_null(False)
                & (ServiceNotification.updated_at < utc_now() - timedelta(days=retention_days))
            ).execute()
    return deleted


def mark_delivery_succeeded(delivery_id: int, claim_token: str) -> None:
    now = utc_now()
    ServiceNotification.update(
        status='delivered',
        attempts=ServiceNotification.attempts + 1,
        last_error=None,
        delivered_at=now,
        updated_at=now,
        claim_token=None,
    ).where(
        (ServiceNotification.id == delivery_id)
        & (ServiceNotification.status == 'processing')
        & (ServiceNotification.claim_token == claim_token)
    ).execute()


def mark_delivery_failed(delivery_id: int, error: str, claim_token: str) -> None:
    ServiceNotification.update(
        status='failed',
        attempts=ServiceNotification.attempts + 1,
        last_error=error[:4000],
        updated_at=utc_now(),
        claim_token=None,
    ).where(
        (ServiceNotification.id == delivery_id)
        & (ServiceNotification.status == 'processing')
        & (ServiceNotification.claim_token == claim_token)
    ).execute()


def worker_summary(group_id: int | None = None, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    now = as_naive_utc(now) if now else utc_now()
    summary: dict[str, dict[str, Any]] = {}
    for worker in WorkerState.select():
        groups = worker.group_ids or []
        # Socket replicas are global gateways. They can serve every group even
        # when no client from the requesting group was connected at the exact
        # heartbeat instant. Roxy-WI processes are also global control-plane
        # components, so their health must not be hidden by group scope.
        is_global_service = worker.service == 'socket' or worker.service.startswith('roxy-wi-')
        if group_id not in (None, 1) and not is_global_service:
            normalized_groups = {int(item) for item in groups if str(item).isdigit()}
            if int(group_id) not in normalized_groups:
                continue

        service = summary.setdefault(worker.service, {
            'active': 0,
            'degraded': 0,
            'stale': 0,
            'draining': 0,
            'stopped': 0,
            'assignments': 0,
            'total': 0,
            'versions': [],
            'last_heartbeat': None,
        })
        service['total'] += 1
        service['assignments'] += worker.active_assignments or 0
        if service['last_heartbeat'] is None or worker.last_heartbeat > service['last_heartbeat']:
            service['last_heartbeat'] = worker.last_heartbeat
        if worker.status == 'draining':
            service['draining'] += 1
        elif worker.status == 'stopped':
            service['stopped'] += 1
        elif worker.status in ACTIVE_WORKER_STATUSES and worker.expires_at > now:
            service['active'] += 1
            if worker.status == 'degraded':
                service['degraded'] += 1
            if worker.version and worker.version not in service['versions']:
                service['versions'].append(worker.version)
        else:
            service['stale'] += 1

    for service in summary.values():
        service['versions'].sort()

    return summary
