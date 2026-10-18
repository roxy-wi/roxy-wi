import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import WafRules


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_delete_can_be_cancelled_retried_and_persists(logged_in, product_url, product, waf_switching,
                                                    app, service, locale):
    page, state = logged_in, waf_switching
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    rule = state.rules[service]
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    row = page.locator(f'#rule-{rule.id}')
    button = row.locator('[data-waf-delete]')
    dialog = page.get_by_role('dialog', name=messages.waf_delete['title'], exact=True)

    expect(button).to_be_hidden()
    row.locator('.admin-actions-toggle').click()
    expect(row.get_by_role('menuitem')).to_have_count(2)
    button.click()
    expect(dialog).to_contain_text(rule.rule_name)
    expect(dialog).to_contain_text(product.server.ip)
    expect(row.locator('input')).to_be_disabled()
    dialog.get_by_role('button', name=messages.words['cancel'].title(), exact=True).click()
    expect(button).to_be_enabled()
    assert not state.commands

    state.fail_before = True
    row.locator('.admin-actions-toggle').click()
    button.click()
    dialog.get_by_role('button', name=messages.words['delete'].title(), exact=True).click()
    expect(page.locator('.toast-error')).to_contain_text(messages.waf_delete['failed'])
    expect(button).to_be_enabled()
    expect(row.locator('input')).to_be_enabled()
    assert WafRules.get_by_id(rule.id)

    state.fail_before = False
    row.locator('.admin-actions-toggle').click()
    button.click()
    dialog.get_by_role('button', name=messages.words['delete'].title(), exact=True).click()
    expect(row).to_have_count(0)
    expect(page.locator('.toast-info')).to_contain_text(messages.waf_delete['saved_' + service])
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')
    assert not (state.roots[service] / 'rules/test.conf').exists()
    assert not WafRules.get_or_none(WafRules.id == rule.id)
    page.reload()
    expect(row).to_have_count(0)
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')


@pytest.mark.parametrize('body', ['null', '{"status":"deleted","id":99999}', '{"status":"Ok"}'])
def test_unconfirmed_deletion_keeps_rule_visible(logged_in, product_url, product, waf_switching, body):
    page = logged_in
    rule = waf_switching.rules['nginx']
    url = f'/waf/nginx/{product.server.ip}/rule/{rule.id}'
    page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rules')
    pending = []
    page.route('**' + url, lambda route: pending.append(route))
    row = page.locator(f'#rule-{rule.id}')
    row.locator('.admin-actions-toggle').click()
    row.locator('[data-waf-delete]').click()
    page.get_by_role('dialog').get_by_role('button', name='Delete', exact=True).click()
    expect(row.locator('[data-waf-delete]')).to_be_disabled()
    page.evaluate('(id) => deleteWafRule(document.querySelector(id + " [data-waf-delete]"))', f'#rule-{rule.id}')
    assert len(pending) == 1
    pending[0].fulfill(body=body, content_type='application/json')
    expect(page.locator('.toast-error')).to_be_visible()
    expect(row).to_be_visible()
    expect(row.locator('[data-waf-delete]')).to_be_enabled()
    expect(page.locator('.toast-info')).to_have_count(0)


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_action_menu_opens_manual_rule_editor(logged_in, product_url, product, waf_switching, service):
    page = logged_in
    rule = waf_switching.rules[service]
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    row = page.locator(f'#rule-{rule.id}')
    link = row.get_by_role('menuitem', name='View/Edit', exact=True)
    expect(link).to_be_hidden()
    row.locator('.admin-actions-toggle').click()
    expect(link).to_be_visible()
    link.click()
    expect(page.locator('#saveconfig[data-waf-editor]')).to_be_visible()
    expect(page).to_have_url(f'{product_url}/waf/{service}/{product.server.ip}/rule/{rule.id}')
