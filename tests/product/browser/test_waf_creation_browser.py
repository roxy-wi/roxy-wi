import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import WafRules


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']
NAME = 'Правило & règle <test> · 规则'
DESCRIPTION = 'Description & "quoted text"'


def open_creation(page, product_url, product, service):
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    page.locator('.add-button').click()
    dialog = page.locator('#add-new-config')
    expect(dialog).to_be_visible()
    expect(page.locator('#waf-create-error')).to_be_hidden()
    expect(page.locator('#waf-create-form button[type="submit"]')).to_be_hidden()
    page.locator('#new_rule_name').fill(NAME)
    page.locator('#new_rule_file').fill('custom-rule')
    page.locator('#new_rule_description').fill(DESCRIPTION)
    return dialog, dialog.locator('..').locator('.ui-dialog-buttonpane button').first


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_creation_keeps_input_after_error_and_opens_correct_editor(logged_in, product_url, product, waf_creation,
                                                                  app, service, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    dialog, button = open_creation(page, product_url, product, service)
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_create
    expect(dialog.locator('..').locator('.ui-dialog-title')).to_have_text(messages['title'])
    expect(page.locator('#waf-filename-hint')).to_have_text(messages['filename_hint'])
    create_url = f'/waf/{service}/{product.server.ip}/rule/create'
    assert dialog.get_attribute('data-create-url') == create_url
    waf_creation.fail_before = True
    with page.expect_response(lambda response: response.url.endswith(create_url)) as failed:
        button.click()
    assert failed.value.status == 500
    expect(page.locator('#waf-create-error')).to_have_text(messages['failed'])
    expect(dialog).to_be_visible()
    expect(button).to_be_enabled()
    expect(page.locator('#new_rule_name')).to_have_value(NAME)
    expect(page.locator('#new_rule_file')).to_have_value('custom-rule')
    expect(page.locator('#new_rule_description')).to_have_value(DESCRIPTION)
    assert WafRules.select().count() == 0

    waf_creation.fail_before = False
    with page.expect_response(lambda response: response.url.endswith(create_url)) as saved:
        page.locator('#new_rule_description').press('Enter')
    assert saved.value.status == 200
    rule = WafRules.get(WafRules.service == service, WafRules.rule_file == 'custom-rule.conf')
    expect(page).to_have_url(f'{product_url}/waf/{service}/{product.server.ip}/rule/{rule.id}')
    expect(page.locator('#saveconfig')).to_be_visible()
    assert '# Roxy-WI rule creation:' in page.evaluate('myCodeMirror.getValue()')
    assert (rule.rule_name, rule.desc, rule.service, rule.serv) == (NAME, DESCRIPTION, service, product.server.ip)


@pytest.mark.parametrize('locale', LOCALES)
def test_invalid_filename_and_existing_remote_file_show_localized_errors(logged_in, product_url, product,
                                                                        waf_creation, app, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    dialog, button = open_creation(page, product_url, product, 'nginx')
    page.locator('#new_rule_file').fill('../outside')
    button.click()
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_create
    expect(page.locator('#waf-create-error')).to_have_text(messages['invalid'])
    assert not waf_creation.commands
    existing = waf_creation.roots['nginx'] / 'rules/custom-rule.conf'
    existing.write_text('# existing customer configuration\n')
    page.locator('#new_rule_file').fill('custom-rule')
    with page.expect_response(lambda response: response.url.endswith('/rule/create')) as conflict:
        button.click()
    assert conflict.value.status == 409
    expect(page.locator('#waf-create-error')).to_have_text(messages['conflict'])
    expect(dialog).to_be_visible()
    expect(button).to_be_enabled()
    assert existing.read_text() == '# existing customer configuration\n'


def test_double_submit_and_close_are_blocked_during_creation(logged_in, product_url, product, waf_creation):
    page = logged_in
    dialog, button = open_creation(page, product_url, product, 'nginx')
    pending = []
    page.route('**/rule/create', lambda route: pending.append(route))
    with page.expect_request('**/rule/create'):
        button.click()
    expect(button).to_be_disabled()
    expect(page.locator('#new_rule_name')).to_be_disabled()
    page.evaluate("$('#waf-create-form').trigger('submit'); $('#add-new-config').dialog('close');")
    expect(dialog).to_be_visible()
    assert len(pending) == 1
    pending[0].fulfill(status=500, json={'status': 'failed'})
    expect(button).to_be_enabled()
    expect(page.locator('#new_rule_name')).to_have_value(NAME)
    expect(page.locator('#waf-create-error')).to_be_visible()
