import os

import pytest
from playwright.sync_api import expect

from app.modules.config import haproxy_files
from app.modules.db.db_model import ServiceSetting


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_service_checkbox_discovers_retries_and_persists(
    logged_in, product_url, product, host_metrics, last_config_edit, monkeypatch, locale,
):
    monkeypatch.setattr('app.routes.service.routes.server_mod.subprocess_execute', lambda command: (['0'], ''))
    state = {'state': 'single', 'code': 'not_configured', 'sources': [], 'files': [], 'mode': 'systemd',
             'verified_running': True, 'example': '-f /etc/haproxy/haproxy.cfg -f /etc/haproxy/conf.d'}
    seen = []
    def discover(ip, server_id, **kwargs):
        seen.append((server_id, kwargs.get('dockerized')))
        return dict(state)
    monkeypatch.setattr(haproxy_files, 'discover_sources', discover)
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.route('**/service/haproxy/statuses', lambda route: route.fulfill(json={'data': []}))
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/service/haproxy/*/backend', lambda route: route.fulfill(json={'data': ''}))
    response = page.goto(product_url + '/service/haproxy')
    assert response.status == 200, response.text()
    card = page.locator('#div-server-11')
    expect(card.locator('[id="edit_date_192.0.2.11"]')).to_have_text(last_config_edit)
    card.locator('.service-actions-toggle').click()
    card.locator('.service-settings-command').click()
    dialog = page.locator('#dialog-settings-service')
    expect(dialog).to_be_visible()
    expect(dialog.locator('#haproxy_multiple_config_files')).not_to_be_checked()
    expect(dialog.locator('#haproxy-sources-settings')).to_be_hidden()
    dialog.locator('label.haproxy_multiple_config_files').click()
    expect(dialog.locator('.haproxy-sources-hint')).to_be_visible()
    expect(dialog.locator('pre')).to_contain_text('-f /etc/haproxy/conf.d')
    expect(dialog).to_contain_text('systemctl daemon-reload')
    state.update(state='error', code='permission_denied')
    dialog.locator('.haproxy-sources-retry').click()
    expect(dialog.locator('pre')).to_have_count(0)
    expect(dialog.locator('.haproxy-sources-hint')).to_have_count(0)
    state.update(state='ready', code='ready', sources=[
        {'path': '/etc/haproxy/conf.d', 'runtime_path': '/etc/haproxy/conf.d', 'kind': 'directory'}])
    dialog.locator('.haproxy-sources-retry').click()
    expect(dialog.locator('.haproxy-sources-list')).to_contain_text('/etc/haproxy/conf.d')
    expect(dialog.locator('.haproxy-sources-hint')).to_have_count(0)
    assert dialog.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    # A pending background request after reload must not delay reopening settings.
    pending_last_edit = []
    page.route('**/service/*/*/last-edit', lambda route: pending_last_edit.append(route))
    # Register before Save: reloading keeps the same URL and starts background requests.
    with page.expect_event('load'):
        with page.expect_response(
            lambda response: response.url.endswith('/service/settings/haproxy')
            and response.request.method == 'POST'
        ) as saved:
            dialog.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    assert saved.value.status == 200
    assert ServiceSetting.get(ServiceSetting.setting == 'multiple_config_files').value == '1'
    assert seen and all(server_id == 11 and dockerized is False for server_id, dockerized in seen)
    card.locator('.service-actions-toggle').click()
    card.locator('.service-settings-command').click()
    expect(page.locator('#haproxy_multiple_config_files')).to_be_checked()
    expect(page.locator('.haproxy-sources-list')).to_be_visible()
    assert pending_last_edit
    for route in pending_last_edit:
        route.fulfill(body=last_config_edit)
