from contextlib import contextmanager
from html import unescape
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import config
from app.modules.db.db_model import Setting, WafRules
from app.modules.roxywi import auth, waf
from app.routes.waf import routes

WAF_DIRS = {'haproxy': '/srv/proxy one', 'nginx': '/srv/proxy two'}


@pytest.fixture
def waf_rules(product):
    rules = {}
    for service in ('haproxy', 'nginx'):
        rules[service] = WafRules.create(serv=product.server.ip, service=service, rule_name='Test rule',
                                        rule_file='test.conf', en=1)
        Setting.update(value=WAF_DIRS[service] + '/').where(
            Setting.param == f'{service}_dir', Setting.group_id == 1).execute()
    rules['other'] = WafRules.create(serv=product.other.ip, service='haproxy', rule_name='Test rule',
                                    rule_file='test.conf', en=1)
    Setting.update(value=str(product.root) + '/').where(
        Setting.param == 'tmp_config_path', Setting.group_id == 1).execute()
    return rules


@pytest.fixture
def forbid_waf_io(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Rejected WAF request reached file or remote operations')
    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', unexpected)
    monkeypatch.setattr(config, 'master_slave_upload_and_restart', unexpected)
    monkeypatch.setattr(waf.server_mod, 'ssh_command', unexpected)
    monkeypatch.setattr(routes.tempfile, 'NamedTemporaryFile', unexpected)


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('operation', ['read', 'save'])
@pytest.mark.parametrize('owner', ['other_server', 'other_service', 'missing'])
def test_waf_rule_must_match_server_and_service(product_client, product, waf_rules, forbid_waf_io,
                                               service, operation, owner):
    rule_id = {'other_server': waf_rules['other'].id,
               'other_service': waf_rules['nginx' if service == 'haproxy' else 'haproxy'].id,
               'missing': 99999}[owner]
    url = f'/waf/{service}/{product.server.ip}/rule/{rule_id}'
    response = (product_client.get(url) if operation == 'read' else
                product_client.post(url + '/save', json={'action': 'save', 'config': '# candidate',
                                                         'config_file_name': 'test.conf'}))
    assert response.status_code == 404, response.text


@pytest.mark.parametrize('owner', ['other', 'missing'])
def test_toggle_rejects_foreign_or_missing_rule(product_client, product, waf_rules, forbid_waf_io, owner):
    rule_id = waf_rules['other'].id if owner == 'other' else 99999
    response = product_client.post(f'/waf/{product.server.ip}/rule/{rule_id}/0')
    assert response.status_code == 404, response.text
    assert WafRules.get_by_id(waf_rules['other'].id).en == 1


@pytest.mark.parametrize('operation', ['read', 'save', 'toggle'])
def test_rule_service_permission_is_required(product_client, product, waf_rules, forbid_waf_io, monkeypatch, operation):
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda service: service != 'nginx')
    rule_id = waf_rules['nginx'].id
    url = f'/waf/nginx/{product.server.ip}/rule/{rule_id}'
    if operation == 'read':
        response = product_client.get(url)
    elif operation == 'save':
        response = product_client.post(url + '/save', json={'action': 'save', 'config': '# candidate'})
    else:
        response = product_client.post(f'/waf/{product.server.ip}/rule/{rule_id}/0')
    assert response.status_code == 403, response.text
    assert WafRules.get_by_id(rule_id).en == 1


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_editor_downloads_the_registered_rule_from_custom_directory(product_client, product, waf_rules, monkeypatch, service):
    downloaded = []

    def download(remote, local):
        downloaded.append(remote)
        Path(local).write_text('# registered rule\n', encoding='utf-8')

    @contextmanager
    def connect(server):
        assert server == product.server.ip
        yield SimpleNamespace(get_sftp=download)

    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', connect)
    # The legacy editor uses a timestamp in local filenames; keep it portable.
    monkeypatch.setattr(routes.roxy_wi_tools, 'GetDate',
                        lambda *_: SimpleNamespace(return_date=lambda _: '2026-10-06'))
    response = product_client.get(f'/waf/{service}/{product.server.ip}/rule/{waf_rules[service].id}')
    expected = f'{WAF_DIRS[service]}/waf/rules/test.conf'
    assert response.status_code == 200, response.text
    assert downloaded == [expected]
    assert f'value="{expected}" name="config_file_name"' in unescape(response.text)
    assert '# registered rule' in response.text


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('json_request', [False, True])
@pytest.mark.parametrize('filename', ['basename', 'full_path', 'omitted'])
def test_save_uses_registered_rule_path(product_client, product, waf_rules, monkeypatch, service, json_request, filename):
    uploaded = []
    expected = f'{WAF_DIRS[service]}/waf/rules/test.conf'

    def upload(server, candidate, *args, **kwargs):
        assert kwargs['waf'] == service
        uploaded.append((server, Path(candidate).read_text(encoding='utf-8'), kwargs['config_file_name']))

    monkeypatch.setattr(config, 'master_slave_upload_and_restart', upload)
    data = {'action' if json_request else 'save': 'save', 'config': '# updated rule'}
    if filename != 'omitted':
        data['config_file_name'] = 'test.conf' if filename == 'basename' else expected
    response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/{waf_rules[service].id}/save',
                                   **({'json': data} if json_request else {'data': data}))
    assert response.status_code == 200, response.text
    assert uploaded == [(product.server.ip, '# updated rule', expected)]


@pytest.mark.parametrize('filename', ['other.conf', '/srv/proxy two/waf/rules/test.conf', '../test.conf'])
def test_save_cannot_override_registered_rule_path(product_client, product, waf_rules, forbid_waf_io, filename):
    response = product_client.post(f'/waf/haproxy/{product.server.ip}/rule/{waf_rules["haproxy"].id}/save',
                                   json={'action': 'save', 'config': '# candidate', 'config_file_name': filename})
    assert response.status_code == 400, response.text


@pytest.mark.parametrize('operation', ['read', 'save', 'toggle'])
def test_invalid_stored_filename_is_rejected_before_io(product_client, product, waf_rules, forbid_waf_io, operation):
    rule = waf_rules['haproxy']
    rule.rule_file = '../outside.conf'
    rule.save()
    url = f'/waf/haproxy/{product.server.ip}/rule/{rule.id}'
    if operation == 'read':
        response = product_client.get(url)
    elif operation == 'save':
        response = product_client.post(url + '/save', json={'action': 'save', 'config': '# candidate'})
    else:
        response = product_client.post(f'/waf/{product.server.ip}/rule/{rule.id}/0')
    assert response.status_code == 400, response.text
    assert WafRules.get_by_id(rule.id).en == 1


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_save_keeps_rule_path_through_upload_pipeline(product_client, product, waf_rules, monkeypatch, service):
    uploads, commands = [], []

    def upload(server, remote, local):
        uploads.append((server, remote, Path(local).read_text(encoding='utf-8')))

    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(config.server_mod, 'ssh_command',
                        lambda server, command, **kw: commands.append((server, shlex.split(command))) or '')
    expected = f'{WAF_DIRS[service]}/waf/rules/test.conf'
    response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/{waf_rules[service].id}/save',
                                   json={'action': 'save', 'config': '# candidate', 'config_file_name': expected})
    assert response.status_code == 200, response.text
    assert 'error' not in response.json['data'].lower()
    assert len(uploads) == 1 and uploads[0][0] == product.server.ip and uploads[0][2] == '# candidate'
    assert commands == [(product.server.ip, ['sudo', 'mv', '-f', uploads[0][1], expected])]


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_legacy_toggle_uses_service_from_registered_rule(product_client, product, waf_rules, monkeypatch, service):
    commands = []
    monkeypatch.setattr(waf.server_mod, 'ssh_command', lambda server, command: commands.append((server, command)))
    rule_id = waf_rules[service].id
    response = product_client.post(f'/waf/{product.server.ip}/rule/{rule_id}/0')
    assert response.status_code == 200, response.text
    assert response.json['status'] == 'updated'
    assert len(commands) == 1 and commands[0][0] == product.server.ip
    assert shlex.split(commands[0][1])[-1] == f'{WAF_DIRS[service]}/waf/modsecurity.conf'
    assert f'{WAF_DIRS[service]}/waf/rules/test.conf' in commands[0][1]
    assert WafRules.get_by_id(rule_id).en == 0
    other_service = 'nginx' if service == 'haproxy' else 'haproxy'
    assert WafRules.get_by_id(waf_rules[other_service].id).en == 1
