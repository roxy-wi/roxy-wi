from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.modules.common.time import utc_now
from app.modules.db.db_model import (
    PortScannerSettings,
    Server,
    ServiceAssignment,
    ServiceCommand,
    UDPBalancer,
    Waf,
)
import app.modules.db.sql as sql
from app.modules.subscription.access import MANAGED_SERVICES, is_feature_available


CHECKER_PORT_SETTINGS = {
    'haproxy': 'haproxy_sock_port',
    'nginx': 'nginx_stats_port',
    'apache': 'apache_stats_port',
}
CHECKER_SERVER_FLAGS = {
    'haproxy': ('haproxy', 'haproxy_alert'),
    'nginx': ('nginx', 'nginx_alert'),
    'apache': ('apache', 'apache_alert'),
    'keepalived': ('keepalived', 'keepalived_alert'),
}
METRICS_SERVER_FLAGS = {
    'haproxy': ('haproxy', 'haproxy_metrics'),
    'nginx': ('nginx', 'nginx_metrics'),
    'apache': ('apache', 'apache_metrics'),
}
METRICS_PORT_SETTINGS = {
    'haproxy': 'haproxy_sock_port',
    'nginx': 'nginx_stats_port',
    'apache': 'apache_stats_port',
    'waf': 'haproxy_sock_port',
}


def _group_setting(name: str, group_id: int):
    value = sql.get_setting(name, group_id=group_id)
    return value if value is not None else sql.get_setting(name, group_id=1)


def _checker_assignment_content(server: Server, service: str, enabled: bool) -> dict[str, Any]:
    port_setting = CHECKER_PORT_SETTINGS.get(service)
    group_id = int(server.group_id)
    return {
        'desired_state': 'running' if enabled else 'stopped',
        'target': {
            'server_id': server.server_id,
            'address': server.ip,
            'service': service,
            'port': int(_group_setting(port_setting, group_id)) if port_setting else 0,
        },
        'settings': {
            'interval_seconds': int(_group_setting('checker_check_interval', group_id)) * 60,
            'maxconn_threshold': int(_group_setting('checker_maxconn_threshold', group_id)),
        },
        'group_id': int(server.group_id),
    }


def _metrics_assignment_content(server: Server, service: str, enabled: bool) -> dict[str, Any]:
    group_id = int(server.group_id)
    settings: dict[str, Any] = {
        'interval_seconds': 30,
        'request_timeout_seconds': 5,
        'username': None,
        'password': None,
        'stats_path': None,
    }
    if service in {'nginx', 'apache'}:
        settings.update({
            'username': str(_group_setting(f'{service}_stats_user', group_id)),
            'password': str(_group_setting(f'{service}_stats_password', group_id)),
            'stats_path': str(_group_setting(f'{service}_stats_page', group_id)),
        })
    return {
        'desired_state': 'running' if enabled else 'stopped',
        'target': {
            'server_id': server.server_id,
            'address': server.ip,
            'service': service,
            'port': int(_group_setting(METRICS_PORT_SETTINGS[service], group_id)),
        },
        'settings': settings,
        'group_id': group_id,
    }


def _portscanner_assignment_content(
        server: Server,
        settings: PortScannerSettings | None,
        enabled: bool,
) -> dict[str, Any]:
    group_id = int(server.group_id)
    return {
        'desired_state': 'running' if enabled else 'stopped',
        'target': {
            'server_id': server.server_id,
            'address': server.ip,
            'service': 'portscanner',
        },
        'settings': {
            'interval_seconds': max(int(_group_setting('port_scan_interval', group_id)) * 60, 30),
            'scan_timeout_seconds': 45,
            'top_ports': 1000,
            'max_retries': 1,
            'timing_template': 4,
            'notify': bool(settings.notify) if settings is not None else False,
            'history': bool(settings.history) if settings is not None else False,
        },
        'group_id': group_id,
    }


def _checker_udp_assignment_content(listener: UDPBalancer, enabled: bool) -> dict[str, Any]:
    return {
        'desired_state': 'running' if enabled else 'stopped',
        'target': {
            # The v1 checker contract calls this field server_id. For UDP it is
            # the stable listener ID; the assignment prefix prevents collisions.
            'server_id': listener.id,
            'address': listener.vip,
            'service': 'udp',
            'port': int(listener.port),
        },
        'settings': {
            'interval_seconds': int(sql.get_setting('checker_check_interval')) * 60,
            'maxconn_threshold': int(sql.get_setting('checker_maxconn_threshold')),
        },
        'group_id': int(listener.group_id_id),
    }


def _queue_checker_assignment(
        assignment_id: str,
        target_id: int,
        service: str,
        group_id: int,
        content: dict[str, Any],
) -> str:
    database = ServiceAssignment._meta.database
    with database.atomic():
        ServiceAssignment.insert(
            assignment_id=assignment_id,
            target_service='checker',
            server_id=target_id,
            service=service,
            user_group=group_id,
            revision=0,
            desired_state='stopped',
            payload='{}',
        ).on_conflict_ignore().execute()
        ServiceAssignment.update(
            revision=ServiceAssignment.revision + 1,
        ).where(ServiceAssignment.assignment_id == assignment_id).execute()
        assignment = ServiceAssignment.get_by_id(assignment_id)

        payload: dict[str, Any] = {
            'command_id': str(uuid4()),
            'type': 'checker.assignment.apply',
            'schema_version': 1,
            'source': 'roxy-wi',
            'assignment_id': assignment_id,
            'revision': assignment.revision,
            **content,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        ServiceAssignment.update(
            desired_state=payload['desired_state'],
            payload=serialized,
            updated_at=utc_now(),
        ).where(ServiceAssignment.assignment_id == assignment_id).execute()
        ServiceCommand.create(
            command_id=payload['command_id'],
            command_type=payload['type'],
            target_service='checker',
            routing_key='checker.assignment.apply',
            assignment_id=assignment_id,
            revision=assignment.revision,
            payload=serialized,
        )
    return payload['command_id']


def _queue_metrics_assignment(server: Server, service: str, content: dict[str, Any]) -> str:
    assignment_id = f'metrics:{service}:server-{server.server_id}'
    database = ServiceAssignment._meta.database
    with database.atomic():
        ServiceAssignment.insert(
            assignment_id=assignment_id,
            target_service='metrics',
            server_id=server.server_id,
            service=service,
            user_group=int(server.group_id),
            revision=0,
            desired_state='stopped',
            payload='{}',
        ).on_conflict_ignore().execute()
        ServiceAssignment.update(revision=ServiceAssignment.revision + 1).where(
            ServiceAssignment.assignment_id == assignment_id
        ).execute()
        assignment = ServiceAssignment.get_by_id(assignment_id)
        payload: dict[str, Any] = {
            'command_id': str(uuid4()),
            'type': 'metrics.assignment.apply',
            'schema_version': 1,
            'source': 'roxy-wi',
            'assignment_id': assignment_id,
            'revision': assignment.revision,
            **content,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        ServiceAssignment.update(
            desired_state=payload['desired_state'],
            payload=serialized,
            updated_at=utc_now(),
        ).where(ServiceAssignment.assignment_id == assignment_id).execute()
        ServiceCommand.create(
            command_id=payload['command_id'],
            command_type=payload['type'],
            target_service='metrics',
            routing_key='metrics.assignment.apply',
            assignment_id=assignment_id,
            revision=assignment.revision,
            payload=serialized,
        )
        return payload['command_id']


def _queue_portscanner_assignment(server: Server, content: dict[str, Any]) -> str:
    assignment_id = f'portscanner:server-{server.server_id}'
    database = ServiceAssignment._meta.database
    with database.atomic():
        ServiceAssignment.insert(
            assignment_id=assignment_id,
            target_service='portscanner',
            server_id=server.server_id,
            service='portscanner',
            user_group=int(server.group_id),
            revision=0,
            desired_state='stopped',
            payload='{}',
        ).on_conflict_ignore().execute()
        ServiceAssignment.update(revision=ServiceAssignment.revision + 1).where(
            ServiceAssignment.assignment_id == assignment_id
        ).execute()
        assignment = ServiceAssignment.get_by_id(assignment_id)
        payload: dict[str, Any] = {
            'command_id': str(uuid4()),
            'type': 'portscanner.assignment.apply',
            'schema_version': 1,
            'source': 'roxy-wi',
            'assignment_id': assignment_id,
            'revision': assignment.revision,
            **content,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        ServiceAssignment.update(
            desired_state=payload['desired_state'],
            payload=serialized,
            updated_at=utc_now(),
        ).where(ServiceAssignment.assignment_id == assignment_id).execute()
        ServiceCommand.create(
            command_id=payload['command_id'],
            command_type=payload['type'],
            target_service='portscanner',
            routing_key='portscanner.assignment.apply',
            assignment_id=assignment_id,
            revision=assignment.revision,
            payload=serialized,
        )
        return payload['command_id']


def queue_checker_assignment(server_id: int, service: str, enabled: bool) -> str:
    """Persist desired checker state and its RabbitMQ command in one transaction."""
    if service not in {'haproxy', 'nginx', 'apache', 'keepalived'}:
        raise ValueError(f'unsupported checker service: {service}')
    # Stop remains available without a subscription.  Any internal caller that
    # tries to enable Checker is clamped to stopped as a defence-in-depth guard.
    enabled = bool(enabled and is_feature_available(MANAGED_SERVICES))
    server = Server.get_by_id(server_id)
    return _queue_checker_assignment(
        f'{service}:server-{server_id}',
        server_id,
        service,
        int(server.group_id),
        _checker_assignment_content(server, service, enabled),
    )


def queue_metrics_assignment(server_id: int, service: str, enabled: bool) -> str:
    """Persist desired Metrics state and its RabbitMQ command atomically."""
    if service not in METRICS_PORT_SETTINGS:
        raise ValueError(f'unsupported metrics service: {service}')
    enabled = bool(enabled and is_feature_available(MANAGED_SERVICES))
    server = Server.get_by_id(server_id)
    return _queue_metrics_assignment(server, service, _metrics_assignment_content(server, service, enabled))


def queue_portscanner_assignment(server_id: int, enabled: bool) -> str:
    """Persist desired Port Scanner state and its RabbitMQ command atomically."""
    server = Server.get_by_id(server_id)
    settings = PortScannerSettings.get_or_none(PortScannerSettings.server_id == server_id)
    enabled = bool(
        enabled
        and settings is not None
        and settings.enabled
        and server.enabled
        and is_feature_available(MANAGED_SERVICES)
    )
    return _queue_portscanner_assignment(
        server, _portscanner_assignment_content(server, settings, enabled)
    )


def queue_checker_udp_assignment(listener_id: int, enabled: bool) -> str:
    """Persist desired state for a UDP listener using the same checker command."""
    enabled = bool(enabled and is_feature_available(MANAGED_SERVICES))
    listener = UDPBalancer.get_by_id(listener_id)
    return _queue_checker_assignment(
        f'udp:server-{listener_id}',
        listener_id,
        'udp',
        int(listener.group_id_id),
        _checker_udp_assignment_content(listener, enabled),
    )


def reconcile_checker_assignments(servers=None) -> int:
    """Import existing checker settings and repair desired-state drift.

    This is intentionally edge-triggered: unchanged assignments are not republished.
    RabbitMQ retains commands while checker is offline; checker DB retains assignments.
    """
    subscription_active = is_feature_available(MANAGED_SERVICES)
    assignments = {
        assignment.assignment_id: assignment
        for assignment in ServiceAssignment.select().where(
            ServiceAssignment.target_service == 'checker'
        )
    }
    queued = 0
    for server in servers if servers is not None else Server.select():
        for service, (installed_field, alert_field) in CHECKER_SERVER_FLAGS.items():
            assignment_id = f'{service}:server-{server.server_id}'
            existing = assignments.get(assignment_id)
            installed = bool(getattr(server, installed_field))
            enabled = bool(
                subscription_active
                and server.enabled
                and installed
                and getattr(server, alert_field)
            )
            if existing is None and not enabled:
                continue
            expected = _checker_assignment_content(server, service, enabled)
            if existing is not None:
                try:
                    current = json.loads(existing.payload)
                except (TypeError, json.JSONDecodeError):
                    current = {}
                if all(current.get(key) == value for key, value in expected.items()):
                    continue
            queue_checker_assignment(server.server_id, service, enabled)
            queued += 1
    return queued


def reconcile_checker_udp_assignments(listeners=None) -> int:
    """Import existing UDP checker flags and repair desired-state drift."""
    subscription_active = is_feature_available(MANAGED_SERVICES)
    assignments = {
        assignment.assignment_id: assignment
        for assignment in ServiceAssignment.select().where(
            (ServiceAssignment.target_service == 'checker')
            & (ServiceAssignment.service == 'udp')
        )
    }
    queued = 0
    for listener in listeners if listeners is not None else UDPBalancer.select():
        assignment_id = f'udp:server-{listener.id}'
        existing = assignments.get(assignment_id)
        enabled = bool(subscription_active and listener.is_checker)
        if existing is None and not enabled:
            continue
        expected = _checker_udp_assignment_content(listener, enabled)
        if existing is not None:
            try:
                current = json.loads(existing.payload)
            except (TypeError, json.JSONDecodeError):
                current = {}
            if all(current.get(key) == value for key, value in expected.items()):
                continue
        queue_checker_udp_assignment(listener.id, enabled)
        queued += 1
    return queued


def reconcile_metrics_assignments(servers=None) -> int:
    """Import existing Metrics flags and repair distributed desired-state drift."""
    subscription_active = is_feature_available(MANAGED_SERVICES)
    assignments = {
        assignment.assignment_id: assignment
        for assignment in ServiceAssignment.select().where(ServiceAssignment.target_service == 'metrics')
    }
    queued = 0
    for server in servers if servers is not None else Server.select():
        for service, (installed_field, metrics_field) in METRICS_SERVER_FLAGS.items():
            assignment_id = f'metrics:{service}:server-{server.server_id}'
            existing = assignments.get(assignment_id)
            enabled = bool(
                subscription_active
                and server.enabled
                and getattr(server, installed_field)
                and getattr(server, metrics_field)
            )
            if existing is None and not enabled:
                continue
            expected = _metrics_assignment_content(server, service, enabled)
            if existing is not None:
                try:
                    current = json.loads(existing.payload)
                except (TypeError, json.JSONDecodeError):
                    current = {}
                if all(current.get(key) == value for key, value in expected.items()):
                    continue
            queue_metrics_assignment(server.server_id, service, enabled)
            queued += 1

        waf = Waf.get_or_none(Waf.server_id == server.server_id)
        assignment_id = f'metrics:waf:server-{server.server_id}'
        existing = assignments.get(assignment_id)
        enabled = bool(subscription_active and server.enabled and server.haproxy and waf and waf.metrics)
        if existing is not None or enabled:
            expected = _metrics_assignment_content(server, 'waf', enabled)
            try:
                current = json.loads(existing.payload) if existing is not None else {}
            except (TypeError, json.JSONDecodeError):
                current = {}
            if not all(current.get(key) == value for key, value in expected.items()):
                queue_metrics_assignment(server.server_id, 'waf', enabled)
                queued += 1
    return queued


def reconcile_portscanner_assignments(settings_rows=None) -> int:
    """Import existing Port Scanner settings and repair desired-state drift."""
    subscription_active = is_feature_available(MANAGED_SERVICES)
    assignments = {
        assignment.assignment_id: assignment
        for assignment in ServiceAssignment.select().where(
            ServiceAssignment.target_service == 'portscanner'
        )
    }
    queued = 0
    rows = settings_rows if settings_rows is not None else PortScannerSettings.select()
    for settings in rows:
        server = Server.get_or_none(Server.server_id == settings.server_id)
        if server is None:
            continue
        assignment_id = f'portscanner:server-{server.server_id}'
        existing = assignments.get(assignment_id)
        enabled = bool(subscription_active and server.enabled and settings.enabled)
        if existing is None and not enabled:
            continue
        expected = _portscanner_assignment_content(server, settings, enabled)
        if existing is not None:
            try:
                current = json.loads(existing.payload)
            except (TypeError, json.JSONDecodeError):
                current = {}
            if all(current.get(key) == value for key, value in expected.items()):
                continue
        queue_portscanner_assignment(server.server_id, enabled)
        queued += 1
    return queued


def stop_checker_assignments_for_server(server_id: int) -> int:
    """Queue stop commands while the target server record is still available."""
    assignments = list(ServiceAssignment.select().where(
        (ServiceAssignment.target_service == 'checker')
        & (ServiceAssignment.server_id == server_id)
        & (ServiceAssignment.service != 'udp')
        & (ServiceAssignment.desired_state != 'stopped')
    ))
    for assignment in assignments:
        queue_checker_assignment(server_id, assignment.service, False)
    return len(assignments)


def stop_metrics_assignments_for_server(server_id: int) -> int:
    assignments = list(ServiceAssignment.select().where(
        (ServiceAssignment.target_service == 'metrics')
        & (ServiceAssignment.server_id == server_id)
        & (ServiceAssignment.desired_state != 'stopped')
    ))
    for assignment in assignments:
        queue_metrics_assignment(server_id, assignment.service, False)
    return len(assignments)


def stop_portscanner_assignments_for_server(server_id: int) -> int:
    assignment = ServiceAssignment.get_or_none(
        (ServiceAssignment.assignment_id == f'portscanner:server-{server_id}')
        & (ServiceAssignment.desired_state != 'stopped')
    )
    if assignment is None:
        return 0
    queue_portscanner_assignment(server_id, False)
    return 1


def stop_checker_udp_assignment(listener_id: int) -> int:
    """Queue a stop while the UDP listener record is still available."""
    assignment = ServiceAssignment.get_or_none(
        (ServiceAssignment.assignment_id == f'udp:server-{listener_id}')
        & (ServiceAssignment.desired_state != 'stopped')
    )
    if assignment is None:
        return 0
    queue_checker_udp_assignment(listener_id, False)
    return 1


def pending_commands(limit: int = 100):
    return list(
        ServiceCommand
        .select()
        .where(ServiceCommand.status.in_(('pending', 'failed')))
        .order_by(ServiceCommand.created_at)
        .limit(limit)
    )


def mark_published(command_id: str, published_at) -> None:
    ServiceCommand.update(
        status='published',
        attempts=ServiceCommand.attempts + 1,
        last_error=None,
        published_at=published_at,
        updated_at=published_at,
    ).where(ServiceCommand.command_id == command_id).execute()


def mark_failed(command_id: str, error: str, updated_at) -> None:
    ServiceCommand.update(
        status='failed',
        attempts=ServiceCommand.attempts + 1,
        last_error=error[:4000],
        updated_at=updated_at,
    ).where(ServiceCommand.command_id == command_id).execute()
