import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from flask import render_template
from pydantic import ValidationError

from app.modules.db.db_model import (
    Alerts,
    ApacheMetrics,
    Metrics,
    MetricsHttpStatus,
    NginxMetrics,
    PortScannerHistory,
    PortScannerPorts,
    PortScannerSettings,
    Server,
    ServiceAssignment,
    ServiceCommand,
    ServiceEvent,
    ServiceEventPosition,
    ServiceNotification,
    UDPBalancer,
    WafMetrics,
    WorkerState,
)
import app.modules.db.service_command as command_sql
import app.modules.db.service_event as event_sql
from app.modules.integrations.rabbitmq_consumer import RabbitConsumerSettings, declare_topology
from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
from app.modules.integrations.service_events import deliver_pending_notifications, process_event
from app.modules.integrations.service_commands import (
    RabbitPublisherSettings,
    declare_command_topology,
    publish_pending_commands,
)


@pytest.fixture(autouse=True)
def active_managed_services_subscription(monkeypatch):
    """Existing command tests model an installation with an active plan."""
    monkeypatch.setattr(command_sql, 'is_feature_available', lambda _feature: True)


def heartbeat_event(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        'event_id': str(uuid4()),
        'type': 'checker.worker.heartbeat',
        'schema_version': 1,
        'source': 'checker',
        'worker_id': f'checker-{uuid4()}',
        'service': 'checker',
        'instance_id': 'pod-1',
        'status': 'running',
        'hostname': 'checker-1',
        'version': '3.0.0',
        'started_at': (now - timedelta(minutes=5)).isoformat(),
        'heartbeat_at': now.isoformat(),
        'ttl_seconds': 30,
        'active_assignments': 4,
        'capacity': 20,
        'group_ids': [9876],
        'metadata': {'zone': 'test'},
    }
    payload.update(overrides)
    return payload


def status_event(**overrides):
    payload = {
        'event_id': str(uuid4()),
        'type': 'checker.status.changed',
        'schema_version': 1,
        'source': 'checker',
        'assignment_id': f'haproxy:test-{uuid4()}',
        'assignment_revision': 12,
        'lease_epoch': 18,
        'sequence': 157,
        'group_id': 9876,
        'server_id': 42,
        'server_address': '192.0.2.42',
        'port': 9999,
        'service': 'haproxy',
        'object_type': 'backend',
        'object_name': 'api/server-1',
        'previous_status': 'UP',
        'current_status': 'DOWN',
        'level': 'critical',
        'message': f'Unique checker event {uuid4()}',
        'alert_type': 'backend',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'notify': False,
    }
    payload.update(overrides)
    return payload


def metric_event(**overrides):
    payload = {
        'event_id': str(uuid4()),
        'type': 'metrics.sample.collected',
        'schema_version': 1,
        'source': 'metrics',
        'assignment_id': 'metrics:haproxy:server-42',
        'assignment_revision': 1,
        'lease_epoch': 2,
        'sequence': 1,
        'group_id': 9876,
        'server_id': 42,
        'server_address': '192.0.2.42',
        'service': 'haproxy',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'values': {
            'curr_con': 8,
            'cur_ssl_con': 3,
            'sess_rate': 4,
            'max_sess_rate': 20,
            'http_2xx': 15,
            'http_3xx': 2,
            'http_4xx': 1,
            'http_5xx': 0,
        },
    }
    payload.update(overrides)
    return payload


def portscanner_event(**overrides):
    payload = {
        'event_id': str(uuid4()),
        'type': 'portscanner.scan.completed',
        'schema_version': 2,
        'source': 'portscanner',
        'assignment_id': 'portscanner:server-42',
        'assignment_revision': 1,
        'lease_epoch': 2,
        'sequence': 1,
        'group_id': 9876,
        'server_id': 42,
        'server_address': '192.0.2.42',
        'service': 'portscanner',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': 1.25,
        'ports': [
            {'port': 22, 'protocol': 'tcp', 'service_name': 'ssh'},
            {'port': 80, 'protocol': 'tcp', 'service_name': 'http'},
        ],
    }
    payload.update(overrides)
    payload.setdefault('opened', payload['ports'])
    payload.setdefault('closed', [])
    return payload


def test_worker_heartbeat_is_upserted_and_group_scoped():
    payload = heartbeat_event()
    worker_id = payload['worker_id']
    now = datetime.fromisoformat(payload['heartbeat_at'])
    try:
        result = process_event(payload)
        assert result.kind == 'worker_heartbeat'

        worker = WorkerState.get_by_id(worker_id)
        assert worker.active_assignments == 4
        assert worker.group_ids == [9876]
        checker_summary = event_sql.worker_summary(group_id=9876)['checker']
        assert checker_summary['active'] == 1
        assert checker_summary['versions'] == ['3.0.0']
        assert 'checker' not in event_sql.worker_summary(group_id=9877)

        next_heartbeat = heartbeat_event(
            worker_id=worker_id,
            event_id=str(uuid4()),
            active_assignments=7,
            status='degraded',
        )
        process_event(next_heartbeat)

        assert WorkerState.select().where(WorkerState.worker_id == worker_id).count() == 1
        assert WorkerState.get_by_id(worker_id).active_assignments == 7

        process_event(heartbeat_event(
            worker_id=worker_id,
            event_id=str(uuid4()),
            heartbeat_at=(now - timedelta(minutes=1)).isoformat(),
            active_assignments=0,
            status='stopped',
        ))
        worker = WorkerState.get_by_id(worker_id)
        assert worker.active_assignments == 7
        assert worker.status == 'degraded'
    finally:
        WorkerState.delete().where(WorkerState.worker_id == worker_id).execute()


def test_expired_worker_is_reported_as_stale():
    now = datetime.now(timezone.utc)
    payload = heartbeat_event(
        heartbeat_at=(now - timedelta(minutes=2)).isoformat(),
        ttl_seconds=30,
    )
    worker_id = payload['worker_id']
    try:
        process_event(payload)
        summary = event_sql.worker_summary(group_id=9876, now=now)
        assert summary['checker']['active'] == 0
        assert summary['checker']['stale'] == 1
    finally:
        WorkerState.delete().where(WorkerState.worker_id == worker_id).execute()


def test_global_socket_worker_is_visible_without_a_connected_group():
    payload = heartbeat_event(
        type='socket.worker.heartbeat',
        source='socket',
        service='socket',
        worker_id=f'socket-{uuid4()}',
        version='2.0.0',
        active_assignments=0,
        group_ids=[],
    )
    try:
        process_event(payload)

        socket_summary = event_sql.worker_summary(group_id=9877)['socket']
        assert socket_summary['active'] == 1
        assert socket_summary['assignments'] == 0
        assert socket_summary['versions'] == ['2.0.0']
    finally:
        WorkerState.delete().where(WorkerState.worker_id == payload['worker_id']).execute()


def test_internal_roxy_process_is_visible_to_every_group():
    now = datetime.now(timezone.utc)
    worker_id = f'roxy-wi-scheduler-{uuid4()}'
    try:
        event_sql.record_worker_heartbeat({
            'worker_id': worker_id,
            'service': 'roxy-wi-scheduler',
            'instance_id': 'scheduler-1',
            'status': 'running',
            'hostname': 'scheduler-1',
            'version': '9.0.0',
            'started_at': now - timedelta(minutes=1),
            'heartbeat_at': now,
            'expires_at': now + timedelta(seconds=75),
            'active_assignments': 0,
            'group_ids': [],
            'metadata': {'kind': 'roxy-wi-process'},
        })

        summary = event_sql.worker_summary(group_id=9877)['roxy-wi-scheduler']
        assert summary['active'] == 1
        assert summary['versions'] == ['9.0.0']
        assert summary['last_heartbeat'] is not None
    finally:
        WorkerState.delete().where(WorkerState.worker_id == worker_id).execute()


def test_status_event_is_persisted_in_user_history_exactly_once():
    payload = status_event()
    result = process_event(payload)
    duplicate = process_event(payload)

    assert result.created is True
    assert duplicate.created is False
    assert ServiceEvent.select().where(ServiceEvent.event_id == payload['event_id']).count() == 1
    assert Alerts.select().where(Alerts.message == payload['message']).count() == 1
    alert = Alerts.get(Alerts.message == payload['message'])
    assert alert.user_group == payload['group_id']
    assert alert.service == 'Checker'


def test_delayed_event_from_an_old_lease_is_added_to_history_without_rolling_position_back():
    assignment_id = f'haproxy:test-{uuid4()}'
    current = status_event(
        assignment_id=assignment_id,
        assignment_revision=4,
        lease_epoch=9,
        sequence=20,
    )
    delayed = status_event(
        assignment_id=assignment_id,
        assignment_revision=4,
        lease_epoch=8,
        sequence=19,
    )

    assert process_event(current).created is True
    assert process_event(delayed).created is True
    assert process_event(delayed).created is False
    assert ServiceEvent.select().where(ServiceEvent.assignment_id == assignment_id).count() == 2
    assert Alerts.select().where(Alerts.message == delayed['message']).count() == 1
    assert ServiceEventPosition.get_by_id(assignment_id).event_id == current['event_id']


def test_event_from_an_old_desired_revision_is_ignored():
    assignment_id = f'haproxy:test-{uuid4()}'
    assignment_payload = {
        'target': {
            'server_id': 42,
            'address': '192.0.2.42',
            'service': 'haproxy',
            'port': 9999,
        },
    }
    ServiceAssignment.create(
        assignment_id=assignment_id,
        target_service='checker',
        server_id=42,
        service='haproxy',
        user_group=9876,
        revision=5,
        desired_state='stopped',
        payload=json.dumps(assignment_payload),
    )
    delayed = status_event(
        assignment_id=assignment_id,
        assignment_revision=4,
        lease_epoch=20,
        sequence=100,
    )
    try:
        assert process_event(delayed).created is False
        assert Alerts.select().where(Alerts.message == delayed['message']).count() == 0
    finally:
        ServiceAssignment.delete().where(
            ServiceAssignment.assignment_id == assignment_id
        ).execute()


def test_metrics_sample_is_validated_and_persisted_exactly_once():
    payload = metric_event()
    assignment_payload = {
        'target': {
            'server_id': payload['server_id'],
            'address': payload['server_address'],
            'service': payload['service'],
            'port': 1999,
        }
    }
    ServiceAssignment.create(
        assignment_id=payload['assignment_id'],
        target_service='metrics',
        server_id=payload['server_id'],
        service=payload['service'],
        user_group=payload['group_id'],
        revision=payload['assignment_revision'],
        desired_state='running',
        payload=json.dumps(assignment_payload),
    )
    try:
        assert process_event(payload).created is True
        assert process_event(payload).created is False
        metric = Metrics.get(Metrics.serv == payload['server_address'])
        http = MetricsHttpStatus.get(MetricsHttpStatus.serv == payload['server_address'])
        assert (metric.curr_con, metric.cur_ssl_con, metric.sess_rate, metric.max_sess_rate) == (8, 3, 4, 20)
        assert (http.ok_ans, http.redir_ans, http.not_found_ans, http.err_ans) == (15, 2, 1, 0)
        assert Metrics.select().where(Metrics.serv == payload['server_address']).count() == 1
    finally:
        Metrics.delete().where(Metrics.serv == payload['server_address']).execute()
        MetricsHttpStatus.delete().where(MetricsHttpStatus.serv == payload['server_address']).execute()
        ServiceEvent.delete().where(ServiceEvent.event_id == payload['event_id']).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == payload['assignment_id']).execute()


@pytest.mark.parametrize(
    ('service', 'model'),
    [('nginx', NginxMetrics), ('apache', ApacheMetrics), ('waf', WafMetrics)],
)
def test_connection_metric_samples_use_existing_service_tables(service, model):
    unique_id = uuid4().int % 1000000 + 1000
    payload = metric_event(
        assignment_id=f'metrics:{service}:server-{unique_id}',
        server_id=unique_id,
        server_address=f'{service}-{uuid4().hex}.example.test',
        service=service,
        values={'conn': 13},
    )
    ServiceAssignment.create(
        assignment_id=payload['assignment_id'],
        target_service='metrics',
        server_id=payload['server_id'],
        service=service,
        user_group=payload['group_id'],
        revision=1,
        desired_state='running',
        payload=json.dumps({'target': {
            'server_id': payload['server_id'], 'address': payload['server_address'],
            'service': service, 'port': 9999,
        }}),
    )
    try:
        assert process_event(payload).kind == 'metric_sample'
        assert model.get(model.serv == payload['server_address']).conn == 13
    finally:
        model.delete().where(model.serv == payload['server_address']).execute()
        ServiceEvent.delete().where(ServiceEvent.event_id == payload['event_id']).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == payload['assignment_id']).execute()


def test_delayed_metrics_sample_from_old_lease_is_saved_without_duplicate_event_json():
    current = metric_event(lease_epoch=9, sequence=20)
    delayed = metric_event(event_id=str(uuid4()), lease_epoch=8, sequence=19)
    ServiceAssignment.create(
        assignment_id=current['assignment_id'],
        target_service='metrics',
        server_id=current['server_id'],
        service=current['service'],
        user_group=current['group_id'],
        revision=1,
        desired_state='running',
        payload=json.dumps({'target': {
            'server_id': current['server_id'], 'address': current['server_address'],
            'service': current['service'], 'port': 1999,
        }}),
    )
    try:
        assert process_event(current).created is True
        assert process_event(delayed).created is True
        assert process_event(delayed).created is False
        assert Metrics.select().where(Metrics.serv == current['server_address']).count() == 2
        assert ServiceEvent.select().where(ServiceEvent.assignment_id == current['assignment_id']).count() == 0
    finally:
        Metrics.delete().where(Metrics.serv == current['server_address']).execute()
        MetricsHttpStatus.delete().where(MetricsHttpStatus.serv == current['server_address']).execute()
        ServiceEvent.delete().where(ServiceEvent.assignment_id == current['assignment_id']).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == current['assignment_id']).execute()


def test_portscanner_snapshot_updates_current_ports_history_and_notification(monkeypatch):
    unique_id = uuid4().int % 1000000 + 1000
    address = f'ports-{uuid4().hex}.example.test'
    payload = portscanner_event(
        assignment_id=f'portscanner:server-{unique_id}',
        server_id=unique_id,
        server_address=address,
    )
    assignment_payload = {
        'target': {
            'server_id': unique_id,
            'address': address,
            'service': 'portscanner',
        },
        'settings': {'notify': True, 'history': True},
    }
    ServiceAssignment.create(
        assignment_id=payload['assignment_id'],
        target_service='portscanner',
        server_id=unique_id,
        service='portscanner',
        user_group=payload['group_id'],
        revision=1,
        desired_state='running',
        payload=json.dumps(assignment_payload),
    )
    calls = []
    from app.modules.tools import alerting
    monkeypatch.setattr(
        alerting,
        'portscanner_alert_routing',
        lambda *args, **_kwargs: calls.append(args),
    )
    try:
        result = process_event(payload)
        assert result.kind == 'port_snapshot'
        assert result.created is True
        assert process_event(payload).created is False

        current = sorted(
            (row.port, row.service_name)
            for row in PortScannerPorts.select().where(PortScannerPorts.serv == address)
        )
        assert current == [(22, 'ssh'), (80, 'http')]
        first_history = sorted(
            (row.status, row.port, row.service_name)
            for row in PortScannerHistory.select().where(PortScannerHistory.serv == address)
        )
        assert first_history == [('opened', 22, 'ssh'), ('opened', 80, 'http')]
        assert ServiceNotification.select().where(
            ServiceNotification.event_id == payload['event_id']
        ).count() == 1

        assert deliver_pending_notifications(limit=100) >= 1
        delivery = ServiceNotification.get(ServiceNotification.event_id == payload['event_id'])
        assert delivery.status == 'delivered'
        stored_event = ServiceEvent.get_by_id(payload['event_id'])
        assert calls[-1] == (
            address,
            payload['group_id'],
            'info',
            stored_event.message,
        )

        changed = portscanner_event(
            event_id=str(uuid4()),
            assignment_id=payload['assignment_id'],
            server_id=unique_id,
            server_address=address,
            sequence=2,
            opened=[{'port': 443, 'protocol': 'tcp', 'service_name': 'https'}],
            closed=[{'port': 80, 'protocol': 'tcp', 'service_name': 'http'}],
            ports=[
                {'port': 22, 'protocol': 'tcp', 'service_name': 'ssh'},
                {'port': 443, 'protocol': 'tcp', 'service_name': 'https'},
            ],
        )
        assert process_event(changed).created is True
        current = sorted(
            (row.port, row.service_name)
            for row in PortScannerPorts.select().where(PortScannerPorts.serv == address)
        )
        assert current == [(22, 'ssh'), (443, 'https')]
        history = sorted(
            (row.status, row.port, row.service_name)
            for row in PortScannerHistory.select().where(PortScannerHistory.serv == address)
        )
        assert history == [
            ('closed', 80, 'http'),
            ('opened', 22, 'ssh'),
            ('opened', 80, 'http'),
            ('opened', 443, 'https'),
        ]
        assert ServiceEvent.select().where(
            ServiceEvent.assignment_id == payload['assignment_id']
        ).count() == 2
    finally:
        event_ids = ServiceEvent.select(ServiceEvent.event_id).where(
            ServiceEvent.assignment_id == payload['assignment_id']
        )
        ServiceNotification.delete().where(ServiceNotification.event_id.in_(event_ids)).execute()
        ServiceEvent.delete().where(ServiceEvent.assignment_id == payload['assignment_id']).execute()
        PortScannerHistory.delete().where(PortScannerHistory.serv == address).execute()
        PortScannerPorts.delete().where(PortScannerPorts.serv == address).execute()
        ServiceAssignment.delete().where(
            ServiceAssignment.assignment_id == payload['assignment_id']
        ).execute()


def test_diagnostic_retention_preserves_pending_notifications():
    old = status_event(
        observed_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        notify=True,
    )
    process_event(old)
    ServiceEvent.update(received_at=datetime.now() - timedelta(days=30)).where(
        ServiceEvent.event_id == old['event_id']
    ).execute()

    assert ServiceNotification.select().where(
        ServiceNotification.event_id == old['event_id']
    ).count() == 1
    assert event_sql.prune_service_events(retention_days=14) >= 1
    assert ServiceEvent.get_or_none(ServiceEvent.event_id == old['event_id']) is None
    assert ServiceNotification.select().where(
        ServiceNotification.event_id == old['event_id']
    ).count() == 1
    ServiceNotification.delete().where(ServiceNotification.event_id == old['event_id']).execute()
    Alerts.delete().where(Alerts.message == old['message']).execute()


def test_status_event_notification_is_retried_from_outbox(monkeypatch):
    payload = status_event(notify=True)
    process_event(payload)
    calls = []

    def fake_alert_routing(*args, **_kwargs):
        calls.append(args)

    from app.modules.tools import alerting
    monkeypatch.setattr(alerting, 'alert_routing', fake_alert_routing)

    assert deliver_pending_notifications(limit=100) >= 1
    delivery = ServiceNotification.get(ServiceNotification.event_id == payload['event_id'])
    assert delivery.status == 'delivered'
    assert calls[-1] == (
        payload['server_address'],
        1,
        payload['group_id'],
        payload['level'],
        payload['message'],
        payload['alert_type'],
    )


def test_event_contract_rejects_cross_service_heartbeat():
    with pytest.raises(ValueError, match='must match'):
        process_event(heartbeat_event(service='metrics'))

    with pytest.raises(ValidationError):
        process_event(status_event(group_id=0))


def test_overview_worker_status_renders_distributed_counts(app):
    internal_services = [[
        'roxy-wi-scheduler',
        'active',
        {'current_version': '9.0.0', 'new_version': '9.0.0'},
        {'active': 1, 'assignments': 0},
        {'category': 'internal', 'instances': 1, 'stale': 0},
    ]]
    distributed_services = [
        [
            'roxy-wi-checker',
            'degraded',
            {'current_version': '5.0.0', 'new_version': '5.0.0'},
            {'active': 2, 'degraded': 1, 'stale': 1, 'assignments': 7},
            {'category': 'distributed', 'instances': 2, 'stale': 1},
        ],
        [
            'roxy-wi-metrics',
            'stale',
            {'current_version': '4.0.0', 'new_version': '4.0.0'},
            {'active': 0, 'degraded': 0, 'stale': 1, 'assignments': 0},
            {'category': 'distributed', 'instances': 0, 'stale': 1},
        ],
        [
            'roxy-wi-socket',
            'degraded',
            {'current_version': '2.0.0', 'new_version': '2.0.0'},
            {'active': 2, 'degraded': 0, 'stale': 1, 'assignments': 4},
            {'category': 'distributed', 'instances': 2, 'stale': 1},
        ],
    ]
    with app.test_request_context('/overview/services'):
        html = render_template(
            'ajax/show_services_ovw.html',
            role=1,
            lang='en',
            url_for=lambda endpoint, **_values: '/' + endpoint.replace('.', '/'),
            internal_services=internal_services,
            distributed_services=distributed_services,
        )

    assert '1 instances' in html
    assert '2 workers · 7 assignments' in html
    assert '0 workers · 0 assignments' in html
    assert '2 workers · 4 connections' in html
    assert html.count('1 stale') == 3
    assert 'master' not in html.lower()


class RecordingChannel:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(**kwargs):
            self.calls.append((name, kwargs))
        return record


def test_rabbit_topology_is_durable_and_dead_lettered():
    channel = RecordingChannel()
    settings = RabbitConsumerSettings(
        host='rabbitmq',
        port=5672,
        vhost='/',
        username='roxy-wi',
        password='secret',
        queue_type='quorum',
    )

    declare_topology(channel, settings)

    queue_calls = [kwargs for name, kwargs in channel.calls if name == 'queue_declare']
    assert queue_calls[0]['durable'] is True
    assert queue_calls[0]['arguments'] == {
        'x-dead-letter-exchange': settings.dead_letter_exchange,
        'x-queue-type': 'quorum',
    }
    assert queue_calls[1]['arguments'] == {'x-queue-type': 'quorum'}
    bindings = [kwargs['routing_key'] for name, kwargs in channel.calls if name == 'queue_bind']
    assert 'checker.#' in bindings
    assert 'metrics.#' in bindings
    assert '#' in bindings


def test_rabbit_connection_reuses_roxy_settings_with_env_overrides(monkeypatch):
    values = {
        'rabbitmq_host': 'rabbit-from-ui',
        'rabbitmq_port': '5673',
        'rabbitmq_vhost': '/roxy',
        'rabbitmq_user': 'ui-user',
        'rabbitmq_password': 'ui-password',
    }
    for env_name in (
        'ROXYWI_RABBITMQ_HOST',
        'ROXYWI_RABBITMQ_PORT',
        'ROXYWI_RABBITMQ_VHOST',
        'ROXYWI_RABBITMQ_USER',
        'ROXYWI_RABBITMQ_PASSWORD',
    ):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(
        'app.modules.integrations.rabbitmq_settings.sql.get_setting',
        lambda name: values[name],
    )

    settings = RabbitConnectionSettings.load()
    assert settings == RabbitConnectionSettings(
        'rabbit-from-ui', 5673, '/roxy', 'ui-user', 'ui-password'
    )

    monkeypatch.setenv('ROXYWI_RABBITMQ_HOST', 'rabbit-from-env')
    assert RabbitConnectionSettings.load().host == 'rabbit-from-env'


def test_command_topology_exists_before_checker_connects():
    channel = RecordingChannel()
    settings = RabbitPublisherSettings(
        'rabbitmq', 5672, '/', 'roxy-wi', 'secret', queue_type='quorum'
    )

    declare_command_topology(channel, settings)

    queue_calls = [kwargs for name, kwargs in channel.calls if name == 'queue_declare']
    assert queue_calls[0]['queue'] == 'roxy-checker.commands'
    assert queue_calls[0]['durable'] is True
    assert queue_calls[0]['arguments'] == {
        'x-dead-letter-exchange': 'roxy.commands.dlx',
        'x-queue-type': 'quorum',
    }
    assert queue_calls[1]['queue'] == 'roxy-checker.commands.dlq'
    assert queue_calls[2]['queue'] == 'roxy-metrics.commands'
    assert queue_calls[3]['queue'] == 'roxy-metrics.commands.dlq'
    assert queue_calls[4]['queue'] == 'roxy-portscanner.commands'
    assert queue_calls[5]['queue'] == 'roxy-portscanner.commands.dlq'
    bindings = [kwargs['routing_key'] for name, kwargs in channel.calls if name == 'queue_bind']
    assert bindings == [
        'checker.assignment.apply', '#',
        'metrics.assignment.apply', '#',
        'portscanner.assignment.apply', '#',
    ]


def test_metrics_assignment_commands_are_revisioned_and_subscription_gated(monkeypatch):
    unique = uuid4().hex[:12]
    server = Server.create(
        hostname=f'metrics-{unique}',
        ip=f'metrics-{unique}.example.test',
        group_id='9876',
        haproxy=1,
        haproxy_metrics=1,
    )
    assignment_id = f'metrics:haproxy:server-{server.server_id}'
    try:
        command_sql.queue_metrics_assignment(server.server_id, 'haproxy', True)
        assignment = ServiceAssignment.get_by_id(assignment_id)
        command = ServiceCommand.get(ServiceCommand.assignment_id == assignment_id)
        payload = json.loads(command.payload)
        assert assignment.target_service == 'metrics'
        assert assignment.desired_state == 'running'
        assert payload['type'] == 'metrics.assignment.apply'
        assert payload['target']['address'] == server.ip

        monkeypatch.setattr(command_sql, 'is_feature_available', lambda _feature: False)
        command_sql.queue_metrics_assignment(server.server_id, 'haproxy', True)
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'stopped'
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        server.delete_instance()


def test_portscanner_assignment_commands_are_revisioned_and_subscription_gated(monkeypatch):
    unique = uuid4().hex[:12]
    server = Server.create(
        hostname=f'portscanner-{unique}',
        ip=f'portscanner-{unique}.example.test',
        group_id='9876',
        enabled=1,
    )
    PortScannerSettings.create(
        server_id=server.server_id,
        user_group_id=9876,
        enabled=1,
        notify=1,
        history=1,
    )
    assignment_id = f'portscanner:server-{server.server_id}'
    monkeypatch.setattr(command_sql, '_group_setting', lambda _name, _group_id: 2)
    try:
        command_sql.queue_portscanner_assignment(server.server_id, True)
        assignment = ServiceAssignment.get_by_id(assignment_id)
        command = ServiceCommand.get(ServiceCommand.assignment_id == assignment_id)
        payload = json.loads(command.payload)
        assert assignment.target_service == 'portscanner'
        assert assignment.desired_state == 'running'
        assert payload['type'] == 'portscanner.assignment.apply'
        assert payload['target'] == {
            'server_id': server.server_id,
            'address': server.ip,
            'service': 'portscanner',
        }
        assert payload['settings']['interval_seconds'] == 120
        assert payload['settings']['notify'] is True
        assert payload['settings']['history'] is True

        monkeypatch.setattr(command_sql, 'is_feature_available', lambda _feature: False)
        command_sql.queue_portscanner_assignment(server.server_id, True)
        assignment = ServiceAssignment.get_by_id(assignment_id)
        assert assignment.desired_state == 'stopped'
        assert assignment.revision == 2
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        PortScannerSettings.delete().where(
            PortScannerSettings.server_id == server.server_id
        ).execute()
        server.delete_instance()


def test_checker_assignment_commands_are_revisioned_and_persistent():
    unique = uuid4().hex[:12]
    server = Server.create(
        hostname=f'checker-{unique}',
        ip=f'worker-{unique}.example.test',
        group_id='9876',
    )
    assignment_id = f'haproxy:server-{server.server_id}'
    try:
        first_command = command_sql.queue_checker_assignment(server.server_id, 'haproxy', True)
        second_command = command_sql.queue_checker_assignment(server.server_id, 'haproxy', False)

        assignment = ServiceAssignment.get_by_id(assignment_id)
        commands = list(
            ServiceCommand.select()
            .where(ServiceCommand.assignment_id == assignment_id)
            .order_by(ServiceCommand.revision)
        )
        assert assignment.revision == 2
        assert assignment.desired_state == 'stopped'
        assert [command.revision for command in commands] == [1, 2]
        assert [command.command_id for command in commands] == [first_command, second_command]
        assert '"desired_state":"running"' in commands[0].payload
        assert '"desired_state":"stopped"' in commands[1].payload
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        server.delete_instance()


def test_existing_checker_settings_are_reconciled_once():
    unique = uuid4().hex[:12]
    server = Server.create(
        hostname=f'reconcile-{unique}',
        ip=f'reconcile-{unique}.example.test',
        group_id='9876',
        haproxy=1,
        haproxy_alert=1,
    )
    assignment_id = f'haproxy:server-{server.server_id}'
    ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
    ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
    server = Server.get_by_id(server.server_id)
    try:
        assert command_sql.reconcile_checker_assignments([server]) == 1
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'running'
        revision = ServiceAssignment.get_by_id(assignment_id).revision

        assert command_sql.reconcile_checker_assignments([server]) == 0
        assert ServiceAssignment.get_by_id(assignment_id).revision == revision

        server.ip = f'reconcile-moved-{unique}.example.test'
        server.save()
        assert command_sql.reconcile_checker_assignments([server]) == 1
        revision += 1
        assert ServiceAssignment.get_by_id(assignment_id).revision == revision

        server.haproxy_alert = 0
        server.save()
        assert command_sql.reconcile_checker_assignments([server]) == 1
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'stopped'
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        server.delete_instance()


def test_checker_is_stopped_when_managed_service_subscription_expires(monkeypatch):
    unique = uuid4().hex[:12]
    server = Server.create(
        hostname=f'expired-{unique}',
        ip=f'expired-{unique}.example.test',
        group_id='9876',
        haproxy=1,
        haproxy_alert=1,
    )
    assignment_id = f'haproxy:server-{server.server_id}'
    try:
        command_sql.queue_checker_assignment(server.server_id, 'haproxy', True)
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'running'

        monkeypatch.setattr(command_sql, 'is_feature_available', lambda _feature: False)
        assert command_sql.reconcile_checker_assignments([server]) == 1

        assignment = ServiceAssignment.get_by_id(assignment_id)
        latest_command = (
            ServiceCommand.select()
            .where(ServiceCommand.assignment_id == assignment_id)
            .order_by(ServiceCommand.revision.desc())
            .get()
        )
        assert assignment.desired_state == 'stopped'
        assert json.loads(latest_command.payload)['desired_state'] == 'stopped'

        command_sql.queue_checker_assignment(server.server_id, 'haproxy', True)
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'stopped'
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        server.delete_instance()


def test_udp_checker_assignments_use_the_distributed_command_path():
    unique = uuid4().hex[:12]
    listener = UDPBalancer.create(
        name=f'udp-{unique}',
        vip=f'udp-{unique}.example.test',
        port=5353,
        group_id=1,
        config='[]',
        description='',
        is_checker=1,
    )
    assignment_id = f'udp:server-{listener.id}'
    try:
        assert command_sql.reconcile_checker_udp_assignments([listener]) == 1
        assignment = ServiceAssignment.get_by_id(assignment_id)
        payload = json.loads(assignment.payload)
        assert assignment.desired_state == 'running'
        assert payload['target'] == {
            'server_id': listener.id,
            'address': listener.vip,
            'service': 'udp',
            'port': 5353,
        }

        assert command_sql.reconcile_checker_udp_assignments([listener]) == 0
        listener.is_checker = 0
        listener.save()
        assert command_sql.reconcile_checker_udp_assignments([listener]) == 1
        assert ServiceAssignment.get_by_id(assignment_id).desired_state == 'stopped'
    finally:
        ServiceCommand.delete().where(ServiceCommand.assignment_id == assignment_id).execute()
        ServiceAssignment.delete().where(ServiceAssignment.assignment_id == assignment_id).execute()
        listener.delete_instance()


class FakePublisherChannel:
    def __init__(self):
        self.messages = []

    def exchange_declare(self, **_kwargs):
        pass

    def queue_declare(self, **_kwargs):
        pass

    def queue_bind(self, **_kwargs):
        pass

    def confirm_delivery(self):
        pass

    def basic_publish(self, **kwargs):
        self.messages.append(kwargs)
        return True


class FakePublisherConnection:
    def __init__(self):
        self.channel_instance = FakePublisherChannel()
        self.is_open = True

    def channel(self):
        return self.channel_instance

    def close(self):
        self.is_open = False


def test_command_outbox_uses_persistent_confirmed_messages(monkeypatch):
    command_id = str(uuid4())
    assignment_id = f'checker:test-{uuid4()}'
    ServiceCommand.create(
        command_id=command_id,
        command_type='checker.assignment.apply',
        target_service='checker',
        routing_key='checker.assignment.apply',
        assignment_id=assignment_id,
        revision=1,
        payload='{"type":"checker.assignment.apply"}',
    )
    connection = FakePublisherConnection()
    monkeypatch.setattr(
        'app.modules.integrations.service_commands.pika.BlockingConnection',
        lambda _parameters: connection,
    )
    try:
        published = publish_pending_commands(
            limit=100,
            settings=RabbitPublisherSettings('rabbitmq', 5672, '/', 'roxy-wi', 'secret'),
        )
        command = ServiceCommand.get_by_id(command_id)
        assert published >= 1
        assert command.status == 'published'
        message = next(item for item in connection.channel_instance.messages if item['properties'].message_id == command_id)
        assert message['routing_key'] == 'checker.assignment.apply'
        assert message['mandatory'] is True
        assert message['properties'].delivery_mode == 2
    finally:
        ServiceCommand.delete().where(ServiceCommand.command_id == command_id).execute()
