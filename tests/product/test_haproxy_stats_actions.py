"""Stats writes use real authorization, CSRF, validation and history."""
from types import SimpleNamespace

import pytest

from app.modules.common.common import checkAjaxInput
from app.modules.db.db_model import ActionHistory, Setting, User, UserGroups
from app.modules.service import haproxy_stats, haproxy_stats_actions
from tests.fixtures.haproxy_stats import INFO, ROWS, stats_csv


@pytest.fixture
def action_host(product, monkeypatch):
    state = SimpleNamespace(rows=[dict(row) for row in ROWS], info=INFO, writes=[], reply='', failure=None)
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()
    def read(server, port, command):
        assert (server, int(port)) == (product.server.ip, 1999)
        assert command in ('show stat', 'show info')
        return stats_csv(state.rows) if command == 'show stat' else state.info
    def write(server, port, command):
        assert (server, int(port)) == (product.server.ip, 1999)
        state.writes.append(command)
        if state.failure:
            raise state.failure
        return state.reply
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', read)
    monkeypatch.setattr(haproxy_stats_actions, 'execute_runtime_command', write)
    return state


def body(action='state', value='drain', row=1):
    return dict(row_key=haproxy_stats.parse_stats(stats_csv())[row]['key'],
                pid=100, uptime=3600, action=action, value=value)


def post(client, product, payload):
    return client.post(f'/stats/server/haproxy/{product.server.ip}', json=payload)


@pytest.mark.parametrize('action,value', [('state', 'ready'), ('state', 'drain'), ('state', 'maint'),
                                        ('weight', 0), ('weight', 75), ('weight', 256)])
def test_single_server_action_and_history(product_client, product, action_host, action, value):
    response = post(product_client, product, body(action, value))
    assert response.status_code == 200, response.text
    assert response.json == {'status': 'ok'}
    assert response.headers['Cache-Control'] == 'no-store'
    command = f'set server web/one {action} {value}'
    assert action_host.writes == [command]
    assert ActionHistory.select().where(ActionHistory.action == f'HAProxy Stats: {command}').exists()


@pytest.mark.parametrize('overrides', [
    {'action': 'shutdown'}, {'value': 'maint; shutdown sessions server web/one'},
    {'action': 'weight', 'value': -1}, {'action': 'weight', 'value': 257},
    {'action': 'weight', 'value': True}, {'action': 'weight', 'value': 0.5},
    {'action': 'weight', 'value': '50%'}, {'action': 'weight', 'value': '50'},
    {'pid': '100'}, {'uptime': -1}, {'row_key': []}, {'command': 'show info'},
])
def test_invalid_actions_never_write(product_client, product, action_host, overrides):
    assert post(product_client, product, {**body(), **overrides}).status_code == 400
    assert action_host.writes == []


@pytest.mark.parametrize('payload', [None, [], {}, {'action': 'state'}])
def test_malformed_actions_never_write(product_client, product, action_host, payload):
    assert post(product_client, product, payload).status_code == 400
    assert action_host.writes == []


@pytest.mark.parametrize('case', ['process', 'uptime', 'removed', 'renamed', 'frontend', 'backend', 'unsafe_name'])
def test_stale_or_non_server_target_never_writes(product_client, product, action_host, case):
    payload = body()
    if case == 'process':
        action_host.info = INFO.replace('Pid: 100', 'Pid: 200')
    elif case == 'uptime':
        action_host.info = INFO.replace('3600', '1')
    elif case == 'removed':
        action_host.rows.pop(1)
    elif case == 'renamed':
        action_host.rows[1]['svname'] = 'replacement'
    elif case in ('frontend', 'backend'):
        payload = body(row=0 if case == 'frontend' else 3)
    else:
        action_host.rows[1]['svname'] = 'one;shutdown sessions server web/two'
        payload['row_key'] = haproxy_stats.parse_stats(stats_csv(action_host.rows))[1]['key']
    assert post(product_client, product, payload).status_code == 409
    assert action_host.writes == []


@pytest.mark.parametrize('role', [1, 2, 3, 4])
def test_actions_follow_operator_permissions(product_client, product, action_host, role):
    UserGroups.update(user_role_id=role).where(UserGroups.user_id == product.admin.user_id).execute()
    page = product_client.get(f'/stats/haproxy/{product.server.ip}')
    assert f'data-can-manage="{str(role <= 3).lower()}"' in page.text
    response = post(product_client, product, body())
    assert response.status_code == (200 if role <= 3 else 403)
    assert len(action_host.writes) == int(role <= 3)


def test_actions_require_login_csrf_and_managed_haproxy_access(product_client, product, action_host):
    with product_client.application.test_client() as anonymous:
        assert post(anonymous, product, body()).status_code == 401
    assert product_client.post(f'/stats/server/haproxy/{product.server.ip}', json=body(),
                               headers={'X-CSRF-TOKEN': ''}).status_code == 401
    UserGroups.update(user_role_id=3).where(UserGroups.user_id == product.admin.user_id).execute()
    for target in (product.other.ip, '192.0.2.250'):
        assert product_client.post(f'/stats/server/haproxy/{target}', json=body()).status_code == 403
    product.server.haproxy = 0
    product.server.save()
    assert post(product_client, product, body()).status_code == 404
    product.server.haproxy = 1
    product.server.save()
    User.update(user_services='2 3').where(User.user_id == product.admin.user_id).execute()
    assert post(product_client, product, body()).status_code == 403
    assert action_host.writes == []


@pytest.mark.parametrize('reply,code,status', [
    ('Permission denied\n', 'action_permissions', 403),
    ('Backend uses a static algorithm. secret-internal-detail\n', 'command_rejected', 409),
])
def test_runtime_rejection_is_not_success(product_client, product, action_host, reply, code, status):
    action_host.reply = reply
    response = post(product_client, product, body('weight', 80))
    assert response.status_code == status
    assert response.json == {'status': 'error', 'code': code}
    assert 'secret-internal-detail' not in response.text
    assert len(action_host.writes) == 1
    assert not ActionHistory.select().where(ActionHistory.action.startswith('HAProxy Stats:')).exists()


@pytest.mark.parametrize('failure', [TimeoutError('private detail'), ConnectionResetError('private detail')])
def test_uncertain_write_is_never_retried(product_client, product, action_host, failure):
    action_host.failure = failure
    response = post(product_client, product, body())
    assert response.status_code == 502
    assert response.json['code'] == 'action_unknown'
    assert len(action_host.writes) == 1


@pytest.mark.parametrize('action,arguments', [
    ('set', 'server web/one state ready'), ('set', 'server web/one state drain'),
    ('set', 'server web/one state maint'), ('set', 'server web/one weight 10'),
    ('set', 'weight web/one 50%'), ('enable', 'server web/one'), ('disable', 'server web/one'),
    ('set', 'maxconn global 200'), ('set', 'maxconn frontend public 500'),
    ('set', 'maxconn server web/one 100'), ('set', 'server web/one maxconn 100'),
])
def test_moved_console_actions_no_longer_execute(product_client, product, monkeypatch, action, arguments):
    monkeypatch.setattr('app.modules.service.haproxy.runtime_command',
                        lambda *args: pytest.fail('Moved command reached the legacy console'))
    response = product_client.post(f'/runtimeapi/action/{product.server.ip}',
                                   data={'servaction': action, 'servbackend': arguments})
    assert response.status_code == 409
    assert response.json['code'] == 'stats_actions_moved'


@pytest.mark.parametrize('action,arguments', [('show', 'info'), ('set', 'server web/one addr 192.0.2.4'),
                                            ('disable', 'frontend public')])
def test_other_console_commands_remain(product_client, product, monkeypatch, action, arguments):
    commands = []
    monkeypatch.setattr('app.modules.service.haproxy.runtime_command', lambda *args: commands.append(args) or 'ok')
    response = product_client.post(f'/runtimeapi/action/{product.server.ip}',
                                   data={'servaction': action, 'servbackend': arguments})
    assert response.status_code == 200
    assert commands[0][1:3] == (action, checkAjaxInput(arguments))
