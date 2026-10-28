import pytest

from app.modules.config import runtime
from app.modules.db.db_model import ActionHistory, User, UserGroups
from tests.fixtures.haproxy_tables import tables_host  # noqa: F401


ENDPOINT = '/stats/tables/haproxy/192.0.2.11'


def snapshot(client, table=None):
    response = client.get(ENDPOINT, query_string={'table': table} if table else {})
    assert response.status_code == 200, response.json
    assert response.headers['Cache-Control'] == 'no-store'
    return response.json


def change_body(data, row=None):
    return dict(action='delete' if row is not None else 'clear', table=data['table']['name'],
                revision=data['table']['revision'], row_key=data['table']['rows'][row]['row_key'] if row is not None else None,
                pid=data['info']['Pid'], uptime=data['info']['Uptime_sec'])


def test_lazy_collection_delete_and_partial_clear(product_client, tables_host):
    data = snapshot(product_client)
    assert [call[1] for call in tables_host.calls] == ['show info', 'show table', 'show table clients', 'show info']
    assert len(data['tables']) == 3
    assert data['table']['used'] == 2
    response = product_client.post(ENDPOINT, json=change_body(data, 0))
    assert response.json == {'status': 'ok', 'remaining': 1, 'verified': True}
    assert tables_host.writes == [('192.0.2.11', 'clear table clients key 203.0.113.42')]
    assert ActionHistory.select().where(ActionHistory.action == 'HAProxy Stats: delete stick table clients').exists()
    response = product_client.post(ENDPOINT, json=change_body(data))
    assert response.json['remaining'] == 1
    assert 'use=1' in tables_host.tables['clients']['rows'][0]


@pytest.mark.parametrize('table,command', [
    ('peers/ipv6', 'clear table peers/ipv6 key 2001:db8::1'),
    ('tokens', r'clear table tokens key user\ name=one\;two\\three'),
])
def test_ipv6_and_escaped_string_deletion(product_client, tables_host, table, command):
    body = change_body(snapshot(product_client, table), 0)
    assert product_client.post(ENDPOINT, json=body).json['remaining'] == 0
    assert tables_host.writes == [('192.0.2.11', command)]


@pytest.mark.parametrize('change,code', [
    ('pid', 'target_changed'), ('uptime', 'target_changed'), ('gone', 'table_entry_gone'),
    ('replaced', 'table_entry_gone'), ('table', 'table_gone'), ('size', 'target_changed'),
])
def test_changed_targets_never_receive_a_write(product_client, tables_host, change, code):
    body = change_body(snapshot(product_client), 0)
    if change == 'pid':
        tables_host.info = tables_host.info.replace('Pid: 100', 'Pid: 101')
    elif change == 'uptime':
        tables_host.info = tables_host.info.replace('3600', '1')
    elif change == 'gone':
        tables_host.tables['clients']['rows'].pop(0)
    elif change == 'replaced':
        tables_host.tables['clients']['rows'][0] = tables_host.tables['clients']['rows'][0].replace('0x100', '0x101')
    elif change == 'table':
        del tables_host.tables['clients']
    else:
        tables_host.tables['clients']['size'] += 1
    assert product_client.post(ENDPOINT, json=body).json['code'] == code
    assert tables_host.writes == []


def test_in_use_entries_rejected_and_no_success_history(product_client, tables_host):
    response = product_client.post(ENDPOINT, json=change_body(snapshot(product_client), 1))
    assert response.status_code == 409
    assert response.json['code'] == 'table_entry_in_use'
    assert not ActionHistory.select().where(ActionHistory.action.startswith('HAProxy Stats:')).exists()


@pytest.mark.parametrize('reply,code,status', [
    ('Permission denied\n', 'action_permissions', 403), ('Unrecognized\n', 'command_rejected', 409),
    (None, 'action_unknown', 502),
])
def test_write_errors_are_not_retried(product_client, tables_host, reply, code, status):
    body = change_body(snapshot(product_client))
    if reply is None:
        tables_host.write_failure = TimeoutError('private password')
    else:
        tables_host.reply = reply
    response = product_client.post(ENDPOINT, json=body)
    assert response.status_code == status
    assert response.json['code'] == code
    assert len(tables_host.writes) == 1
    assert 'private' not in response.text


@pytest.mark.parametrize('error,code,status', [
    (TimeoutError('private'), 'runtime_timeout', 504), (OSError('private'), 'runtime_unavailable', 503),
    (RuntimeError('private'), 'response_too_large', 502),
])
def test_read_errors_are_explicit(product_client, tables_host, error, code, status):
    tables_host.read_failure = error
    response = product_client.get(ENDPOINT)
    assert response.status_code == status
    assert response.json['code'] == code
    assert 'private' not in response.text


def test_permissions_csrf_validation_and_removed_routes(product_client, product, tables_host):
    body = change_body(snapshot(product_client))
    tables_host.calls.clear()
    for payload in (None, [], {}, body | {'table': 'clients;show env'}, body | {'pid': True}):
        assert product_client.post(ENDPOINT, json=payload).status_code == 400
    assert tables_host.calls == []
    assert product_client.post(ENDPOINT, json=body, headers={'X-CSRF-TOKEN': ''}).status_code == 401
    with product_client.application.test_client() as anonymous:
        assert anonymous.get(ENDPOINT, headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 401
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    for target in (product.other.ip, '192.0.2.250'):
        assert product_client.get('/stats/tables/haproxy/' + target).status_code == 403
        assert product_client.post('/stats/tables/haproxy/' + target, json=body).status_code == 403
    assert snapshot(product_client)['table']['name'] == 'clients'
    assert product_client.post(ENDPOINT, json=body).status_code == 403
    assert tables_host.writes == []
    for path in ('tables/192.0.2.11', 'table/192.0.2.11/clients'):
        assert product_client.get('/runtimeapi/' + path).status_code == 404
    for path in ('table/delete/192.0.2.11/clients/203.0.113.42', 'table/clear/192.0.2.11/clients'):
        assert product_client.post('/runtimeapi/' + path).status_code == 404
    product.server.haproxy = 0
    product.server.save()
    assert product_client.get(ENDPOINT).status_code == 404
    product.server.haproxy = 1
    product.server.save()
    User.update(user_services='2 3').where(User.user_id == product.admin.user_id).execute()
    assert product_client.get(ENDPOINT).status_code == 403


def test_write_success_with_failed_verification_is_explicit(product_client, tables_host, monkeypatch):
    body = change_body(snapshot(product_client))
    original = runtime.clear_stick_table

    def clear(*args, **kwargs):
        response = original(*args, **kwargs)
        tables_host.read_failure = TimeoutError('private')
        return response

    monkeypatch.setattr(runtime, 'clear_stick_table', clear)
    response = product_client.post(ENDPOINT, json=body)
    assert response.json == {'status': 'ok', 'remaining': None, 'verified': False}
    assert len(tables_host.writes) == 1


def test_empty_tables_and_unsupported_key_deletion(product_client, tables_host):
    tables_host.tables['tokens']['type'] = 'binary'
    data = snapshot(product_client, 'tokens')
    assert not data['table']['rows'][0]['deletable']
    response = product_client.post(ENDPOINT, json=change_body(data, 0))
    assert response.json['code'] == 'table_key_read_only'
    assert tables_host.writes == []
    tables_host.tables['tokens']['rows'] = []
    assert snapshot(product_client, 'tokens')['table']['rows'] == []
    tables_host.tables.clear()
    assert snapshot(product_client)['table'] is None


def test_restart_during_verification_does_not_report_new_process_counts(product_client, tables_host, monkeypatch):
    body = change_body(snapshot(product_client))
    original = runtime.execute_runtime_command

    def restart(server, port, command):
        if command == 'show table' and tables_host.writes:
            tables_host.info = tables_host.info.replace('Pid: 100', 'Pid: 200')
        return original(server, port, command)

    monkeypatch.setattr(runtime, 'execute_runtime_command', restart)
    response = product_client.post(ENDPOINT, json=body)
    assert response.json == {'status': 'ok', 'remaining': None, 'verified': False}
    assert len(tables_host.writes) == 1
