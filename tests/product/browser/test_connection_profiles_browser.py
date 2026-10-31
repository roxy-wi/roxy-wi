import os
from pathlib import Path

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


def select(page, key, value, label):
    selector = '#connection-profile-' + key
    if page.locator(selector).is_visible():
        page.locator(selector).select_option(value)
    else:
        page.locator(selector + '-button').click()
        page.locator(selector + '-menu').get_by_role('option', name=label, exact=True).click()


def test_profile_creation_edit_and_check_do_not_return_saved_password(logged_in, product_url, monkeypatch):
    monkeypatch.setattr('app.routes.admin.connection_profiles.check_connection',
                        lambda value: {'status': 'connected', 'detail': 'Transport checked'})
    page = logged_in
    page.goto(product_url + '/admin/connections')
    page.get_by_role('button', name='New connection profile', exact=True).click()
    form = page.locator('#connection-profile-form')
    form.get_by_label('Name', exact=True).fill('Browser audit receiver')
    select(page, 'transport', 'https', 'HTTPS')
    form.get_by_label('HTTPS receiver URL', exact=True).fill('https://audit.example.test/events')
    select(page, 'auth', 'basic', 'Basic')
    form.get_by_label('Username', exact=True).fill('audit-user')
    form.get_by_label('Password', exact=True).fill('SyntheticBrowserPassword!')
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#connection-profile-status')).to_have_text('Connection profile saved.')
    saved = page.request.get(product_url + '/admin/connection-profiles').json()['profiles'][0]
    assert saved['configured']['password'] is True
    assert saved['settings']['auth'] == 'basic'
    row = page.locator('#connection-profile-table tr').filter(has_text='Browser audit receiver')
    expect(row).to_have_count(1)
    row.get_by_role('button', name='Edit', exact=True).click()
    expect(form).to_be_visible()
    expect(form.get_by_label('Password', exact=True)).to_have_value('')
    expect(form.locator('[data-configured="password"]')).to_have_text('Configured')
    form.get_by_label('Name', exact=True).fill('Updated browser receiver')
    form.get_by_role('button', name='Save', exact=True).click()
    row = page.locator('#connection-profile-table tr').filter(has_text='Updated browser receiver')
    expect(row).to_have_count(1)
    row.get_by_role('button', name='Test connection', exact=True).click()
    expect(page.locator('#connection-profile-status')).to_have_text('Transport checked')
    expect(page.locator('body')).not_to_contain_text('SyntheticBrowserPassword!')
    capture = os.environ.get('ROXYWI_CAPTURE_PROFILE_SCREENSHOTS')
    if capture:
        folder = Path(capture)
        folder.mkdir(parents=True, exist_ok=True)
        row.get_by_role('button', name='Edit', exact=True).click()
        expect(form.get_by_label('Password', exact=True)).to_have_value('')
        expect(page.locator('#nprogress')).to_have_count(0)
        page.screenshot(path=str(folder / 'connection-profiles-light.png'))
        page.evaluate("changeTheme('dark')")
        page.wait_for_timeout(300)
        page.screenshot(path=str(folder / 'connection-profiles-dark.png'))


def test_profile_names_are_rendered_as_text(logged_in, product_url):
    page = logged_in
    page.goto(product_url + '/admin/connections')
    page.get_by_role('button', name='New connection profile', exact=True).click()
    form = page.locator('#connection-profile-form')
    name = '<img src=x onerror="throw new Error(1)">'
    form.get_by_label('Name', exact=True).fill(name)
    form.get_by_label('Host', exact=True).fill('audit.example.test')
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#connection-profile-status')).to_have_text('Connection profile saved.')
    expect(page.locator('#connection-profile-table')).to_contain_text(name)
    expect(page.locator('#connection-profile-table img')).to_have_count(0)
