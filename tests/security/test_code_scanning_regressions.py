import inspect
from pathlib import Path

import pytest
from flask import g

import app.api.routes.change_routes as public_change_routes
import app.routes.change.routes as change_routes
import app.routes.service.routes as service_routes
from app.modules.roxywi.exception import RoxywiValidationError


@pytest.mark.security
def test_batch_status_does_not_return_internal_exception_details(app, monkeypatch):
    secret = 'database password: do-not-return-this'
    log_messages = []

    class FailingServiceView:
        def get(self, _service, _server_id):
            raise RuntimeError(secret)

    monkeypatch.setattr(service_routes, 'ServiceView', FailingServiceView)
    monkeypatch.setattr(
        service_routes.roxywi_common,
        'logging',
        lambda _server, message, **_kwargs: log_messages.append(message),
    )

    with app.test_request_context('/service/haproxy/statuses', method='POST', json={'server_ids': [7]}):
        response = inspect.unwrap(service_routes.service_statuses)('haproxy')
        payload = response.get_json()

    assert payload['data'][0]['error'] == 'Cannot get service status'
    assert secret not in str(payload)
    assert secret in log_messages[0]


@pytest.mark.security
@pytest.mark.parametrize('route_module', (change_routes, public_change_routes))
def test_change_center_error_responses_hide_untrusted_exception_messages(app, monkeypatch, route_module):
    secret = 'SQL: SELECT credential_secret FROM users'
    monkeypatch.setattr(route_module.roxywi_common, 'logging', lambda *_args, **_kwargs: None)

    with app.test_request_context('/changes/api'):
        response, status = route_module._error_response(ValueError(secret))

    assert status == 400
    assert response.get_json() == {'status': 'failed', 'error': 'Invalid request'}
    assert secret not in response.get_data(as_text=True)


@pytest.mark.security
@pytest.mark.parametrize('route_module', (change_routes, public_change_routes))
def test_change_center_keeps_controlled_domain_error_messages(app, route_module):
    with app.test_request_context('/changes/api'):
        response, status = route_module._error_response(
            RoxywiValidationError('Deployment check failed')
        )

    assert status == 400
    assert response.get_json()['error'] == 'Deployment check failed'


@pytest.mark.security
def test_config_file_redirect_encodes_selected_filename():
    template_path = (
        Path(__file__).resolve().parents[2]
        / 'app'
        / 'templates'
        / 'ajax'
        / 'show_configs_files.html'
    )
    source = template_path.read_text(encoding='utf-8')

    assert "+ encodeURIComponent(selectedFile)" in source
    assert "+ selectedFile);" not in source
