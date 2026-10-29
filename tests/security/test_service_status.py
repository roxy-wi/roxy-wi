from types import SimpleNamespace

import pytest
from flask import g

from app.views.service.views import ServiceView
from app.modules.service import managed_runtime


HAPROXY_INFO = """Version: 3.1.7-c3f4089
Process_num: 1
Uptime: 0d 2h36m27s
Memmax_MB: 0
PoolAlloc_MB: 0
PoolUsed_MB: 0
Maxconn: 4001
CurrConns: 0
MaxconnReached: 0
"""


@pytest.mark.security
def test_haproxy_status_runs_runtime_query_on_target_address(app, monkeypatch):
    commands = []
    server = SimpleNamespace(
        ip='10.0.0.173',
        haproxy_active=1,
        haproxy_alert=1,
        haproxy_metrics=1,
    )
    monkeypatch.setattr(
        'app.views.service.views.SupportClass.return_server_ip_or_id',
        lambda self, server_reference: 65,
    )
    monkeypatch.setattr(
        'app.views.service.views.server_sql.get_server_with_group',
        lambda server_id, group_id: server,
    )
    monkeypatch.setattr(
        'app.views.service.views.sql.get_setting',
        lambda setting: 1999,
    )
    monkeypatch.setattr(
        'app.views.service.views.service_sql.select_service_setting',
        lambda server_id, service, setting: '0',
    )
    monkeypatch.setattr(
        'app.views.service.views.server_mod.subprocess_execute',
        lambda command: (_ for _ in ()).throw(AssertionError('status query must not run on Roxy-WI')),
    )
    monkeypatch.setattr(
        'app.views.service.views.server_mod.ssh_command',
        lambda server_ip, command, **kwargs: commands.append((server_ip, command, kwargs)) or HAPROXY_INFO,
    )

    with app.test_request_context('/service/haproxy/65/status'):
        g.user_params = {'group_id': 7}
        response = ServiceView().get('haproxy', 65)
        data = response.get_json()

    assert commands == [(
        '10.0.0.173',
        'echo "show info" |nc 10.0.0.173 1999 -w 1',
        {'timeout': 5, 'connect_timeout': 10, 'banner_timeout': 10},
    )]
    assert data['Version'] == '3.1.7-c3f4089'
    assert data['Process'] == '1'
    assert data['status'] == 'running'
    assert data['CurrConns'] == '0'
    assert data['Maxconn'] == '4001'


@pytest.mark.security
def test_haproxy_info_parser_ignores_malformed_and_unknown_lines():
    parsed = ServiceView.return_dict_from_out([
        'Version: 3.1.7',
        'Process_num: 1',
        'Malformed line',
        'Unknown: ignored',
    ])

    assert parsed == {'Version': '3.1.7', 'Process': '1'}


@pytest.mark.security
def test_apache_status_uses_http_client_without_exposing_credentials_to_shell(app, monkeypatch):
    requests = []
    settings = {
        'apache_stats_user': 'status-user',
        'apache_stats_password': 'secret; touch /tmp/pwned',
        'apache_stats_port': '8080',
        'apache_stats_page': '/server-status',
    }
    server = SimpleNamespace(
        ip='192.0.2.20',
        apache_active=1,
        apache_alert=0,
        apache_metrics=1,
    )

    monkeypatch.setattr(managed_runtime, 'managed_server', lambda _: server)
    server.server_id = 65

    class Response:
        text = (
            'ServerVersion: Apache/2.4.62 (Unix)\n'
            'ServerUptime: 1 day 2 hours\n'
            'Processes: 3\n'
        )

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(
        'app.views.service.views.SupportClass.return_server_ip_or_id',
        lambda self, server_reference: 65,
    )
    monkeypatch.setattr(
        'app.views.service.views.server_sql.get_server_with_group',
        lambda server_id, group_id: server,
    )
    monkeypatch.setattr(
        'app.views.service.views.sql.get_setting',
        lambda setting: settings[setting],
    )
    monkeypatch.setattr(
        'app.views.service.views.service_sql.select_service_setting',
        lambda server_id, service, setting: '0',
    )
    monkeypatch.setattr(
        'app.views.service.views.server_mod.subprocess_execute',
        lambda command: (_ for _ in ()).throw(AssertionError('Apache status must not invoke a shell')),
    )
    monkeypatch.setattr(
        'app.views.service.views.requests.get',
        lambda url, **kwargs: requests.append((url, kwargs)) or Response(),
    )

    with app.test_request_context('/service/apache/65/status'):
        g.user_params = {'group_id': 7}
        response = ServiceView().get('apache', 65)
        data = response.get_json()

    assert requests == [(
        'http://192.0.2.20:8080/server-status?auto',
        {
            'auth': ('status-user', 'secret; touch /tmp/pwned'),
            'timeout': 5,
            'allow_redirects': False,
        },
    )]
    assert data['Version'] == '2.4.62'
    assert data['Uptime'] == '1 day 2 hours'
    assert data['Process'] == '3'
    assert data['status'] == 'running'
