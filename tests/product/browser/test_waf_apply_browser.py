import os

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


def confirm_apply(page, messages, service='nginx'):
    if page.locator('#waf-server-grid').count():
        page.locator('[data-waf-card] .admin-actions-toggle').click()
    page.locator('[data-waf-apply-button]').click()
    action = messages['action_' + service]
    dialog = page.get_by_role('dialog', name=action, exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role('button', name=action, exact=True).click()


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_pending_changes_survive_navigation_and_failed_apply(logged_in, product_url, product,
                                                            waf_applying, waf_switching, app, service, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_apply
    hint = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_mode['hint_' + service]
    rules_url = f'/waf/{service}/{product.server.ip}/rules'
    page.goto(product_url + rules_url)
    panel = page.locator('[data-waf-apply]')
    expect(page.locator('[data-waf-apply-button]')).to_have_count(1)
    expect(panel.get_by_role('button', name=messages['action_' + service], exact=True)).to_be_visible()
    expect(panel).to_have_attribute('data-state', 'unknown')
    expect(panel.locator('[data-waf-apply-label]')).to_have_text(messages['unknown'])
    assert panel.locator('[data-waf-apply-label]').get_attribute('title') == messages['scope']

    rule_id = waf_switching.rules[service].id
    page.locator(f'label[for="rule_id-{rule_id}"]').click()
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(panel.locator('[data-waf-apply-label]')).to_have_attribute('title', hint)
    expect(panel.locator('[data-waf-apply-label]')).to_be_visible()
    page.reload()
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(panel.get_by_role('button', name=messages['action_' + service], exact=True)).to_be_visible()
    expect(panel.locator('[data-waf-apply-label]')).to_have_attribute('title', hint)
    waf_applying.action_failed = True
    with page.expect_response(lambda response: response.url.endswith('/apply')) as response:
        confirm_apply(page, messages, service)
    assert response.value.status == 500
    expect(page.locator('.toast-error')).to_contain_text(messages[service + '_apply_failed'])
    expect(page.locator('.toast-error')).to_contain_text(
        app.jinja_env.get_template(f'languages/{locale}.html').module.waf_error_details['action_failed'])
    expect(page.locator('.toast-success')).to_have_count(0)
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(panel.locator('[data-waf-apply-button]')).to_be_enabled()

    waf_applying.action_failed = False
    confirm_apply(page, messages, service)
    expect(panel).to_have_attribute('data-state', 'applied')
    expect(panel.locator('[data-waf-apply-label]')).to_have_text(messages['applied'])
    expect(panel.locator('[data-waf-apply-label]')).to_be_hidden()
    expect(panel.locator('[data-waf-apply-label]')).to_have_attribute('title', messages['scope'])
    expect(page.locator('.toast-success')).to_contain_text(messages['success'])
    page.goto(f'{product_url}/waf/{service}')
    expect(panel).to_have_attribute('data-state', 'applied')
    expect(panel.locator('[data-waf-apply-label]')).to_be_visible()
    expect(panel.locator('button')).to_have_count(0)
    expect(page.locator('[data-waf-apply-button]')).to_have_count(1)
    expect(page.get_by_title(messages['action_' + service], exact=True)).to_have_count(1)
    # The existing overview action uses the same apply transaction.
    confirm_apply(page, messages, service)
    expect(page.locator('.toast-success')).to_contain_text(messages['success'])
    expect(panel).to_have_attribute('data-state', 'applied')
    assert len(waf_applying.apply_calls) == 3


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service,action', [('haproxy', 'restart'), ('nginx', 'reload')])
def test_editor_plain_save_and_save_with_apply_update_state(logged_in, product_url, product,
                                                           waf_applying, waf_switching, app, service, action, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    rule_id = waf_switching.rules[service].id
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rule/{rule_id}')
    expect(page.locator('#saveconfig')).to_be_visible()
    expect(page.locator('[data-waf-apply-button]')).to_have_count(0)
    expect(page.locator('#saveconfig button')).to_have_count(2)
    expect(page.locator('#saveconfig button[value="save"]')).to_have_text(messages.words['save'].title())
    expect(page.locator(f'#saveconfig button[value="{action}"]')).to_have_text(messages.phrases['save_and_' + action])
    page.evaluate('myCodeMirror.setValue("# saved rule")')
    page.locator('#saveconfig button[value="save"]').click()
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(page.locator('[data-waf-apply-button]')).to_have_count(0)
    expect(panel.locator('[data-waf-apply-label]')).to_be_visible()
    page.reload()
    expect(panel).to_have_attribute('data-state', 'pending')
    expect(page.locator('[data-waf-apply-button]')).to_have_count(0)
    assert page.evaluate('myCodeMirror.getValue()') == '# saved rule'
    page.locator(f'#saveconfig button[value="{action}"]').click()
    expect(panel).to_have_attribute('data-state', 'applied')
    expect(page.locator('[data-waf-apply-button]')).to_have_count(0)
    expect(panel.locator('[data-waf-apply-label]')).to_be_hidden()


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
    page.locator('[data-waf-refresh]').click()
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
    page.locator('[data-waf-card] .admin-actions-toggle').click()
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
    expect(panel.locator('[data-waf-apply-label]')).to_have_attribute('title', messages['scope'])


def test_apply_error_displays_server_message_as_text(logged_in, product_url, waf_applying, app):
    page = logged_in
    page.goto(product_url + '/waf/haproxy')
    message = 'Configuration failed: <img src=x onerror="throw 1">'
    page.route('**/apply', lambda route: route.fulfill(status=500, json={'status': 'failed', 'error': message}))
    messages = app.jinja_env.get_template('languages/en.html').module.waf_apply
    confirm_apply(page, messages, 'haproxy')
    expect(page.locator('.toast-error .toast-message')).to_have_text(message)
    expect(page.locator('.toast-error img')).to_have_count(0)


def test_restart_refreshes_process_status_and_available_actions(logged_in, product_url, waf_applying, app):
    page = logged_in
    waf_applying.diagnostics['haproxy'].update(process='stopped', check='not_checked')
    page.goto(product_url + '/waf/haproxy')
    expect(page.locator('.start-waf')).to_be_enabled()
    expect(page.locator('.stop-waf')).to_be_disabled()

    def apply_and_start(route):
        response = route.fetch()
        assert response.status == 200
        waf_applying.diagnostics['haproxy'].update(process='running', check='ready')
        route.fulfill(response=response)

    page.route('**/apply', apply_and_start)
    messages = app.jinja_env.get_template('languages/en.html').module.waf_apply
    with page.expect_response(lambda response: '/waf/overview/haproxy/' in response.url):
        confirm_apply(page, messages, 'haproxy')
    expect(page.locator('summary.rw-status-running')).to_be_visible()
    expect(page.locator('.start-waf')).to_be_disabled()
    expect(page.locator('.stop-waf')).to_be_enabled()
