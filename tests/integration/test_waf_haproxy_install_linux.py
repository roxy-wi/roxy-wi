"""Run only the WAF backend task on temporary files, without installing services."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from ansible.module_utils.common.json import AnsibleJSONEncoder
from ansible.utils.unsafe_proxy import wrap_var
import pytest
import yaml

from app.modules.config import candidate


pytestmark = pytest.mark.skipif(
    sys.platform != 'linux' or not all(shutil.which(tool) for tool in ('haproxy', 'flock', 'ansible-playbook')),
    reason='Linux with HAProxy, flock and Ansible required',
)
TASKS = Path(__file__).resolve().parents[2] / 'app/scripts/ansible/roles/waf/tasks/haproxy_config.yml'
MAIN = ('global\ndefaults\n mode http\n timeout connect 1s\n timeout client 1s\n timeout server 1s\n'
        'frontend public\n bind 127.0.0.1:19999\n default_backend web\n')
BACKEND = 'backend web\n server one 127.0.0.1:20001\n'


@pytest.fixture
def waf_install(tmp_path):
    root = tmp_path / 'proxy'
    folder = root / 'conf.d'
    folder.mkdir(parents=True)
    # The main file need not be named haproxy.cfg or be inside haproxy_dir.
    main = tmp_path / "custom configs/proxy's main.cfg"
    main.parent.mkdir()
    main.write_text(MAIN)
    main.chmod(0o640)
    other = folder / '20-web.cfg'
    other.write_text(BACKEND)
    temporary = tmp_path / 'temporary'
    temporary.mkdir()

    def run(*, included=True):
        sources = [str(main), str(folder)] if included else [str(folder)]
        command = shlex.split(candidate.candidate_command(
            'haproxy', str(main), '', 'save', main=str(main), root=str(root), sources=sources))
        # Same transaction and lock, using a private path without sudo in tests.
        command = command[2:]
        command[3] = str(tmp_path / 'config.lock')
        command[4] = sys.executable
        inventory = {'all': {'hosts': {'localhost': {
            'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
            'HAPROXY_CONFIG_PATH': str(main), 'HAPROXY_CONFIG_COMMAND': command,
        }}}}
        inventory_path = tmp_path / 'inventory.json'
        inventory_path.write_text(json.dumps(wrap_var(inventory), cls=AnsibleJSONEncoder, preprocess_unsafe=True))
        playbook = tmp_path / 'play.yml'
        playbook.write_text(yaml.safe_dump([{
            'hosts': 'all', 'gather_facts': False, 'become': False,
            'environment': {'TMPDIR': str(temporary)},
            'tasks': [{'ansible.builtin.include_tasks': str(TASKS)}],
        }]))
        result = subprocess.run(
            ['ansible-playbook', '-i', str(inventory_path), str(playbook)],
            env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp')},
            text=True, capture_output=True, timeout=60,
        )
        assert not list(temporary.glob('roxywi-waf-haproxy-*')), result.stdout
        assert not list(temporary.glob('roxywi-candidate-*')), result.stdout
        return result

    return main, other, run


def test_waf_backend_stays_in_configured_main_and_repeated_run_does_not_duplicate(waf_install):
    main, other, run = waf_install
    for _ in range(2):
        result = run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert main.read_text().startswith(MAIN)
        assert main.read_text().count('backend waf\n') == 1
        assert other.read_text() == BACKEND
        assert main.stat().st_mode & 0o777 == 0o640
    assert not (other.parent.parent / 'haproxy.cfg').exists()


@pytest.mark.parametrize('problem', ['invalid_other_file', 'main_not_loaded', 'existing_backend'])
def test_waf_backend_validation_failure_preserves_all_original_files(waf_install, problem):
    main, other, run = waf_install
    if problem == 'invalid_other_file':
        other.write_text(BACKEND + ' invalid_directive\n')
    elif problem == 'existing_backend':
        other.write_text(BACKEND + 'backend waf\n mode tcp\n server customer 127.0.0.1:54321\n')
    before = {path: path.read_bytes() for path in (main, other)}
    result = run(included=problem != 'main_not_loaded')
    assert result.returncode != 0, result.stdout
    assert 'validation_failed' in result.stdout
    assert {path: path.read_bytes() for path in before} == before
