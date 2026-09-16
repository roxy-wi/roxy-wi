import importlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import permutations
from uuid import uuid4

import pytest
from peewee import SqliteDatabase
from playhouse.migrate import SqliteMigrator, migrate

from app.modules.common.time import utc_now
from app.modules.db import service_event as storage
from app.modules.db.db_model import (
    Alerts, ApacheMetrics, Metrics, MetricsHttpStatus, NginxMetrics,
    PortScannerHistory, PortScannerPorts, ServiceAssignment, ServiceCommand,
    ServiceEvent, ServiceEventDelivery, ServiceEventPosition, ServiceEventRetention,
    ServiceNotification, WafMetrics,
)
from app.modules.db.service_event_storage import METRIC_MODELS, event_key, prune_history
from app.modules.integrations.service_events import deliver_pending_notifications, process_event
from tests.integration.test_service_events import metric_event, portscanner_event, status_event


MODELS = [
    Alerts, ApacheMetrics, Metrics, MetricsHttpStatus, NginxMetrics, WafMetrics,
    PortScannerHistory, PortScannerPorts, ServiceEvent, ServiceEventDelivery,
    ServiceEventPosition, ServiceEventRetention, ServiceNotification, ServiceAssignment, ServiceCommand,
]


@pytest.fixture(autouse=True)
def event_database(tmp_path):
    database = SqliteDatabase(tmp_path / 'events.db', pragmas={
        'foreign_keys': 1, 'journal_mode': 'wal', 'busy_timeout': 5000,
    })
    with database.bind_ctx(MODELS, bind_refs=False, bind_backrefs=False):
        database.create_tables(MODELS)
        yield database
        database.close()


def assignment(payload, **settings):
    ServiceAssignment.create(
        assignment_id=payload['assignment_id'], target_service=payload['source'],
        server_id=payload['server_id'], service=payload['service'], user_group=payload['group_id'],
        revision=payload['assignment_revision'], desired_state='running',
        payload=json.dumps({'target': {
            'server_id': payload['server_id'], 'address': payload['server_address'],
            'service': payload['service'],
        }, 'settings': settings}),
    )


@pytest.mark.parametrize('arrival_order', list(permutations(range(3))))
def test_port_changes_are_independent_of_arrival_order(arrival_order):
    now = utc_now()
    port = {'port': 443, 'protocol': 'tcp', 'service_name': 'https'}
    events = [
        portscanner_event(sequence=1, ports=[port], opened=[port], closed=[], observed_at=now.isoformat()),
        portscanner_event(sequence=2, ports=[], opened=[], closed=[port],
                          observed_at=(now + timedelta(seconds=1)).isoformat()),
        portscanner_event(sequence=3, ports=[port], opened=[port], closed=[],
                          observed_at=(now + timedelta(seconds=2)).isoformat()),
    ]
    assignment(events[0], history=True, notify=True)
    for index in arrival_order:
        assert process_event(events[index]).created
        assert not process_event(events[index]).created
        assert not process_event(dict(events[index], event_id=str(uuid4()))).created
    assert PortScannerHistory.select().count() == 3
    assert [(row.port, row.status) for row in PortScannerHistory.select().order_by(PortScannerHistory.date)] == [
        (443, 'opened'), (443, 'closed'), (443, 'opened'),
    ]
    assert PortScannerPorts.get().port == 443
    assert PortScannerPorts.get().date == now + timedelta(seconds=2)
    assert ServiceNotification.select().count() == 3
    assert ServiceEventPosition.get().event_id == events[2]['event_id']


def test_portscanner_requires_v2_and_consistent_changes():
    with pytest.raises(ValueError, match='schema_version'):
        process_event(portscanner_event(schema_version=1))
    with pytest.raises(ValueError, match='closed ports'):
        process_event(portscanner_event(closed=[{'port': 22, 'service_name': 'ssh'}]))
    with pytest.raises(ValueError, match='opened ports'):
        process_event(portscanner_event(ports=[], opened=[{'port': 22, 'service_name': 'ssh'}]))
    missing_version = portscanner_event()
    del missing_version['schema_version']
    with pytest.raises(ValueError, match='schema_version'):
        process_event(missing_version)


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache', 'waf'])
def test_metrics_identity_lives_only_in_graph_rows(service):
    payload = metric_event(service=service)
    if service != 'haproxy':
        payload['values'] = {'conn': 4}
    assignment(payload)
    for sequence in [3, 1, 2]:
        event = dict(payload, sequence=sequence, event_id=str(uuid4()))
        assert process_event(event).created
        assert not process_event(event).created
        assert not process_event(dict(event, event_id=str(uuid4()))).created
    assert METRIC_MODELS[service].select().count() == 3
    assert ServiceEvent.select().count() == 0
    assert ServiceNotification.select().count() == 0
    assert ServiceEventPosition.select().count() == 1
    assert ServiceEventPosition.get().sequence == 3


def test_failure_of_second_graph_write_rolls_back_first_and_position(monkeypatch):
    payload = metric_event()
    assignment(payload)
    original = MetricsHttpStatus.create

    def fail(**_kwargs):
        raise RuntimeError('graph write failed')

    monkeypatch.setattr(MetricsHttpStatus, 'create', fail)
    with pytest.raises(RuntimeError, match='graph write failed'):
        process_event(payload)
    assert Metrics.select().count() == 0
    assert ServiceEventPosition.select().count() == 0
    monkeypatch.setattr(MetricsHttpStatus, 'create', original)
    assert process_event(payload).created
    assert Metrics.select().count() == MetricsHttpStatus.select().count() == 1


def test_outbox_failure_rolls_back_history_and_diagnostic(monkeypatch):
    payload = status_event(notify=True)

    def fail(**_kwargs):
        raise RuntimeError('outbox write failed')

    monkeypatch.setattr(ServiceNotification, 'create', fail)
    with pytest.raises(RuntimeError, match='outbox write failed'):
        process_event(payload)
    assert Alerts.select().count() == ServiceEvent.select().count() == 0
    assert ServiceEventPosition.select().count() == 0


def test_parallel_consumers_commit_each_sample_once(event_database):
    payload = metric_event()
    assignment(payload)

    def consume(_index):
        try:
            return process_event(payload).created
        finally:
            event_database.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(consume, range(12))) == 1
    assert Metrics.select().count() == MetricsHttpStatus.select().count() == 1


def test_pending_delivery_survives_both_diagnostic_and_history_retention(monkeypatch):
    payload = status_event(notify=True, observed_at=(utc_now() - timedelta(days=30)).isoformat())
    assert process_event(payload).created
    ServiceEvent.update(received_at=utc_now() - timedelta(days=30)).execute()
    prune_history('checker', 14)
    storage.prune_service_events()
    storage.prune_notifications()
    assert ServiceEvent.select().count() == Alerts.select().count() == 0
    assert ServiceNotification.select().count() == 1
    assert not process_event(payload).created

    from app.modules.tools import alerting
    calls = []
    monkeypatch.setattr(alerting, 'alert_routing', lambda *args, **_kwargs: calls.append(args))
    assert deliver_pending_notifications() == 1
    assert len(calls) == 1
    assert storage.prune_notifications() == 1
    assert not process_event(dict(payload, event_id=str(uuid4()))).created


def test_retention_does_not_resurrect_samples_when_window_is_extended():
    payload = metric_event(observed_at=(utc_now() - timedelta(days=5)).isoformat())
    assignment(payload)
    assert process_event(payload).created
    prune_history('metrics', 3)
    cutoff = ServiceEventRetention.get_by_id('metrics').cutoff
    prune_history('metrics', 30)
    assert ServiceEventRetention.get_by_id('metrics').cutoff == cutoff
    assert not process_event(payload).created
    assert Metrics.select().count() == 0


def test_history_disabled_notification_keeps_identity_after_success(monkeypatch):
    payload = portscanner_event()
    assignment(payload, notify=True, history=False)
    assert process_event(payload).created
    from app.modules.tools import alerting
    monkeypatch.setattr(alerting, 'portscanner_alert_routing', lambda *args, **_kwargs: None)
    assert deliver_pending_notifications() == 1
    ServiceNotification.update(updated_at=utc_now() - timedelta(days=4)).execute()
    ServiceEvent.delete().execute()
    storage.prune_notifications()
    assert ServiceNotification.get().payload is None
    later = dict(payload, event_id=str(uuid4()), sequence=2, opened=[], closed=[])
    assert process_event(later).created
    assert not process_event(payload).created
    assert not process_event(dict(payload, event_id=str(uuid4()))).created


def test_expired_claim_cannot_finish_work_owned_by_another_consumer():
    payload = status_event(notify=True)
    process_event(payload)
    old = storage.claim_pending_deliveries()[0]
    ServiceNotification.update(updated_at=utc_now() - timedelta(minutes=6)).execute()
    new = storage.claim_pending_deliveries()[0]
    assert old.claim_token != new.claim_token
    storage.mark_delivery_succeeded(old.id, old.claim_token)
    assert ServiceNotification.get().status == 'processing'
    storage.mark_delivery_failed(old.id, 'late failure', old.claim_token)
    assert ServiceNotification.get().attempts == 0
    storage.mark_delivery_succeeded(new.id, new.claim_token)
    assert ServiceNotification.get().status == 'delivered'


def test_notification_migration_is_resumable_and_preserves_pending_data():
    payload = status_event(notify=True)
    process_event(payload)
    ServiceNotification.delete().execute()
    ServiceEventDelivery.create(event_id=payload['event_id'], status='failed', attempts=3, last_error='retry')
    migration = importlib.import_module('app.modules.db.migrations.20260913000000_separate_notification_outbox')
    migration.up()
    migration.up()
    assert ServiceNotification.select().count() == 1
    notification = ServiceNotification.get()
    assert notification.status == 'failed'
    assert notification.attempts == 3
    assert notification.event_key == event_key(payload)
    assert json.loads(notification.payload)['message'] == payload['message']
    ServiceEvent.delete().execute()
    assert ServiceNotification.select().count() == 1


def test_migration_adds_and_backfills_identity_without_duplicating_legacy_graphs(event_database):
    payload = metric_event()
    assignment(payload)
    assert process_event(payload).created
    storage._store_diagnostic(dict(payload, observed_at=datetime.fromisoformat(payload['observed_at'])))
    checker = status_event()
    assert process_event(checker).created
    migrator = SqliteMigrator(event_database)
    for model in [*METRIC_MODELS.values(), MetricsHttpStatus, Alerts, PortScannerHistory]:
        table = model._meta.table_name
        for index in event_database.get_indexes(table):
            if 'event_id' in index.columns or 'event_key' in index.columns:
                migrate(migrator.drop_index(table, index.name))
        migrate(migrator.drop_column(table, 'event_id'), migrator.drop_column(table, 'event_key'))
    ServiceEventPosition.delete().execute()
    migrate(migrator.add_index('service_events', ('source',), unique=False))
    migration = importlib.import_module('app.modules.db.migrations.20260913001000_service_history_identities')
    migration.up()
    migration.up()
    assert Metrics.get().event_id == MetricsHttpStatus.get().event_id == payload['event_id']
    assert Alerts.get().event_id == checker['event_id']
    assert {tuple(index.columns) for index in event_database.get_indexes('service_events')} == {
        ('event_id',), ('received_at',),
        ('assignment_id', 'assignment_revision', 'lease_epoch', 'sequence'),
    }
    ServiceEvent.delete().execute()
    assert not process_event(payload).created
    assert not process_event(checker).created
    assert Metrics.select().count() == Alerts.select().count() == 1


def test_previous_revision_uses_original_history_settings_without_changing_current_ports():
    payload = portscanner_event()
    assignment(payload, history=False, notify=False)
    desired = json.loads(ServiceAssignment.get().payload)
    desired['settings'] = {'history': True, 'notify': True}
    desired['group_id'] = payload['group_id']
    ServiceCommand.create(
        command_id=str(uuid4()), command_type='portscanner.assignment.apply',
        target_service='portscanner', routing_key='portscanner.assignment.apply',
        assignment_id=payload['assignment_id'], revision=1, payload=json.dumps(desired),
    )
    ServiceAssignment.update(revision=2, desired_state='stopped').execute()
    assert process_event(payload).created
    assert PortScannerHistory.select().count() == 2
    assert PortScannerPorts.select().count() == 0
    assert ServiceNotification.select().count() == 1
    with pytest.raises(ValueError, match='target does not match'):
        process_event(dict(payload, group_id=payload['group_id'] + 1, event_id=str(uuid4())))


def test_checker_retry_after_diagnostic_purge_does_not_duplicate_history_or_delivery():
    payload = status_event(notify=True)
    assert process_event(payload).created
    ServiceEvent.delete().execute()
    assert not process_event(payload).created
    assert not process_event(dict(payload, event_id=str(uuid4()))).created
    assert Alerts.select().count() == ServiceNotification.select().count() == 1


def test_no_change_scans_do_not_grow_history_or_diagnostics():
    payload = portscanner_event(ports=[], opened=[], closed=[])
    assignment(payload, history=True, notify=True)
    for sequence in range(1, 11):
        assert process_event(dict(payload, sequence=sequence, event_id=str(uuid4()))).created
    assert ServiceEventPosition.select().count() == 1
    assert PortScannerHistory.select().count() == ServiceEvent.select().count() == 0
    assert ServiceNotification.select().count() == 0


def test_real_routing_propagates_channel_failure_to_outbox(monkeypatch):
    payload = portscanner_event()
    assignment(payload, history=True, notify=True)
    process_event(payload)
    from app.modules.tools import alerting
    calls, logs = [], []

    def failed_socket(*_args):
        raise RuntimeError('https://example.test/secret-token')

    monkeypatch.setattr(alerting, 'publish_socket_notification', failed_socket)
    monkeypatch.setattr(alerting, 'telegram_send_mess', lambda *args, **kwargs: calls.append('telegram'))
    monkeypatch.setattr(alerting, 'slack_send_mess', lambda *args, **kwargs: calls.append('slack'))
    monkeypatch.setattr(alerting.roxywi_common, 'logging', lambda *args, **kwargs: logs.append(str(args)))
    assert deliver_pending_notifications() == 0
    failed = ServiceNotification.get()
    assert failed.status == 'failed'
    assert failed.attempts == 1
    assert calls == ['telegram', 'slack']
    assert 'secret-token' not in failed.last_error
    assert 'secret-token' not in str(logs)
    monkeypatch.setattr(alerting, 'publish_socket_notification', lambda *args: None)
    assert deliver_pending_notifications() == 0
    assert ServiceNotification.get().attempts == 1
    ServiceNotification.update(updated_at=utc_now() - timedelta(seconds=31)).execute()
    assert deliver_pending_notifications() == 1
    assert ServiceNotification.get().status == 'delivered'


def test_web_bootstrap_does_not_leave_an_unowned_database_connection(tmp_path):
    result = subprocess.run(
        [sys.executable, '-c',
         'import app; from app.modules.db.db_model import BaseModel; '
         'assert BaseModel._meta.database.is_closed()'],
        env=dict(os.environ, ROXYWI_DB_PATH=str(tmp_path / 'bootstrap.db'), ROXYWI_PROCESS_ROLE='web'),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
