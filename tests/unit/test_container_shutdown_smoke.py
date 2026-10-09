from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
from types import SimpleNamespace
import urllib.request

import pytest

import roxy_wi
import roxy_wi_health
from app.modules.db.readiness import DatabaseReadinessMonitor
from app.routes.health import routes


@pytest.fixture
def smoke():
    path = Path(__file__).resolve().parents[1] / 'container_shutdown_smoke.py'
    spec = importlib.util.spec_from_file_location('container_shutdown_smoke', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('extra_args', ['', '--max-requests 100', '--config "/custom path/gunicorn.py"',
                                       '-c /custom.py --log-level debug', '--config=/custom.py'])
def test_launcher_preserves_operator_options_without_forcing_its_config(monkeypatch, extra_args):
    monkeypatch.setenv('GUNICORN_CMD_ARGS', extra_args)
    monkeypatch.setattr(roxy_wi_health, 'register_web', lambda: None)
    command = []
    monkeypatch.setattr(roxy_wi.os, 'execvp', lambda name, args: command.extend(args))
    roxy_wi.run_web()
    assert '--config' not in command and '-c' not in command
    arguments = shlex.split(os.environ['GUNICORN_CMD_ARGS'])
    assert arguments[:2] == ['--config', 'python:roxy_wi_gunicorn']
    assert arguments[2:] == shlex.split(extra_args)


@pytest.mark.skipif(sys.platform == 'win32', reason='Gunicorn requires Unix')
@pytest.mark.parametrize('custom_config', [None, '--config', '--config=', '-c'])
def test_actual_gunicorn_parser_selects_default_or_shutdown_hooks(monkeypatch, smoke, custom_config):
    from gunicorn.app.wsgiapp import WSGIApplication

    path = str(Path(smoke.__file__).resolve())
    extra = '--max-requests 17'
    if custom_config:
        option = custom_config + ('' if custom_config.endswith('=') else ' ')
        extra += ' ' + option + shlex.quote(path)
    monkeypatch.setenv('GUNICORN_CMD_ARGS', extra)
    monkeypatch.setattr(roxy_wi_health, 'register_web', lambda: None)
    command = []
    monkeypatch.setattr(roxy_wi.os, 'execvp', lambda name, args: command.extend(args))
    roxy_wi.run_web()
    monkeypatch.setattr(sys, 'argv', command)
    application = WSGIApplication()
    assert application.cfg.max_requests == 17
    expected_file = Path(path) if custom_config else Path(roxy_wi.__file__).with_name('roxy_wi_gunicorn.py')
    for hook in ('post_worker_init', 'worker_exit'):
        assert Path(getattr(application.cfg, hook).__code__.co_filename).resolve() == expected_file.resolve()


def test_shutdown_hooks_keep_readiness_monitor_and_hold_the_http_request(smoke, app, monkeypatch, tmp_path):
    checked = threading.Event()

    def check():
        checked.set()
        return True, 'ready'

    monitor = DatabaseReadinessMonitor(check, interval=60)
    monkeypatch.setattr(routes, 'database_readiness', monitor)
    monkeypatch.setattr(smoke, 'DATA', tmp_path)
    # Restore the real application view when the fixture finishes.
    monkeypatch.setitem(app.view_functions, 'health.live', app.view_functions['health.live'])
    worker = SimpleNamespace()

    def request():
        with app.test_client() as client:
            return client.get('/health/live?shutdown-test=1')

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        smoke.post_worker_init(worker)
        assert checked.wait(2), 'Custom config did not start the production readiness monitor'
        with app.test_client() as client:
            assert client.get('/health/live').json == {'status': 'ok'}
        pending = pool.submit(request)
        smoke.wait_for(lambda: (tmp_path / 'web-started-1').exists(), 'HTTP request in progress', timeout=3)
        assert not pending.done(), 'The shutdown fixture did not hold the HTTP request'
        (tmp_path / 'web-release').touch()
        response = pending.result(timeout=3)
        assert response.status_code == 200 and response.data == b'completed'
    finally:
        (tmp_path / 'web-release').touch()
        pool.shutdown(wait=True)
        smoke.worker_exit(None, worker)
    assert not monitor._thread.is_alive()


@pytest.mark.parametrize('body,success', [(b'completed', True), (b'{"status":"ok"}', False)])
def test_http_fixture_reports_an_unexpected_response(smoke, monkeypatch, tmp_path, body, success):
    @contextmanager
    def urlopen(url, timeout):
        assert url == 'http://test-web:8080/health/live?shutdown-test=1'
        yield SimpleNamespace(status=200, read=lambda: body)

    monkeypatch.setenv('SHUTDOWN_WEB_HOST', 'test-web')
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(smoke, 'DATA', tmp_path)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    if success:
        smoke.fixture('web-request')
        assert (tmp_path / 'web-response-received').exists()
    else:
        with pytest.raises(AssertionError, match='Unexpected shutdown response: HTTP 200:.*status'):
            smoke.fixture('web-request')
        assert not (tmp_path / 'web-response-received').exists()


def test_exited_client_fails_immediately_instead_of_waiting_for_timeout(smoke, monkeypatch):
    def unexpected_sleep(_):
        pytest.fail('Wait continued after the HTTP client exited')

    monkeypatch.setattr(smoke, 'time', SimpleNamespace(monotonic=lambda: 0, sleep=unexpected_sleep))
    with pytest.raises(AssertionError, match='HTTP request in progress: HTTP client exited'):
        smoke.wait_for(lambda: False, 'HTTP request in progress', failed=lambda: 'HTTP client exited')


def test_shutdown_config_does_not_import_app_in_master_process(smoke):
    code = ('import runpy, sys; runpy.run_path(sys.argv[1], run_name="shutdown_config"); '
            'assert "app" not in sys.modules')
    result = subprocess.run([sys.executable, '-c', code, smoke.__file__], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
