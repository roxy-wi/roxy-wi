import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import WafRules


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LOCALES = ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh']


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_toggle_restores_last_confirmed_checkbox_on_failure_and_retries(logged_in, product_url, product,
                                                                       waf_switching, service, locale, app):
    page = logged_in
    state = waf_switching
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    rule = state.rules[service]
    page.goto(f'{product_url}/waf/{service}/{product.server.ip}/rules')
    checkbox = page.locator(f'#rule_id-{rule.id}')
    label = page.locator(f'label[for="rule_id-{rule.id}"]')
    row = page.locator(f'#rule-{rule.id}')
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_toggle
    url = f'/waf/{service}/{product.server.ip}/rule/{rule.id}/'
    expect(checkbox).to_be_checked()
    state.fail_before = True
    with page.expect_response(lambda response: response.url.endswith(url + '0')) as failure:
        label.click()
    assert failure.value.status == 500
    expect(checkbox).to_be_checked()
    expect(checkbox).to_be_enabled()
    expect(page.locator('.toast-error')).to_contain_text(messages['failed'])
    expect(page.locator('.toast-info')).to_have_count(0)
    assert WafRules.get_by_id(rule.id).en == 1

    state.fail_before = False
    with page.expect_response(lambda response: response.url.endswith(url + '0')) as saved:
        label.click()
    assert saved.value.status == 200
    expect(checkbox).not_to_be_checked()
    expect(checkbox).to_be_enabled()
    expect(row).to_have_attribute('data-enabled', '0')
    expect(page.locator('.toast-info')).to_contain_text(messages['saved_' + service])
    expect(page.locator('.toast-error')).to_have_count(0)
    assert WafRules.get_by_id(rule.id).en == 0

    state.fail_before = True
    with page.expect_response(lambda response: response.url.endswith(url + '1')) as failed_enable:
        label.click()
    assert failed_enable.value.status == 500
    expect(checkbox).not_to_be_checked()
    expect(checkbox).to_be_enabled()
    expect(page.locator('.toast-error')).to_contain_text(messages['failed'])
    assert WafRules.get_by_id(rule.id).en == 0


@pytest.mark.parametrize('locale', LOCALES)
def test_wildcard_conflict_is_visible_and_checkbox_stays_enabled(logged_in, product_url, product, waf_switching,
                                                               app, locale):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    entrypoint = waf_switching.entrypoints['nginx']
    entrypoint.write_text(entrypoint.read_text().replace('test.conf', '*.conf'))
    rule = waf_switching.rules['nginx']
    page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rules')
    with page.expect_response(lambda response: response.url.endswith(f'/rule/{rule.id}/0')) as response:
        page.locator(f'label[for="rule_id-{rule.id}"]').click()
    assert response.value.status == 409
    expect(page.locator(f'#rule_id-{rule.id}')).to_be_checked()
    expect(page.locator(f'#rule_id-{rule.id}')).to_be_enabled()
    message = app.jinja_env.get_template(f'languages/{locale}.html').module.waf_toggle['conflict']
    expect(page.locator('.toast-error')).to_contain_text(message)


@pytest.mark.parametrize('response_body', ['{"status":"updated","enabled":1}', 'null'])
def test_pending_toggle_blocks_duplicate_submission_and_rejects_unconfirmed_response(logged_in, product_url,
                                                                                    product, waf_switching, response_body):
    page = logged_in
    rule = waf_switching.rules['nginx']
    page.goto(f'{product_url}/waf/nginx/{product.server.ip}/rules')
    pending = []
    page.route(f'**/waf/nginx/{product.server.ip}/rule/{rule.id}/0', lambda route: pending.append(route))
    with page.expect_request(f'**/rule/{rule.id}/0'):
        page.locator(f'label[for="rule_id-{rule.id}"]').click()
    checkbox = page.locator(f'#rule_id-{rule.id}')
    expect(checkbox).to_be_disabled()
    page.evaluate('(id) => $("#rule_id-" + id).prop("checked", true).trigger("change")', rule.id)
    expect(checkbox).not_to_be_checked()
    assert len(pending) == 1
    pending[0].fulfill(body=response_body, content_type='application/json')
    expect(checkbox).to_be_enabled()
    expect(checkbox).to_be_checked()
    expect(page.locator('.toast-error')).to_contain_text(page.locator('#waf_rules').get_attribute('data-toggle-error'))
    expect(page.locator('.toast-info')).to_have_count(0)
