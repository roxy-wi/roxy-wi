import os

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_status_opens_with_keyboard_and_explains_failed_check(logged_in, product_url, product, waf_modes, app, locale, service):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_diagnostics
    reason = 'unready' if service == 'haproxy' else 'invalid'
    waf_modes.diagnostics[service]['check'] = reason
    page.goto(f'{product_url}/waf/{service}')
    details = page.locator('[data-waf-diagnostics]')
    summary = details.locator('summary')
    expect(summary).to_contain_text(messages['attention'])
    expect(details.locator('dl')).not_to_be_visible()
    summary.focus()
    page.keyboard.press('Enter')
    expect(details.locator('dl')).to_be_visible()
    expect(details).to_contain_text(messages[reason + '_hint'])
    expect(details).to_contain_text(messages['scope_' + service])
    expect(page.locator('[data-waf-apply-button]')).to_be_visible()
    page.keyboard.press('Enter')
    expect(details.locator('dl')).not_to_be_visible()
    # A failed SSH check on refresh must keep the installed WAF controls.
    waf_modes.diagnostic_error = OSError('sensitive diagnostic output')
    page.reload()
    expect(summary).to_contain_text(messages['process_unknown'])
    summary.click()
    expect(details).to_contain_text(messages['connection_failed_hint'])
    expect(page.locator('[data-waf-apply-button]')).to_be_visible()
    expect(page.locator('[data-confirmed-mode]')).to_have_attribute('data-confirmed-mode', 'On')
    expect(page.locator('body')).not_to_contain_text('sensitive diagnostic output')
