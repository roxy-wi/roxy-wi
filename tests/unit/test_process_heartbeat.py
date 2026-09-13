from datetime import datetime

from app.modules import process_heartbeat


def test_process_heartbeat_records_running_and_stopped(monkeypatch):
    payloads = []
    closes = []
    monkeypatch.setattr(process_heartbeat.socket, 'gethostname', lambda: 'roxy-1')
    monkeypatch.setattr(process_heartbeat, 'record_worker_heartbeat', payloads.append)
    monkeypatch.setattr(process_heartbeat, 'close_database_connection', lambda: closes.append(True))
    monkeypatch.setattr(process_heartbeat, 'get_service_version', lambda: '9.0.0')

    reporter = process_heartbeat.ProcessHeartbeat(
        'roxy-wi-scheduler',
        interval_seconds=5,
        ttl_seconds=30,
    )
    reporter.start()
    reporter.stop()

    assert [payload['status'] for payload in payloads] == ['running', 'stopped']
    assert payloads[0]['worker_id'] == 'roxy-wi-scheduler:roxy-1'
    assert payloads[0]['version'] == '9.0.0'
    assert payloads[0]['metadata'] == {'kind': 'roxy-wi-process'}
    assert isinstance(payloads[0]['heartbeat_at'], datetime)
    assert payloads[0]['expires_at'] > payloads[0]['heartbeat_at']
    assert payloads[1]['expires_at'] == payloads[1]['heartbeat_at']
    assert len(closes) == 2


def test_unknown_process_role_does_not_start_a_reporter(monkeypatch):
    monkeypatch.setenv('ROXYWI_PROCESS_ROLE', 'migrate')
    monkeypatch.setattr(process_heartbeat, '_process_heartbeat', None)

    assert process_heartbeat.start_configured_process_heartbeat() is None


def test_process_health_can_be_marked_degraded(monkeypatch):
    payloads = []
    monkeypatch.setattr(process_heartbeat, 'record_worker_heartbeat', payloads.append)
    monkeypatch.setattr(process_heartbeat, 'close_database_connection', lambda: None)

    reporter = process_heartbeat.ProcessHeartbeat(
        'roxy-wi-service-events',
        interval_seconds=5,
        ttl_seconds=30,
    )
    reporter.set_status('degraded', last_error='RabbitMQ unavailable')

    assert payloads[-1]['status'] == 'degraded'
    assert payloads[-1]['metadata'] == {
        'kind': 'roxy-wi-process',
        'last_error': 'RabbitMQ unavailable',
    }
