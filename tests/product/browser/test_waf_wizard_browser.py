import os
import re

import pytest
from playwright.sync_api import expect

from app.modules.config import waf_wizard, waf_state
from app.modules.db.db_model import Waf, WafNginx, WafRules
from app.modules.roxywi import common


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


def choose(page, name, value, messages):
    page.locator(f'#wizard-{name}-button').click()
    page.get_by_role('option', name=messages[value], exact=True).click()


def open_form(page, product_url, product, service, locale):
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    page.locator('.waf-rule-actions .add-button').click()
    page.locator('[data-waf-wizard-link]').click()
    expect(page.locator('#waf-wizard')).to_be_visible()
    page.locator('#new_waf_rule').fill('Правило · règle · 规则')
    page.locator('#new_rule_file').fill(' wizard-test ')
    page.locator('#new_rule_description').fill('Form test & <literal>')
    page.locator('#wizard-value').fill('/admin')


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_wizard_preview_save_reopen_and_apply_in_all_languages(logged_in, product_url, product, wizard_host,
                                                             app, locale, service):
    page = logged_in
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_wizard
    open_form(page, product_url, product, service, locale)
    expect(page.locator('h2')).to_contain_text(messages['title'])
    expect(page.locator('[data-waf-apply-button]')).to_have_count(0)
    words = app.jinja_env.get_template(f'languages/{locale}.html').module.words
    expect(page.locator('#wizard-preview-button')).to_have_text(words['generate'].title() + ' ' + words['config'])
    page.locator('#wizard-preview-button').click()
    dialog = page.get_by_role('dialog', name=words['generated'].title() + ' ' + words['config'], exact=True)
    expect(dialog).to_be_visible()
    expect(page.locator('.ui-widget-overlay')).to_be_visible()
    expect(page.locator('[data-generated]')).to_contain_text('Roxy-WI MANAGED')
    assert not wizard_host.apply_calls
    page.keyboard.press('Escape')
    expect(dialog).to_be_hidden()
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page).to_have_url(re.compile(r'/rule/\d+/wizard$'))
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')
    expect(page.locator('[data-waf-apply-label]')).to_be_visible()
    expect(page.locator('#new_rule_file')).to_have_value('wizard-test.conf')
    page.reload()
    expect(page.locator('#wizard-value')).to_have_value('/admin')
    expect(page.locator('#new_waf_rule')).to_have_attribute('readonly', '')
    page.locator('#wizard-value').fill('/private')
    page.locator('#wizard-preview-button').click()
    expect(page.locator('[data-previous]')).to_contain_text('Roxy-WI MANAGED')
    dialog.locator('summary').click()
    expect(page.locator('[data-previous]')).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    # Reopening recalculates the shared dialog size for a narrow viewport.
    page.keyboard.press('Escape')
    page.locator('#wizard-preview-button').click()
    expect(dialog).to_be_visible()
    box = dialog.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 391
    dialog.get_by_role('button', name=words['close'].title(), exact=True).last.click()
    expect(dialog).to_be_hidden()
    action = 'restart' if service == 'haproxy' else 'reload'
    page.locator(f'#waf-wizard button[value="{action}"]').click()
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'applied')
    expect(page.locator('[data-waf-apply-label]')).to_be_hidden()
    rule = WafRules.get(WafRules.serv == product.server.ip, WafRules.service == service)
    assert waf_wizard.read_spec((wizard_host.roots[service] / 'rules/wizard-test.conf').read_text())['conditions'][0]['value'] == '/private'
    assert rule.wizard
    page.reload()
    expect(page.locator('#wizard-value')).to_have_value('/private')
    expect(page.locator('[data-waf-apply-label]')).to_be_hidden()


@pytest.mark.parametrize('locale', LOCALES)
def test_exclusion_fields_and_failed_save_keep_form_values(logged_in, product_url, product, wizard_host, app, locale):
    page = logged_in
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_wizard
    open_form(page, product_url, product, 'nginx', locale)
    choose(page, 'kind', 'exclusion', messages)
    expect(page.locator('[data-field="field"]')).to_be_visible()
    expect(page.locator('[data-field="action"]')).to_be_hidden()
    page.locator('#wizard-exclude-id').fill('942100')
    page.locator('#wizard-exclude-parameter').fill('body')
    page.locator('#wizard-preview-button').click()
    expect(page.locator('[data-generated]')).to_contain_text('ctl:ruleRemoveTargetById=942100;ARGS:body')
    page.keyboard.press('Escape')
    wizard_host.fail_before = True
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page.locator('#wizard-error')).to_have_text(messages['failed'])
    expect(page.locator('#wizard-value')).to_have_value('/admin')
    expect(page.locator('#wizard-exclude-parameter')).to_have_value('body')
    expect(page.locator('#waf-wizard button[value="save"]')).to_be_enabled()
    wizard_host.fail_before = False
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')
    page.reload()
    expect(page.locator('#wizard-kind')).to_have_value('exclusion')
    expect(page.locator('#wizard-exclude-parameter')).to_have_value('body')


def test_no_duplicate_submit_and_fields_locked_during_save(logged_in, product_url, product, wizard_host):
    page = logged_in
    open_form(page, product_url, product, 'nginx', 'en')
    pending = []
    page.route('**/wizard', lambda route: pending.append(route))
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page.locator('#wizard-value')).to_be_disabled()
    expect(page.locator('#wizard-kind-button')).to_have_attribute('aria-disabled', 'true')
    page.evaluate("$('#waf-wizard').trigger('submit')")
    assert len(pending) == 1
    pending[0].fulfill(status=500, json={'error': '<script>untrusted</script>'})
    expect(page.locator('#wizard-error')).to_have_text('<script>untrusted</script>')
    expect(page.locator('#wizard-error script')).to_have_count(0)
    expect(page.locator('#wizard-value')).to_be_enabled()


def test_hidden_fields_do_not_block_other_rule_types(logged_in, product_url, product, wizard_host, app):
    page = logged_in
    messages = app.jinja_env.get_template('languages/en.html').module.waf_wizard
    open_form(page, product_url, product, 'nginx', 'en')
    choose(page, 'field', 'header', messages)
    page.locator('#wizard-key').fill('invalid|name')
    choose(page, 'kind', 'exclusion', messages)
    page.locator('#wizard-exclude-parameter').fill('invalid|parameter')
    choose(page, 'kind', 'rule', messages)
    choose(page, 'field', 'uri', messages)
    expect(page.locator('#wizard-key')).to_be_disabled()
    expect(page.locator('#wizard-exclude-parameter')).to_be_disabled()
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')


def test_home_plan_sees_enterprise_requirement_and_keeps_manual_editor(logged_in, product_url, product,
                                                                    wizard_host, monkeypatch):
    monkeypatch.setattr(common, 'return_user_subscription', lambda: {'user_status': 1, 'user_plan': 'user'})
    page = logged_in
    page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rules')
    page.locator('.waf-rule-actions .add-button').click()
    expect(page.locator('[data-waf-wizard-link]')).to_contain_text('Enterprise')
    expect(page.locator('.add-button')).to_be_visible()
    page.locator('[data-waf-wizard-link]').click()
    expect(page.locator('body')).to_contain_text('requires an active Enterprise plan')
    expect(page.locator('#waf-wizard')).to_have_count(0)
    assert not wizard_host.commands


@pytest.mark.parametrize('locale', LOCALES)
def test_single_add_menu_and_responsive_wizard(logged_in, product_url, product, wizard_host, app, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_wizard
    page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rules')
    actions = page.locator('.waf-rule-actions')
    trigger = actions.locator('.add-button')
    expect(trigger).to_have_count(1)
    expect(actions.locator('[data-waf-wizard-link]')).to_be_hidden()
    expect(actions.locator('[data-waf-manual]')).to_be_hidden()
    table_box = page.locator('#waf_rules').bounding_box()
    assert actions.bounding_box()['y'] - table_box['height'] - table_box['y'] >= 12
    trigger.focus()
    page.keyboard.press('Enter')
    expect(trigger).to_have_attribute('aria-expanded', 'true')
    expect(actions.get_by_role('menuitem', name=messages['manual_editor'], exact=True)).to_be_visible()
    page.keyboard.press('Escape')
    expect(trigger).to_have_attribute('aria-expanded', 'false')
    trigger.click()
    actions.locator('[data-waf-manual]').click()
    expect(page.locator('#add-new-config')).to_be_visible()
    expect(actions.get_by_role('menu')).to_be_hidden()
    page.get_by_role('dialog').locator('.ui-dialog-buttonpane button').last.click()
    expect(page.locator('#add-new-config')).to_be_hidden()
    trigger.click()
    actions.locator('[data-waf-wizard-link]').click()
    expect(page.locator('#waf-wizard')).to_be_visible()
    label = page.locator('label[for="new_waf_rule"]')
    field = page.locator('#new_waf_rule')
    label_box = label.bounding_box()
    assert label_box['x'] + label_box['width'] <= field.bounding_box()['x']
    for width in (1440, 600):
        page.set_viewport_size({'width': width, 'height': 1000})
        wizard = page.locator('.waf-wizard')
        assert wizard.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
        expect(page.get_by_text(messages['managed'], exact=True)).to_be_visible()
    assert not wizard_host.commands


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('match', ['all', 'any'])
def test_compound_conditions_auto_ids_and_reopen(logged_in, product_url, product, wizard_host, app, locale, match):
    page = logged_in
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_wizard
    reserved = wizard_host.roots['nginx'] / 'rules/reserved.conf'
    reserved.write_text('SecAction "id:10000,phase:1,pass"\n')
    open_form(page, product_url, product, 'nginx', locale)
    expect(page.locator('#wizard-auto-id')).to_be_checked()
    expect(page.locator('#wizard-id')).to_be_disabled()
    choose(page, 'match', match, messages)
    page.get_by_role('button', name=messages['add_condition'], exact=True).click()
    expect(page.locator('[data-condition]')).to_have_count(2)
    page.locator('#wizard-field-1-button').click()
    page.get_by_role('option', name=messages['method'], exact=True).click()
    page.locator('#wizard-value-1').fill('POST')
    page.locator('#wizard-preview-button').click()
    expect(page.locator('[data-generated]')).to_contain_text('id:10001,phase:1')
    expect(page.locator('[data-generated]')).to_contain_text('chain' if match == 'all' else 'id:10002,phase:1')
    page.keyboard.press('Escape')
    # A read-only preview does not reserve IDs; save rechecks availability.
    reserved.write_text('SecAction "id:10000,phase:1,pass"\nSecAction "id:10001,phase:1,pass"\n')
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page).to_have_url(re.compile(r'/rule/\d+/wizard$'))
    expect(page.locator('#wizard-id')).to_have_value('10002')
    expect(page.locator('#wizard-auto-id')).not_to_be_checked()
    page.reload()
    expect(page.locator('#wizard-match')).to_have_value(match)
    expect(page.locator('#wizard-value-1')).to_have_value('POST')
    expect(page.locator('#wizard-value')).to_have_value('/admin')
    page.locator('[data-condition]').nth(1).get_by_role('button', name=messages['remove_condition'], exact=True).click()
    expect(page.locator('[data-condition]')).to_have_count(1)
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page.locator('#waf-wizard button[value="save"]')).to_be_enabled()
    saved = waf_wizard.read_spec((wizard_host.roots['nginx'] / 'rules/wizard-test.conf').read_text())
    assert len(saved['conditions']) == 1 and saved['id'] == 10002


def test_global_exclusion_and_hidden_conditions(logged_in, product_url, product, wizard_host, app):
    page = logged_in
    messages = app.jinja_env.get_template('languages/en.html').module.waf_wizard
    open_form(page, product_url, product, 'nginx', 'en')
    choose(page, 'kind', 'exclusion', messages)
    page.locator('#wizard-exclude-id').fill('942100')
    page.locator('label[for="wizard-all-requests"]').click()
    expect(page.locator('#wizard-condition-list')).to_be_hidden()
    expect(page.locator('#wizard-value')).to_be_disabled()
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page).to_have_url(re.compile(r'/rule/\d+/wizard$'))
    page.reload()
    expect(page.locator('#wizard-all-requests')).to_be_checked()
    saved = waf_wizard.read_spec((wizard_host.roots['nginx'] / 'rules/wizard-test.conf').read_text())
    assert saved['conditions'] == [] and saved['exclude_id'] == 942100


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_master_rule_creation_and_disable_visible_on_slave(logged_in, product_url, product, wizard_host,
                                                         waf_cluster, app, service):
    page = logged_in
    slave, roots = waf_cluster
    open_form(page, product_url, product, service, 'ru')
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page).to_have_url(re.compile(r'/rule/\d+/wizard$'))
    source = WafRules.get(WafRules.serv == product.server.ip, WafRules.service == service)
    replica = WafRules.get(WafRules.serv == slave.ip, WafRules.service == service)
    page.goto(f'{product_url}/waf/{service}/{slave.ip}/rules')
    expect(page.locator(f'#rule_id-{replica.id}')).to_be_checked()
    page.locator(f'#rule-{replica.id} .admin-actions-toggle').click()
    page.locator(f'#rule-{replica.id} a').click()
    expect(page.locator('#wizard-value')).to_have_value('/admin')
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    with page.expect_response(lambda response: response.url.endswith(f'/rule/{source.id}/0')) as disabled:
        page.locator(f'label[for="rule_id-{source.id}"]').click()
    assert disabled.value.status == 200
    page.goto(f'{product_url}/waf/{service}/{slave.ip}/rules')
    expect(page.locator(f'#rule_id-{replica.id}')).not_to_be_checked()
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'pending')
    assert (roots[service] / 'rules/wizard-test.conf').read_bytes() == (
        wizard_host.roots[service] / 'rules/wizard-test.conf').read_bytes()


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_server_selection_preserves_fields_and_targets_preview_and_save(logged_in, product_url, product,
                                                                       wizard_host, waf_cluster, service, locale):
    page = logged_in
    slave, roots = waf_cluster
    if service == 'haproxy':
        Waf.create(server_id=slave.server_id, metrics=0)
    else:
        WafNginx.create(server_id=slave.server_id)
    with waf_state.track_changes(slave.server_id, service, applying=True):
        pass
    (roots[service] / 'rules/reserved.conf').write_text('SecAction "id:10000,phase:1,pass"\n')
    open_form(page, product_url, product, service, locale)
    server = page.locator('#wizard-server')
    expect(server).to_have_value(product.server.ip)
    expect(page.locator('#wizard-server-button')).to_contain_text(product.server.hostname)
    page.locator('#wizard-server-button').click()
    page.get_by_role('option', name=slave.hostname, exact=True).click()
    expect(server).to_have_value(slave.ip)
    expect(page.locator('#wizard-value')).to_have_value('/admin')

    expect(page.locator('#new_rule_file')).to_have_value(' wizard-test ')
    expect(page.locator('[data-waf-sync-hint]')).to_be_hidden()
    expect(page.locator('[data-waf-rules-link]')).to_have_attribute('href', f'/waf/{service}/{slave.ip}/rules')
    expect(page.locator('[data-waf-apply]')).to_have_attribute('data-state', 'applied')
    page.locator('#wizard-preview-button').click()
    expect(page.locator('[data-generated]')).to_contain_text('id:10001,phase:1')
    page.keyboard.press('Escape')
    page.locator('#waf-wizard button[value="save"]').click()
    expect(page).to_have_url(re.compile(rf'/waf/{service}/{re.escape(slave.ip)}/rule/\d+/wizard$'))
    expect(server).to_be_disabled()
    expect(page.locator('#wizard-server-button')).to_have_attribute('aria-disabled', 'true')
    assert WafRules.get().serv == slave.ip
    assert (roots[service] / 'rules/wizard-test.conf').exists()
    assert not (wizard_host.roots[service] / 'rules/wizard-test.conf').exists()
    page.reload()
    expect(server).to_be_disabled()
    expect(server).to_have_value(slave.ip)
    expect(page.locator('#wizard-value')).to_have_value('/admin')


def test_late_state_response_cannot_replace_selected_server(logged_in, product_url, product, wizard_host, waf_cluster):
    page = logged_in
    slave, _ = waf_cluster
    WafNginx.create(server_id=slave.server_id)
    open_form(page, product_url, product, 'nginx', 'en')
    pending = []
    page.route(f'**/waf/nginx/{slave.ip}/state?*', lambda route: pending.append(route))
    page.locator('#wizard-server-button').click()
    page.get_by_role('option', name=slave.hostname, exact=True).click()
    expect(page.locator('#waf-wizard')).to_have_attribute('action', f'/waf/nginx/{slave.ip}/wizard')
    page.locator('#wizard-server-button').click()
    page.get_by_role('option', name=product.server.hostname, exact=True).click()
    panel = page.locator('[data-waf-apply]')
    expect(panel).to_have_attribute('data-state-url', f'/waf/nginx/{product.server.ip}/state?button=0')
    assert len(pending) == 1
    pending[0].fulfill(body='<div data-waf-apply>Stale target</div>', content_type='text/html')
    expect(panel).to_have_attribute('data-state-url', f'/waf/nginx/{product.server.ip}/state?button=0')
    expect(page.locator('[data-waf-sync-hint]')).to_be_visible()
    expect(page.locator('#wizard-value')).to_have_value('/admin')
