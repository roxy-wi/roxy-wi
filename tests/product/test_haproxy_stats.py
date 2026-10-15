from base64 import b64encode
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest
import requests

from app.modules.db.db_model import Setting


STATS_HTML = b'<table class="tbl"><tr class="backend"><td>app_backend</td></tr></table>'


@pytest.fixture
def stats_http(product, monkeypatch):
    settings = {
        'haproxy_stats_user': 'stats-user',
        'haproxy_stats_password': 'StatsPassword!',
        'haproxy_stats_port': '8404',
        'haproxy_stats_page': 'stats',
    }
    for name, value in settings.items():
        Setting.update(value=value).where(Setting.param == name, Setting.group_id == 1).execute()
    state = SimpleNamespace(requests=[], redirect_get=False)

    def send(adapter, request, **kwargs):
        host = f'[{product.server.ip}]' if ':' in product.server.ip else product.server.ip
        assert request.url == f'http://{host}:8404/stats'
        assert request.headers['Authorization'] == 'Basic ' + b64encode(b'stats-user:StatsPassword!').decode()
        assert kwargs['timeout'] == 5
        state.requests.append(request)
        response = requests.Response()
        response.request, response.url = request, request.url
        if request.method == 'POST':
            # HAProxy redirects after a form submission, even an empty one.
            response.status_code, response._content = 303, b''
            response.headers['Location'] = '/stats;st=NONE'
        elif state.redirect_get:
            response.status_code, response._content = 302, b''
            response.headers['Location'] = 'http://192.0.2.99/stats'
        else:
            assert request.method == 'GET'
            response.status_code, response._content = 200, STATS_HTML
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    return state


@pytest.mark.parametrize('server_ip', ['192.0.2.11', '2001:db8::11', 'proxy.example.com'])
def test_stats_view_fetches_table_with_get(product_client, product, stats_http, server_ip):
    product.server.ip = server_ip
    product.server.save()
    response = product_client.get(f'/stats/view/haproxy/{server_ip}')
    assert response.status_code == 200
    assert response.data == STATS_HTML
    assert len(stats_http.requests) == 1
    assert stats_http.requests[0].method == 'GET'
    assert stats_http.requests[0].body is None


def test_stats_action_posts_form_then_view_refreshes_with_get(product_client, product, stats_http):
    form = {'action': 'maint', 's': 'app1', 'b': '#3'}
    response = product_client.post(f'/runtimeapi/stats/action/{product.server.ip}', data=form)
    assert response.status_code == 200
    assert len(stats_http.requests) == 1  # Do not follow HAProxy's 303 redirect.
    assert stats_http.requests[0].method == 'POST'
    assert parse_qs(stats_http.requests[0].body) == {key: [value] for key, value in form.items()}

    # The existing Stats UI refreshes the table after a successful action.
    response = product_client.get(f'/stats/view/haproxy/{product.server.ip}')
    assert response.status_code == 200
    assert response.data == STATS_HTML
    assert [request.method for request in stats_http.requests] == ['POST', 'GET']


def test_stats_get_does_not_follow_redirect_to_another_server(product_client, product, stats_http):
    stats_http.redirect_get = True
    response = product_client.get(f'/stats/view/haproxy/{product.server.ip}')
    assert response.status_code == 200
    assert response.data == b''
    assert [request.method for request in stats_http.requests] == ['GET']
