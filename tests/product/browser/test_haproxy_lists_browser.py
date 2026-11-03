import os

import pytest
from playwright.sync_api import expect

from tests.fixtures.haproxy_lists import list_hosts


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


def open_lists(page, url):
    page.goto(url + '/add/haproxy#lists')
    page.locator('#lists-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#lists-table')).to_contain_text('allowed.lst')


def test_edit_empty_list_and_validation_keeps_dialog_open(logged_in, product_url, list_hosts, product, tmp_path):
    page = logged_in
    open_lists(page, product_url)
    page.locator('#lists-table .admin-actions-toggle').click()
    menu = page.locator('#lists-table .admin-actions-menu')
    expect(menu).to_be_visible()
    expect(menu.locator('svg')).to_have_count(4)
    menu.get_by_role('button', name='Edit', exact=True).click()
    expect(page.locator('#lists-content')).to_have_value('192.0.2.1\n')
    dialog = page.get_by_role('dialog').filter(has=page.locator('#lists-editor'))
    expect(page.locator('#nprogress')).to_have_count(0)
    bounds = dialog.bounding_box()
    assert bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= 1000
    page.screenshot(path=str(tmp_path / 'lists-desktop.png'))
    page.locator('#lists-content').fill('192.0.2.1\nnot-an-ip')
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#lists-editor-status')).to_contain_text('Line 2')
    expect(dialog).to_be_visible()
    expect(page.locator('#lists-content')).to_have_value('192.0.2.1\nnot-an-ip')
    page.locator('#lists-content').fill('')
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#lists-results')).to_contain_text('Applied')
    expect(page.locator('#lists-editor-status')).to_have_text('Saved')
    assert list_hosts.local.read_text() == ''
    page.set_viewport_size({'width': 390, 'height': 844})
    bounds = dialog.bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
    assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth')
    expect(page.locator('#nprogress')).to_have_count(0)
    page.screenshot(path=str(tmp_path / 'lists-mobile.png'))


def test_compare_runtime_then_create_and_delete_unused_list(logged_in, product_url, product, list_hosts):
    page = logged_in
    list_hosts.nodes[product.server.ip].active = ['2001:db8::1']
    open_lists(page, product_url)
    page.locator('#lists-table .lists-name-button').click()
    expect(page.locator('#lists-sources')).to_contain_text('Differences')
    expect(page.locator('#lists-comparison')).to_have_attribute('open', '')
    page.locator('#lists-sources button').last.click()
    expect(page.locator('#lists-content')).to_have_value('2001:db8::1\n')
    dialog = page.get_by_role('dialog').filter(has=page.locator('#lists-editor'))
    dialog.locator('.ui-dialog-buttonpane').get_by_role('button', name='Close', exact=True).click()
    page.locator('#lists-create').click()
    page.locator('#lists-name').fill('office.prod.lst')
    page.locator('#lists-entry').fill('192.0.2.0/24')
    page.locator('#lists-add-entry').click()
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#lists-results')).to_contain_text('Not used')
    dialog.locator('.ui-dialog-buttonpane').get_by_role('button', name='Close', exact=True).click()
    row = page.locator('#lists-table tbody tr').filter(has_text='office.prod.lst')
    row.locator('.admin-actions-toggle').click()
    row.get_by_role('button', name='Delete', exact=True).click()
    confirm = page.get_by_role('dialog').filter(has_text='Delete this list from Roxy-WI')
    confirm.get_by_role('button', name='Delete', exact=True).click()
    expect(row).to_have_count(0)
    page.goto(product_url + '/runtimeapi')
    expect(page.locator('a[href="#lists"]')).to_have_count(0)
