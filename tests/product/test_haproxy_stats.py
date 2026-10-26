from types import SimpleNamespace

import pytest
import requests

from app.modules.db.db_model import Setting, UserGroups, User
from app.modules.service.stats import haproxy_stats
from tests.fixtures.haproxy_stats import INFO, stats_csv


STATS_HTML = b'<table class="tbl"><tr class="backend"><td>app_backend</td></tr></table>'


@pytest.fixture
def stats_runtime(product, monkeypatch):
    state = SimpleNamespace(calls=[], failure=None)
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()
    def execute(server, port, command):
        state.calls.append((server, port, command))
        assert port == 1999
        assert command in ('show stat', 'show info')
        if state.failure:
            raise state.failure
        return stats_csv() if command == 'show stat' else INFO
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', execute)
    return state


@pytest.fixture
def stats_http(product, monkeypatch):
    def send(*args, **kwargs):
        pytest.fail('HAProxy Stats must never use HTTP credentials')
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)


@pytest.mark.parametrize('server_ip', ['192.0.2.11', '2001:db8::11', 'proxy.example.com'])
def test_stats_view_fetches_runtime_json(product_client, product, stats_http, stats_runtime, server_ip):
    product.server.ip = server_ip
    product.server.save()
    response = product_client.get(f'/stats/view/haproxy/{server_ip}')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'
    assert response.json['server'] == server_ip
    assert response.json['rows'][1]['name'] == 'one'
    assert response.headers['Cache-Control'] == 'no-store'
    assert stats_runtime.calls == [(server_ip, 1999, command) for command in ('show info', 'show stat', 'show info')]


def test_legacy_http_stats_action_is_removed(product_client, product, stats_http):
    form = {'action': 'maint', 's': 'app1', 'b': '#3'}
    response = product_client.post(f'/runtimeapi/stats/action/{product.server.ip}', data=form)
    assert response.status_code == 404



@pytest.mark.parametrize('locale,refresh_label', [
    ('en', 'Refresh'), ('ru', 'Обновить'), ('fr', 'Actualiser'),
    ('es-ES', 'Actualizar'), ('pt-br', 'Atualizar'), ('zh', '刷新'),
])
def test_read_only_page_and_runtime_page_remain_separate(product_client, product, locale, refresh_label):
    product_client.set_cookie('lang', locale)
    response = product_client.get(f'/stats/haproxy/{product.server.ip}')
    assert response.status_code == 200
    assert b'id="haproxy-stats"' in response.data
    assert f'value="{product.server.ip}" selected'.encode() in response.data
    assert b'haproxy-stats.js' in response.data
    assert b'runtimeapi/stats/action' not in response.data
    assert f'id="hs-refresh">{refresh_label}</button>'.encode() in response.data
    environment = product_client.application.jinja_env
    translated = environment.get_template(f'languages/{locale}.html').module.haproxy_stats
    english = environment.get_template('languages/en.html').module.haproxy_stats
    assert translated.keys() == english.keys()
    assert all(isinstance(value, str) and value.strip() for value in translated.values())
    help_text = environment.get_template(f'languages/{locale}.html').module.haproxy_stats_fields
    english_help = environment.get_template('languages/en.html').module.haproxy_stats_fields
    assert help_text.keys() == english_help.keys()
    assert all(isinstance(value, str) and value.strip() for value in help_text.values())
    assert b'value="30" selected' in response.data
    assert b'runtimeapi.js' in product_client.get('/runtimeapi').data


def test_stats_reader_role_tenant_and_managed_target_checks(product_client, product, stats_runtime):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(f'/stats/haproxy/{product.server.ip}').status_code == 200
    assert product_client.get(f'/stats/view/haproxy/{product.server.ip}').status_code == 200
    stats_runtime.calls.clear()
    for server in (product.other.ip, '192.0.2.250'):
        assert product_client.get(f'/stats/view/haproxy/{server}').status_code == 403
    product.server.haproxy = 0
    product.server.save()
    assert product_client.get(f'/stats/view/haproxy/{product.server.ip}').status_code == 404
    assert stats_runtime.calls == []


def test_stats_requires_login_and_is_get_only(client, product, product_client, stats_runtime):
    # A separate client has no login cookies.
    with product_client.application.test_client() as anonymous:
        assert anonymous.get(f'/stats/view/haproxy/{product.server.ip}', headers={'Accept': 'application/json'}).status_code == 401
    assert product_client.post(f'/stats/view/haproxy/{product.server.ip}', json={}).status_code == 405
    assert stats_runtime.calls == []


def test_stats_checks_service_access_before_connecting(product_client, product, stats_runtime):
    User.update(user_services='2 3').where(User.user_id == product.admin.user_id).execute()
    assert product_client.get(f'/stats/view/haproxy/{product.server.ip}').status_code == 403
    assert product_client.get('/stats/haproxy/').status_code == 403
    assert stats_runtime.calls == []


@pytest.mark.parametrize('failure,status,code', [
    (ConnectionRefusedError('credential-secret'), 503, 'runtime_unavailable'),
    (TimeoutError('credential-secret'), 504, 'runtime_timeout'),
    (ValueError('credential-secret'), 500, 'operation_failed'),
])
def test_stats_failure_is_not_an_empty_success(product_client, product, stats_runtime, failure, status, code):
    stats_runtime.failure = failure
    response = product_client.get(f'/stats/view/haproxy/{product.server.ip}')
    assert response.status_code == status
    assert response.json == {'status': 'error', 'code': code}
    assert response.headers['Cache-Control'] == 'no-store'
    assert b'credential-secret' not in response.data


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_other_stats_pages_keep_existing_transport(product_client, product, monkeypatch, service):
    calls = []
    def fetch(server, selected, group):
        calls.append((str(server), selected, group))
        return STATS_HTML
    monkeypatch.setattr('app.routes.main.routes.service_common.get_stat_page', fetch)
    response = product_client.get(f'/stats/view/{service}/{product.server.ip}')
    assert response.status_code == 200 and response.data == STATS_HTML
    assert calls == [(product.server.ip, service, '1')]
