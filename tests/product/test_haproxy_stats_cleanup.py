from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.modules.db.db_model import Setting
from app.modules.service import exporter_installation, installation


PARAMS = ('haproxy_stats_user', 'haproxy_stats_password', 'haproxy_stats_port', 'haproxy_stats_page')
ANSIBLE = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles'


def test_prometheus_settings_remain_for_existing_and_new_groups(product):
    from app.modules.db.group import add_setting_for_new_group
    from app.create_db import default_values
    assert Setting.select().where(Setting.param.in_(PARAMS), Setting.group_id == 1).count() == 4
    Setting.update(value='custom-password').where(Setting.param == 'haproxy_stats_password', Setting.group_id == 1).execute()
    default_values()
    assert Setting.get(Setting.param == 'haproxy_stats_password', Setting.group_id == 1).value == 'custom-password'
    add_setting_for_new_group(2)
    assert Setting.select().where(Setting.param.in_(PARAMS), Setting.group_id == 2).count() == 4
    assert Setting.get(Setting.param == 'haproxy_stats_password', Setting.group_id == 2).value != 'custom-password'


def test_settings_ui_and_runtime_actions_after_cleanup(product_client, product, monkeypatch):
    response = product_client.get('/admin/settings')
    assert response.status_code == 200
    assert all(param.encode() in response.data for param in PARAMS)
    assert b'haproxy_sock_port' in response.data
    assert b'nginx_stats_password' in response.data
    calls = []
    monkeypatch.setattr('app.modules.service.haproxy.runtime_command', lambda *args: calls.append(args) or 'ok')
    response = product_client.post(f'/runtimeapi/action/{product.server.ip}',
                                   data=dict(servaction='show', servbackend='info', save='0'))
    assert response.status_code == 200 and response.data == b'ok'
    assert calls == [(product.server.ip, 'show', 'info', '0')]


def test_haproxy_installation_keeps_prometheus_endpoint_and_runtime(monkeypatch):
    settings = dict(haproxy_sock_port='1999', server_state_file='/etc/haproxy/state',
                    haproxy_dir='/etc/haproxy', haproxy_container_name='haproxy', haproxy_stats_port='8085',
                    haproxy_stats_user='exporter', haproxy_stats_password='custom-password')
    monkeypatch.setattr(installation.sql, 'get_setting', settings.__getitem__)
    monkeypatch.setattr(installation.server_sql, 'get_server', lambda _: SimpleNamespace(ip='192.0.2.10'))
    inv, hosts = installation.generate_haproxy_inv(dict(
        servers=[dict(id=1, master=True, version='2.8.14')], services=dict(haproxy=dict(docker=False))), 'haproxy')
    assert hosts == ['192.0.2.10']
    environment = Environment(loader=FileSystemLoader(ANSIBLE), undefined=StrictUndefined)
    config = environment.get_template('haproxy/templates/haproxy.cfg.j2').render(**inv['server']['hosts'][hosts[0]])
    assert 'stats socket *:1999 level admin' in config
    assert 'listen stats' in config
    assert 'bind *:8085' in config
    assert 'stats auth exporter:custom-password' in config
    assert 'http-request use-service prometheus-exporter if { path /metrics }' in config
    sections = []
    monkeypatch.setattr(installation.add_sql, 'insert_or_update_new_section', lambda *args: sections.append(args))
    monkeypatch.setattr(installation.add_sql, 'insert_new_section', lambda *args: sections.append(args))
    installation._create_default_config_in_db(1)
    assert [section[1] for section in sections] == ['global', 'defaults', 'listen']
    assert '*:1999 level admin' in sections[0][3].socket
    assert 'prometheus-exporter' in sections[2][3].option


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_exporters_keep_configured_http_settings(monkeypatch, service):
    settings = {f'{service}_stats_{name}': value for name, value in (
        ('port', '8085'), ('user', 'user'), ('password', 'secret'), ('page', 'status'))}
    settings['server_state_file'] = '/etc/haproxy/state'
    monkeypatch.setattr(exporter_installation.sql, 'get_setting', settings.__getitem__)
    inv, _ = exporter_installation.generate_exporter_inv('192.0.2.10', '0.10.0', service)
    host = inv['server']['hosts']['192.0.2.10']
    assert host['STAT_PORT'] == '8085' and host['STAT_PAGE'] == 'status'
    assert host['STATS_USER'] == 'user' and host['STATS_PASS'] == 'secret'
    if service == 'haproxy':
        environment = Environment(loader=FileSystemLoader(ANSIBLE), undefined=StrictUndefined)
        playbook = environment.get_template('haproxy_exporter.yml').render(ansible_host='192.0.2.10', **host)
        assert '--haproxy.scrape-uri=http://user:secret@192.0.2.10:8085/status;csv' in playbook
