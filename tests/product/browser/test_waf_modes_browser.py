import os

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


def choose_mode(page, server_id, label):
    page.locator(f'[id="{server_id}_select-button"]').click()
    option = page.locator(f'[id="{server_id}_select-menu"]').get_by_role('option', name=label, exact=True)
    # jQuery UI ignores a mouse event at the previous selection's exact pixel.
    # Move within the item as a user would before clicking its center again.
    option.hover(position={'x': 5, 'y': 5})
    option.click()


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_mode_restores_confirmed_value_on_failure_and_retries(logged_in, product_url, product,
                                                            waf_modes, service, locale, app):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_mode
    page.goto(f'{product_url}/waf/{service}')
    select = page.locator(f'[id="{product.server.server_id}_select"]')
    message = page.locator('[data-waf-mode-message]')
    expect(select).to_have_value('On')
    expect(page.locator('.overviewHead')).to_contain_text(messages['label'])
    expect(page.locator('.waf-mode-hint')).to_have_count(0)
    waf_modes.fail_before = True
    url = f'/waf/{service}/mode/{product.server.server_id}/Off'
    with page.expect_response(lambda response: response.url.endswith(url)) as failure:
        choose_mode(page, product.server.server_id, messages['Off'])
    assert failure.value.status == 500
    expect(select).to_have_value('On')
    expect(select).to_be_enabled()
    expect(message).to_have_text(messages['failed'])
    expect(page.locator('.toast-error')).to_contain_text(messages['failed'])
    expect(page.locator('.toast-info')).to_have_count(0)

    waf_modes.fail_before = False
    with page.expect_response(lambda response: response.url.endswith(url)) as saved:
        choose_mode(page, product.server.server_id, messages['Off'])
    assert saved.value.status == 200
    expect(select).to_have_value('Off')
    expect(select).to_be_enabled()
    expect(select).to_have_attribute('data-confirmed-mode', 'Off')
    expect(message).to_be_empty()
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')
    expect(page.locator('[data-waf-apply-label]')).to_have_attribute('title', messages['hint_' + service])
    expect(page.locator('.toast-info')).to_contain_text(messages['saved_' + service])
    expect(page.locator('.toast-error')).to_have_count(0)
    assert (waf_modes.roots[service] / 'modsecurity.conf').read_text() == 'SecRuleEngine Off\n'
    assert len([args for _, args in waf_modes.commands if args[0] == 'set-mode']) == 2

    page.reload()
    expect(select).to_have_value('Off')
    expect(select).to_have_attribute('data-confirmed-mode', 'Off')
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')


@pytest.mark.parametrize('locale', LOCALES)
def test_unreadable_mode_keeps_installed_waf_actions(logged_in, product_url, product, waf_modes, app, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_mode
    (waf_modes.roots['nginx'] / 'modsecurity.conf').write_text('SecRuleEngine On\nSecRuleEngine Off\n')
    page.goto(f'{product_url}/waf/nginx')
    expect(page.locator(f'[id="{product.server.server_id}_select"]')).to_be_disabled()
    expect(page.locator(f'[id="{product.server.server_id}_select-button"]')).to_contain_text(messages['unavailable'])
    expect(page.locator('.waf-mode-hint')).to_have_text(messages['read_failed'])
    expect(page.locator(f'a[href="/waf/nginx/{product.server.ip}/rules"]')).to_be_visible()
    expect(page.locator('.reload-waf')).to_be_visible()
    expect(page.locator('button[onclick^="installWaf"]')).to_have_count(0)


@pytest.mark.parametrize('body', ['null', '{"status":"Ok"}', '{"status":"Ok","mode":"On"}'])
def test_mode_blocks_duplicate_submission_and_rejects_unconfirmed_response(logged_in, product_url, product,
                                                                          waf_modes, app, body):
    page = logged_in
    messages = app.jinja_env.get_template('languages/en.html').module.waf_mode
    page.goto(f'{product_url}/waf/nginx')
    select = page.locator(f'[id="{product.server.server_id}_select"]')
    expect(select).to_have_value('On')
    pending = []
    url = f'**/waf/nginx/mode/{product.server.server_id}/Off'
    page.route(url, lambda route: pending.append(route))
    with page.expect_request(url):
        choose_mode(page, product.server.server_id, messages['Off'])
    expect(select).to_be_disabled()
    page.evaluate('(id) => $(document.getElementById(id + "_select")).val("DetectionOnly").trigger("selectmenuchange")',
                  product.server.server_id)
    expect(select).to_have_value('Off')
    assert len(pending) == 1
    pending[0].fulfill(body=body, content_type='application/json')
    expect(select).to_be_enabled()
    expect(select).to_have_value('On')
    expect(select).to_have_attribute('data-confirmed-mode', 'On')
    expect(page.locator('[data-waf-mode-message]')).to_have_text(messages['failed'])
    expect(page.locator('.toast-info')).to_have_count(0)


def test_refreshed_rows_keep_one_mode_handler(logged_in, product_url, product, waf_modes, app):
    page = logged_in
    page.goto(f'{product_url}/waf/nginx')
    select = page.locator(f'[id="{product.server.server_id}_select"]')
    expect(select).to_have_value('On')
    for _ in range(2):
        with page.expect_response(lambda response: response.url.endswith(f'/waf/overview/nginx/{product.server.ip}')):
            page.locator('a[onclick="showOverviewWaf(ip, hostnamea)"]').click()
        expect(select).to_have_value('On')
    messages = app.jinja_env.get_template('languages/en.html').module.waf_mode
    with page.expect_response(lambda response: response.url.endswith('/DetectionOnly')):
        choose_mode(page, product.server.server_id, messages['DetectionOnly'])
    expect(select).to_have_attribute('data-confirmed-mode', 'DetectionOnly')
    assert len([args for _, args in waf_modes.commands if args[0] == 'set-mode']) == 1
