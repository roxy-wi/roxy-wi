from copy import deepcopy
import os
from pathlib import Path
import sys

import pytest
import yaml


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Ansible requires a POSIX control node')
ROLE_DIR = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf'


def test_early_install_failure_cleans_up_without_masking_original_error(tmp_path):
    import ansible_runner

    tasks = yaml.safe_load((ROLE_DIR / 'tasks/main.yml').read_text(encoding='utf-8'))[0]
    cleanup = deepcopy(tasks['always'])
    scratch = tmp_path / 'build'
    scratch.mkdir()
    # Keep the real cleanup tasks, redirecting only their literal /tmp paths.
    # An undefined build fact must still fail this test, not be substituted away.
    for task in cleanup:
        task['with_items'] = [
            str(scratch / Path(path).name) if path.startswith('/tmp/') else path
            for path in task['with_items']
        ]
        for path in task['with_items']:
            if str(path).startswith(str(scratch) + '/'):
                Path(path).write_text('unfinished build', encoding='utf-8')

    private_data_dir = tmp_path / 'runner'
    private_data_dir.mkdir()
    events = []
    result = ansible_runner.run(
        private_data_dir=str(private_data_dir),
        inventory={'all': {'hosts': {'localhost': {
            'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
        }}}},
        playbook=[{
            'hosts': 'all', 'gather_facts': False, 'become': False,
            'tasks': [{
                'block': [{
                    'name': 'Simulate unavailable build dependency',
                    'ansible.builtin.fail': {'msg': 'No package yajl-devel available.'},
                }],
                'always': cleanup,
            }],
        }],
        envvars={'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'local-tmp'),
                 'ANSIBLE_REMOTE_TEMP': str(tmp_path / 'remote-tmp')},
        event_handler=lambda event: events.append(event),
        quiet=True,
    )

    assert result.rc == 2
    failures = [event['event_data'] for event in events if event['event'] == 'runner_on_failed']
    assert len(failures) == 1
    assert failures[0]['res']['msg'] == 'No package yajl-devel available.'
    assert list(scratch.iterdir()) == []
