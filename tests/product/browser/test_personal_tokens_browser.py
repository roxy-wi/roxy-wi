import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


def test_create_once_use_and_revoke_personal_token(logged_in, product_url):
    page = logged_in
    page.goto(product_url+'/user/api-access')
    form = page.locator('#personal-token-form')
    form.get_by_label('Name', exact=True).fill('CI inventory integration')
    form.locator('[name="scope"][value="inventory.read"]').check(force=True)
    form.get_by_label('Current password', exact=True).fill('TestBootstrapPassword!')
    form.get_by_role('button', name='Create personal token', exact=True).click()
    expect(page.locator('#personal-token-status')).to_have_text('Token created. Copy it now.')
    value = page.locator('#personal-token-value')
    token = value.input_value()
    assert token.startswith('eyJ')
    assert token not in page.request.get(product_url+'/user/personal-tokens').text()
    assert token not in page.evaluate('JSON.stringify(window.localStorage)')
    assert token not in page.evaluate('JSON.stringify(window.sessionStorage)')
    response = page.request.get(product_url+'/api/servers', headers={'Authorization': 'Bearer '+token})
    assert response.status == 200
    page.get_by_role('button', name='Hide token', exact=True).click()
    expect(value).to_have_value('')
    expect(page.locator('#personal-token-created')).not_to_be_visible()
    page.reload()
    row = page.locator('#personal-token-table tr').filter(has_text='CI inventory integration')
    expect(row).to_contain_text('Active')
    capture = os.environ.get('ROXYWI_CAPTURE_PAT_SCREENSHOTS')
    if capture:
        folder = Path(capture)
        folder.mkdir(parents=True, exist_ok=True)
        expect(page.locator('#nprogress')).to_have_count(0)
        page.screenshot(path=str(folder/'personal-tokens-light.png'))
        page.evaluate("changeTheme('dark')")
        page.wait_for_timeout(300)
        page.screenshot(path=str(folder/'personal-tokens-dark.png'))
    page.on('dialog', lambda dialog: dialog.accept())
    row.get_by_role('button', name='Revoke', exact=True).click()
    expect(row).to_contain_text('Revoked')
    assert page.request.get(product_url+'/api/servers', headers={'Authorization': 'Bearer '+token}).status in {401, 422}
    page.reload()
    expect(page.locator('#personal-token-created')).not_to_be_visible()
    expect(value).to_have_value('')


def test_token_name_is_rendered_as_text_and_no_scope_is_preselected(logged_in, product_url):
    page = logged_in
    page.goto(product_url+'/user/api-access')
    form = page.locator('#personal-token-form')
    expect(form.locator('[name="scope"]:checked')).to_have_count(0)
    expect(form.get_by_label('Validity in days (1–365)', exact=True)).to_have_value('90')
    name = '<img src=x onerror=alert(1)>'
    form.get_by_label('Name', exact=True).fill(name)
    form.locator('[name="scope"][value="inventory.read"]').check(force=True)
    form.get_by_label('Current password', exact=True).fill('TestBootstrapPassword!')
    form.get_by_role('button', name='Create personal token', exact=True).click()
    expect(page.locator('#personal-token-status')).to_have_text('Token created. Copy it now.')
    expect(page.locator('#personal-token-table')).to_contain_text(name)
    expect(page.locator('#personal-token-table img')).to_have_count(0)
    page.get_by_role('button', name='Hide token', exact=True).click()
