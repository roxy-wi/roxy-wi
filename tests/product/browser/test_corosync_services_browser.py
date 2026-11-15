"""Use the user and server service selectors through the real administration UI."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server, User


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('kind', ['user', 'server'])
def test_corosync_service_can_be_added_removed_and_saved(logged_in, product_url, product, kind):
    page = logged_in
    ident = product.admin.user_id if kind == 'user' else product.server.server_id
    tab = 'users' if kind == 'user' else 'servers'

    def open_dialog():
        page.goto(product_url + '/admin#' + tab)
        row = page.locator(f'#{kind}-{ident}')
        toggle = row.locator('.admin-actions-toggle')
        toggle.scroll_into_view_if_needed()
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        toggle.click()
        row.get_by_role('button', name='Change Services', exact=True).click()
        dialog = page.locator('.ui-dialog').filter(has=page.locator('#checked_services'))
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text('Corosync / Pacemaker')
        return dialog

    def stored():
        if kind == 'user':
            return '7' in User.get_by_id(ident).user_services.split()
        return bool(Server.get_by_id(ident).corosync)

    initial = stored()
    for enabled in (not initial, initial):
        dialog = open_dialog()
        selector = '#add_service-7' if enabled else '#remove_service-7'
        dialog.locator(selector + ' span').click()
        expect(dialog.locator('#checked_services #remove_service-7')).to_have_count(int(enabled))
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith(f'/{kind}/services/{ident}')) as response:
            dialog.get_by_role('button', name='Save', exact=True).click()
        assert response.value.status == 200, response.value.text()
        assert stored() == enabled
    dialog = open_dialog()
    expect(dialog.locator('#checked_services #remove_service-7')).to_have_count(int(initial))
    page.screenshot(path=f'.test-artifacts/corosync-{kind}-services.png', animations='disabled')
    dialog.get_by_role('button', name='Cancel', exact=True).click()
