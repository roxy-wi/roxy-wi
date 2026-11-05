"""Real permissions and templates with only the status endpoint substituted."""

import re

import pytest
import requests

from app.modules.db.db_model import Setting, User, UserGroups
from app.modules.service.stats import proxy_stats
from tests.fixtures.proxy_stats import APACHE_BASIC, NGINX, status_host  # noqa: F401


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_snapshot_and_page(product_client, product, status_host, service):
    Setting.update(value="literal'password").where(
        Setting.param == service + '_stats_password', Setting.group_id == 1,
    ).execute()
    response = product_client.get(f'/stats/view/{service}/{product.server.ip}')
    assert response.status_code == 200
    assert response.json['counters']['requests'] == 20
    assert response.json['info']['version'] == ('2.4.62' if service == 'apache' else None)
    assert 'version' not in response.json['counters']
    assert response.json['observed_at'].endswith('Z')
    assert response.headers['Cache-Control'] == 'no-store'
    assert status_host.calls[-1][-1] == "literal'password"
    if service == 'apache':
        assert '?auto=' in status_host.calls[-1][3]
    page = product_client.get(f'/stats/{service}/{product.server.ip}')
    assert page.status_code == 200
    assert 'id="proxy-stats"' in page.text
    assert 'value="30" selected' in page.text
    assert 'proxy-stats.js' in page.text
    assert 'haproxy-stats.js' not in page.text
    assert 'id="ps-actions"' not in page.text
    assert 'proxy-diagnostics.js' not in page.text
    assert "literal'password" not in page.text


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_authorization_before_transport(product_client, product, status_host, service):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(f'/stats/view/{service}/{product.server.ip}').status_code == 200
    status_host.calls.clear()
    for ip in (product.other.ip, '192.0.2.250'):
        assert product_client.get(f'/stats/view/{service}/{ip}').status_code == 403
    setattr(product.server, service, 0)
    product.server.save()
    assert product_client.get(f'/stats/view/{service}/{product.server.ip}').status_code == 404
    assert status_host.calls == []


@pytest.mark.parametrize('status,body,error,expected,code', [
    (401, b'private', None, 502, 'stats_forbidden'),
    (403, b'private', None, 502, 'stats_forbidden'),
    (404, b'private', None, 502, 'not_configured'),
    (302, b'private', None, 502, 'unavailable'),
    (503, b'private', None, 502, 'unavailable'),
    (200, b'<html>private</html>', None, 502, 'invalid_response'),
    (200, b'\xff', None, 502, 'invalid_response'),
    (200, b'x' * (1024 * 1024 + 1), None, 502, 'invalid_response'),
    (200, NGINX, requests.Timeout('private'), 504, 'timeout'),
    (200, NGINX, requests.ConnectionError('private'), 502, 'unavailable'),
    (200, NGINX, RuntimeError('private'), 500, 'operation_failed'),
], ids=['unauthenticated', 'denied', 'missing', 'redirect', 'http_error', 'html', 'encoding', 'size', 'timeout', 'connection', 'internal'])
def test_failures_are_structured_and_redacted(product_client, product, status_host, status, body, error, expected, code):
    status_host.status, status_host.content['nginx'], status_host.error = status, body, error
    response = product_client.get(f'/stats/view/nginx/{product.server.ip}')
    assert response.status_code == expected
    assert response.json == {'status': 'error', 'code': code}
    assert 'private' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'


def test_group_credentials_and_apache_query(product_client, product, status_host):
    product.other.apache = 1
    product.other.save()
    for name, value in {'port': '8888', 'page': '/status?foo=bar&auto', 'user': 'other', 'password': "other's"}.items():
        Setting.create(param='apache_stats_' + name, value=value, section='apache', group_id=2, desc='')
    response = product_client.get(f'/stats/view/apache/{product.other.ip}')
    assert response.status_code == 200
    assert status_host.calls[-1] == (product.other.ip, 'apache', 8888, '/status?foo=bar&auto=', 'other', "other's")


@pytest.mark.parametrize('language', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_all_translations_cover_metrics_and_states(app, language):
    catalog = app.jinja_env.get_template('languages/' + language + '.html').module.proxy_stats
    metrics = (set(proxy_stats.NginxStats.model_fields) | set(proxy_stats.ApacheStats.model_fields) |
               {'rps', 'bps', 'gap', 'connection_rate'}) - {'scoreboard'}
    assert metrics <= set(catalog['fields'])
    assert set(catalog['states']) == set('._SRWKDCLGI')
    assert all(len(pair) == 2 and all(pair) for pair in catalog['fields'].values())


def test_basic_apache_keeps_missing_counters_null(product_client, product, status_host):
    status_host.content['apache'] = APACHE_BASIC
    response = product_client.get(f'/stats/view/apache/{product.server.ip}')
    assert response.status_code == 200
    assert response.json['counters']['requests'] is None
    assert response.json['counters']['average_bps'] is None


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_stats_login_service_permissions_and_get_only(product_client, product, status_host, service):
    path = f'/stats/view/{service}/{product.server.ip}'
    with product_client.application.test_client() as anonymous:
        assert anonymous.get(path, headers={'Accept': 'application/json'}).status_code == 401
    assert product_client.post(path, json={}).status_code == 405
    User.update(user_services='1').where(User.user_id == product.admin.user_id).execute()
    assert product_client.get(path).status_code == 403
    assert status_host.calls == []


def test_overview_reuses_counters_without_conflating_connections_and_requests(product_client, product, status_host):
    response = product_client.get('/service/nginx/connections/' + product.server.ip)
    assert response.status_code == 200
    assert re.search(r'id="cur_sess">\s*3\s*<', response.text)
    assert re.search(r'id="total_sess">\s*10\s*<', response.text)
    status_host.content['apache'] = APACHE_BASIC
    response = product_client.get('/service/apache/bytes/' + product.server.ip)
    assert response.status_code == 200
    assert re.search(r'id="bin">\s*—\s*<', response.text)
    assert re.search(r'id="bout">\s*—\s*<', response.text)


@pytest.mark.parametrize('path', ['/service/nginx/connections/', '/service/apache/bytes/'])
def test_overview_checks_group_and_service_before_transport(product_client, product, status_host, path):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    assert product_client.get(path + product.other.ip).status_code == 403
    User.update(user_services='1').where(User.user_id == product.admin.user_id).execute()
    assert product_client.get(path + product.server.ip).status_code == 403
    assert status_host.calls == []
