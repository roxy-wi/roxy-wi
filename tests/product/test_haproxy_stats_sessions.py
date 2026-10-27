import pytest

from app.modules.db.db_model import ActionHistory, User, UserGroups
from tests.fixtures.haproxy_sessions import sessions_host  # noqa: F401


def snapshot(client, product):
    response = client.get(f'/stats/sessions/haproxy/{product.server.ip}')
    assert response.status_code == 200, response.text
    return response.json


def query(data, row=0):
    return dict(session_id=data['rows'][row]['id'], row_key=data['rows'][row]['key'],
                pid=data['info']['Pid'], uptime=data['info']['Uptime_sec'])


def details(client, product, body):
    return client.get(f'/stats/session/haproxy/{product.server.ip}', query_string=body)


def test_sessions_detail_termination_and_history(product_client, product, sessions_host):
    data = snapshot(product_client, product)
    assert len(data['rows']) == 3
    assert [command for _, command in sessions_host.calls] == ['show info', 'show sess', 'show info']
    body = query(data)
    response = details(product_client, product, body)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json['row']['fields']['src'] == '203.0.113.42:51832'
    assert 'source=203.0.113.42' in response.json['raw']
    body['revision'] = response.json['revision']
    response = product_client.post(f'/stats/session/haproxy/{product.server.ip}', json=body)
    assert response.json == {'status': 'ok'}
    assert response.headers['Cache-Control'] == 'no-store'
    assert sessions_host.writes == [(product.server.ip, 'shutdown session 0x7f001')]
    assert ActionHistory.select().where(ActionHistory.action == 'HAProxy Stats: shutdown session 0x7f001').exists()
    # Replaying the confirmation cannot terminate an unrelated stream.
    assert product_client.post(f'/stats/session/haproxy/{product.server.ip}', json=body).status_code == 410
    assert len(sessions_host.writes) == 1


@pytest.mark.parametrize('changed', ['pid', 'uptime', 'removed', 'epoch', 'source', 'uid', 'format'])
def test_changed_sessions_never_receive_shutdown(product_client, product, sessions_host, changed):
    body = query(snapshot(product_client, product))
    body['revision'] = details(product_client, product, body).json['revision']
    if changed == 'pid':
        sessions_host.info = sessions_host.info.replace('Pid: 100', 'Pid: 200')
    elif changed == 'uptime':
        sessions_host.info = sessions_host.info.replace('3600', '1')
    elif changed == 'removed':
        sessions_host.rows.pop(0)
    elif changed == 'epoch':
        sessions_host.rows[0]['epoch'] = '0x4'
    elif changed == 'source':
        sessions_host.rows[0]['src'] = '203.0.113.99:50000'
    elif changed == 'uid':
        sessions_host.uid += 1
    else:
        sessions_host.detail_override = 'Future session detail format\n'
    response = product_client.post(f'/stats/session/haproxy/{product.server.ip}', json=body)
    assert response.status_code == (410 if changed == 'removed' else 409), response.text
    assert sessions_host.writes == []


def test_unknown_detail_format_is_readable_but_not_writable(product_client, product, sessions_host):
    body = query(snapshot(product_client, product))
    sessions_host.detail_override = 'Future format <script>privateMarkup()</script>\n'
    response = details(product_client, product, body)
    assert response.status_code == 200
    assert response.json['revision'] is None
    assert response.json['raw'] == sessions_host.detail_override


@pytest.mark.parametrize('failure,code,status', [
    (TimeoutError('private secret'), 'runtime_timeout', 504),
    (ConnectionRefusedError('private secret'), 'runtime_unavailable', 503),
    (RuntimeError('private secret'), 'response_too_large', 502),
])
def test_read_failures_are_explicit_and_redacted(product_client, product, sessions_host, failure, code, status):
    sessions_host.read_failure = failure
    response = product_client.get(f'/stats/sessions/haproxy/{product.server.ip}')
    assert response.status_code == status
    assert response.json == {'status': 'error', 'code': code}


@pytest.mark.parametrize('reply,code,status', [
    ('Permission denied\n', 'action_permissions', 403),
    ("No such session (use 'show sess').\n", 'session_gone', 410),
    ('secret backend error', 'command_rejected', 409),
    (None, 'action_unknown', 502),
])
def test_write_failure_is_not_retried_or_logged_as_success(product_client, product, sessions_host, reply, code, status):
    body = query(snapshot(product_client, product))
    body['revision'] = details(product_client, product, body).json['revision']
    if reply is None:
        sessions_host.write_failure = TimeoutError('secret detail')
    else:
        sessions_host.reply = reply
    response = product_client.post(f'/stats/session/haproxy/{product.server.ip}', json=body)
    assert response.status_code == status
    assert response.json['code'] == code
    assert len(sessions_host.writes) == 1
    assert not ActionHistory.select().where(ActionHistory.action.startswith('HAProxy Stats: shutdown')).exists()


def test_reader_role_access_csrf_and_removed_runtime_routes(product_client, product, sessions_host):
    body = query(snapshot(product_client, product))
    body['revision'] = details(product_client, product, body).json['revision']
    endpoint = f'/stats/session/haproxy/{product.server.ip}'
    with product_client.application.test_client() as anonymous:
        assert anonymous.get(f'/stats/sessions/haproxy/{product.server.ip}',
                             headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 401
    assert product_client.post(endpoint, json=body, headers={'X-CSRF-TOKEN': ''}).status_code == 401
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert len(snapshot(product_client, product)['rows']) == 3
    assert details(product_client, product, query(snapshot(product_client, product))).status_code == 200
    assert product_client.post(endpoint, json=body).status_code == 403
    for target in (product.other.ip, '192.0.2.250'):
        assert product_client.get(f'/stats/sessions/haproxy/{target}').status_code == 403
        assert product_client.get(f'/stats/session/haproxy/{target}', query_string=query(snapshot(product_client, product))).status_code == 403
    product.server.haproxy = 0
    product.server.save()
    assert product_client.get(f'/stats/sessions/haproxy/{product.server.ip}').status_code == 404
    product.server.haproxy = 1
    product.server.save()
    User.update(user_services='2 3').where(User.user_id == product.admin.user_id).execute()
    assert product_client.get(f'/stats/sessions/haproxy/{product.server.ip}').status_code == 403
    assert sessions_host.writes == []
    for path in ('session/192.0.2.11', 'session/192.0.2.11/0x7f001'):
        assert product_client.get('/runtimeapi/' + path).status_code == 404
    assert product_client.post('/runtimeapi/session/delete/192.0.2.11/0x7f001').status_code == 404


@pytest.mark.parametrize('payload', [None, [], {}, {'session_id': 'all'},
    {'session_id': '0x1;shutdown sessions server web/one'}, {'session_id': '0x1\nshow env'},
])
def test_bad_requests_never_reach_runtime(product_client, product, sessions_host, payload):
    response = product_client.post(f'/stats/session/haproxy/{product.server.ip}', json=payload)
    assert response.status_code == 400
    assert sessions_host.calls == []


def test_bad_query_and_permission_response_are_not_empty_success(product_client, product, sessions_host):
    assert details(product_client, product, {'session_id': 'all'}).status_code == 400
    assert sessions_host.calls == []
    sessions_host.list_override = 'Permission denied\n'
    response = product_client.get(f'/stats/sessions/haproxy/{product.server.ip}')
    assert response.status_code == 403
    assert response.json['code'] == 'runtime_permissions'
