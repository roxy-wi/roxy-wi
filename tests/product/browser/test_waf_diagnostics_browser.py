import os

import pytest
from playwright.sync_api import expect

from app.modules.service import action as service_action


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
    expect(details.locator('p')).to_have_count(1)
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


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_healthy_status_is_only_in_tooltip_and_details_stay_accessible(logged_in, product_url, waf_modes, app, locale, service):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_diagnostics
    page.goto(f'{product_url}/waf/{service}')
    details = page.locator('[data-waf-diagnostics]')
    summary = details.locator('summary')
    expect(summary).to_have_attribute('title', messages['summary_' + service])
    expect(summary).to_have_attribute('aria-label', messages['open'] + ': ' + messages['summary_' + service])
    expect(summary).to_have_text('')
    expect(details.locator('.serverUp')).to_be_visible()
    expect(details.locator('dl')).not_to_be_visible()
    summary.focus()
    page.keyboard.press('Enter')
    expect(details.locator('dl')).to_be_visible()
    expect(details.locator('dl')).to_contain_text(messages['process_running'])
    expect(details.locator('p')).to_have_count(0)
    expect(page.locator('body')).not_to_contain_text(messages['summary_' + service])


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_waf_action_labels_and_confirmation_keep_service_commands(logged_in, product_url, product, waf_modes,
                                                                app, monkeypatch, locale, service):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    calls = []
    monkeypatch.setattr(service_action, 'common_action', lambda *args: calls.append(args))
    page.goto(f'{product_url}/waf/{service}')
    for action, label in [('start', 'enable'), ('stop', 'disable')]:
        command = messages.waf_actions[label] if service == 'nginx' else messages.words[action].title()
        control = page.locator('.' + action + '-waf')
        if service == 'nginx':
            expect(control).to_have_attribute('title', command)
        control.focus()
        page.keyboard.press('Enter')
        dialog = page.locator('.ui-dialog').filter(has=page.locator('#dialog-confirm'))
        expect(dialog.locator('.ui-dialog-title')).to_have_text(f'{command} {product.server.hostname}?')
        button = dialog.get_by_role('button', name=command, exact=True)
        expect(button).to_be_visible()
        before = len(calls)
        dialog.get_by_role('button', name=messages.words['cancel'].title(), exact=True).click()
        assert len(calls) == before
        control.click()
        with page.expect_navigation(wait_until='domcontentloaded'):
            button.click()
        expect(page.locator('[data-waf-diagnostics]')).to_be_visible()
        assert calls == [(product.server.ip, item, 'waf_' + service) for item in ('start', 'stop')[:before + 1]]
