"""Run the actual candidate script and HAProxy against isolated temporary files."""
import os
import shutil
import subprocess
import sys
import shlex
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.config import candidate as transaction


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('haproxy'), reason='Linux and HAProxy required')
SCRIPT = Path(os.environ.get('ROXYWI_HAPROXY_TEST_SCRIPT', transaction.__file__))
DISCOVERY = Path(os.environ.get('ROXYWI_HAPROXY_DISCOVERY_SCRIPT',
                               Path(__file__).resolve().parents[2] / 'app/modules/config/haproxy_discovery.py'))
MAIN = ('global\n'
        'defaults\n mode http\n timeout connect 1s\n timeout client 1s\n timeout server 1s\n'
        'frontend public\n bind 127.0.0.1:19999\n default_backend web\n')
BACKEND = 'backend web\n server one 127.0.0.1:20001\n'


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / 'haproxy'
    folder = root / 'conf.d'
    folder.mkdir(parents=True)
    main = root / 'haproxy.cfg'
    main.write_text(MAIN)
    target = folder / '20-site92.cfg'
    target.write_text(BACKEND)
    target.chmod(0o640)
    return root, main, target


def apply(tree, text, action='test', *, target=None, sources=None, command='', container=''):
    root, main, original = tree
    target = target or original
    candidate = root.parent / (uuid4().hex + '.cfg')
    if action != 'check':
        candidate.write_text(text)
    spec = dict(service='haproxy', target=str(target), candidate=str(candidate) if action != 'check' else '', action=action, container=container,
                action_command=command, root=str(root), main=str(main), sources=[str(p) for p in (sources or [main, original.parent])])
    result = subprocess.run(['flock', '-w', '5', str(root.parent / 'config.lock'), sys.executable, str(SCRIPT), json.dumps(spec)],
                            text=True, capture_output=True, timeout=20)
    assert not candidate.exists(), result.stderr
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_validation_uses_other_files_without_replacing_working_file(tree):
    result = apply(tree, BACKEND.replace('20001', '20002'))
    assert result == {'status': 'ok'}, result
    assert tree[2].read_text() == BACKEND


@pytest.mark.parametrize('failure', ['candidate', 'other_file'])
def test_invalid_configuration_never_replaces_working_file(tree, failure):
    text = BACKEND + ' invalid_directive\n' if failure == 'candidate' else BACKEND
    if failure == 'other_file':
        tree[1].write_text(MAIN.replace('default_backend web', 'default_backend missing'))
    result = apply(tree, text, 'save')
    assert result['status'] == 'failed'
    assert tree[2].read_text() == BACKEND


def test_save_changes_only_selected_file_and_preserves_permissions(tree):
    text = BACKEND.replace('20001', '20002')
    result = apply(tree, text, 'save')
    assert result == {'status': 'ok'}, result
    assert tree[2].read_text() == text
    assert tree[2].stat().st_mode & 0o777 == 0o640
    assert tree[1].read_text() == MAIN


def test_new_file_with_spaces_joins_directory_in_lexical_order(tree):
    target = tree[2].parent / '30-extra 92.cfg'
    result = apply(tree, 'backend extra\n server two 127.0.0.1:20002\n', 'save', target=target)
    assert result == {'status': 'ok'}, result
    assert target.read_text().startswith('backend extra\n')
    assert tree[2].read_text() == BACKEND


def test_sources_and_directory_files_keep_their_order(tree):
    # A defaults section must precede the proxy that names it.
    folder = tree[2].parent
    (folder / '10-defaults.cfg').write_text('defaults named\n mode http\n timeout connect 1s\n timeout client 1s\n timeout server 1s\n')
    result = apply(tree, 'backend web from named\n server one 127.0.0.1:20001\n')
    assert result == {'status': 'ok'}, result
    result = apply(tree, BACKEND, sources=[folder, tree[1]])
    assert result == {'status': 'ok'}, result


def test_hidden_and_nested_files_are_not_implicitly_loaded(tree):
    (tree[2].parent / '.hidden.cfg').write_text('invalid\n')
    nested = tree[2].parent / 'nested'
    nested.mkdir()
    (nested / 'invalid.cfg').write_text('invalid\n')
    assert apply(tree, BACKEND) == {'status': 'ok'}


def test_file_outside_f_sources_cannot_be_applied(tree):
    other = tree[0] / 'inactive.cfg'
    other.write_text('backend inactive\n')
    result = apply(tree, 'backend inactive2\n', 'save', target=other)
    assert result['status'] == 'failed' and 'not included' in result['reason']
    assert other.read_text() == 'backend inactive\n'


def test_overlapping_sources_are_rejected(tree):
    result = apply(tree, BACKEND, sources=[tree[1], tree[2].parent, tree[2]])
    assert result['status'] == 'failed' and 'more than once' in result['reason']


def test_symlink_outside_allowed_root_is_rejected(tree):
    outside = tree[0].parent / 'outside.cfg'
    outside.write_text(BACKEND)
    tree[2].unlink()
    tree[2].symlink_to(outside)
    result = apply(tree, BACKEND.replace('web', 'other'), 'save')
    assert result['status'] == 'failed' and 'outside' in result['reason']
    assert outside.read_text() == BACKEND


def test_failed_reload_restores_original_file_and_metadata(tree):
    result = apply(tree, BACKEND.replace('20001', '20002'), 'reload', command='exit 7')
    assert result['status'] == 'failed' and result['restored']
    assert tree[2].read_text() == BACKEND
    assert tree[2].stat().st_mode & 0o777 == 0o640


def test_failed_restore_preserves_recovery_copy(tree, monkeypatch):
    replace = transaction.os.replace

    def fail_restore(source, destination):
        if destination == tree[2] and Path(source).read_text() == BACKEND:
            raise OSError('synthetic restore failure')
        return replace(source, destination)

    monkeypatch.setattr(transaction.os, 'replace', fail_restore)
    candidate = tree[0].parent / 'candidate.cfg'
    candidate.write_text(BACKEND.replace('20001', '20002'))
    result = transaction.execute(dict(service='haproxy', target=str(tree[2]), main=str(tree[1]), root=str(tree[0]),
                                      sources=[str(tree[1]), str(tree[2].parent)], candidate=str(candidate),
                                      action='reload', action_command='exit 7'))
    assert result['code'] == 'recovery_failed'
    backup = Path(result['backup'])
    assert backup.read_text() == BACKEND


def test_concurrent_saves_serialize_validation_and_replacement(tree, monkeypatch):
    binary = shutil.which('haproxy')
    bin_dir = tree[0].parent / 'bin'
    bin_dir.mkdir()
    log = tree[0].parent / 'checks.log'
    wrapper = bin_dir / 'haproxy'
    wrapper.write_text('#!/bin/sh\nprintf "start\\n" >> "$CHECK_LOG"\nsleep 0.2\n' +
                       shlex.quote(binary) + ' "$@"\nrc=$?\nprintf "end\\n" >> "$CHECK_LOG"\nexit "$rc"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('CHECK_LOG', str(log))
    candidates = [BACKEND.replace('20001', port) for port in ('20002', '20003')]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda text: apply(tree, text, 'save'), candidates))
    assert all(result == {'status': 'ok'} for result in results), results
    assert log.read_text().splitlines() == ['start', 'end', 'start', 'end']
    assert tree[2].read_text() in candidates


@pytest.mark.parametrize('mount', ['directory', 'file', 'different_path', 'read_only', 'readonly_tmp', 'readonly_alias_first'])
def test_docker_mount_visibility_is_checked_before_saving(tree, mount):
    if os.environ.get('ROXYWI_TEST_DOCKER_CONFIG') != '1':
        pytest.skip('Set ROXYWI_TEST_DOCKER_CONFIG=1')
    name = 'roxywi-config-test-' + uuid4().hex
    tree[2].chmod(0o644)
    root = str(tree[0])
    volume = f'{root}:{root}'
    if mount == 'file':
        volume = f'{tree[2]}:{tree[2]}'
    elif mount in ('different_path', 'readonly_tmp', 'readonly_alias_first'):
        volume = f'{root}:/configs'
    elif mount == 'read_only':
        volume += ':ro'
    extra_mount = ['-v', f'{tree[0]}:/tmp:ro'] if mount == 'readonly_tmp' else []
    if mount == 'readonly_alias_first':
        extra_mount = ['-v', f'{tree[0]}:/aaa:ro']
    try:
        subprocess.run(['docker', 'run', '-d', '--name', name, '-v', volume, *extra_mount,
                        '--entrypoint', 'sleep', 'haproxy:3.0-alpine', '120'], check=True, capture_output=True)
        text = BACKEND.replace('20001', '20002')
        result = apply(tree, text, 'save', container=name)
        if mount in ('file', 'read_only'):
            assert result['status'] == 'failed' and 'Mount the configuration directory' in result['reason']
            assert tree[2].read_text() == BACKEND
            return
        assert result == {'status': 'ok'}, result
        container_target = '/configs/conf.d/' + tree[2].name if mount in ('different_path', 'readonly_tmp', 'readonly_alias_first') else str(tree[2])
        content = subprocess.check_output(['docker', 'exec', name, 'cat', container_target], text=True)
        assert content == text
        result = apply(tree, text, 'check', container=name)
        assert result == {'status': 'ok'}, result
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=True, capture_output=True)


def inspect_startup(tree, mode, name):
    command = [sys.executable, str(DISCOVERY), mode, name, str(tree[0]), str(tree[1])]
    if os.geteuid() != 0:
        command = ['sudo', '-n', *command]
    return json.loads(subprocess.check_output(command, text=True, timeout=30))


def test_docker_discovery_reads_running_arguments_and_maps_sources(tree):
    if os.environ.get('ROXYWI_TEST_DOCKER_CONFIG') != '1':
        pytest.skip('Set ROXYWI_TEST_DOCKER_CONFIG=1')
    name = 'roxywi-discovery-test-' + uuid4().hex
    tree[2].chmod(0o644)
    try:
        subprocess.run(['docker', 'run', '-d', '--name', name, '-v', f'{tree[0]}:/usr/local/etc/haproxy',
                        'haproxy:3.0-alpine', 'haproxy', '-db', '-f', '/usr/local/etc/haproxy/haproxy.cfg',
                        '-f', '/usr/local/etc/haproxy/conf.d'], check=True, capture_output=True)
        result = inspect_startup(tree, 'docker', name)
        assert result['state'] == 'ready' and result['verified_running'], result
        assert [source['path'] for source in result['sources']] == [str(tree[1]), str(tree[2].parent)]
        assert result['files'] == [str(tree[1]), str(tree[2])]
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=True, capture_output=True)


def test_systemd_discovery_reads_effective_transient_unit(tree):
    if not Path('/run/systemd/system').is_dir():
        pytest.skip('A running systemd is required')
    name = 'roxywi-discovery-test-' + uuid4().hex + '.service'
    prefix = [] if os.geteuid() == 0 else ['sudo', '-n']
    environment = tree[0].parent / 'environment'
    environment.write_text('ROXYWI_TEST_VALUE=not-exported\n')
    subprocess.run([*prefix, 'systemd-run', '--unit=' + name, '--property=Type=oneshot',
                    '--property=RemainAfterExit=yes', '--property=EnvironmentFile=' + str(environment),
                    shutil.which('haproxy'), '-c', '-f', str(tree[1]), '-f', str(tree[2].parent)],
                   check=True, capture_output=True)
    try:
        for _ in range(30):
            pid = subprocess.check_output(['systemctl', 'show', name, '--property=MainPID', '--value'], text=True).strip()
            if pid == '0':
                break
            time.sleep(0.1)
        result = inspect_startup(tree, 'systemd', name)
        assert result['state'] == 'ready' and not result['verified_running'], result
        assert [source['path'] for source in result['sources']] == [str(tree[1]), str(tree[2].parent)]
        assert 'not-exported' not in json.dumps(result)
    finally:
        subprocess.run([*prefix, 'systemctl', 'stop', name], check=True, capture_output=True)
