import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

import roxy_wi_health as health
from app.modules import process_heartbeat


@pytest.fixture
def local_health(tmp_path, monkeypatch):
    monkeypatch.setattr(health, 'health_directory', lambda: tmp_path)
    monkeypatch.setattr(health, '_health', None)
    return tmp_path


def ready_worker(role='operations'):
    worker = health.LocalProcessHealth(role)
    worker.pulse(rabbitmq=True)
    worker.dependency('database', True)
    worker.write()
    return worker


@pytest.mark.parametrize('role', sorted(health.WORKER_ROLES))
@pytest.mark.parametrize('dependency', ['database', 'rabbitmq'])
def test_dependency_outage_and_recovery_do_not_fail_liveness(local_health, role, dependency):
    worker = ready_worker(role)
    assert health.probe('ready', role) == (True, 'ready')

    worker.dependency(dependency, False)
    worker.write()
    assert health.probe('live', role) == (True, 'live')
    assert health.probe('ready', role) == (False, f'{dependency} unavailable or check expired')

    worker.dependency(dependency, True)
    worker.write()
    assert health.probe('ready', role) == (True, 'ready')


def test_stale_dependency_sample_is_not_kept_green_by_local_writer(local_health, monkeypatch):
    clock = SimpleNamespace(monotonic=lambda: 1000)
    monkeypatch.setattr(health, 'time', clock)
    worker = ready_worker()
    clock.monotonic = lambda: 1080
    worker.pulse(rabbitmq=True)
    worker.write()

    assert health.probe('live')[0] is True
    assert health.probe('ready') == (False, 'database unavailable or check expired')


def test_background_writer_cannot_hide_stuck_working_loop(local_health, monkeypatch):
    clock = SimpleNamespace(monotonic=lambda: 1000)
    monkeypatch.setattr(health, 'time', clock)
    worker = ready_worker()
    clock.monotonic = lambda: 1121
    worker.dependency('database', True)
    worker.write()

    assert health.probe('live') == (False, 'worker loop is not progressing')
    assert health.probe('ready')[0] is False


def test_writer_failure_expires_local_heartbeat(local_health, monkeypatch):
    clock = SimpleNamespace(monotonic=lambda: 1000)
    monkeypatch.setattr(health, 'time', clock)
    ready_worker()
    clock.monotonic = lambda: 1016

    assert health.probe('live') == (False, 'local heartbeat expired')


@pytest.mark.parametrize('status', ['starting', 'draining'])
def test_starting_and_draining_are_live_but_not_ready(local_health, status):
    worker = ready_worker()
    worker.status(status)
    worker.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False
    worker.pulse(rabbitmq=True)
    worker.write()
    if status == 'draining':
        assert health.probe('ready')[0] is False


def test_stopped_process_fails_both_checks(local_health):
    worker = ready_worker()
    worker.status('stopped')
    worker.write()
    assert health.probe('live')[0] is False
    assert health.probe('ready')[0] is False
    worker.stop()
    assert not worker.path.exists()


def test_pid_reuse_does_not_reuse_previous_health(local_health):
    worker = ready_worker()
    snapshot = json.loads(worker.path.read_text())
    snapshot['created_at'] -= 1
    worker.path.write_text(json.dumps(snapshot))
    assert health.probe('live')[0] is False


def test_process_must_exist_in_local_namespace(local_health, monkeypatch):
    ready_worker()
    monkeypatch.setattr(health, '_same_process', lambda _: False)
    assert health.probe('live')[0] is False


def test_role_selection_does_not_use_another_worker(local_health):
    ready_worker('operations')
    assert health.probe('live', 'scheduler')[0] is False
    ready_worker('scheduler')
    assert health.probe('ready')[0] is False  # Ambiguous on a package host.
    assert health.probe('ready', 'operations')[0] is True
    assert health.probe('ready', 'scheduler')[0] is True


def test_corrupt_sample_fails_closed_without_exposing_contents(local_health):
    (local_health / 'operations-1.json').write_text('secret=not-json')
    healthy, detail = health.probe()
    assert healthy is False
    assert 'secret' not in detail


def test_real_db_heartbeat_controls_database_readiness(local_health, monkeypatch):
    worker = ready_worker()
    monkeypatch.setattr(health, '_health', worker)
    monkeypatch.setattr(process_heartbeat, 'close_database_connection', lambda: None)
    reporter = process_heartbeat.ProcessHeartbeat('roxy-wi-operations')

    def unavailable(_):
        raise OSError('Database is unavailable')

    monkeypatch.setattr(process_heartbeat, 'record_worker_heartbeat', unavailable)
    reporter._record()
    worker.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False

    monkeypatch.setattr(process_heartbeat, 'record_worker_heartbeat', lambda _: None)
    reporter._record()
    worker.write()
    assert health.probe('ready')[0] is True


def test_blocked_db_reporter_does_not_block_local_health(local_health, monkeypatch):
    worker = ready_worker()
    monkeypatch.setattr(health, '_health', worker)
    entered = threading.Event()
    release = threading.Event()

    def record(_):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(process_heartbeat, 'record_worker_heartbeat', record)
    monkeypatch.setattr(process_heartbeat, 'close_database_connection', lambda: None)
    reporter = process_heartbeat.ProcessHeartbeat('roxy-wi-operations')
    thread = threading.Thread(target=reporter._record)
    thread.start()
    try:
        assert entered.wait(2)
        worker.pulse(rabbitmq=True)
        worker.write()
        assert health.probe('live')[0] is True
    finally:
        release.set()
        thread.join(timeout=5)


def test_scheduler_broker_probe_authenticates_and_recovers(local_health, monkeypatch):
    import pika
    from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings

    worker = ready_worker('scheduler')
    monkeypatch.setattr(health, '_health', worker)
    monkeypatch.setattr(process_heartbeat, 'close_database_connection', lambda: None)
    settings = RabbitConnectionSettings('broker', 5672, '/test', 'tester', 'test-secret')
    monkeypatch.setattr(RabbitConnectionSettings, 'load', lambda: settings)
    reporter = process_heartbeat.ProcessHeartbeat('roxy-wi-scheduler')
    calls = []

    def unavailable(parameters):
        assert parameters.virtual_host == '/test'
        assert parameters.stack_timeout == 3
        assert parameters.credentials.username == 'tester'
        raise pika.exceptions.AMQPConnectionError()

    monkeypatch.setattr(pika, 'BlockingConnection', unavailable)
    reporter._check_scheduler_broker()
    worker.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False
    monkeypatch.setattr(pika, 'BlockingConnection', lambda _: SimpleNamespace(
        channel=lambda: calls.append('channel'), close=lambda: calls.append('close'),
    ))
    reporter._check_scheduler_broker()
    worker.write()
    assert health.probe('ready')[0] is True
    assert calls == ['channel', 'close']


def test_cli_does_not_import_application_or_initialize_database(local_health):
    ready_worker()
    code = (
        'import sys; from pathlib import Path; import roxy_wi_health, roxy_wi; '
        'probe_path = Path(sys.argv[1]); roxy_wi_health.health_directory = lambda: probe_path; '
        'sys.argv = ["roxy_wi.py", "healthcheck", "--role", "operations"]; '
        '\ntry: roxy_wi.main()\nfinally: assert "app" not in sys.modules'
    )
    env = {**os.environ, 'ROXYWI_CONFIG_FILE': str(local_health / 'missing.cfg'),
           'ROXYWI_PROCESS_ROLE': 'scheduler', 'ROXYWI_SCHEDULER_ENABLED': '1'}
    result = subprocess.run([sys.executable, '-c', code, str(local_health)],
                            capture_output=True, text=True, env=env, timeout=10,
                            cwd=Path(__file__).resolve().parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ready'
    assert not (local_health / 'missing.cfg').exists()


def test_web_probes_use_http_custom_bind_and_ignore_proxy(local_health, monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            ready = self.path == '/health/live'
            self.send_response(200 if ready else 503)
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok' if ready else 'unavailable'}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv('ROXYWI_WEB_BIND', f'0.0.0.0:{server.server_port}')
        monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
        monkeypatch.setenv('NO_PROXY', '')
        health.register_web()
        assert health.probe('live', 'web')[0] is True
        assert health.probe('ready', 'web')[0] is False
        assert calls == ['/health/live', '/health/ready']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_web_registration_does_not_restrict_existing_gunicorn_binds(local_health, monkeypatch):
    monkeypatch.setenv('ROXYWI_WEB_BIND', 'unix:/tmp/roxy-wi.sock')
    health.register_web()
    snapshot = json.loads(next(local_health.glob('web-*.json')).read_text())
    assert snapshot['bind'] == 'unix:/tmp/roxy-wi.sock'


def test_event_consumer_pulses_its_actual_idle_loop(local_health, monkeypatch):
    from app.modules.integrations import rabbitmq_consumer as events

    worker = ready_worker('service-events')
    monkeypatch.setattr(health, '_health', worker)
    timers = []
    channel = SimpleNamespace(basic_consume=lambda **_: None)
    connection = SimpleNamespace(
        is_open=True, channel=lambda: channel,
        call_later=lambda delay, callback: timers.append((delay, callback)),
        close=lambda: None,
    )

    def consume():
        assert timers[0][0] == 5
        timers.pop()[1]()
        worker.write()
        assert health.probe('ready', 'service-events')[0] is True
        assert len(timers) == 1

    channel.start_consuming = consume
    monkeypatch.setattr(events.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(events, 'declare_topology', lambda *_: None)
    monkeypatch.setattr(events, 'deliver_pending_notifications', lambda **_: None)
    monkeypatch.setattr(events, 'set_process_heartbeat_status', lambda *_: None)
    consumer = events.ServiceEventConsumer(events.RabbitConsumerSettings('broker', 5672, '/', 'test', 'test'))
    consumer.consume_once()
    worker.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False  # Connection was closed.


def test_event_database_failure_marks_unready_and_requeues(local_health, monkeypatch):
    from app.modules.integrations import rabbitmq_consumer as events

    worker = ready_worker('service-events')
    monkeypatch.setattr(health, '_health', worker)
    nacks = []

    def unavailable(_):
        raise OSError('database unavailable')

    monkeypatch.setattr(events, 'process_event', unavailable)
    consumer = events.ServiceEventConsumer(events.RabbitConsumerSettings('broker', 5672, '/', 'test', 'test'))
    consumer._message(SimpleNamespace(basic_nack=lambda **kw: nacks.append(kw)),
                      SimpleNamespace(delivery_tag=1), None, b'{}')
    worker.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False
    assert nacks == [{'delivery_tag': 1, 'requeue': True}]


def test_long_operation_keeps_loop_live(local_health, monkeypatch):
    from app.modules.operations import worker as operations
    from app.modules.operations.queue import OperationQueueSettings

    clock_value = [1000]
    monkeypatch.setattr(health, 'time', SimpleNamespace(monotonic=lambda: clock_value[0]))
    local_worker = ready_worker()
    monkeypatch.setattr(health, '_health', local_worker)
    worker = operations.OperationWorker(OperationQueueSettings('broker', 5672, '/', 'test', 'test'))
    release = threading.Event()
    running = threading.Event()
    deliveries = []
    checks = []
    operation_threads = []

    def execute(*_args):
        operation_threads.append(threading.current_thread())
        running.set()
        assert release.wait(5)
        return 'completed'

    def basic_get(**_kwargs):
        if deliveries:
            worker._stop_event.set()
            return None, None, None
        deliveries.append(True)
        return SimpleNamespace(delivery_tag=1), None, b'{"operation_id":"test", "task_id":1}'

    def data_events(**_kwargs):
        if worker._stop_event.is_set():
            return
        assert running.wait(2)
        clock_value[0] += 45
        local_worker.dependency('database', True)
        local_worker.write()
        checks.append(health.probe('live')[0])
        if len(checks) >= 3:
            release.set()
            # Yield to the real operation thread before the next consume pass.
            operation_threads[0].join(timeout=2)

    channel = SimpleNamespace(basic_get=basic_get, basic_ack=lambda *_: None)
    connection = SimpleNamespace(is_open=True, channel=lambda: channel,
                                 close=lambda: None, process_data_events=data_events)
    monkeypatch.setattr(operations.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(operations, 'declare_operation_topology', lambda *_: None)
    monkeypatch.setattr(operations, 'set_process_heartbeat_status', lambda *_: None)
    monkeypatch.setattr(operations, 'claim_operation', lambda *_: (True, 'running'))
    monkeypatch.setattr(operations, 'execute_operation', execute)
    try:
        worker.consume_once()
    finally:
        release.set()
    assert len(checks) >= 3
    assert all(checks)
    assert clock_value[0] >= 1135  # Longer than the 120s loop timeout.


@pytest.mark.parametrize('role', ['operations', 'service-events'])
def test_consumer_shutdown_marks_draining(local_health, monkeypatch, role):
    from app.modules.integrations.rabbitmq_consumer import RabbitConsumerSettings, ServiceEventConsumer
    from app.modules.operations.queue import OperationQueueSettings
    from app.modules.operations.worker import OperationWorker

    reporter = ready_worker(role)
    monkeypatch.setattr(health, '_health', reporter)
    if role == 'operations':
        worker = OperationWorker(OperationQueueSettings('broker', 5672, '/', 'test', 'test'))
    else:
        worker = ServiceEventConsumer(RabbitConsumerSettings('broker', 5672, '/', 'test', 'test'))
    worker.stop()
    reporter.write()
    assert health.probe('live')[0] is True
    assert health.probe('ready')[0] is False
