import os

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


def confirm_apply(page, messages):
    page.locator('[data-waf-apply-button]').click()
    dialog = page.get_by_role('dialog', name=messages['apply'], exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role('button', name=messages['apply'], exact=True).click()


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_pending_changes_survive_navigation_and_failed_apply(logged_in, product_url, product,
                                                            waf_applying, waf_switching, app, service, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_apply
    rules_url = f'/waf/{service}/{product.server.ip}/rules'
    page.goto(product_url + rules_url)
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state', 'unknown')
    expect(panel.locator('[data-waf-apply-label]')).to_have_text(messages['unknown'])
    assert panel.locator('[data-waf-apply-label]').get_attribute('title') == messages['scope']

    rule_id = waf_switching.rules[service].id
    page.locator(f'label[for="rule_id-{rule_id}"]').click()
    expect(panel).to_have_attribute('data-state', 'pending')
    page.reload()
    expect(panel).to_have_attribute('data-state', 'pending')
    waf_applying.action_failed = True
    with page.expect_response(lambda response: response.url.endswith('/apply')) as response:
        confirm_apply(page, messages)
    assert response.value.status == 500
    expect(page.locator('.toast-error')).to_contain_text(messages['failed'])
    expect(page.locator('.toast-success')).to_have_count(0)
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(panel.locator('[data-waf-apply-button]')).to_be_enabled()

    waf_applying.action_failed = False
    confirm_apply(page, messages)
    expect(panel).to_have_attribute('data-state', 'applied')
    expect(panel.locator('[data-waf-apply-label]')).to_have_text(messages['applied'])
    expect(page.locator('.toast-success')).to_contain_text(messages['success'])
    page.goto(f'{product_url}/waf/{service}')
    expect(panel).to_have_attribute('data-state', 'applied')
    # The existing overview action uses the same apply transaction.
    confirm_apply(page, messages)
    expect(page.locator('.toast-success')).to_contain_text(messages['success'])
    expect(panel).to_have_attribute('data-state', 'applied')
    assert len(waf_applying.apply_calls) == 3


@pytest.mark.parametrize('service,action', [('haproxy', 'restart'), ('nginx', 'reload')])
def test_editor_plain_save_and_save_with_apply_update_state(logged_in, product_url, product,
                                                           waf_applying, waf_switching, service, action):
    page = logged_in
    rule_id = waf_switching.rules[service].id
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rule/{rule_id}')
    expect(page.locator('#saveconfig')).to_be_visible()
    page.evaluate('myCodeMirror.setValue("# saved rule")')
    page.locator('#saveconfig button[value="save"]').click()
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state', 'pending')
    page.reload()
    expect(panel).to_have_attribute('data-state', 'pending')
    assert page.evaluate('myCodeMirror.getValue()') == '# saved rule'
    page.locator(f'#saveconfig button[value="{action}"]').click()
    expect(panel).to_have_attribute('data-state', 'applied')


@pytest.mark.parametrize('body', ['null', '{"status":"Ok"}', '{}'])
def test_apply_ignores_double_click_and_unconfirmed_responses(logged_in, product_url, product,
                                                            waf_applying, app, body):
    page = logged_in
    messages = app.jinja_env.get_template('languages/en.html').module.waf_apply
    page.goto(f'{product_url}/waf/nginx')
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state', 'unknown')
    pending = []
    page.route('**/apply', lambda route: pending.append(route))
    confirm_apply(page, messages)
    expect(page.locator('[data-waf-apply-button]')).to_have_attribute('aria-disabled', 'true')
    page.evaluate('confirmWafApply(document.querySelector("[data-waf-apply-button]"))')
    page.locator('a[onclick="showOverviewWaf(ip, hostnamea)"]').click()
    expect(panel).to_have_attribute('data-state', 'pending')
    assert len(pending) == 1
    expect(page.get_by_role('dialog')).to_have_count(0)
    pending[0].fulfill(body=body, content_type='application/json')
    expect(page.locator('.toast-error')).to_contain_text(messages['failed'])
    expect(page.locator('.toast-success')).to_have_count(0)
    expect(panel).to_have_attribute('data-state', 'unknown')


def test_cancel_and_failed_status_refresh_do_not_claim_applied(logged_in, product_url, product, waf_applying, app):
    page = logged_in
    messages = app.jinja_env.get_template('languages/en.html').module.waf_apply
    page.goto(f'{product_url}/waf/nginx')
    page.locator('[data-waf-apply-button]').click()
    page.evaluate('confirmWafApply(document.querySelector("[data-waf-apply-button]"))')
    expect(page.get_by_role('dialog')).to_have_count(1)
    page.get_by_role('dialog').get_by_role('button', name='Cancel', exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(0)
    assert not waf_applying.apply_calls
    confirm_apply(page, messages)
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state', 'applied')
    page.route('**/state?*', lambda route: route.fulfill(status=500, body='failed'))
    page.evaluate('refreshWafState(document)')
    expect(panel).to_have_attribute('data-state', 'unknown')
    expect(panel.locator('[data-waf-apply-label]')).to_have_text(messages['unknown'])
