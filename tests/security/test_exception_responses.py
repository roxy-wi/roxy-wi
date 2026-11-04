"""Client errors must not serialize internal exception messages or causes."""
import inspect
from types import SimpleNamespace

import pytest
from flask import g

from app.modules.config import runtime
from app.modules.roxywi import error_handler
from app.modules.roxywi import nettools
from app.modules.server import command
from app.modules.roxywi.exception import (
    RoxywiInputError, RoxywiValidationError, RoxywiResourceNotFound,
)
from app.routes.admin import oidc_routes
from app.routes.logs import routes as log_routes
from app.routes.runtime import routes as runtime_routes
from app.views.service import haproxy_lists_views
from app.views.service import views as service_views


pytestmark = pytest.mark.security
PRIVATE = 'password=private-token; SELECT secret FROM users; /srv/private/config.py'


def fail(*_args, **_kwargs):
    try:
        raise OSError(PRIVATE)
    except OSError as cause:
        raise RuntimeError(PRIVATE) from cause


@pytest.fixture
def safe_logs(monkeypatch):
    records = []
    monkeypatch.setattr(error_handler.logger, 'error', lambda *args, **kwargs: records.append((args, kwargs)))
    yield records
    assert PRIVATE not in repr(records)
    assert all('exc' not in fields and 'exception' not in fields for _, fields in records)


@pytest.mark.parametrize('exception_type', (RuntimeError, ValueError, OSError, RoxywiValidationError))
def test_message_boundary_does_not_trust_generic_or_domain_exception_text(exception_type, safe_logs):
    assert PRIVATE not in error_handler.safe_error_message(exception_type(PRIVATE))
    assert safe_logs


def test_deliberate_input_error_preserves_message_and_value_error_contract(safe_logs):
    error = RoxywiInputError('Select a .cfg file inside the HAProxy directory')
    assert isinstance(error, ValueError)
    assert error_handler.safe_error_message(error) == error.public_message
    assert not safe_logs


@pytest.mark.parametrize(('function', 'args'), (
    (nettools.telnet_from_server, ('localhost', '192.0.2.10', 443)),
    (nettools.nslookup_from_server, ('localhost', 'example.test', 'A')),
))
def test_local_command_failure_does_not_escape_through_stderr(monkeypatch, safe_logs, function, args):
    def cannot_start(*_args, **_kwargs):
        raise OSError(PRIVATE)
    monkeypatch.setattr(command.subprocess, 'run', cannot_start)
    result = function(*args)
    assert result.startswith('error:')
    assert 'Cannot start the local command' in result
    assert PRIVATE not in result
    assert safe_logs


@pytest.mark.parametrize(('route', 'operation', 'args'), (
    ('show_backends', 'show_backends', ('192.0.2.10',)),
    ('get_lists', 'list_of_lists', ('192.0.2.10',)),
    ('get_list', 'show_lists', ('192.0.2.10', 1, 'white', 'allow.lst')),
))
def test_runtime_route_failure_and_success_contract(app, monkeypatch, safe_logs, route, operation, args):
    function = inspect.unwrap(getattr(runtime_routes, route))
    monkeypatch.setattr(runtime, operation, fail)
    with app.test_request_context('/runtimeapi'):
        response = app.make_response(function(*args))
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'error: Internal server error'
    assert safe_logs

    monkeypatch.setattr(runtime, operation, lambda *_args, **_kwargs: 'runtime result')
    with app.test_request_context('/runtimeapi'):
        response = app.make_response(function(*args))
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'runtime result'


def test_list_read_failure_is_redacted_before_json_serialization(app, monkeypatch, safe_logs, tmp_path):
    from app.modules.service import haproxy_lists
    from app.scripts import haproxy_lists as list_files

    def unreadable(*_args):
        raise OSError(PRIVATE)
    monkeypatch.setattr(haproxy_lists, 'local_path', lambda *_args: tmp_path / 'allow.lst')
    monkeypatch.setattr(list_files, 'read_file', unreadable)
    monkeypatch.setattr(haproxy_lists_views.SupportClass, 'return_group_id', lambda _query: 1)
    with app.test_request_context('/service/haproxy/list'):
        response = inspect.unwrap(haproxy_lists_views.HaproxyListView.get)(
            haproxy_lists_views.HaproxyListView(), 'haproxy', 'allow.lst', 'white', SimpleNamespace(group_id=1),
        )
        response = app.make_response(response)
    assert PRIVATE not in response.get_data(as_text=True)
    assert response.status_code == 500
    assert response.get_json()['error'] == 'Cannot update HAProxy list: Internal server error'
    assert safe_logs


@pytest.mark.parametrize('service', ('haproxy', 'nginx', 'apache'))
def test_service_status_does_not_publish_exception_in_result_data(app, monkeypatch, safe_logs, service):
    server = SimpleNamespace(ip='192.0.2.10', **{
        f'{service}_active': 1, f'{service}_alert': 1, f'{service}_metrics': 1,
    })
    from app.modules.service import managed_runtime
    server.server_id = 1
    monkeypatch.setattr(managed_runtime, 'managed_server', lambda _: server)
    monkeypatch.setattr(service_views.SupportClass, 'return_server_ip_or_id', lambda *_args: 1)
    monkeypatch.setattr(service_views.server_sql, 'get_server_with_group', lambda *_args: server)
    monkeypatch.setattr(service_views.sql, 'get_setting', lambda *_args: 1999)
    monkeypatch.setattr(service_views.service_sql, 'select_service_setting', lambda *_args: '0')
    monkeypatch.setattr(service_views.server_mod, 'ssh_command', fail)
    monkeypatch.setattr(service_views.requests, 'get', fail)
    with app.test_request_context(f'/service/{service}/1/status'):
        g.user_params = {'group_id': 1}
        response = app.make_response(service_views.ServiceView().get(service, 1))
    assert 'Internal server error' in response.get_json()['error']
    assert PRIVATE not in response.get_data(as_text=True)
    assert safe_logs


@pytest.mark.parametrize(('values', 'expected'), (
    ({'relative': '60', 'limit': '1001'}, 'The row limit must be between 1 and 1000'),
    ({'relative': '60', 'limit': PRIVATE}, 'Invalid value provided'),
    ({'from': PRIVATE, 'to': '2026-10-21T00:00:00Z'}, 'Invalid value provided'),
))
def test_log_validation_retains_actionable_messages_but_hides_conversion_errors(app, monkeypatch, safe_logs, values, expected):
    monkeypatch.setattr(log_routes.roxywi_auth, 'page_for_admin', lambda **_kwargs: None)
    monkeypatch.setattr(log_routes.roxywi_auth, 'is_admin', lambda: True)
    monkeypatch.setattr(log_routes.roxywi_common, 'check_user_group_for_flask', lambda: True)
    with app.test_request_context('/logs/internal/query', method='POST', data=values):
        g.user_params = {'user_id': 1, 'group_id': 1, 'role': 1}
        response, status = inspect.unwrap(log_routes.query_internal_logs)()
    assert status == 400
    assert response.get_json() == {'error': expected}
    assert PRIVATE not in response.get_data(as_text=True)


@pytest.mark.parametrize(('error', 'expected', 'status'), (
    (RoxywiValidationError('OIDC target group does not exist'), 'OIDC target group does not exist', 400),
    (RoxywiResourceNotFound('OIDC provider was not found'), 'OIDC provider was not found', 404),
))
def test_oidc_uses_public_domain_message_not_exception_string(app, monkeypatch, error, expected, status):
    # args/__str__ may carry internal diagnostics separately from the public contract.
    error.args = (PRIVATE,)
    monkeypatch.setattr(oidc_routes.roxywi_auth, 'page_for_admin', lambda: None)
    def reject(*_args):
        raise error
    monkeypatch.setattr(oidc_routes.oidc_sql, 'create_mapping', reject)
    with app.test_request_context('/admin/oidc/providers/1/mappings', method='POST', json={
        'external_group': 'staff', 'group_id': 1, 'role_id': 4,
    }):
        response, actual_status = inspect.unwrap(oidc_routes.create_oidc_mapping)(1)
    assert actual_status == status
    assert response.get_json() == {'status': 'failed', 'error': expected}
    assert PRIVATE not in response.get_data(as_text=True)
