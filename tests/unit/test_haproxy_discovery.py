import json
import shlex

import pytest

from app.modules.config import haproxy_discovery as discovery


def test_sources_preserve_order_and_resolve_relative_paths():
    assert discovery.sources_from_argv(['haproxy', '-Ws', '-f', 'main.cfg', '-C', '/etc/haproxy',
                                        '--', 'conf.d', 'last.cfg']) == [
        '/etc/haproxy/main.cfg', '/etc/haproxy/conf.d', '/etc/haproxy/last.cfg']


@pytest.mark.parametrize('argv', [[], ['sh', '-c', 'haproxy -f /a'], ['haproxy', '-f'], ['haproxy', '-db']])
def test_unsupported_commands_are_not_guessed(argv):
    with pytest.raises(discovery.DiscoveryError, match='unsupported_startup'):
        discovery.sources_from_argv(argv)


def test_environment_expansion_preserves_quoted_single_argument():
    env = {'CONFIG': '/etc/haproxy/main file.cfg', 'OPTIONS': '-f "/etc/haproxy/extra files"'}
    args = discovery.expand_environment(['haproxy', '-f', '${CONFIG}', '$OPTIONS'], env)
    assert discovery.sources_from_argv(args) == ['/etc/haproxy/main file.cfg', '/etc/haproxy/extra files']


def test_environment_file_is_never_executed(tmp_path):
    path = tmp_path / 'environment'
    path.write_text('CONFIG="/etc/haproxy/haproxy.cfg"\nSECRET=$(touch /tmp/never-execute-this)\n', encoding='utf-8')
    assert discovery.environment_file(path) == {
        'CONFIG': '/etc/haproxy/haproxy.cfg', 'SECRET': '$(touch /tmp/never-execute-this)'}


def systemd_output(env_file, pid=0):
    return '\n'.join([
        'LoadState=loaded', 'MainPID=%s' % pid, 'WorkingDirectory=/etc/haproxy',
        'Environment=CONFIG=/old.cfg "OPTIONS=-f conf.d"',
        'EnvironmentFiles=%s (ignore_errors=no)' % shlex.quote(env_file.as_posix()),
        'ExecStart={ path=/usr/sbin/haproxy ; argv[]=/usr/sbin/haproxy -Ws -f ${CONFIG} $OPTIONS ; ignore_errors=no ; pid=0 ; }'])


def test_systemd_effective_environment_and_running_arguments(monkeypatch, tmp_path):
    env_file = tmp_path / 'haproxy environment'
    env_file.write_text('CONFIG="/etc/haproxy/main file.cfg"\n', encoding='utf-8')
    monkeypatch.setattr(discovery, 'run', lambda args: systemd_output(env_file, pid=12))
    monkeypatch.setattr(discovery, 'process_argv', lambda pid: ['haproxy', '-Ws', '-f', '/etc/haproxy/main file.cfg', '-f', 'conf.d'])
    sources, mounts, verified = discovery.systemd_sources('haproxy')
    assert sources == ['/etc/haproxy/main file.cfg', '/etc/haproxy/conf.d']
    assert mounts == [] and verified


def test_changed_systemd_settings_require_application_before_use(monkeypatch, tmp_path):
    env_file = tmp_path / 'environment'
    env_file.write_text('CONFIG=/etc/haproxy/new.cfg\n', encoding='utf-8')
    monkeypatch.setattr(discovery, 'run', lambda args: systemd_output(env_file, pid=12))
    monkeypatch.setattr(discovery, 'process_argv', lambda pid: ['haproxy', '-f', '/etc/haproxy/old.cfg'])
    result = discovery.discover('systemd', 'haproxy', '/etc/haproxy', '/etc/haproxy/haproxy.cfg')
    assert result['code'] == 'startup_changed' and not result['files']


@pytest.mark.parametrize('pid', [0, 12])
def test_docker_entrypoint_and_command_are_combined(monkeypatch, pid):
    payload = [{'Config': {'Entrypoint': ['docker-entrypoint.sh'],
                           'Cmd': ['haproxy', '-f', '/config/main.cfg', '-f', '/config/conf.d'],
                           'Env': ['SECRET=do-not-expose']}, 'State': {'Pid': pid},
                'Mounts': [{'Source': '/etc/haproxy', 'Destination': '/config', 'RW': True}]}]
    monkeypatch.setattr(discovery, 'run', lambda args: json.dumps(payload))
    monkeypatch.setattr(discovery, 'process_argv', lambda value: payload[0]['Config']['Cmd'] if value else None)
    sources, mounts, verified = discovery.docker_sources('test')
    assert verified == bool(pid)
    assert [discovery.host_path(path, mounts) for path in sources] == ['/etc/haproxy/main.cfg', '/etc/haproxy/conf.d']


def test_container_paths_use_most_specific_mount():
    mounts = [{'Destination': '/config', 'Source': '/etc/haproxy'},
              {'Destination': '/config/conf.d', 'Source': '/srv/haproxy.d'}]
    assert discovery.host_path('/config/conf.d/site.cfg', mounts) == '/srv/haproxy.d/site.cfg'
    with pytest.raises(discovery.DiscoveryError, match='mount_missing'):
        discovery.host_path('/other/site.cfg', mounts)


def test_permission_failure_is_distinct_from_missing_sources(monkeypatch):
    def denied(name):
        raise PermissionError('secret file contents must not be returned')
    monkeypatch.setattr(discovery, 'systemd_sources', denied)
    result = discovery.discover('systemd', 'haproxy', '/etc/haproxy', '/etc/haproxy/haproxy.cfg')
    assert result['state'] == 'error' and result['code'] == 'permission_denied'
    assert 'secret' not in json.dumps(result)
