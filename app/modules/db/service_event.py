from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Mapping

from peewee import IntegrityError

from app.modules.common.time import as_naive_utc, utc_now
from app.modules.db.db_model import (
    Alerts,
    ApacheMetrics,
    Metrics,
    MetricsHttpStatus,
    NginxMetrics,
    PortScannerHistory,
    PortScannerPorts,
    ServiceEvent,
    ServiceEventDelivery,
    WafMetrics,
    WorkerState,
)


ACTIVE_WORKER_STATUSES = frozenset({'starting', 'running', 'degraded'})

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


def store_status_event(data: Mapping[str, Any]) -> bool:
    """Persist an event and its user-visible alert exactly once.

    Returns True for a newly stored event and False for an already known event_id.
    """
    database = ServiceEvent._meta.database
    observed_at = as_naive_utc(data['observed_at'])
    event_values = {
        'event_id': data['event_id'],
        'event_type': data['type'],
        'source': data['source'],
        'schema_version': data['schema_version'],
        'assignment_id': data.get('assignment_id'),
        'assignment_revision': data.get('assignment_revision'),
        'lease_epoch': data.get('lease_epoch'),
        'sequence': data.get('sequence'),
        'server_id': data.get('server_id'),
        'user_group': data['group_id'],
        'service': data['service'],
        'object_type': data.get('object_type'),
        'object_name': data.get('object_name'),
        'previous_status': data.get('previous_status'),
        'current_status': data.get('current_status'),
        'level': data['level'],
        'message': data['message'],
        'observed_at': observed_at,
        'received_at': utc_now(),
        'payload': json.dumps(data, sort_keys=True, separators=(',', ':'), default=str),
    }
    try:
        with database.atomic():
            if data.get('assignment_id'):
                latest = (
                    ServiceEvent.select(
                        ServiceEvent.assignment_revision,
                        ServiceEvent.lease_epoch,
                        ServiceEvent.sequence,
                    )
                    .where(ServiceEvent.assignment_id == data['assignment_id'])
                    .order_by(
                        ServiceEvent.assignment_revision.desc(),
                        ServiceEvent.lease_epoch.desc(),
                        ServiceEvent.sequence.desc(),
                    )
                    .first()
                )
                incoming_order = (
                    data.get('assignment_revision') or 0,
                    data.get('lease_epoch') or 0,
                    data.get('sequence') or 0,
                )
                if latest is not None:
                    latest_order = (
                        latest.assignment_revision or 0,
                        latest.lease_epoch or 0,
                        latest.sequence or 0,
                    )
                    if incoming_order <= latest_order:
                        return False
            ServiceEvent.create(**event_values)
            Alerts.create(
                user_group=data['group_id'],
                level=data['level'],
                ip=data.get('server_address', ''),
                port=data.get('port', 0),
                message=data['message'],
                service=data.get('history_service', 'Checker'),
                date=observed_at,
            )
            if data.get('notify', True):
                ServiceEventDelivery.create(event_id=data['event_id'])
    except IntegrityError:
        if ServiceEvent.get_or_none(ServiceEvent.event_id == data['event_id']) is not None:
            return False
        if data.get('assignment_id') and ServiceEvent.get_or_none(
            (ServiceEvent.assignment_id == data['assignment_id'])
            & (ServiceEvent.assignment_revision == data.get('assignment_revision'))
            & (ServiceEvent.lease_epoch == data.get('lease_epoch'))
            & (ServiceEvent.sequence == data.get('sequence'))
        ) is not None:
            return False
        raise
    return True


def store_metric_sample(data: Mapping[str, Any]) -> bool:
    """Persist one idempotent worker sample into the existing graph tables."""
    database = ServiceEvent._meta.database
    observed_at = as_naive_utc(data['observed_at'])
    event_values = {
        'event_id': data['event_id'],
        'event_type': data['type'],
        'source': data['source'],
        'schema_version': data['schema_version'],
        'assignment_id': data['assignment_id'],
        'assignment_revision': data['assignment_revision'],
        'lease_epoch': data['lease_epoch'],
        'sequence': data['sequence'],
        'server_id': data['server_id'],
        'user_group': data['group_id'],
        'service': data['service'],
        'observed_at': observed_at,
        'received_at': utc_now(),
        'payload': json.dumps(data, sort_keys=True, separators=(',', ':'), default=str),
    }
    values = data['values']
    try:
        with database.atomic():
            latest = (
                ServiceEvent.select(
                    ServiceEvent.assignment_revision,
                    ServiceEvent.lease_epoch,
                    ServiceEvent.sequence,
                )
                .where(ServiceEvent.assignment_id == data['assignment_id'])
                .order_by(
                    ServiceEvent.assignment_revision.desc(),
                    ServiceEvent.lease_epoch.desc(),
                    ServiceEvent.sequence.desc(),
                )
                .first()
            )
            incoming_order = (
                data['assignment_revision'], data['lease_epoch'], data['sequence']
            )
            if latest is not None:
                latest_order = (
                    latest.assignment_revision or 0,
                    latest.lease_epoch or 0,
                    latest.sequence or 0,
                )
                if incoming_order <= latest_order:
                    return False
            ServiceEvent.create(**event_values)
            if data['service'] == 'haproxy':
                Metrics.create(
                    serv=data['server_address'],
                    curr_con=values['curr_con'],
                    cur_ssl_con=values['cur_ssl_con'],
                    sess_rate=values['sess_rate'],
                    max_sess_rate=values['max_sess_rate'],
                    date=observed_at,
                )
                MetricsHttpStatus.create(
                    serv=data['server_address'],
                    ok_ans=values['http_2xx'],
                    redir_ans=values['http_3xx'],
                    not_found_ans=values['http_4xx'],
                    err_ans=values['http_5xx'],
                    date=observed_at,
                )
            else:
                model = {'nginx': NginxMetrics, 'apache': ApacheMetrics, 'waf': WafMetrics}[data['service']]
                model.create(serv=data['server_address'], conn=values['conn'], date=observed_at)
    except IntegrityError:
        if ServiceEvent.get_or_none(ServiceEvent.event_id == data['event_id']) is not None:
            return False
        if ServiceEvent.get_or_none(
            (ServiceEvent.assignment_id == data['assignment_id'])
            & (ServiceEvent.assignment_revision == data['assignment_revision'])
            & (ServiceEvent.lease_epoch == data['lease_epoch'])
            & (ServiceEvent.sequence == data['sequence'])
        ) is not None:
            return False
        raise
    return True


def _format_port_changes(changes: list[tuple[int, str]], limit: int = 20) -> str:
    visible = ', '.join(f'{port}/{service}' for port, service in changes[:limit])
    remaining = len(changes) - limit
    if remaining > 0:
        visible = f'{visible}, +{remaining} more'
    return visible


def store_portscanner_snapshot(data: Mapping[str, Any]) -> bool:
    """Persist one ordered scan snapshot and update legacy Port Scanner tables."""
    database = ServiceEvent._meta.database
    observed_at = as_naive_utc(data['observed_at'])
    incoming_order = (
        data['assignment_revision'], data['lease_epoch'], data['sequence']
    )
    new_ports = {
        int(port['port']): str(port.get('service_name') or 'unknown')[:255]
        for port in data['ports']
    }
    try:
        with database.atomic():
            latest = (
                ServiceEvent.select(
                    ServiceEvent.assignment_revision,
                    ServiceEvent.lease_epoch,
                    ServiceEvent.sequence,
                )
                .where(ServiceEvent.assignment_id == data['assignment_id'])
                .order_by(
                    ServiceEvent.assignment_revision.desc(),
                    ServiceEvent.lease_epoch.desc(),
                    ServiceEvent.sequence.desc(),
                )
                .first()
            )
            if latest is not None:
                latest_order = (
                    latest.assignment_revision or 0,
                    latest.lease_epoch or 0,
                    latest.sequence or 0,
                )
                if incoming_order <= latest_order:
                    return False

            old_ports = {
                int(port.port): str(port.service_name or 'unknown')
                for port in PortScannerPorts.select().where(
                    PortScannerPorts.serv == data['server_address']
                )
            }
            opened = [(port, new_ports[port]) for port in sorted(set(new_ports) - set(old_ports))]
            closed = [(port, old_ports[port]) for port in sorted(set(old_ports) - set(new_ports))]
            message_parts = []
            if opened:
                message_parts.append(f'opened {_format_port_changes(opened)}')
            if closed:
                message_parts.append(f'closed {_format_port_changes(closed)}')
            message = (
                f'Port changes on server {data["server_address"]}: {"; ".join(message_parts)}'
                if message_parts else None
            )

            stored_payload = dict(data)
            stored_payload.update({
                'level': 'info' if message else None,
                'message': message,
                'alert_type': 'port',
            })
            ServiceEvent.create(
                event_id=data['event_id'],
                event_type=data['type'],
                source=data['source'],
                schema_version=data['schema_version'],
                assignment_id=data['assignment_id'],
                assignment_revision=data['assignment_revision'],
                lease_epoch=data['lease_epoch'],
                sequence=data['sequence'],
                server_id=data['server_id'],
                user_group=data['group_id'],
                service='portscanner',
                object_type='port_snapshot',
                previous_status=str(len(old_ports)),
                current_status=str(len(new_ports)),
                level='info' if message else None,
                message=message,
                observed_at=observed_at,
                received_at=utc_now(),
                payload=json.dumps(stored_payload, sort_keys=True, separators=(',', ':'), default=str),
            )

            PortScannerPorts.delete().where(
                PortScannerPorts.serv == data['server_address']
            ).execute()
            if new_ports:
                PortScannerPorts.insert_many([
                    {
                        'serv': data['server_address'],
                        'user_group_id': data['group_id'],
                        'port': port,
                        'service_name': service_name,
                        'date': observed_at,
                    }
                    for port, service_name in sorted(new_ports.items())
                ]).execute()

            if data.get('history'):
                changes = [
                    {
                        'serv': data['server_address'],
                        'port': port,
                        'status': status,
                        'service_name': service_name,
                        'date': observed_at,
                    }
                    for status, ports in (('opened', opened), ('closed', closed))
                    for port, service_name in ports
                ]
                if changes:
                    PortScannerHistory.insert_many(changes).execute()
            if message and data.get('notify'):
                ServiceEventDelivery.create(event_id=data['event_id'])
    except IntegrityError:
        if ServiceEvent.get_or_none(ServiceEvent.event_id == data['event_id']) is not None:
            return False
        if ServiceEvent.get_or_none(
            (ServiceEvent.assignment_id == data['assignment_id'])
            & (ServiceEvent.assignment_revision == data['assignment_revision'])
            & (ServiceEvent.lease_epoch == data['lease_epoch'])
            & (ServiceEvent.sequence == data['sequence'])
        ) is not None:
            return False
        raise
    return True


def pending_deliveries(limit: int = 100):
    return list(
        ServiceEventDelivery
        .select(ServiceEventDelivery, ServiceEvent)
        .join(ServiceEvent)
        .where(ServiceEventDelivery.status.in_(('pending', 'failed')))
        .order_by(ServiceEventDelivery.created_at)
        .limit(limit)
    )


def claim_pending_deliveries(limit: int = 100):
    """Claim notification work so parallel HA schedulers do not send it together."""
    now = utc_now()
    abandoned_before = now - timedelta(minutes=5)
    claimed_ids = []
    candidates = list(
        ServiceEventDelivery.select(ServiceEventDelivery.id, ServiceEventDelivery.status)
        .where(
            (ServiceEventDelivery.status.in_(('pending', 'failed')))
            | (
                (ServiceEventDelivery.status == 'processing')
                & (ServiceEventDelivery.updated_at < abandoned_before)
            )
        )
        .order_by(ServiceEventDelivery.created_at)
        .limit(limit)
    )
    for candidate in candidates:
        updated = ServiceEventDelivery.update(
            status='processing',
            updated_at=now,
        ).where(
            (ServiceEventDelivery.id == candidate.id)
            & (
                (ServiceEventDelivery.status.in_(('pending', 'failed')))
                | (
                    (ServiceEventDelivery.status == 'processing')
                    & (ServiceEventDelivery.updated_at < abandoned_before)
                )
            )
        ).execute()
        if updated:
            claimed_ids.append(candidate.id)
    if not claimed_ids:
        return []
    return list(
        ServiceEventDelivery
        .select(ServiceEventDelivery, ServiceEvent)
        .join(ServiceEvent)
        .where(ServiceEventDelivery.id.in_(claimed_ids))
        .order_by(ServiceEventDelivery.created_at)
    )


def prune_worker_states(retention_days: int = 7) -> int:
    cutoff = utc_now() - timedelta(days=retention_days)
    return WorkerState.delete().where(
        (WorkerState.expires_at < cutoff)
        | ((WorkerState.status == 'stopped') & (WorkerState.updated_at < cutoff))
    ).execute()


def prune_service_events(retention_days: int) -> int:
    cutoff = utc_now() - timedelta(days=retention_days)
    old_event_ids = ServiceEvent.select(ServiceEvent.event_id).where(
        ServiceEvent.observed_at < cutoff
    )
    ServiceEventDelivery.delete().where(
        ServiceEventDelivery.event_id.in_(old_event_ids)
    ).execute()
    return ServiceEvent.delete().where(ServiceEvent.observed_at < cutoff).execute()


def mark_delivery_succeeded(delivery_id: int) -> None:
    now = utc_now()
    ServiceEventDelivery.update(
        status='delivered',
        attempts=ServiceEventDelivery.attempts + 1,
        last_error=None,
        delivered_at=now,
        updated_at=now,
    ).where(ServiceEventDelivery.id == delivery_id).execute()


def mark_delivery_failed(delivery_id: int, error: str) -> None:
    ServiceEventDelivery.update(
        status='failed',
        attempts=ServiceEventDelivery.attempts + 1,
        last_error=error[:4000],
        updated_at=utc_now(),
    ).where(ServiceEventDelivery.id == delivery_id).execute()


def worker_summary(group_id: int | None = None, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    now = as_naive_utc(now) if now else utc_now()
    summary: dict[str, dict[str, int]] = {}
    for worker in WorkerState.select():
        groups = worker.group_ids or []
        # Socket replicas are global gateways. They can serve every group even
        # when no client from the requesting group was connected at the exact
        # heartbeat instant, so their health must not be hidden by group scope.
        if group_id not in (None, 1) and worker.service != 'socket':
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
        })
        service['total'] += 1
        service['assignments'] += worker.active_assignments or 0
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
