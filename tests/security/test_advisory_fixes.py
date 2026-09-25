import json
import logging
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g
from flask_jwt_extended import create_access_token

from app.modules.config import common as config_common, config as config_mod
from app.modules.roxywi import auth, common, logger, log_snapshot
from app.modules.roxywi.class_models import SSLCertUploadRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound
from app.modules.service import action, common as service_common, haproxy
from app.routes.add import routes as add_routes
from app.routes.waf import routes as waf_routes

pytestmark = pytest.mark.security


@pytest.fixture
def actor(app, monkeypatch):
    params = dict(user_id=1, user='test', role=4, group_id=1, lang='en', servers=[], user_services=[])
    monkeypatch.setattr(common, 'get_users_params', lambda **_: dict(params))
    monkeypatch.setattr(auth, 'is_admin', lambda level=1, **_: params['role'] <= level)
    monkeypatch.setattr(auth, 'is_access_permit_to_service', lambda _: True)
    monkeypatch.setattr(common, 'check_user_group_for_flask', lambda: True)
    def server(ip):
        if ip == '192.0.2.99':
            raise RoxywiResourceNotFound()
        return SimpleNamespace(server_id=1, ip=ip, group_id=2 if ip == '192.0.2.20' else 1)
    monkeypatch.setattr(common.server_sql, 'get_server_by_ip', server)
    monkeypatch.setattr(common.server_sql, 'get_server', lambda _: server('192.0.2.10'))
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return params, {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('target', ['192.0.2.20', '192.0.2.99'])
def test_stats_rejects_unmanaged_or_other_group_before_http(client, actor, monkeypatch, service, target):
    monkeypatch.setattr(haproxy.requests, 'post', lambda *a, **k: pytest.fail('HTTP credentials escaped'))
    monkeypatch.setattr(service_common.requests, 'get', lambda *a, **k: pytest.fail('HTTP credentials escaped'))
    response = client.get(f'/stats/view/{service}/{target}', headers=actor[1])
    assert response.status_code == 403


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('role,target', [(4, '192.0.2.10'), (1, '192.0.2.20')])
def test_stats_registered_targets_do_not_follow_redirects(app, actor, monkeypatch, service, role, target):
    calls = []
    actor[0]['role'] = role
    monkeypatch.setattr(haproxy.sql, 'get_setting', lambda *a, **k: 'test')
    monkeypatch.setattr(service_common, 'render_template', lambda *a, **k: 'stats')
    monkeypatch.setattr(common, 'get_user_lang_for_flask', lambda: {})
    def http(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(content=b'stats', status_code=302, headers={'Location': 'http://192.0.2.99/'})
    monkeypatch.setattr(haproxy.requests, 'post', http)
    monkeypatch.setattr(service_common.requests, 'get', http)
    with app.test_request_context('/'):
        g.user_params = actor[0]
        if service == 'haproxy':
            haproxy.stat_page_action(target, 1)
        else:
            service_common.get_stat_page(target, service, 1)
    assert calls[0][0].startswith(f'http://{target}:')
    assert calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['auth'] == ('test', 'test')


@pytest.mark.parametrize('method', ['POST', 'PUT', 'DELETE'])
def test_guest_cannot_mutate_maps(client, actor, monkeypatch, method):
    for name in ('create_map', 'save_map', 'delete_map'):
        monkeypatch.setattr(add_routes.add_mod, name, lambda *a, **k: pytest.fail('Map mutated'))
    response = client.open('/add/map', method=method, headers=actor[1], data={'serv': '192.0.2.10', 'map_name': 'test.map'})
    assert response.status_code == 403


@pytest.mark.parametrize('role', [1, 2, 3])
@pytest.mark.parametrize('method,helper', [('POST', 'create_map'), ('PUT', 'save_map'), ('DELETE', 'delete_map')])
def test_map_writers_keep_access(client, actor, monkeypatch, role, method, helper):
    actor[0]['role'] = role
    calls = []
    monkeypatch.setattr(add_routes.add_mod, helper, lambda *a: calls.append(a) or 'ok')
    response = client.open('/add/map', method=method, headers=actor[1], data={'serv': '192.0.2.10', 'map_name': 'test.map'})
    assert response.status_code in (200, 201)
    assert len(calls) == 1


def test_guest_can_read_map(client, actor, monkeypatch):
    monkeypatch.setattr(add_routes.add_mod, 'edit_map', lambda *a: 'existing map')
    assert client.get('/add/map?map_name=test.map', headers=actor[1]).get_data(as_text=True) == 'existing map'


@pytest.mark.parametrize('method,url', [('POST', '/add/cert/add'), ('DELETE', '/add/cert/1/test.pem')])
def test_guest_cannot_mutate_certificates(client, actor, monkeypatch, method, url):
    for name in ('upload_ssl_cert', 'del_ssl_cert'):
        monkeypatch.setattr(add_routes.add_mod, name, lambda *a: pytest.fail('Certificate mutated'))
    response = client.open(url, method=method, headers=actor[1], json={'server_ip': '192.0.2.10', 'name': 'test', 'cert': 'synthetic'})
    assert response.status_code == 403


@pytest.mark.parametrize('name', ['<img src=x onerror=alert(1)>', '../test', 'test\nname', 'test/name', "test' onclick='alert(1)"])
def test_certificate_upload_rejects_html_and_paths(name):
    with pytest.raises(ValueError):
        SSLCertUploadRequest(server_ip='192.0.2.10', name=name, cert='synthetic')


def test_certificate_upload_accepts_domain_names():
    assert SSLCertUploadRequest(server_ip='192.0.2.10', name='example.com-2026', cert='synthetic').name == 'example.com-2026'


@pytest.mark.parametrize('verb', ['restart\ntouch /tmp/marker', 'reload\r\nwhoami', 'restart;id', 'reload | id', '', None, 'save'])
def test_service_actions_reject_shell_fragments_before_settings(monkeypatch, verb):
    monkeypatch.setattr(action.service_sql, 'select_service_setting', lambda *a: pytest.fail('Settings read before action validation'))
    with pytest.raises(ValueError):
        action.get_action_command('waf', verb, 1)


@pytest.mark.parametrize('docker', ['0', '1'])
@pytest.mark.parametrize('verb', ['start', 'stop', 'restart', 'reload'])
def test_service_action_commands_preserve_valid_verbs(monkeypatch, docker, verb):
    monkeypatch.setattr(action.service_sql, 'select_service_setting', lambda *a: docker)
    monkeypatch.setattr(action.sql, 'get_setting', lambda *a: 'waf')
    monkeypatch.setattr(action.service_common, 'get_correct_service_name', lambda *a: 'waf')
    expected = ('kill -s HUP' if verb == 'reload' else verb) if docker == '1' else verb
    assert action.get_action_command('waf', verb, 1) == (f'sudo docker {expected} waf > /dev/null' if docker == '1' else f'sudo systemctl {verb} waf')


@pytest.mark.parametrize('json_request', [False, True])
@pytest.mark.parametrize('verb', ['restart\ntouch /tmp/marker', 'reload;id', None])
def test_waf_rejects_actions_before_writing(client, actor, monkeypatch, json_request, verb):
    actor[0]['role'] = 2
    monkeypatch.setattr(waf_routes.roxywi_common, 'check_is_server_in_group', lambda *a: None)
    monkeypatch.setattr(waf_routes.config_mod, 'master_slave_upload_and_restart', lambda *a, **k: pytest.fail('WAF uploaded'))
    data = {'serv': '192.0.2.10', 'config': 'synthetic', 'config_file_name': 'test.conf', ('action' if json_request else 'save'): verb}
    response = client.post('/waf/haproxy/192.0.2.10/rule/1/save', headers=actor[1], **({'json': data} if json_request else {'data': data}))
    assert response.status_code == 400


@pytest.mark.parametrize('json_request', [False, True])
@pytest.mark.parametrize('verb', ['save', 'reload', 'restart'])
def test_waf_legitimate_save_contract(client, actor, monkeypatch, tmp_path, json_request, verb):
    actor[0]['role'] = 2
    calls = []
    monkeypatch.setattr(waf_routes.roxywi_common, 'check_is_server_in_group', lambda *a: None)
    monkeypatch.setattr(waf_routes.roxy_wi_tools, 'GetDate', lambda *_: SimpleNamespace(return_date=lambda _: '2026-09-22'))
    monkeypatch.setattr(waf_routes.sql, 'get_setting', lambda name, **k: 'UTC' if name == 'time_zone' else str(tmp_path) + '/')
    monkeypatch.setattr(waf_routes.common, 'resolve_waf_config_path', lambda *a: '/etc/waf/test.conf')
    monkeypatch.setattr(waf_routes.config_mod, 'master_slave_upload_and_restart', lambda *a, **k: calls.append(a) or 'saved')
    data = {'config': 'synthetic', 'config_file_name': 'test.conf', ('action' if json_request else 'save'): verb}
    response = client.post('/waf/haproxy/192.0.2.10/rule/1/save', headers=actor[1], **({'json': data} if json_request else {'data': data}))
    assert response.status_code == 200
    assert calls, response.get_data(as_text=True)
    assert calls[0][2] == verb
    assert Path(calls[0][1]).read_text() == 'synthetic'
    if json_request:
        assert response.json['data'] == 'saved'


@pytest.mark.parametrize('target', ['192.0.2.99', '192.0.2.20', '192.0.2.10;id', '192.0.2.10$(id)'])
def test_log_target_cannot_inject_or_cross_groups(client, actor, monkeypatch, target):
    monkeypatch.setattr(log_snapshot.ssh_mod, 'ssh_connect', lambda *a, **k: pytest.fail('Unauthorized SSH connection'))
    response = client.post('/logs/query/haproxy', data={
        'server': target, 'file': 'haproxy.log', 'relative': 3600,
    }, headers=actor[1])
    assert response.status_code == 403 or 'Invalid managed server address' in response.get_data(as_text=True)


@pytest.mark.parametrize('central', [0, 1])
def test_guest_log_read_preserves_target_and_filters(client, actor, monkeypatch, central):
    hosts, commands = [], []
    monkeypatch.setattr(log_snapshot.sql, 'get_setting', lambda key: {'syslog_server_enable': central, 'syslog_server': '192.0.2.30', 'haproxy_path_logs': '/var/log/haproxy'}[key])
    timestamp = datetime.now(timezone.utc).isoformat()
    content = ''.join(json.dumps({'timestamp': timestamp, 'message': message}) + '\n'
                      for message in ('keep this', 'keep but drop', 'other')).encode()

    class Connection:
        def __enter__(self):
            return SimpleNamespace(ssh=self)

        def __exit__(self, *_):
            return False

        def exec_command(self, command, **kwargs):
            commands.append(command)
            stdout = BytesIO(content)
            stdout.channel = SimpleNamespace(recv_exit_status=lambda: 0)
            return BytesIO(), stdout, BytesIO()

    def connect(host, **kwargs):
        hosts.append(host)
        return Connection()

    monkeypatch.setattr(log_snapshot.ssh_mod, 'ssh_connect', connect)
    response = client.post('/logs/query/haproxy', data={
        'server': '192.0.2.10', 'file': 'haproxy.log', 'relative': 3600, 'search': 'keep', 'exclude': 'drop',
    }, headers=actor[1])
    assert response.status_code == 200
    assert [json.loads(entry['text'])['message'] for entry in response.json['entries']] == ['keep this']
    assert hosts == ['192.0.2.30' if central else '192.0.2.10']
    assert ('/var/log/192.0.2.10/syslog.log' if central else '/var/log/haproxy/haproxy.log') in commands[0]


@pytest.mark.parametrize('kind', ['absolute', 'traversal', 'foreign', 'symlink'])
def test_baseline_rejects_file_disclosure_before_upload(tmp_path, monkeypatch, kind):
    configs = tmp_path / 'configs'
    configs.mkdir()
    secret = tmp_path / 'secret.cfg'
    secret.write_text('synthetic-secret')
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(configs))
    monkeypatch.setattr(config_common.config_sql, 'config_version_exists', lambda *a: False)
    paths = {'absolute': str(secret), 'traversal': '../secret.cfg', 'foreign': str(configs / '192.0.2.20-date.cfg.old')}
    if kind == 'symlink':
        link = configs / '192.0.2.10-date.cfg.old'
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip('Symlink creation requires OS privileges')
        paths[kind] = str(link)
    monkeypatch.setattr(config_mod, 'upload', lambda *a: pytest.fail('Uploaded before checking baseline'))
    for upload in (config_mod.upload_and_restart, config_mod.master_slave_upload_and_restart):
        with pytest.raises(ValueError):
            upload('192.0.2.10', 'unused', 'reload', 'haproxy', oldcfg=paths[kind])
    with pytest.raises(ValueError):
        config_mod._prepare_config_version_diff('192.0.2.10', 'haproxy', 'unused', 'unused', paths[kind], 'unused')


def test_valid_and_missing_baselines_preserve_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(tmp_path))
    old = Path(config_common.generate_config_path('haproxy', '192.0.2.10') + '.old')
    candidate = tmp_path / '192.0.2.10-next.cfg'
    old.write_text('before\n')
    candidate.write_text('after\n')
    def download(server, path, **kwargs):
        Path(path).write_text('downloaded\n')
    monkeypatch.setattr(config_mod, 'get_config', download)
    for baseline, expected in [(str(old), '-before'), ('192.0.2.10-2026-09-22.120000.cfg.old', '-downloaded'), (None, '-downloaded')]:
        diff = config_mod._prepare_config_version_diff('192.0.2.10', 'haproxy', '/etc/haproxy/haproxy.cfg', str(candidate), baseline, str(tmp_path / 'download'))
        assert expected in diff and '+after' in diff


def test_save_and_test_do_not_generate_service_verbs(monkeypatch):
    monkeypatch.setattr(config_mod.sql, 'get_setting', lambda *a: 'test')
    monkeypatch.setattr(config_mod.service_sql, 'select_service_setting', lambda *a: '0')
    monkeypatch.setattr(config_mod.service_action, 'get_action_command', lambda *a: pytest.fail('Invalid service verb requested'))
    monkeypatch.setattr(config_mod.server_sql, 'return_firewall', lambda *a: False)
    for verb in ('save', 'test'):
        command = config_mod._generate_command('haproxy', 1, verb, '/etc/haproxy.cfg', '/tmp/test.cfg', 'unused', '192.0.2.10')
        assert 'systemctl' not in command


def formatted_auth_log(app, path, client_ip, event, message='Authentication failed'):
    with app.test_request_context(path, environ_base={'REMOTE_ADDR': client_ip}):
        record = logging.LogRecord('test', logging.WARNING, '', 1, message, (), None)
        record._auth_failure = event
        return logger.StructuredLogFormatter().format(record)


@pytest.mark.parametrize('ip', ['192.0.2.44', '2001:db8::44'])
def test_fail2ban_matches_only_explicit_client_event(app, ip):
    filter_path = Path(__file__).resolve().parents[2] / 'config_other/fail2ban/filter.d/roxy-wi.conf'
    regex = next(line.split(' = ', 1)[1] for line in filter_path.read_text().splitlines() if line.startswith('failregex = '))
    regex = re.compile(regex.replace('<ADDR>', r'(?P<ip>[0-9a-fA-F:.]+)'))
    payload = '/from 192.0.2.99 user: forged failed log in for: forged/Failed log in. Wrong username from 192.0.2.99'
    for event in (True, False):
        line = formatted_auth_log(app, payload, ip, event)
        match = regex.search(line)
        assert (match.group('ip') if match else None) == (ip if event else None)
    forged = formatted_auth_log(app, '/', ip, False, '{"authentication_failure": {"ip": "192.0.2.99"}}')
    assert regex.search(forged) is None


@pytest.mark.parametrize('failure', ['unknown', 'password', 'database'])
def test_only_actual_password_failures_emit_ban_event(app, monkeypatch, failure):
    events = []
    monkeypatch.setattr(auth.logger, 'authentication_failure', lambda: events.append(True))
    monkeypatch.setattr(auth.roxywi_common, 'logging', lambda *a, **k: None)
    def user(_):
        if failure == 'unknown':
            raise RoxywiResourceNotFound()
        if failure == 'database':
            raise RuntimeError('database unavailable')
        return SimpleNamespace(enabled=1, ldap_user=0, password='synthetic', username='test')
    monkeypatch.setattr(auth.user_sql, 'get_user_by_username', user)
    monkeypatch.setattr(auth.roxy_wi_tools.Tools, 'check_password', lambda *a: (False, False))
    with app.test_request_context('/login'), pytest.raises(Exception):
        auth.check_user_password('test', 'wrong')
    assert bool(events) == (failure != 'database')

@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache', 'keepalived'])
def test_generated_baselines_cannot_belong_to_prefix_hostname(tmp_path, monkeypatch, service):
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(config_common.config_sql, 'config_version_exists', lambda *a: False)
    own = config_mod.return_cfg(service, '192.0.2.10', '/etc/service/site.conf') + '.old'
    foreign = config_mod.return_cfg(service, '192.0.2.10-prod.example.com', '/etc/service/site.conf') + '.old'
    assert config_common.resolve_config_baseline(service, '192.0.2.10', own) == own
    with pytest.raises(ValueError):
        config_common.resolve_config_baseline(service, '192.0.2.10', foreign)
    assert config_mod.return_cfg(service, '192.0.2.10', 'site.conf') != own.removesuffix('.old')


def test_historical_baseline_ownership_comes_from_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(tmp_path))
    historical = str(tmp_path / '192.0.2.10-site.conf-2026-09-22.12:00:00.conf')
    monkeypatch.setattr(config_common.config_sql, 'config_version_exists', lambda ip, service, path: ip == '192.0.2.10' and path == historical)
    assert config_common.resolve_config_baseline('nginx', '192.0.2.10', historical) == historical
    with pytest.raises(ValueError):
        config_common.resolve_config_baseline('nginx', '192.0.2.1', historical)


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_new_config_form_has_no_fabricated_baseline(app, service):
    from flask import render_template
    with app.test_request_context('/'):
        g.user_params = {'role': 3, 'servers': [(1, 'server', '192.0.2.10')]}
        html = render_template('config.html', lang='en', service=service,
            service_desc=SimpleNamespace(service=service), serv='192.0.2.10', action='',
            config=' ', cfg='', config_file_name='/etc/service/new.conf',
            remote_config_path='/etc/service/new.conf', stderr='', error='', is_serv_protected=False,
            is_restart=0, user_subscription={'user_status': 1, 'user_plan': 'support'},
            direct_deployment_allowed=True, change_center_creation_allowed=True)
    assert 'value="" name="config_local_path"' in html
    assert 'value=".old" name="config_local_path"' not in html


@pytest.mark.parametrize('expired', [False, True])
def test_expired_session_does_not_emit_ban_event(client, app, monkeypatch, expired):
    from datetime import timedelta
    events = []
    monkeypatch.setattr(logger, 'authentication_failure', lambda: events.append(True))
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'}, expires_delta=timedelta(seconds=-1)) if expired else 'invalid.jwt.signature'
    response = client.get('/stats/view/haproxy/192.0.2.10', headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
    assert response.status_code == 401
    assert bool(events) == (not expired)

@pytest.mark.parametrize('baseline', ['../secret.cfg', '192.0.2.10-prod.example.com-2026-09-22.120000.cfg.old'])
def test_section_save_rejects_unowned_baseline_before_reading(client, actor, monkeypatch, tmp_path, baseline):
    from app.routes.config import routes
    actor[0]['role'] = 3
    monkeypatch.setattr(config_common, 'get_config_dir', lambda _: str(tmp_path))
    monkeypatch.setattr(config_common.config_sql, 'config_version_exists', lambda *a: False)
    monkeypatch.setattr(routes.section_mod, 'rewrite_section', lambda *a: pytest.fail('Untrusted baseline read'))
    response = client.post('/config/section/haproxy/192.0.2.10/save', headers=actor[1], json={
        'config': 'listen test', 'oldconfig': baseline, 'action': 'reload', 'start_line': '0', 'end_line': '1',
    })
    assert response.status_code == 400
