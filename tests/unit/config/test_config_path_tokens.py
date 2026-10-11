"""File identity survives URL encoding, transport, and persistence."""
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import common, config
from app.modules.config.path_tokens import decode_file_path, encode_file_path
from app.modules.config.viewer import build_document
from app.modules.service import common as service_common


PATHS = [
    ('haproxy', '/etc/haproxy/сайт 92.cfg'),
    ('nginx', '/etc/nginx/conf.d/сайт 92.conf'),
    ('apache', '/etc/apache2/sites-enabled/сайт 92.conf'),
    ('keepalived', '/etc/keepalived/сайт 92.conf'),
]


@pytest.mark.parametrize('service,path', PATHS)
def test_viewer_links_resolve_to_the_original_path_for_every_service(monkeypatch, service, path):
    monkeypatch.setattr(common.sql, 'get_setting', lambda name: '/etc/haproxy' if name == 'haproxy_dir' else path)
    doc = build_document('', service, '192.0.2.11', path, editable=True)
    token = doc['edit_url'].rsplit('/', 1)[1]
    assert token.startswith('_p_')
    assert common.resolve_viewer_path(service, token) == path
    assert common.resolve_viewer_path(service, path) == path


@pytest.mark.parametrize('value', ['92etc92nginx92site.conf', 'site.conf', '', '_p_', '_p_bad!',
                                  encode_file_path('relative.conf'), None])
def test_legacy_and_malformed_paths_are_not_accepted(value):
    with pytest.raises(ValueError):
        decode_file_path(value)


@pytest.mark.parametrize('service,path', PATHS)
@pytest.mark.parametrize('encoded', [False, True])
def test_download_passes_a_raw_path_to_sftp(monkeypatch, tmp_path, service, path, encoded):
    monkeypatch.setattr(config.sql, 'get_setting', lambda name: '/etc/haproxy' if name == 'haproxy_dir' else path)
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda *a, **kw: path)
    calls = []
    class SSH:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_sftp(self, remote, local): calls.append(remote)
    monkeypatch.setattr(config.mod_ssh, 'ssh_connect', lambda *a: SSH())
    config.get_config('192.0.2.11', str(tmp_path / 'download'), service=service,
                      config_file_name=encode_file_path(path) if encoded else path)
    assert calls == [path]


@pytest.mark.parametrize('service,path', PATHS[1:3])
def test_save_quotes_the_path_only_in_shell_and_keeps_version_identity(monkeypatch, tmp_path, service, path):
    settings = {service + '_container_name': service, 'tmp_config_path': '/tmp/config staging'}
    monkeypatch.setattr(config.sql, 'get_setting', lambda name: settings[name])
    monkeypatch.setattr(config.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=11))
    monkeypatch.setattr(config.server_sql, 'return_firewall', lambda ip: False)
    monkeypatch.setattr(config.service_sql, 'select_service_setting', lambda *a: '0')
    monkeypatch.setattr(config.deployment_policy, 'require_direct_deployment_for_server', lambda *a, **kw: None)
    monkeypatch.setattr(config.user_sql, 'get_user_id', lambda user_id: SimpleNamespace(user_id=user_id))
    monkeypatch.setattr(config, '_prepare_config_version_diff', lambda *a: '')
    monkeypatch.setattr(config, 'upload', lambda *a: None)
    monkeypatch.setattr(config.roxywi_common, 'logging', lambda *a, **kw: None)
    versions, commands = [], []
    monkeypatch.setattr(config, '_create_config_version', lambda *a, **kw: versions.append(a[2]))
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda ip, cmd, **kw: commands.append(shlex.split(cmd)) or 'valid')
    config.upload_and_restart('192.0.2.11', str(tmp_path / 'candidate'), 'save', service, user_id=1,
                              config_file_name=encode_file_path(path), normalize_config=False)
    assert versions == [path]
    assert commands[0][:3] == ['sudo', 'mv', '-f']
    assert commands[0][3].startswith('/tmp/config staging/')
    assert commands[0][4] == path


@pytest.mark.parametrize('path', ['/etc/nginx/../private.conf', '/etc/nginx/a;touch injected.conf',
                                  '/etc/nginx/a\n.conf', '/etc/nginx/a\x00.conf'])
def test_encoding_cannot_bypass_path_validation(path):
    with pytest.raises(ValueError):
        config._replace_config_path_to_correct(encode_file_path(path))


@pytest.mark.parametrize('service,path', PATHS[1:3])
def test_listing_preserves_whitespace_in_file_names(monkeypatch, service, path):
    root = path.rsplit('/', 2)[0]
    main = root + '/main.conf'
    monkeypatch.setattr(config.sql, 'get_setting', lambda name: main if name.endswith('_config_path') else root)
    commands = []
    monkeypatch.setattr(config.server_mod, 'ssh_command', lambda ip, cmd: commands.append(cmd) or path + '\x00')
    assert config.list_config_files('192.0.2.11', service) == [main, path]
    assert shlex.split(commands[0])[-1] == '-print0'


@pytest.mark.parametrize('service,path', PATHS[1:3])
def test_backend_links_use_the_shared_file_token(monkeypatch, service, path):
    monkeypatch.setattr(service_common.section_mod, 'get_remote_sections', lambda *a: path + ': example.test;\r\n')
    result = service_common.overview_backends('192.0.2.11', service)
    assert result == {encode_file_path(path): 'example.test'}
