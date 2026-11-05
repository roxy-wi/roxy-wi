"""Representative stock status responses; no optional monitoring modules."""

from datetime import datetime
from types import SimpleNamespace

import pytest
import requests
from app.modules.service import managed_runtime
from app.modules.service.stats import proxy_stats


NGINX = b'''Active connections: 3
server accepts handled requests
 10 9 20
Reading: 0 Writing: 1 Waiting: 2
'''
APACHE = b'''ServerVersion: Apache/2.4.62
ServerMPM: event
Total Accesses: 20
Total kBytes: 100
Uptime: 300
CPULoad: .025
ReqPerSec: .066667
BytesPerSec: 341.33
BytesPerReq: 5120
BusyWorkers: 2
IdleWorkers: 3
ConnsTotal: 5
ConnsAsyncWriting: 1
ConnsAsyncKeepAlive: 2
ConnsAsyncClosing: 0
Scoreboard: _W_K_....
'''
APACHE_BASIC = b'BusyWorkers: 1\nIdleWorkers: 2\nScoreboard: W__...\n'


@pytest.fixture
def status_host(product, monkeypatch):
    product.server.apache = 1
    product.server.save()
    state = SimpleNamespace(
        content={'nginx': NGINX, 'apache': APACHE}, status=200, error=None, calls=[],
        now=datetime(2026, 11, 4, 12, 0),
    )

    def fetch(*args):
        state.calls.append(args)
        if state.error:
            raise state.error
        response = requests.Response()
        response.status_code = state.status
        response._content = state.content[args[1]]
        return response

    monkeypatch.setattr(proxy_stats, 'utc_now', lambda: state.now)
    monkeypatch.setattr(managed_runtime, 'statistics_response', fetch)
    return state
