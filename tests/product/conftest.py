"""Product scenarios use real routes, authentication, templates and a fresh database."""
from dataclasses import replace
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
from types import SimpleNamespace

import pytest
from peewee import Model

from app import cache, initialize_database
from app.modules.db import db_model as models
from app.modules.db.migration_manager import Migration
from app.modules.roxywi import common, roxy
from app.modules.roxywi import waf, waf_rule_file
from app.modules.config import config, candidate
from app.modules.server.ssh import crypt_password
from app.modules.common.time import utc_now
from tests.fixtures.certificate_runtime import Runtime, make_pem
from app.modules.service import certificates
from app.scripts import certificate_remote


@pytest.fixture
def product(app, tmp_path, monkeypatch):
    path = tmp_path / 'product.db'
    monkeypatch.setenv('ROXYWI_DB_PATH', str(path))
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path / 'lib'))
    monkeypatch.setenv('ROXYWI_LOG_STORE_PATH', str(tmp_path / 'journal'))
    monkeypatch.setenv('ROXYWI_LOG_STORE_ENABLED', '1')
    monkeypatch.setenv('ROXYWI_LOG_PATH', str(tmp_path / 'legacy'))
    monkeypatch.setattr(models, 'database_settings', replace(models.database_settings, sqlite_path=str(path)))
    database = models.connect()
    bound = [value for value in vars(models).values()
             if isinstance(value, type) and issubclass(value, Model) and value is not Model]
    # Only the external subscription service is replaced. Login, roles and group
    # checks read the real database on every request, including after a role change.
    monkeypatch.setattr(roxy, 'update_plan', lambda: None)
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 1, 'user_plan': 'support'})
    with database.bind_ctx([*bound, Migration], bind_refs=False, bind_backrefs=False):
        cache.clear()
        initialize_database()
        models.Cred.create(id=11, name='Product SSH', username='operator', group_id=1,
                           key_enabled=0, password=crypt_password('SyntheticSSHPassword!'))
        server = models.Server.create(server_id=11, hostname='Product HAProxy', ip='192.0.2.11',
                                      group_id='1', cred_id=11, haproxy=1, nginx=1, description='Product fixture')
        models.Groups.create(group_id=2, name='Other team')
        other = models.Server.create(server_id=22, hostname='Other team private server', ip='192.0.2.22',
                                     group_id='2', cred_id=11, haproxy=1, description='Private')
        admin = models.User.get(models.User.username == 'admin')
        yield SimpleNamespace(db=database, server=server, other=other, admin=admin, root=tmp_path)
        cache.clear()
        database.close()


@pytest.fixture
def product_client(client, product):
    response = client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin'})
    assert response.status_code == 200, response.get_data(as_text=True)
    client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
    client.environ_base['HTTP_ACCEPT'] = 'application/json'
    return client


@pytest.fixture
def certificate_host(product, monkeypatch):
    state = Runtime(product.root, monkeypatch)
    state.old, state.new = make_pem(1), make_pem(2)
    state.add(product.server.ip, state.old)
    state.failed_hosts = set()
    state.stored_on = []
    if os.name == 'nt':
        # Expose POSIX URLs while the synthetic managed hosts use Windows temporary files.
        encode_path = certificates.encode_file_path
        monkeypatch.setattr(certificates, 'encode_file_path', lambda path: encode_path('/' + Path(path).as_posix()))
    monkeypatch.setattr(certificates, 'deployment_settings',
                        lambda server, name, **kw: dict(state.settings(server.ip), pem_name=name or 'site.pem'))

    def request(server, data):
        if server.ip in state.failed_hosts and data['operation'] == 'deploy':
            raise certificates.CertificateError('Target failed', 'remote_failed')
        try:
            if data.get('path') and os.name == 'nt':
                data = dict(data, path=str(Path(data['path'].lstrip('/'))))
            if data.get('destination'):
                # Synthetic hosts share runtime paths but have isolated filesystem roots.
                destination = dict(data['destination'])
                master_folder = str(state.files[product.server.ip].parent)
                destination['path'] = destination['path'].replace(master_folder, str(state.files[server.ip].parent), 1)
                data = dict(data, destination=destination)
            if data['operation'] == 'store':
                state.stored_on.append(server.ip)
                return certificate_remote.store_file(dict(data, cert_dir=str(state.files[server.ip].parent)))
            if data['operation'] in ('catalog', 'read-file', 'remove-file') and data.get('runtime') is False:
                data = dict(data, cert_dir=str(state.files[server.ip].parent))
            return {'catalog': certificate_remote.catalog, 'deploy': certificate_remote.deploy,
                    'check-new': certificate_remote.creation_preflight,
                    'read-file': certificate_remote.read_file, 'remove-file': certificate_remote.remove_file,
                    'rollback': certificate_remote.finish_deployment,
                    'commit': certificate_remote.finish_deployment}[data['operation']](data)
        except certificate_remote.CertificateFailure as error:
            raise certificates.CertificateError('Certificate operation failed', error.code) from None
    monkeypatch.setattr(certificates, 'remote', request)
    return state


@pytest.fixture
def service_worker_controls(product, monkeypatch):
    """Remote heartbeats are real database rows; local packages are absent."""
    now = utc_now()
    for service in ('checker', 'metrics'):
        models.WorkerState.create(worker_id='remote-' + service, service=service, hostname='remote-worker',
                                  status='running', group_ids=[1], last_heartbeat=now,
                                  expires_at=now + timedelta(minutes=5))
    state = SimpleNamespace(local_installed=False, commands=[])

    def local_command(command):
        state.commands.append(command)
        # Checker/Metrics must never be gated on the web host's RPM/APT state.
        assert 'roxy-wi-checker' not in command and 'roxy-wi-metrics' not in command
        if 'keep_alive.py' in command:
            return ['0'], ''
        assert 'roxy-wi-keep_alive' in command or 'roxy-wi-keep-alive' in command
        return (['1.0'] if state.local_installed else []), ''

    monkeypatch.setattr('app.routes.service.routes.server_mod.subprocess_execute', local_command)
    return state


@pytest.fixture
def waf_creation(product, monkeypatch):
    """Real remote file operation on isolated files; replace only SSH transport."""
    state = SimpleNamespace(commands=[], roots={}, fail_before=False, lose_response=False, failed_hosts=set())
    for service in ('haproxy', 'nginx'):
        root = product.root / service / 'waf'
        (root / 'rules').mkdir(parents=True)
        (root / 'modsecurity.conf').write_text('SecRuleEngine On\n', encoding='utf-8')
        (root / 'waf.conf').write_text('Include ' + json.dumps(str(root / 'modsecurity.conf')) + '\n', encoding='utf-8')
        state.roots[service] = root
        models.Setting.update(value=f'/srv/{service} custom').where(
            models.Setting.param == f'{service}_dir', models.Setting.group_id == 1).execute()
    models.Setting.update(value=str(product.root)).where(
        models.Setting.param == 'tmp_config_path', models.Setting.group_id == 1).execute()

    state.host_roots = {product.server.ip: state.roots}

    def add_server(server):
        roots = {}
        for service, source in state.roots.items():
            root = product.root / server.ip / service / 'waf'
            shutil.copytree(source, root)
            for path in root.rglob('*.conf'):
                path.write_text(path.read_text().replace(str(source).replace('\\', '\\\\'),
                                                         str(root).replace('\\', '\\\\')))
            roots[service] = root
        (roots['nginx'].parent / 'nginx.conf').write_text('# nginx main\n')
        state.host_roots[server.ip] = roots
        return roots

    state.add_server = add_server

    def local_path(remote, server):
        for service, root in state.host_roots[server].items():
            prefix = f'/srv/{service} custom/waf/'
            if remote.startswith(prefix):
                return root.joinpath(*PurePosixPath(remote[len(prefix):]).parts)
        pytest.fail(f'Unexpected WAF path: {remote}')

    def ssh(server, command, **kwargs):
        assert server in state.host_roots
        assert kwargs['rc'] == 1
        assert kwargs['timeout'] > 30
        tokens = shlex.split(command)
        assert tokens[:5] == ['sudo', '-n', 'flock', '-w', '30']
        assert tokens[6:8] == ['python3', '-c']
        assert tokens[8] == Path(waf_rule_file.__file__).read_text(encoding='utf-8')
        state.commands.append((server, tokens[9:]))
        if state.fail_before or server in state.failed_hosts:
            raise OSError('synthetic SSH failure')
        def path(remote):
            return local_path(remote, server)
        result = {'status': 'ok'}
        try:
            if tokens[9] == 'inspect-ids':
                result['ids'] = waf_rule_file.inspect_rule_ids(path(tokens[10]), path(tokens[11]))
            elif tokens[9] == 'create-before':
                waf_rule_file.create_rule(path(tokens[10]), path(tokens[11]), tokens[12], before_rules=True)
            elif tokens[9] == 'read-mode':
                result['mode'] = waf_rule_file.read_mode(path(tokens[10]))
            elif tokens[9] == 'set-mode':
                waf_rule_file.set_mode(path(tokens[10]), tokens[11])
                result['mode'] = tokens[11]
            elif tokens[9] == 'delete':
                waf_rule_file.delete_rule(path(tokens[10]), path(tokens[11]))
            elif tokens[9] == 'toggle':
                enabled = int(tokens[-1])
                waf_rule_file.switch_rule(path(tokens[-3]), path(tokens[-2]), enabled)
                result['enabled'] = enabled
            else:
                waf_rule_file.create_rule(path(tokens[-3]), path(tokens[-2]), tokens[-1])
        except waf_rule_file.RuleConflict:
            return json.dumps({'status': 'conflict'})
        if state.lose_response:
            state.lose_response = False
            raise OSError('synthetic lost SSH response')
        return json.dumps(result)

    @contextmanager
    def connect(server):
        assert server in state.host_roots

        def download(remote, local):
            if server in state.failed_hosts:
                raise OSError('synthetic SFTP failure')
            Path(local).write_bytes(local_path(remote, server).read_bytes())

        yield SimpleNamespace(get_sftp=download)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', connect)
    return state


@pytest.fixture
def wizard_host(waf_applying):
    for service, root in waf_applying.roots.items():
        crs = root / 'rules/crs.conf'
        crs.write_text('SecRule ARGS "attack" "id:942100,phase:2,deny"\n')
        entry = root / ('waf.conf' if service == 'nginx' else 'modsecurity.conf')
        entry.write_text(entry.read_text() + 'Include ' + json.dumps(str(crs)) + '\n')
    return waf_applying


@pytest.fixture
def waf_cluster(product, wizard_host):
    slave = models.Server.create(server_id=33, hostname='Product Slave', ip='192.0.2.33', group_id='1',
                                 cred_id=11, haproxy=1, nginx=1, master=product.server.server_id)
    return slave, wizard_host.add_server(slave)


@pytest.fixture
def waf_modes(waf_creation, product, monkeypatch):
    models.Waf.create(server_id=product.server.server_id, metrics=0)
    models.WafNginx.create(server_id=product.server.server_id)
    ssh = waf.server_mod.ssh_command
    waf_creation.diagnostics = {
        'haproxy': dict(status='ok', process='running', check='ready', module='not_applicable', error=''),
        'nginx': dict(status='ok', process='running', check='valid', module='enabled', error=''),
    }
    waf_creation.diagnostic_error = None

    def command(server, command, **kwargs):
        tokens = shlex.split(command)
        if len(tokens) > 8 and tokens[8] == candidate.remote_source():
            spec = json.loads(tokens[-1])
            assert spec['action'] == 'status' and not spec['candidate'] and not spec['action_command']
            assert server == product.server.ip
            assert kwargs['rc'] == 1 and kwargs['timeout'] == 90
            if waf_creation.diagnostic_error:
                raise waf_creation.diagnostic_error
            return json.dumps(waf_creation.diagnostics[spec['service'].removesuffix('_waf')])
        return ssh(server, command, **kwargs)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', command)
    return waf_creation


@pytest.fixture
def waf_switching(waf_creation, product):
    state = waf_creation
    state.rules = {}
    state.entrypoints = {}
    for service, root in state.roots.items():
        rule = models.WafRules.create(serv=product.server.ip, service=service, rule_name='Test rule',
                                      rule_file='test.conf', en=1)
        path = root / 'rules/test.conf'
        path.write_text('# customer rule content\n', encoding='utf-8')
        entrypoint = root / ('waf.conf' if service == 'nginx' else 'modsecurity.conf')
        waf_rule_file.switch_rule(entrypoint, path, 1)
        state.rules[service] = rule
        state.entrypoints[service] = entrypoint
    return state


@pytest.fixture
def waf_applying(waf_modes, product, monkeypatch):
    """Execute file operations and apply transactions; simulate only host processes."""
    state = waf_modes
    state.apply_calls, state.uploads, state.apply_hosts = [], {}, []
    state.lost_apply_hosts, state.failed_apply_hosts = set(), set()
    state.valid, state.ready, state.action_failed = True, True, False
    state.apply_disconnected, state.apply_lost, state.apply_response = False, False, None
    state.pid, state.clock = 1, 0
    main = state.roots['nginx'].parent / 'nginx.conf'
    main.write_text('# nginx main\n')
    models.Setting.update(value='/srv/nginx custom/nginx.conf').where(
        models.Setting.param == 'nginx_config_path', models.Setting.group_id == 1).execute()
    original_ssh = waf.server_mod.ssh_command

    def upload(server, remote, local):
        staged = product.root / ('upload-' + Path(remote).name)
        shutil.copyfile(local, staged)
        state.uploads[remote] = staged

    def ssh(server, command, **kwargs):
        tokens = shlex.split(command)
        if tokens[:3] == ['sudo', 'rm', '-f']:
            if tokens[-1] in state.uploads:
                state.uploads[tokens[-1]].unlink(missing_ok=True)
            return ''
        if len(tokens) < 9 or tokens[8] != candidate.remote_source():
            return original_ssh(server, command, **kwargs)
        if json.loads(tokens[-1])['action'] == 'status':
            return original_ssh(server, command, **kwargs)
        assert server in state.host_roots
        assert kwargs['rc'] == 1 and kwargs['timeout'] == candidate.REMOTE_TIMEOUT
        spec = json.loads(tokens[-1])
        state.apply_calls.append(spec.copy())
        state.apply_hosts.append(server)
        if state.apply_disconnected or server in state.failed_apply_hosts:
            raise OSError('synthetic apply connection failure')
        service = spec['service'].removesuffix('_waf')
        root = state.host_roots[server][service]
        spec.update(target=str(root / ('modsecurity.conf' if spec.get('apply_only') else 'rules/' + PurePosixPath(spec['target']).name)),
                    main=str(root.parent / 'nginx.conf' if service == 'nginx' else root / 'modsecurity.conf'))
        if spec['candidate']:
            spec['candidate'] = str(state.uploads[spec['candidate']])
        result = candidate.execute(spec)
        if state.apply_lost or server in state.lost_apply_hosts:
            state.apply_lost = False
            state.lost_apply_hosts.discard(server)
            raise OSError('synthetic lost apply response')
        return state.apply_response if state.apply_response is not None else json.dumps(result)

    def run(arguments, **kwargs):
        if arguments[:2] == ['systemctl', 'show']:
            return SimpleNamespace(returncode=0, stdout=b'loaded')
        if arguments[0] == 'nginx':
            return SimpleNamespace(returncode=int(not state.valid), stdout=b'')
        assert arguments[:2] == ['sh', '-c']
        state.pid += 1
        return SimpleNamespace(returncode=int(state.action_failed), stdout=b'')

    def tick(seconds):
        state.clock += seconds

    monkeypatch.setattr(config, 'upload', upload)
    monkeypatch.setattr(waf.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(candidate, '_run', run)
    monkeypatch.setattr(candidate._HaproxyWafValidator, 'process_id', lambda _: state.pid)
    monkeypatch.setattr(candidate._HaproxyWafValidator, 'listener_port', lambda *a: 12345)
    monkeypatch.setattr(candidate._HaproxyWafValidator, 'ready', lambda *a: state.ready)
    monkeypatch.setattr(candidate, 'time', SimpleNamespace(monotonic=lambda: state.clock, sleep=tick))
    monkeypatch.setattr(config, 'normalize_config_file', lambda _: None)
    return state
