"""Run the actual remote helper concurrently under the production host lock."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('flock'), reason='Linux flock required')
SCRIPT = Path(__file__).resolve().parents[2] / 'app/modules/roxywi/waf_rule_file.py'


@pytest.mark.parametrize('same_request', [True, False])
def test_concurrent_remote_creation(tmp_path, same_request):
    root = tmp_path / 'waf with spaces'
    (root / 'rules').mkdir(parents=True)
    entrypoint = root / 'waf.conf'
    entrypoint.write_text('SecRuleEngine On\n')
    rule = root / 'rules/test.conf'
    commands = [
        ['flock', '-w', '30', str(root / '.lock'), sys.executable, str(SCRIPT),
         str(entrypoint), str(rule), ('a' if same_request or index == 0 else 'b') * 64]
        for index in range(2)
    ]
    processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for command in commands]
    results = []
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=35)
            assert process.returncode == 0, stderr
            assert not stderr
            results.append(json.loads(stdout)['status'])
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert sorted(results) == (['ok', 'ok'] if same_request else ['conflict', 'ok'])
    assert entrypoint.read_text().count('test.conf') == 1
    assert len(list((root / 'rules').iterdir())) == 1


def test_missing_entrypoint_returns_failure_without_creating_rule(tmp_path):
    (tmp_path / 'rules').mkdir()
    rule = tmp_path / 'rules/test.conf'
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / 'waf.conf'), str(rule), 'a' * 64],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert not rule.exists()
