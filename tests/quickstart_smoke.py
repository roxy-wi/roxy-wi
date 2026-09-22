#!/usr/bin/env python3
"""Exercise the documented quick start on an isolated Linux Docker runner."""

from http.cookiejar import CookieJar
import importlib.util
import json
from pathlib import Path
import ssl
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quickstart', ROOT / 'docker' / 'quickstart.py')
quickstart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quickstart)
ORIGIN = 'https://localhost:8443'


def launch(action, **kwargs):
    return subprocess.run([sys.executable, str(ROOT / 'docker' / 'quickstart.py'), action],
                          cwd=ROOT, check=True, timeout=1200, **kwargs)


def https_client():
    # Trust only the temporary quick-start CA, as a browser user does in the guide.
    certificate = quickstart.run(quickstart.compose(
        'exec', '-T', 'https', 'cat', '/data/caddy/pki/authorities/local/root.crt'),
        capture_output=True, text=True).stdout
    context = ssl.create_default_context(cadata=certificate)
    cookies = CookieJar()
    return build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(cookies)), cookies


def wait_ready(client):
    deadline = time.monotonic() + 60
    while True:
        try:
            with client.open(f'{ORIGIN}/health/ready', timeout=10) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise
        if time.monotonic() >= deadline:
            raise RuntimeError('Quick-start HTTPS did not become ready')
        time.sleep(2)


def main():
    # Never stop a developer's existing evaluation stack or replace its secrets.
    if quickstart.ENV_FILE.exists():
        raise RuntimeError('Run this test in a clean, disposable checkout without .env.quickstart')
    try:
        launch('start')
        original = quickstart.ENV_FILE.read_bytes()
        manifest = json.loads(quickstart.run(quickstart.compose('config', '--format', 'json'),
                                           capture_output=True, text=True).stdout)
        assert not manifest['services']['web'].get('ports'), 'Web must not publish an HTTP port'
        for service in manifest['services'].values():
            for port in service.get('ports', []):
                assert port['host_ip'] == '127.0.0.1', 'Quick start must publish only on loopback'
        # Caddy has no health probe: wait for the certificate after the process starts.
        for attempt in range(30):
            try:
                client, cookies = https_client()
                break
            except subprocess.CalledProcessError:
                if attempt == 29:
                    raise
                time.sleep(2)
        wait_ready(client)
        password = launch('password', capture_output=True, text=True).stdout.strip()
        assert password, 'No initial admin password was generated'
        request = Request(f'{ORIGIN}/login', headers={'Content-Type': 'application/json'},
                          data=json.dumps({'login': 'admin', 'pass': password, 'next': '/changes'}).encode())
        with client.open(request, timeout=30) as response:
            assert json.load(response)['status'] == 'done', 'HTTPS login failed'
        assert any(cookie.name == 'access_token_cookie' and cookie.secure for cookie in cookies)
        with client.open(f'{ORIGIN}/changes', timeout=30) as response:
            assert response.status == 200, 'Authenticated page failed'
        launch('stop')
        launch('start')
        assert quickstart.ENV_FILE.read_bytes() == original, 'Restart changed persisted secrets'
        wait_ready(client)
        with client.open(f'{ORIGIN}/changes', timeout=30) as response:
            assert response.status == 200, 'Session or database did not survive restart'
        assert launch('password', capture_output=True, text=True).stdout.strip() == password
        print('Quick-start HTTPS login, port isolation and persisted restart passed.')
    finally:
        if quickstart.ENV_FILE.exists():
            launch('stop')


if __name__ == '__main__':
    main()
