import threading

import pytest
from werkzeug.serving import make_server
from app.modules.server import server as server_module


@pytest.fixture(scope='session')
def browser_context_args(browser_context_args):
    return {**browser_context_args, 'ignore_https_errors': True,
            'viewport': {'width': 1440, 'height': 1000}, 'locale': 'en-US', 'timezone_id': 'UTC'}


@pytest.fixture
def product_url(app, product, monkeypatch):
    # Synthetic servers have no network listener. Keep real server-list routes,
    # replacing only the external ICMP probe (which is Linux-specific).
    monkeypatch.setattr(server_module, 'server_is_up', lambda _ip: 'down')
    # Real HTTPS is necessary because the normal login redirects to HTTPS.
    server = make_server('127.0.0.1', 0, app, threaded=True, ssl_context='adhoc')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'https://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive(), 'Product test server did not stop'


@pytest.fixture(autouse=True)
def browser_errors(page):
    errors = []
    page.set_default_timeout(10000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    yield
    assert not errors, '\n'.join(errors)


@pytest.fixture
def last_config_edit(monkeypatch):
    # Keep the real last-edit route without connecting to a synthetic SSH host.
    value = 'Jan 1 12:00'

    def ssh_command(server_ip, command, **kwargs):
        assert server_ip == '192.0.2.11'
        assert command.startswith('ls -l ')
        return value

    monkeypatch.setattr(server_module, 'ssh_command', ssh_command)
    return value


@pytest.fixture
def host_metrics(monkeypatch):
    # The production collector uses Linux-specific psutil fields. Keep real
    # routes and charts on every test host, replacing only the OS readings.
    samples = {'ram': [1024, 512, 32, 256, 768, 2048],
               'cpu': [10, 5, 0, 80, 2, 1, 2, 0, 20]}
    for metric, field in [('ram', 'rams'), ('cpu', 'cpus')]:
        monkeypatch.setattr(
            f'app.modules.roxywi.metrics.show_{metric}_metrics',
            lambda _ip, metric=metric, field=field: {
                'chartData': {field: ' '.join(map(str, samples[metric]))},
            },
        )
    return samples


@pytest.fixture
def logged_in(page, product_url):
    response = page.request.post(product_url + '/login', data={
        'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin',
    })
    assert response.status == 200, response.text()
    return page
