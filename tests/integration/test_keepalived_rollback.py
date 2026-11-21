"""Exercise real Ansible rollback operations against isolated temporary files."""
import hashlib
import os
from pathlib import Path
import stat
import sys

import pytest


pytestmark = pytest.mark.skipif(
    os.name != 'posix', reason='Ansible requires a POSIX control node',
)
ROLE = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/keepalived'


@pytest.mark.parametrize('scenario', (
    'replace', 'metadata-only', 'first-install', 'concurrent-edit', 'unchanged',
))
def test_real_rollback_preserves_original_or_concurrent_file(tmp_path, scenario):
    import ansible_runner

    target = tmp_path / 'keepalived.conf'
    original = b'original configuration\n'
    candidate = b'candidate configuration\n'
    current = original if scenario == 'metadata-only' else candidate
    if scenario == 'concurrent-edit':
        current = b'a newer operator edit\n'
    target.write_bytes(current)
    target.chmod(0o644)
    result = {
        'changed': scenario != 'unchanged',
        'checksum': hashlib.sha1(
            original if scenario == 'metadata-only' else candidate,
        ).hexdigest(),
    }
    before = {'exists': scenario != 'first-install', 'mode': '0600',
              'uid': os.getuid(), 'gid': os.getgid()}
    if scenario in ('replace', 'concurrent-edit'):
        backup = tmp_path / 'original.backup'
        backup.write_bytes(original)
        result['backup_file'] = str(backup)
    private_data_dir = tmp_path / 'runner'
    private_data_dir.mkdir()
    events = []
    run = ansible_runner.run(
        private_data_dir=str(private_data_dir),
        inventory={'all': {'hosts': {'localhost': {
            'ansible_connection': 'local',
            'ansible_python_interpreter': sys.executable,
        }}}},
        playbook=[{
            'hosts': 'all', 'gather_facts': False, 'become': False,
            'vars': {'keepalived_restore': {
                'path': str(target), 'original': before, 'result': result,
            }},
            'tasks': [{'ansible.builtin.include_tasks': str(
                ROLE / 'tasks/rollback_file.yml',
            )}],
        }],
        envvars={
            'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'local-tmp'),
            'ANSIBLE_REMOTE_TEMP': str(tmp_path / 'remote-tmp'),
        },
        event_handler=lambda event: events.append(event),
        quiet=True,
    )
    failures = [event['event_data'] for event in events
                if event['event'] == 'runner_on_failed']
    if scenario == 'concurrent-edit':
        assert run.rc == 2
        assert 'automatic rollback refused' in failures[0]['res']['msg']
        assert target.read_bytes() == current
    else:
        assert run.rc == 0, failures
        if scenario == 'first-install':
            assert not target.exists()
        elif scenario == 'unchanged':
            assert target.read_bytes() == current
            assert stat.S_IMODE(target.stat().st_mode) == 0o644
        else:
            assert target.read_bytes() == original
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
