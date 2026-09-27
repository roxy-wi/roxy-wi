import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from flask_apscheduler import APScheduler

from app.modules.integrations import rabbitmq_consumer as events
from app.modules.operations import worker as operations
from app.modules.operations.queue import OperationQueueSettings
from app.modules import process_heartbeat
import roxy_wi
import scheduler_runner


def operation_worker():
    return operations.OperationWorker(OperationQueueSettings('broker', 5672, '/', 'test', 'test'))


def event_worker():
    return events.ServiceEventConsumer(events.RabbitConsumerSettings('broker', 5672, '/', 'test', 'test'))


@pytest.mark.parametrize('module,factory', [(operations, operation_worker), (events, event_worker)])
def test_signal_handler_only_requests_stop(monkeypatch, module, factory):
    worker = factory()
    def forbidden(*args):
        pytest.fail('Signal handler entered a health, database or RabbitMQ API')
    monkeypatch.setattr(module.local_health, 'draining', forbidden)
    monkeypatch.setattr(module, 'set_process_heartbeat_status', forbidden)
    worker._connection = SimpleNamespace(is_open=True, add_callback_threadsafe=forbidden)
    worker.stop()
    worker.stop()
    assert worker._stop_event.is_set()


def test_operations_return_delivery_received_during_stop(monkeypatch):
    worker = operation_worker()
    calls = []
    def get(**kwargs):
        worker.stop()
        return SimpleNamespace(delivery_tag=12), None, b'{"task_id":1,"operation_id":"test"}'
    channel = SimpleNamespace(basic_get=get, basic_nack=lambda tag, **kw: calls.append(('nack', tag, kw)))
    connection = SimpleNamespace(is_open=True, channel=lambda: channel, close=lambda: calls.append('closed'))
    monkeypatch.setattr(operations.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(operations, 'declare_operation_topology', lambda *_: None)
    monkeypatch.setattr(operations, 'set_process_heartbeat_status', calls.append)
    monkeypatch.setattr(operations, 'claim_operation', lambda *_: pytest.fail('Claimed new work while stopping'))
    worker.consume_once()
    assert calls == ['running', 'draining', ('nack', 12, {'requeue': True}), 'closed']


def test_operations_finish_claimed_task_without_taking_another(monkeypatch):
    worker = operation_worker()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def execute(*args):
        started.set()
        assert release.wait(5)
        calls.append('finished')
        finished.set()
        return 'completed'
    def get(**kwargs):
        calls.append('get')
        assert calls.count('get') == 1
        return SimpleNamespace(delivery_tag=1), None, b'{"task_id":1,"operation_id":"test"}'
    def pump(**kwargs):
        assert started.wait(2)
        worker.stop()
        # A second iteration observes the signal before releasing the task.
        if worker._draining:
            assert not finished.is_set()
            release.set()
            assert finished.wait(2)
    channel = SimpleNamespace(basic_get=get, basic_ack=lambda _: calls.append('ack'))
    connection = SimpleNamespace(is_open=True, channel=lambda: channel, process_data_events=pump,
                                 close=lambda: calls.append('closed'))
    monkeypatch.setattr(operations.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(operations, 'declare_operation_topology', lambda *_: None)
    monkeypatch.setattr(operations, 'set_process_heartbeat_status', calls.append)
    monkeypatch.setattr(operations, 'claim_operation', lambda *_: (True, 'running'))
    monkeypatch.setattr(operations, 'execute_operation', execute)
    try:
        worker.consume_once()
    finally:
        release.set()
    assert calls == ['running', 'get', 'ack', 'draining', 'finished', 'closed']


def test_service_event_finishes_commit_and_ack_before_stopping(monkeypatch):
    worker = event_worker()
    calls = []
    def process(body):
        worker.stop()  # Signal during a database transaction.
        calls.append('committed')
        return SimpleNamespace(kind='test', created=True)
    monkeypatch.setattr(events, 'process_event', process)
    monkeypatch.setattr(events, 'close_database_connection', lambda: calls.append('db-closed'))
    monkeypatch.setattr(events, 'deliver_pending_notifications', lambda **_: pytest.fail('Started more work after SIGTERM'))
    monkeypatch.setattr(events, 'set_process_heartbeat_status', calls.append)
    channel = SimpleNamespace(basic_ack=lambda **_: calls.append('ack'), basic_nack=lambda **_: calls.append('nack'))
    worker._message(channel, SimpleNamespace(delivery_tag=1), None, b'{}')
    worker._message(channel, SimpleNamespace(delivery_tag=2), None, b'{}')
    assert calls == ['committed', 'db-closed', 'ack', 'draining', 'nack']


def test_idle_service_consumer_stops_via_its_pika_loop(monkeypatch):
    worker = event_worker()
    timers, calls = [], []
    def consume():
        worker.stop()
        timers.pop()[1]()
        assert not timers
    channel = SimpleNamespace(basic_consume=lambda **_: None, start_consuming=consume,
                              stop_consuming=lambda: calls.append('cancel-consumer'))
    connection = SimpleNamespace(is_open=True, channel=lambda: channel,
        call_later=lambda delay, callback: timers.append((delay, callback)), close=lambda: calls.append('closed'))
    monkeypatch.setattr(events.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(events, 'declare_topology', lambda *_: None)
    monkeypatch.setattr(events, 'deliver_pending_notifications', lambda **_: None)
    monkeypatch.setattr(events, 'set_process_heartbeat_status', calls.append)
    worker.consume_once()
    assert calls == ['running', 'draining', 'cancel-consumer', 'closed']


def test_scheduler_waits_for_running_job_and_keeps_draining_loop_alive(monkeypatch):
    scheduler = APScheduler(scheduler=BackgroundScheduler())
    started, release, stop, draining = (threading.Event() for _ in range(4))
    calls, errors = [], []
    def job():
        started.set()
        assert release.wait(5)
        calls.append('finished')
    monkeypatch.setattr(process_heartbeat, 'set_process_heartbeat_status', lambda status: draining.set())
    monkeypatch.setattr(scheduler_runner.local_health, 'pulse', lambda: calls.append('pulse'))
    scheduler.add_job('blocking', job)
    scheduler.start()
    def run():
        try:
            scheduler_runner.run_scheduler(scheduler, stop)
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(2)
        stop.set()
        assert draining.wait(2)
        # Wait for the actual drain watchdog, without relying on a fixed sleep.
        thread.join(timeout=1.2)
        assert thread.is_alive()
        assert calls.count('pulse') >= 2
        release.set()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert calls[-1] == 'finished'
        assert not scheduler.running
        assert errors == []
    finally:
        stop.set()
        release.set()
        thread.join(timeout=3)
        if scheduler.running:
            scheduler.shutdown()


def test_scheduler_shutdown_failure_is_reported(monkeypatch):
    stop = threading.Event()
    stop.set()
    def fail(**_kwargs):
        raise RuntimeError('shutdown failed')
    scheduler = SimpleNamespace(running=True, scheduler=SimpleNamespace(add_executor=lambda *a, **kw: None),
        add_job=lambda **_: None, pause=lambda: None, shutdown=fail)
    monkeypatch.setattr(process_heartbeat, 'set_process_heartbeat_status', lambda _: None)
    with pytest.raises(RuntimeError, match='shutdown failed'):
        scheduler_runner.run_scheduler(scheduler, stop)


def test_web_forwards_configured_graceful_timeout(monkeypatch):
    monkeypatch.setattr(roxy_wi, 'os', SimpleNamespace(environ={'ROXYWI_WEB_GRACEFUL_TIMEOUT': '75'},
        execvp=lambda name, argv: captured.extend(argv)))
    monkeypatch.setattr(scheduler_runner.local_health, 'register_web', lambda: None)
    captured = []
    roxy_wi.run_web()
    assert captured[captured.index('--graceful-timeout') + 1] == '75'


def test_compose_and_helm_allow_roles_to_finish_work():
    root = Path(__file__).resolve().parents[2]
    for filename in ('docker-compose.yml', 'docker-compose.sqlite.yml'):
        manifest = yaml.safe_load((root / 'docker' / filename).read_text())
        for role, duration in [('web', '150s'), ('scheduler', '5m'), ('service-events', '5m'), ('operations', '30m')]:
            service = manifest['services'][role]
            assert service['init'] is True
            assert service['stop_grace_period'].endswith(':-' + duration + '}')
    values = yaml.safe_load((root / 'helm/roxy-wi/values.yaml').read_text())
    assert values['web']['terminationGracePeriodSeconds'] > values['web']['gunicorn']['gracefulTimeout']
    assert values['scheduler']['terminationGracePeriodSeconds'] == 300
    assert values['serviceEvents']['terminationGracePeriodSeconds'] == 300
    assert values['operations']['terminationGracePeriodSeconds'] == 1800
