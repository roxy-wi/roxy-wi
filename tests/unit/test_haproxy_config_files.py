import hashlib
import importlib
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest
from peewee import SqliteDatabase

from app.modules.config import config, haproxy_files
from app.modules.config.path_tokens import encode_file_path, decode_file_path
from app.modules.db import add as add_sql
from app.modules.db.db_model import Groups, Setting, Server, HaproxySection
from app.modules.roxywi.class_models import HaproxyGlobalRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound


@pytest.fixture
def settings(monkeypatch):
    values = {'haproxy_dir': '/etc/haproxy', 'haproxy_config_path': '/etc/haproxy/haproxy.cfg',
              'haproxy_container_name': 'haproxy', 'tmp_config_path': '/tmp'}
    monkeypatch.setattr(config.sql, 'get_setting', lambda name, **kwargs: values[name])
    monkeypatch.setattr(config.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11))
    monkeypatch.setattr(haproxy_files, 'multiple_files_enabled', lambda server_id: True)
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a, **kw: {
        'state': 'ready', 'sources': [{'path': values['haproxy_config_path']}, {'path': '/etc/haproxy/conf.d'}],
        'files': [values['haproxy_config_path'], '/etc/haproxy/conf.d/a b.cfg', '/etc/haproxy/conf.d/site92.cfg']})
    return values


def test_sources_preserve_argument_and_directory_order(settings):
    assert shlex.split(haproxy_files.check_command('192.0.2.11', 11)) == [
        'sudo', 'haproxy', '-c', '-f', '/etc/haproxy/haproxy.cfg', '-f', '/etc/haproxy/conf.d']
    command = shlex.split(haproxy_files.check_command('192.0.2.11', 11, 'proxy'))
    args = command[command.index('roxywi-haproxy') + 1:]
    assert args[:4] == ['/etc/haproxy/haproxy.cfg', '', 'check', 'proxy']
    assert args[-2:] == ['/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d']


def test_disabled_mode_keeps_main_file_and_does_not_inspect_startup(settings, monkeypatch):
    monkeypatch.setattr(haproxy_files, 'multiple_files_enabled', lambda server_id: False)
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a: pytest.fail('Unexpected inspection'))
    assert haproxy_files.config_sources('192.0.2.11', 11) == ['/etc/haproxy/haproxy.cfg']
    assert config.list_config_files('192.0.2.11', 'haproxy') == ['/etc/haproxy/haproxy.cfg']


def test_discovery_failure_never_falls_back_to_another_validation_set(settings, monkeypatch):
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a: {'state': 'error', 'code': 'permission_denied'})
    with pytest.raises(ValueError, match='permission_denied'):
        haproxy_files.config_sources('192.0.2.11', 11)


@pytest.mark.parametrize('action', ['test', 'save'])
def test_discovery_failure_does_not_upload_a_candidate(settings, monkeypatch, tmp_path, action):
    monkeypatch.setattr(haproxy_files, 'discover_sources', lambda *a: {'state': 'error', 'code': 'startup_changed'})
    monkeypatch.setattr(config.service_sql, 'select_service_setting', lambda *a: '0')
    monkeypatch.setattr(config.deployment_policy, 'require_direct_deployment_for_server', lambda *a, **kw: None)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(config, 'upload', lambda *a: pytest.fail('Candidate uploaded without discovered sources'))
    candidate = tmp_path / 'candidate.cfg'
    candidate.write_text('backend web\n', encoding='utf-8')
    with pytest.raises(Exception, match='startup_changed'):
        if action == 'test':
            config.validate_candidate_config('192.0.2.11', str(candidate), 'haproxy')
        else:
            config.upload_and_restart('192.0.2.11', str(candidate), 'save', 'haproxy',
                                      record_version=False, normalize_config=False)


@pytest.mark.parametrize('path', ['/etc/haproxy/site92.cfg', '/etc/haproxy/русский сайт.cfg'])
def test_file_tokens_round_trip_without_changing_names(path, settings):
    token = encode_file_path(path)
    assert '/' not in token
    assert decode_file_path(token) == path
    assert haproxy_files.resolve_path(token) == path
    assert haproxy_files.resolve_path(path) == path


@pytest.mark.parametrize('path', ['/etc/nginx/a.cfg', '/etc/haproxy/../a.cfg', '/etc/haproxy/a.pem',
                                 '/etc/haproxy/a\n.cfg', '/etc/haproxy2/a.cfg'])
def test_selected_path_stays_inside_config_directory(path, settings):
    with pytest.raises(ValueError):
        haproxy_files.resolve_path(path)


def test_listing_preserves_discovered_file_order_and_spaces(settings):
    assert config.list_config_files('192.0.2.11', 'haproxy') == [
        '/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d/a b.cfg', '/etc/haproxy/conf.d/site92.cfg']


def test_download_uses_selected_file_after_remote_symlink_check(settings, monkeypatch, tmp_path):
    calls = []
    class SSH:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_sftp(self, remote, local): calls.append(remote)
    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', lambda *a: SSH())
    path = '/etc/haproxy/extra/site92.cfg'
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda ip, cmd, **kw: path)
    config.get_config('192.0.2.11', str(tmp_path / 'file.cfg'), config_file_name=encode_file_path(path))
    assert calls == [path]


def test_new_file_version_diff_uses_empty_baseline(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda *a, **kw: '__ROXYWI_MISSING_CONFIG__')
    candidate = tmp_path / 'candidate.cfg'
    candidate.write_text('backend new\n', encoding='utf-8')
    diff = config._prepare_config_version_diff('192.0.2.11', 'haproxy', '/etc/haproxy/new.cfg',
                                               str(candidate), None, '/tmp/remote-only.cfg')
    assert '+backend new' in diff
    assert Path(str(candidate) + '.old').read_text() == ''


def test_candidate_validation_and_save_keep_file_identity(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(config.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11))
    monkeypatch.setattr(config.server_sql, 'return_firewall', lambda ip: False)
    monkeypatch.setattr(config.service_sql, 'select_service_setting', lambda *a: '0')
    monkeypatch.setattr(config.deployment_policy, 'require_direct_deployment_for_server', lambda *a, **kw: None)
    monkeypatch.setattr(config.subprocess, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(config, 'normalize_config_file', lambda *a: None)
    monkeypatch.setattr(config, 'upload', lambda *a: None)
    commands = []
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda ip, cmd, **kw: commands.append(shlex.split(cmd)) or '')
    target = '/etc/haproxy/conf.d/site92.cfg'
    candidate = tmp_path / 'candidate.cfg'
    candidate.write_text('backend web\n', encoding='utf-8')
    config.validate_candidate_config('192.0.2.11', str(candidate), 'haproxy', encode_file_path(target))
    config.upload_and_restart('192.0.2.11', str(candidate), 'save', 'haproxy',
                              config_file_name=target, record_version=False)
    for command, action in zip(commands, ('test', 'save')):
        args = command[command.index('roxywi-haproxy') + 1:]
        assert args[0] == target
        assert args[2] == action
        assert args[-2:] == ['/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d']
    assert commands[0] != commands[1]


@pytest.mark.parametrize('partially_migrated', [False, True])
def test_legacy_sections_migrate_and_remain_isolated_by_file(settings, partially_migrated):
    migration = importlib.import_module('app.modules.db.migrations.20261005000000_haproxy_config_files')
    database = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
    with database.bind_ctx([Groups, Setting, Server, HaproxySection], bind_refs=False, bind_backrefs=False):
        database.create_tables([Groups, Setting, Server])
        Groups.create(group_id=1, name='Default')
        Server.create(server_id=11, hostname='test', ip='192.0.2.11', group_id='1')
        Setting.create(param='haproxy_config_path', value='/etc/haproxy/haproxy.cfg', section='haproxy', desc='', group_id=1)
        database.execute_sql('CREATE TABLE haproxy_sections (id INTEGER PRIMARY KEY, server_id INTEGER NOT NULL '
                             'REFERENCES servers(id) ON DELETE CASCADE, type TEXT, name TEXT, config JSON, '
                             'UNIQUE(server_id, type, name))')
        original = HaproxyGlobalRequest(daemon=True).model_dump(mode='json')
        database.execute_sql('INSERT INTO haproxy_sections VALUES (?, ?, ?, ?, ?)',
                             (71, 11, 'global', 'global', json.dumps(original)))
        if partially_migrated:
            database.execute_sql("ALTER TABLE haproxy_sections ADD COLUMN config_path TEXT DEFAULT ''")
            database.execute_sql("ALTER TABLE haproxy_sections ADD COLUMN file_id TEXT DEFAULT ''")
            database.execute_sql('UPDATE haproxy_sections SET config_path=?, file_id=? WHERE id=71',
                                 ('/etc/haproxy/haproxy.cfg', hashlib.sha256(b'/etc/haproxy/haproxy.cfg').hexdigest()))
        migration.up()
        migration.up()
        main = add_sql.get_section(11, 'global', 'global')
        assert main.id == 71 and main.config == original
        assert main.file_id == hashlib.sha256(b'/etc/haproxy/haproxy.cfg').hexdigest()
        extra = '/etc/haproxy/conf.d/site92.cfg'
        with pytest.raises(RoxywiResourceNotFound):
            add_sql.get_section(11, 'global', 'global', config_path=extra)
        add_sql.insert_or_update_new_section(11, 'global', 'global', HaproxyGlobalRequest(daemon=False), config_path=extra)
        assert HaproxySection.select().count() == 2
        assert add_sql.get_section(11, 'global', 'global').config['daemon'] is True
        assert add_sql.get_section(11, 'global', 'global', config_path=extra).config['daemon'] is False
        add_sql.delete_section(11, 'global', 'global', config_path=extra)
        assert HaproxySection.select().count() == 1
        Server.delete().where(Server.server_id == 11).execute()
        assert HaproxySection.select().count() == 0
    database.close()
