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
def logged_in(page, product_url):
    response = page.request.post(product_url + '/login', data={
        'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/admin',
    })
    assert response.status == 200, response.text()
    return page
