"""Exercise the shipped audit rotation policy with real logrotate and open writers."""
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


pytestmark = pytest.mark.skipif(
    sys.platform != 'linux' or not shutil.which('logrotate'), reason='Linux with logrotate required',
)
ROLE = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf_logs'


@pytest.fixture
def rotation(tmp_path):
    policy = (ROLE / 'files/logrotate.conf').read_text()
    paths = {}
    for service in ('haproxy', 'nginx'):
        path = tmp_path / service / 'waf/audit.log'
        path.parent.mkdir(parents=True)
        paths[service] = path
        policy = policy.replace(f'/var/log/{service}/waf/audit.log', str(path))
    # Run as the test user; the installed policy uses root for both WAF services.
    policy = policy.replace('su root root', f'su {tmp_path.owner()} {tmp_path.group()}')
    config = tmp_path / 'logrotate.conf'
    config.write_text(policy)

    def run(force=False):
        result = subprocess.run(
            ['logrotate', '--state', str(tmp_path / 'status'), *(['--force'] if force else []), str(config)],
            text=True, capture_output=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    return paths, run


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_rotation_preserves_open_writer_and_bounds_compressed_archives(rotation, service):
    paths, run = rotation
    path = paths[service]
    with path.open('ab', buffering=0) as writer:
        inode = path.stat().st_ino
        for index in range(9):
            payload = f'audit event {index}\n'.encode()
            writer.write(payload)
            run(force=True)
            assert path.stat().st_ino == inode
            assert path.stat().st_size == 0
            with gzip.open(str(path) + '.1.gz', 'rb') as archive:
                assert archive.read() == payload
        writer.write(b'event after rotation\n')
    assert path.read_bytes() == b'event after rotation\n'
    assert len(list(path.parent.glob('audit.log.*.gz'))) == 7
    # The other WAF need not be installed; missingok must handle its absent log.
    assert not paths['nginx' if service == 'haproxy' else 'haproxy'].exists()


def test_size_limit_rotates_before_the_next_day_and_ignores_small_logs(rotation):
    paths, run = rotation
    for path in paths.values():
        path.write_text('small audit event\n')
    run()
    assert not list(paths['nginx'].parent.glob('audit.log.*'))
    with paths['nginx'].open('r+b') as log:
        log.truncate(51 * 1024 * 1024)
    run()
    assert paths['nginx'].stat().st_size == 0
    assert Path(str(paths['nginx']) + '.1.gz').exists()
    assert paths['haproxy'].read_text() == 'small audit event\n'


def test_empty_logs_are_not_rotated(rotation):
    paths, run = rotation
    for path in paths.values():
        path.touch()
    run(force=True)
    assert all(not list(path.parent.glob('audit.log.*')) for path in paths.values())


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='Ansible required')
@pytest.mark.parametrize('exists', [False, True])
def test_role_secures_audit_file_without_truncating_records_on_repeated_runs(tmp_path, exists):
    tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
    task = next(task for task in tasks if task.get('ansible.builtin.file', {}).get('path', '').endswith('/audit.log'))
    path = tmp_path / 'audit.log'
    original = b'existing audit event\n' if exists else b''
    if exists:
        path.write_bytes(original)
        path.chmod(0o644)
    before = path.stat() if exists else None
    # Use the same file task with a private path and the unprivileged test user.
    task['ansible.builtin.file'].update(path=str(path), owner=tmp_path.owner(), group=tmp_path.group())
    play = tmp_path / 'audit-file.yml'
    play.write_text(yaml.safe_dump([{
        'hosts': 'localhost', 'gather_facts': False, 'connection': 'local',
        'vars': {'ansible_python_interpreter': sys.executable}, 'tasks': [task, task],
    }]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)],
                            env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp'),
                                 'ANSIBLE_REMOTE_TEMP': str(tmp_path / 'ansible-remote'), 'ANSIBLE_NOCOLOR': '1'},
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'changed=1' in result.stdout, result.stdout
    after = path.stat()
    assert after.st_mode & 0o777 == 0o640
    assert path.read_bytes() == original
    if before:
        assert after.st_ino == before.st_ino
        assert after.st_mtime_ns == before.st_mtime_ns
