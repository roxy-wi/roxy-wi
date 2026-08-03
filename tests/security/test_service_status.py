from types import SimpleNamespace

import pytest
from flask import g

from app.views.service.views import ServiceView


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
def test_haproxy_status_runs_runtime_query_on_target_loopback(app, monkeypatch):
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
        'echo "show info" |nc 127.0.0.1 1999 -w 1',
        {'timeout': 5},
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
