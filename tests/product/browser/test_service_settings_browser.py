"""All service settings share a layout and save only their own controls."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import ServiceSetting


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1')]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_shared_service_settings_layout_and_save(logged_in, product_url, product, host_metrics, monkeypatch, service, locale):
    setattr(product.server, service, 1)
    product.server.save()
    monkeypatch.setattr('app.routes.service.routes.server_mod.subprocess_execute', lambda command: (['0'], ''))
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.route('**/service/*/statuses', lambda route: route.fulfill(json={'data': []}))
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/service/*/*/backend', lambda route: route.fulfill(json={'data': ''}))
    response = page.goto(product_url + '/service/' + service)
    assert response.status == 200, response.text()
    card = page.locator('#div-server-11')
    card.locator('.service-actions-toggle').click()
    card.locator('.service-settings-command').click()
    dialog = page.locator('#dialog-settings-service')
    expect(dialog).to_be_visible()
    expect(dialog.locator('table.service-settings-table')).to_be_visible()
    expect(dialog.locator('tr')).to_have_count(3 if service == 'haproxy' else 2)
    expect(dialog.locator('[name="dockerized"]')).not_to_be_checked()
    expect(dialog.locator('[name="restart"]')).not_to_be_checked()
    assert abs(dialog.locator('..').bounding_box()['width'] - 640) <= 1
    dialog.locator(f'label.{service}_restart').click()
    # A checked input belonging to another service must not leak into this form.
    page.evaluate('''otherService => {
        const input = document.createElement('input');
        input.type = 'checkbox'; input.id = otherService + '_dockerized'; input.checked = true;
        document.body.append(input);
    }''', 'nginx' if service == 'haproxy' else 'haproxy')
    with page.expect_response(lambda response: response.url.endswith('/service/settings/' + service)
                              and response.request.method == 'POST') as saved:
        dialog.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    assert saved.value.status == 200
    settings = {row.setting: row.value for row in ServiceSetting.select().where(
        ServiceSetting.server_id == 11, ServiceSetting.service == service)}
    assert settings['restart'] == '1' and settings['dockerized'] == '0'
    assert ('multiple_config_files' in settings) == (service == 'haproxy')

    page.wait_for_load_state('networkidle')
    page.set_viewport_size({'width': 390, 'height': 844})
    card.locator('.service-actions-toggle').click()
    card.locator('.service-settings-command').click()
    expect(dialog.locator('[name="restart"]')).to_be_checked()
    expect(dialog.locator('[name="dockerized"]')).not_to_be_checked()
    bounds = dialog.locator('..').bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 391
    assert dialog.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
