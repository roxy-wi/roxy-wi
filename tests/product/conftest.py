"""Product scenarios use real routes, authentication, templates and a fresh database."""
from dataclasses import replace
from contextlib import contextmanager
import json
from pathlib import Path, PurePosixPath
import shlex
from types import SimpleNamespace

import pytest
from peewee import Model

from app import cache, initialize_database
from app.modules.db import db_model as models
from app.modules.db.migration_manager import Migration
from app.modules.roxywi import common, roxy
from app.modules.roxywi import waf, waf_rule_file
from app.modules.config import config
from app.modules.server.ssh import crypt_password


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
def waf_creation(product, monkeypatch):
    """Real remote file operation on isolated files; replace only SSH transport."""
    state = SimpleNamespace(commands=[], roots={}, fail_before=False, lose_response=False)
    for service in ('haproxy', 'nginx'):
        root = product.root / service / 'waf'
        (root / 'rules').mkdir(parents=True)
        (root / 'modsecurity.conf').write_text('SecRuleEngine On\n', encoding='utf-8')
        (root / 'waf.conf').write_text('Include /existing/modsecurity.conf\n', encoding='utf-8')
        state.roots[service] = root
        models.Setting.update(value=f'/srv/{service} custom').where(
            models.Setting.param == f'{service}_dir', models.Setting.group_id == 1).execute()
    models.Setting.update(value=str(product.root)).where(
        models.Setting.param == 'tmp_config_path', models.Setting.group_id == 1).execute()

    def local_path(remote):
        for service, root in state.roots.items():
            prefix = f'/srv/{service} custom/waf/'
            if remote.startswith(prefix):
                return root.joinpath(*PurePosixPath(remote[len(prefix):]).parts)
        pytest.fail(f'Unexpected WAF path: {remote}')

    def ssh(server, command, **kwargs):
        assert server == product.server.ip
        assert kwargs['rc'] == 1
        assert kwargs['timeout'] > 30
        tokens = shlex.split(command)
        assert tokens[:5] == ['sudo', '-n', 'flock', '-w', '30']
        assert tokens[6:8] == ['python3', '-c']
        assert tokens[8] == Path(waf_rule_file.__file__).read_text(encoding='utf-8')
        state.commands.append((server, tokens[-3:]))
        if state.fail_before:
            raise OSError('synthetic SSH failure')
        try:
            waf_rule_file.create_rule(local_path(tokens[-3]), local_path(tokens[-2]), tokens[-1])
        except waf_rule_file.RuleConflict:
            return json.dumps({'status': 'conflict'})
        if state.lose_response:
            state.lose_response = False
            raise OSError('synthetic lost SSH response')
        return json.dumps({'status': 'ok'})

    @contextmanager
    def connect(server):
        assert server == product.server.ip

        def download(remote, local):
            Path(local).write_bytes(local_path(remote).read_bytes())

        yield SimpleNamespace(get_sftp=download)

    monkeypatch.setattr(waf.server_mod, 'ssh_command', ssh)
    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', connect)
    return state
