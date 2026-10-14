"""Exercise the transaction with an isolated NGINX tree and real HTTP traffic.

The included file uses an NGINX map to test full-tree validation without needing
the optional ModSecurity module. No system service or production path is used.
"""
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from app.modules.config import candidate as transaction


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('nginx') or not shutil.which('flock'),
                                reason='Linux with nginx and flock required')


def wait_for_response(url, expected):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.read() == expected:
                    return
        except OSError:
            pass
        time.sleep(0.05)
    pytest.fail(f'NGINX did not return {expected!r}')


@pytest.fixture
def nginx(tmp_path):
    (tmp_path / 'waf/rules').mkdir(parents=True)
    target = tmp_path / 'waf/rules/test.conf'
    target.write_text('map $http_host $waf_test { default old; }\n')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    main = tmp_path / 'nginx.conf'
    temporary_paths = '\n'.join(f'{kind}_temp_path "{tmp_path / kind}";' for kind in
                                ('client_body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'))
    main.write_text(f'''pid "{tmp_path / 'nginx.pid'}";
error_log "{tmp_path / 'error.log'}";
events {{}}
http {{
    access_log off;
    {temporary_paths}
    include "{target}";
    server {{ listen 127.0.0.1:{port}; return 200 "$waf_test"; }}
}}
''')
    process = subprocess.Popen(['nginx', '-c', str(main), '-p', str(tmp_path), '-e', str(tmp_path / 'startup.log'),
                                '-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f'http://127.0.0.1:{port}/'
    try:
        wait_for_response(url, b'old')
        yield tmp_path, target, main, url
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def run_transaction(root, target, main, text, action, executable=sys.executable):
    candidate = root / 'upload.conf'
    candidate.write_text(text)
    args = json.dumps(dict(service='nginx_waf', target=str(target), candidate=str(candidate), main=str(main),
                           action='reload' if action else 'save', action_command=action))
    result = subprocess.run(['flock', '-w', '5', str(root / 'waf.lock'), executable,
                             str(Path(transaction.__file__)), args], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_default_host_python_can_save_apply_and_clean_up(nginx):
    # The managed host's python3 can be older than the application's Python.
    # CentOS Stream 8, for example, invokes Python 3.6 through sudo python3.
    root, target, main, url = nginx
    executable = shutil.which('python3')
    if not executable:
        pytest.skip('Host python3 is unavailable')
    response = run_transaction(root, target, main, 'map $http_host $waf_test { default legacy; }\n',
                               shlex.join(['nginx', '-c', str(main), '-s', 'reload']), executable=executable)
    assert response == {'status': 'ok'}
    wait_for_response(url, b'legacy')
    assert not list(root.rglob('.roxywi-*'))
    assert not (root / 'upload.conf').exists()


def test_invalid_candidate_is_restored_and_valid_reload_changes_live_response(nginx):
    root, target, main, url = nginx
    original = target.read_bytes()
    reload_command = shlex.join(['nginx', '-c', str(main), '-s', 'reload'])
    result = run_transaction(root, target, main, 'unknown_waf_directive;\n', reload_command)
    assert result['code'] == 'validation_failed'
    assert target.read_bytes() == original
    wait_for_response(url, b'old')
    result = run_transaction(root, target, main, 'map $http_host $waf_test { default new; }\n', reload_command)
    assert result == {'status': 'ok'}
    wait_for_response(url, b'new')
    assert not list(root.rglob('.roxywi-*'))


def test_failed_reload_recovers_previous_configuration_and_http_response(nginx):
    root, target, main, url = nginx
    marker = root / 'first-action'
    reload_command = shlex.join(['nginx', '-c', str(main), '-s', 'reload'])
    action = f'if [ ! -f {shlex.quote(str(marker))} ]; then touch {shlex.quote(str(marker))}; exit 1; fi; {reload_command}'
    result = run_transaction(root, target, main, 'map $http_host $waf_test { default new; }\n', action)
    assert result['code'] == 'apply_failed'
    assert target.read_text() == 'map $http_host $waf_test { default old; }\n'
    wait_for_response(url, b'old')
    assert not list(root.rglob('.roxywi-*'))
