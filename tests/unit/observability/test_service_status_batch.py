from pathlib import Path

from flask import jsonify

from app.routes.service.routes import _service_status_payload
import app.routes.config.routes as config_routes
import app.modules.service.common as service_common


def test_batch_status_normalizes_json_response(app):
    with app.app_context():
        payload = _service_status_payload(jsonify({'server_id': 7, 'status': 'running'}))

    assert payload == {'server_id': 7, 'status': 'running', 'http_status': 200}


def test_batch_status_preserves_error_payload_and_http_status(app):
    with app.app_context():
        payload = _service_status_payload((jsonify({'error': 'SSH unavailable'}), 503))

    assert payload['error'] == 'SSH unavailable'
    assert payload['status'] == 'failed'
    assert payload['http_status'] == 503


def test_batch_status_rejects_non_mapping_results():
    payload = _service_status_payload(('unexpected response', 500))

    assert payload == {
        'status': 'failed',
        'error': 'unexpected response',
        'http_status': 500,
    }


def test_batch_status_route_documents_and_limits_input():
    routes = (Path(__file__).resolve().parents[3] / 'app/routes/service/routes.py').read_text(encoding='utf-8')

    assert "@bp.post('/<service>/statuses')" in routes
    assert "len(server_ids) > 100" in routes
    assert "server_ids must contain integer IDs" in routes
    assert "server_id not in normalized_ids" in routes


def test_last_edit_ssh_failure_is_a_local_card_result(monkeypatch):
    monkeypatch.setattr(service_common.sql, 'get_setting', lambda _name: '/etc/haproxy/haproxy.cfg')
    observed = {}

    def timeout(_server_ip, _command, **kwargs):
        observed.update(kwargs)
        raise RuntimeError('connection timed out')

    monkeypatch.setattr(service_common.server_mod, 'ssh_command', timeout)

    result = service_common.get_overview_last_edit('192.0.2.15', 'haproxy')

    assert result.startswith('error: Cannot get last date')
    assert 'connection timed out' in result
    assert observed == {'connect_timeout': 10, 'banner_timeout': 10}


def test_service_status_ssh_checks_use_bounded_connection_timeouts():
    views = (Path(__file__).resolve().parents[3] / 'app/views/service/views.py').read_text(encoding='utf-8')

    assert views.count('connect_timeout=10, banner_timeout=10') == 4


def test_candidate_validation_uses_a_temporary_file_and_removes_it(app, monkeypatch):
    observed = {}
    monkeypatch.setattr(
        config_routes.SupportClass,
        'return_server_ip_or_id',
        lambda self, server_id: '192.0.2.44',
    )

    def fake_validate(server_ip, candidate_path, service, config_file_name=None):
        path = Path(candidate_path)
        observed.update(
            server_ip=server_ip,
            candidate_path=path,
            contents=path.read_text(encoding='utf-8'),
            service=service,
            file_path=config_file_name,
        )
        assert path.exists()
        return 'Configuration is valid'

    monkeypatch.setattr(config_routes.config_mod, 'validate_candidate_config', fake_validate)
    raw_view = config_routes.validate_candidate.__wrapped__
    with app.test_request_context(json={'config': 'global\n  daemon\n', 'file_path': '/etc/haproxy/haproxy.cfg'}):
        response = raw_view('haproxy', '44')
        payload = response.get_json()

    assert payload == {'status': 'success', 'data': 'Configuration is valid'}
    assert observed['server_ip'] == '192.0.2.44'
    assert observed['contents'] == 'global\n  daemon\n'
    assert observed['service'] == 'haproxy'
    assert observed['file_path'] == '/etc/haproxy/haproxy.cfg'
    assert not observed['candidate_path'].exists()


def test_candidate_validation_rejects_missing_and_oversized_configs(app):
    raw_view = config_routes.validate_candidate.__wrapped__
    with app.test_request_context(json={'file_path': '/etc/haproxy/haproxy.cfg'}):
        response, status = raw_view('haproxy', '44')
    assert status == 400
    assert response.get_json()['status'] == 'failed'

    with app.test_request_context(json={'config': 'x' * (10 * 1024 * 1024 + 1)}):
        response, status = raw_view('haproxy', '44')
    assert status == 413
    assert response.get_json()['error'] == 'config is too large'
