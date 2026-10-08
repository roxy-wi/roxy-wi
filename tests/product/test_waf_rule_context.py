from contextlib import contextmanager
from html import unescape
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import config
from app.modules.db.db_model import Setting, WafRules, ServiceSetting
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
    monkeypatch.setattr(routes.tempfile, 'TemporaryDirectory', unexpected)


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
    response = product_client.get(f'/waf/{service}/{product.server.ip}/rule/{waf_rules[service].id}')
    expected = f'{WAF_DIRS[service]}/waf/rules/test.conf'
    assert response.status_code == 200, response.text
    assert downloaded == [expected]
    assert f'value="{expected}" name="config_file_name"' in unescape(response.text)
    assert '# registered rule' in response.text
    assert not list(product.root.glob('waf-read-*'))
    assert 'name="oldconfig"' not in response.text


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
    assert not list(product.root.glob('waf-save-*'))


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


@pytest.mark.parametrize('failure', ['download', 'decode'])
def test_read_error_never_opens_partial_or_stale_content(product_client, product, waf_rules, monkeypatch, failure):
    sentinel = product.root / 'another-editor.old'
    sentinel.write_text('unrelated baseline')

    def download(server, path, **kwargs):
        Path(path).write_bytes(b'partial secret\xff')
        if failure == 'download':
            raise OSError('synthetic SSH failure')

    monkeypatch.setattr(config, 'get_config', download)
    response = product_client.get(f'/waf/haproxy/{product.server.ip}/rule/{waf_rules["haproxy"].id}')
    assert response.status_code == 500
    assert response.json['status'] == 'failed'
    assert 'Could not open the WAF rule' in response.json['error']
    assert 'partial secret' not in response.text and 'synthetic SSH failure' not in response.text
    assert not list(product.root.glob('waf-read-*'))
    assert sentinel.read_text() == 'unrelated baseline'


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
@pytest.mark.parametrize('action', ['save', 'reload', 'restart'])
@pytest.mark.parametrize('docker', ['0', '1'])
def test_editor_uses_correct_runtime_service(product_client, product, waf_rules, monkeypatch, service, action, docker):
    target = 'nginx' if service == 'nginx' else 'waf'
    ServiceSetting.create(server_id=11, service=target, setting='dockerized', value=docker)
    # The wrong target deliberately has the opposite container setting.
    other = 'waf' if service == 'nginx' else 'haproxy'
    ServiceSetting.create(server_id=11, service=other, setting='dockerized', value=str(1 - int(docker)))
    Setting.insert(param=f'{target}_container_name', value='custom-waf-container', section=target, desc='', group_id=1).on_conflict(
        conflict_target=[Setting.param, Setting.group_id], update={Setting.value: 'custom-waf-container'}).execute()
    commands = []
    sentinel = product.root / 'another-editor.old'
    sentinel.write_text('unrelated baseline')
    monkeypatch.setattr(config, 'upload', lambda *a: None)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(config.server_mod, 'ssh_command',
                        lambda server, command, **kw: commands.append(command) or '')
    response = product_client.post(f'/waf/{service}/{product.server.ip}/rule/{waf_rules[service].id}/save',
                                   json={'action': action, 'config': '# rule', 'oldconfig': str(sentinel)})
    assert response.status_code == 200, response.text
    assert response.json['status'] == 'ok'
    assert len(commands) == 1
    command = shlex.split(commands[0])
    assert command[:3] == ['sudo', 'mv', '-f']
    assert command[4] == f'{WAF_DIRS[service]}/waf/rules/test.conf'
    if action == 'save':
        assert len(command) == 5
    elif docker == '1':
        docker_action = ['kill', '-s', 'HUP'] if action == 'reload' else [action]
        assert command[5:] == ['&&', 'sudo', 'docker', *docker_action, 'custom-waf-container', '>', '/dev/null']
    else:
        assert command[5:] == ['&&', 'sudo', 'systemctl', action, target]
    assert sentinel.read_text() == 'unrelated baseline'
    assert not list(product.root.glob('waf-save-*'))


@pytest.mark.parametrize('failure', ['upload', 'apply', 'cleanup'])
def test_failed_save_is_not_success_and_cleans_only_its_files(product_client, product, waf_rules, monkeypatch, failure):
    uploads, commands = [], []
    sentinel = product.root / 'another-editor.old'
    sentinel.write_text('unrelated baseline')

    def upload(server, remote, local):
        uploads.append((remote, Path(local)))
        if failure == 'upload':
            raise OSError('synthetic upload failure')

    def ssh(server, command, **kwargs):
        commands.append(shlex.split(command))
        if not command.startswith('sudo rm') or failure == 'cleanup':
            raise OSError('synthetic remote failure')
        return ''

    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(config.server_mod, 'ssh_command', ssh)
    response = product_client.post(f'/waf/haproxy/{product.server.ip}/rule/{waf_rules["haproxy"].id}/save',
                                   json={'action': 'restart', 'config': '# candidate', 'oldconfig': str(sentinel)})
    assert response.status_code == 500, response.text
    assert response.json['status'] == 'failed'
    assert 'did not complete' in response.json['error']
    assert len(uploads) == 1 and not uploads[0][1].exists()
    assert commands[-1] == ['sudo', 'rm', '-f', '--', uploads[0][0]]
    assert sentinel.read_text() == 'unrelated baseline'
    assert not list(product.root.glob('waf-save-*'))


def test_failed_replica_save_does_not_report_success(product_client, product, waf_rules, monkeypatch):
    product.other.master = product.server.server_id
    product.other.save()
    calls = []

    def upload(server, *args, **kwargs):
        calls.append(server)
        raise OSError('synthetic replica failure')

    monkeypatch.setattr(config, 'upload_and_restart', upload)
    response = product_client.post(f'/waf/haproxy/{product.server.ip}/rule/{waf_rules["haproxy"].id}/save',
                                   json={'action': 'save', 'config': '# candidate'})
    assert response.status_code == 500 and response.json['status'] == 'failed'
    assert calls == [product.other.ip]
    assert not list(product.root.glob('waf-save-*'))


def test_waf_test_action_is_rejected_before_io(product_client, product, waf_rules, forbid_waf_io):
    response = product_client.post(f'/waf/haproxy/{product.server.ip}/rule/{waf_rules["haproxy"].id}/save',
                                   json={'action': 'test', 'config': '# candidate'})
    assert response.status_code == 400


def test_nginx_restart_restriction_is_checked_before_upload(product_client, product, waf_rules, monkeypatch):
    ServiceSetting.create(server_id=11, service='nginx', setting='restart', value='1')
    monkeypatch.setattr(config, 'upload', lambda *a: pytest.fail('Uploaded despite restart restriction'))
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    response = product_client.post(f'/waf/nginx/{product.server.ip}/rule/{waf_rules["nginx"].id}/save',
                                   json={'action': 'restart', 'config': '# candidate'})
    assert response.status_code == 500 and response.json['status'] == 'failed'
