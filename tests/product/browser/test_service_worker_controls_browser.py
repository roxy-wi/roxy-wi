import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server, ServiceAssignment


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1')]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_remote_worker_switches_save_assignments(logged_in, product_url, product, service_worker_controls,
                                                host_metrics, last_config_edit, locale, service):
    setattr(product.server, service, 1)
    product.server.save()
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.route('**/service/*/statuses', lambda route: route.fulfill(json={'data': []}))
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/service/*/*/backend', lambda route: route.fulfill(json={'data': ''}))
    page.route('**/service/*/bytes/*', lambda route: route.fulfill(body=''))
    page.route('**/service/nginx/connections/*', lambda route: route.fulfill(body=''))
    response = page.goto(product_url + '/service/' + service)
    assert response.status == 200
    expect(page.locator('#alert-11')).to_be_enabled()
    expect(page.locator('#metrics-11')).to_be_enabled()
    expect(page.locator('#active-11')).to_be_disabled()
    for name in ('alert', 'metrics'):
        with page.expect_response(lambda response: response.url.endswith('/tools/update') and response.request.method == 'POST') as saved:
            page.locator(f'label[for="{name}-11"]').click()
        assert saved.value.status == 200 and saved.value.text() == 'ok'
        expect(page.locator('#' + name + '-11')).to_be_checked()
    server = Server.get_by_id(11)
    assert getattr(server, service + '_alert') == getattr(server, service + '_metrics') == 1
    assignments = list(ServiceAssignment.select().where(ServiceAssignment.server_id == 11, ServiceAssignment.service == service))
    assert {row.target_service for row in assignments} == {'checker', 'metrics'}
    assert all(row.desired_state == 'running' for row in assignments)
