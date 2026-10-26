import pytest
from pydantic import ValidationError

from app.modules.roxywi.class_models import (
    HaproxyStatsMaxconnRequest, HaproxyStatsServerQuery, HaproxyStatsServerRequest,
)


def payload(action='edit', value=None):
    return dict(action=action, row_key='row-key', pid=100, uptime=3600, revision='a' * 64,
                targets=['192.0.2.11'], value=value if action == 'delete' else value or {'address': '192.0.2.10', 'port': 80})


@pytest.mark.parametrize('action,value', [
    ('edit', {'address': '192.0.2.10', 'port': 1}),
    ('edit', {'address': '2001:db8::10', 'port': 65535}),
    ('add', {'name': 'new-server', 'address': '2001:db8::10', 'port': 443, 'check': False, 'check_port': 80}),
    ('delete', None),
])
def test_server_actions_keep_the_existing_wire_contract(action, value):
    body = payload(action, value)
    assert HaproxyStatsServerRequest.model_validate(body).model_dump(mode='json') == body


@pytest.mark.parametrize('field,value', [
    ('pid', True), ('pid', '100'), ('pid', 100.0), ('pid', 0),
    ('uptime', False), ('uptime', '3600'), ('uptime', -1),
    ('action', 'reload'), ('action', []), ('row_key', ''), ('row_key', 'x' * 2049),
    ('revision', 'a' * 63), ('revision', 'a' * 64 + '\n'),
    ('targets', '192.0.2.11'), ('targets', [123]), ('targets', None),
    ('value', None), ('value', []), ('unexpected', 'value'),
])
def test_server_request_rejects_invalid_types_ranges_and_extra_fields(field, value):
    with pytest.raises(ValidationError):
        HaproxyStatsServerRequest.model_validate({**payload(), field: value})


@pytest.mark.parametrize('value', [
    {'address': 3221225994, 'port': 80},
    {'address': True, 'port': 80},
    {'address': 'example.com', 'port': 80},
    {'address': 'fe80::1%eth0', 'port': 80},
    {'address': '192.0.2.10\nbackend bad', 'port': 80},
    {'address': '192.0.2.10', 'port': 0},
    {'address': '192.0.2.10', 'port': 65536},
    {'address': '192.0.2.10', 'port': True},
    {'address': '192.0.2.10', 'port': '80'},
    {'address': '192.0.2.10', 'port': 80.0},
    {'address': '192.0.2.10'},
    {'address': '192.0.2.10', 'port': 80, 'name': 'unexpected'},
])
def test_server_value_rejects_coercion_injection_and_wrong_fields(value):
    with pytest.raises(ValidationError):
        HaproxyStatsServerRequest.model_validate(payload(value=value))


@pytest.mark.parametrize('action,value', [
    ('add', {'address': '192.0.2.10', 'port': 80}),
    ('edit', {'name': 'new', 'address': '192.0.2.10', 'port': 80, 'check': True, 'check_port': 80}),
    ('delete', {'address': '192.0.2.10', 'port': 80}),
    ('add', {'name': 'bad\n', 'address': '192.0.2.10', 'port': 80, 'check': True, 'check_port': 80}),
    ('add', {'name': 'new', 'address': '192.0.2.10', 'port': 80, 'check': 1, 'check_port': 80}),
    ('add', {'name': 'new', 'address': '192.0.2.10', 'port': 80, 'check': True, 'check_port': '80'}),
])
def test_action_selects_its_own_value_schema(action, value):
    with pytest.raises(ValidationError):
        HaproxyStatsServerRequest.model_validate(payload(action, value))


def test_query_accepts_http_strings_but_requires_all_fields():
    query = dict(action='edit', row_key='row-key', pid='100', uptime='0')
    assert HaproxyStatsServerQuery.model_validate(query).model_dump() == {**query, 'pid': 100, 'uptime': 0}
    for key in query:
        with pytest.raises(ValidationError):
            HaproxyStatsServerQuery.model_validate({k: v for k, v in query.items() if k != key})
    with pytest.raises(ValidationError):
        HaproxyStatsServerQuery.model_validate({**query, 'unexpected': 'field'})


@pytest.mark.parametrize('body', [None, [], 'invalid', 1, True, {}])
def test_request_requires_an_object(body):
    with pytest.raises(ValidationError):
        HaproxyStatsServerRequest.model_validate(body)


def maxconn_payload(scope='server', value=150):
    return dict(scope=scope, row_key=None if scope == 'global' else 'row-key',
                value=value, pid=100, uptime=0, targets=['192.0.2.11'])


@pytest.mark.parametrize('scope,value', [
    ('server', 0), ('server', 2147483647), ('frontend', 1), ('frontend', 2147483647),
    ('global', 1), ('global', 2147483647),
])
def test_maxconn_scopes_keep_wire_contract_and_accept_boundary_values(scope, value):
    body = maxconn_payload(scope, value)
    assert HaproxyStatsMaxconnRequest.model_validate(body).model_dump(mode='json') == body


@pytest.mark.parametrize('field,value', [
    ('scope', 'backend'), ('scope', []), ('scope', None),
    ('value', True), ('value', '150'), ('value', 150.0), ('value', -1), ('value', 2147483648),
    ('pid', True), ('pid', '100'), ('pid', 100.0), ('pid', 0),
    ('uptime', False), ('uptime', '0'), ('uptime', -1),
    ('targets', '192.0.2.11'), ('targets', [123]), ('targets', ('192.0.2.11',)),
    ('row_key', None), ('row_key', ''), ('row_key', 'x' * 2049), ('row_key', []),
    ('unexpected', True),
])
def test_maxconn_rejects_coercion_invalid_fields_and_ranges(field, value):
    with pytest.raises(ValidationError):
        HaproxyStatsMaxconnRequest.model_validate({**maxconn_payload(), field: value})


@pytest.mark.parametrize('scope', ['global', 'frontend'])
def test_maxconn_zero_is_only_allowed_for_server_scope(scope):
    with pytest.raises(ValidationError):
        HaproxyStatsMaxconnRequest.model_validate(maxconn_payload(scope, 0))


def test_maxconn_global_requires_explicit_null_row_key_and_every_field():
    body = maxconn_payload('global')
    with pytest.raises(ValidationError):
        HaproxyStatsMaxconnRequest.model_validate({**body, 'row_key': 'row-key'})
    for key in body:
        with pytest.raises(ValidationError):
            HaproxyStatsMaxconnRequest.model_validate({k: v for k, v in body.items() if k != key})


@pytest.mark.parametrize('body', [None, [], 'invalid', 1, True, {}])
def test_maxconn_request_requires_an_object(body):
    with pytest.raises(ValidationError):
        HaproxyStatsMaxconnRequest.model_validate(body)
