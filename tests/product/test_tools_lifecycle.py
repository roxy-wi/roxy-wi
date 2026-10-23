from types import SimpleNamespace

import pytest

from app.modules.db.db_model import UserGroups
from app.modules.roxywi import roxy
from app.modules.server.command import CommandResult


@pytest.fixture
def local_tools(monkeypatch):
    state = SimpleNamespace(commands=[], logged=[], return_code=0, timed_out=False, docker=False)
    monkeypatch.setattr(roxy, 'deployment_mode', lambda: 'package')
    monkeypatch.setattr(roxy, 'is_docker', lambda: state.docker)
    monkeypatch.setattr(roxy.roxy_sql, 'get_user', lambda: SimpleNamespace(Status=1))
    monkeypatch.setattr(roxy.roxywi_common, 'logging', lambda *args, **kwargs: state.logged.append(args))

    def execute(args, **kwargs):
        state.commands.append((args, kwargs))
        return CommandResult(tuple(args), '', 'private command output', state.return_code,
                             timed_out=state.timed_out)

    monkeypatch.setattr(roxy, 'run_local', execute)
    return state


@pytest.mark.parametrize('service', ['fail2ban', 'rabbitmq-server'])
@pytest.mark.parametrize('action,arguments', [('start', ['enable', '--now']),
                                             ('stop', ['disable', '--now']), ('restart', ['restart'])])
def test_tools_execute_local_service_actions(product_client, local_tools, service, action, arguments):
    response = product_client.post(f'/admin/tools/action/{service}/{action}')
    assert response.status_code == 200 and response.text == 'ok'
    assert local_tools.commands == [(['sudo', '-n', 'systemctl', *arguments, service], {'timeout': 60})]
    assert len(local_tools.logged) == 1


@pytest.mark.parametrize('service', ['fail2ban', 'rabbitmq-server'])
@pytest.mark.parametrize('timed_out', [False, True])
def test_failed_tools_action_is_not_reported_or_audited_as_success(
    product_client, local_tools, service, timed_out,
):
    local_tools.return_code = -1 if timed_out else 1
    local_tools.timed_out = timed_out
    response = product_client.post(f'/admin/tools/action/{service}/stop')
    assert response.status_code == 500
    assert response.json['status'] == 'failed'
    assert service in response.json['error']
    assert ('Timed out' if timed_out else 'sudo permissions') in response.json['error']
    assert 'private command output' not in response.text
    assert local_tools.logged == []


def test_legacy_supervisor_actions_also_check_exit_status(product_client, local_tools):
    local_tools.docker = True
    local_tools.return_code = 1
    response = product_client.post('/admin/tools/action/fail2ban/stop')
    assert response.status_code == 500
    assert local_tools.commands[0][0] == ['sudo', '-n', 'supervisorctl', 'stop', 'fail2ban']
    assert local_tools.logged == []


def test_non_admin_cannot_control_local_services(product_client, product, local_tools):
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.post('/admin/tools/action/rabbitmq-server/stop')
    assert response.status_code == 403
    assert local_tools.commands == []


def test_unknown_tool_cannot_execute_local_command(product_client, local_tools):
    response = product_client.post('/admin/tools/action/sshd/stop')
    assert response.status_code == 404
    assert local_tools.commands == []
