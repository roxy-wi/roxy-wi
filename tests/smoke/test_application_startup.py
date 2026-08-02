import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def _stop_process(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.terminate()
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=5)
    return output


@pytest.mark.smoke
def test_application_starts_and_serves_login_page(tmp_path):
    port = _unused_local_port()
    environment = os.environ.copy()
    environment.update({
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': os.pathsep.join(
            path for path in (str(PROJECT_ROOT), environment.get('PYTHONPATH')) if path
        ),
        'ROXYWI_TESTING': '1',
        'ROXYWI_CONFIG_FILE': str(PROJECT_ROOT / 'tests' / 'fixtures' / 'roxy-wi.cfg'),
        'ROXYWI_DB_PATH': str(tmp_path / 'startup-smoke.db'),
        'ROXYWI_LOG_PATH': str(tmp_path / 'logs'),
        'ROXYWI_SECRET_KEY': 'startup-smoke-flask-secret-key-at-least-32-chars',
        'ROXYWI_JWT_ALGORITHM': 'HS256',
        'ROXYWI_JWT_SECRET_KEY': 'startup-smoke-jwt-secret-key-at-least-32-chars',
        'ROXYWI_BOOTSTRAP_ADMIN_PASSWORD': 'StartupSmokeAdminPassword!',
        'ROXYWI_SECRET_PHRASE': 'E2nCq8NnECvPQ5zUQntL_-Nt-qBncYkrEmMkYGzVpyM=',
        'ROXYWI_SMOKE_PORT': str(port),
    })
    process = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / 'tests' / 'smoke' / 'startup_server.py')],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.monotonic() + 15
    last_error = None
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = _stop_process(process)
                pytest.fail(f'Roxy-WI exited before becoming ready:\n{output}')
            try:
                with urlopen(f'http://127.0.0.1:{port}/login', timeout=1) as response:
                    body = response.read()
                    assert response.status == 200
                    assert response.headers.get_content_type() == 'text/html'
                    assert b'id="login-form"' in body
                    return
            except URLError as exc:
                last_error = exc
                time.sleep(0.1)
        output = _stop_process(process)
        pytest.fail(f'Roxy-WI did not become ready: {last_error}\n{output}')
    finally:
        if process.poll() is None:
            _stop_process(process)
