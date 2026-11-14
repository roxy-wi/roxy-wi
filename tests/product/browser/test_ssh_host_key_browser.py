"""Confirm, cancel and retry SSH trust using the real administration page."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server
from app.modules.server import host_keys
from tests.product.test_ssh_host_key_confirmation import ssh_peer


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def add_form(page, product_url):
    page.goto(product_url + '/admin#servers')
    page.locator('#add-server-button').click()
    page.locator('#new-server-add').fill('SSH approval test')
    page.locator('#new-ip').fill('192.0.2.33')
    page.locator('#new-port').fill('2222')
    page.evaluate("$('#credentials').val('11').selectmenu('refresh')")
    return page.locator('.ui-dialog').filter(has=page.locator('#server-add-table'))


@pytest.mark.parametrize('width,theme,locale', [(1440, 'light', 'en'), (390, 'dark', 'ru')])
def test_cancel_preserves_form_and_confirm_creates_server(logged_in, product_url, ssh_peer, width, theme, locale):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 900})
    page.add_init_script("localStorage.setItem('theme', '" + theme + "')")
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    form = add_form(page, product_url)
    form.locator('.ui-dialog-buttonpane button').first.click()
    review = page.locator('.ssh-host-key-dialog')
    expect(review).to_be_visible()
    expect(review).to_contain_text(host_keys.fingerprint(ssh_peer.key))
    expect(review).to_contain_text('192.0.2.33')
    expect(review).to_contain_text('2222')
    cancel = review.locator('..').locator('.ui-dialog-buttonpane button').last
    expect(cancel).to_be_focused()
    assert not Server.select().where(Server.ip == '192.0.2.33').exists()
    assert ssh_peer.scans == []
    bounds = review.locator('..').bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    page.screenshot(path=f'.test-artifacts/ssh-confirmation-{locale}-{width}.png')
    page.keyboard.press('Escape')
    expect(review).to_have_count(0)
    expect(page.locator('#new-ip')).to_have_value('192.0.2.33')
    form.locator('.ui-dialog-buttonpane button').first.click()
    expect(review).to_be_visible()
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/server')) as response:
        review.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    assert response.value.status == 201, response.value.text()
    expect(page.locator('#server-add-table')).to_be_hidden()
    assert Server.get(Server.ip == '192.0.2.33').ssh_host_key == ssh_peer.key
    assert len(ssh_peer.scans) == 1


def test_changed_key_is_shown_again_without_saving(logged_in, product_url, ssh_peer):
    page = logged_in
    form = add_form(page, product_url)
    form.locator('.ui-dialog-buttonpane button').first.click()
    review = page.locator('.ssh-host-key-dialog')
    expect(review).to_be_visible()
    previous = host_keys.fingerprint(ssh_peer.key)
    ssh_peer.key = ssh_peer.replacement
    review.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    expect(review).to_contain_text('has changed')
    expect(review).to_contain_text(previous)
    expect(review).to_contain_text(host_keys.fingerprint(ssh_peer.key))
    review.locator('..').locator('.ui-dialog-buttonpane button').last.click()
    expect(review).to_have_count(0)
    assert not Server.select().where(Server.ip == '192.0.2.33').exists()
    assert not ssh_peer.scans


def test_check_ssh_requires_confirmation_before_authentication(logged_in, product_url, ssh_peer, monkeypatch):
    authenticated = []
    monkeypatch.setattr('app.modules.server.server.ssh_command',
                        lambda *args, **kwargs: authenticated.append(args) or 'ok')
    page = logged_in
    page.goto(product_url + '/admin#servers')
    row = page.locator('#server-11')
    page.add_style_tag(content='* {scroll-behavior:auto !important;}')
    row.locator('.admin-actions-toggle').scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    row.locator('.admin-actions-toggle').click()
    row.get_by_role('button', name='Check SSH', exact=True).click()
    review = page.locator('.ssh-host-key-dialog')
    expect(review).to_be_visible()
    assert not authenticated
    review.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    expect(page.locator('.toast-message').filter(has_text='Connect is accepted')).to_be_visible()
    assert len(authenticated) == 1
    assert Server.get_by_id(11).ssh_host_key == ssh_peer.key


def test_connection_failure_keeps_form_editable_for_retry(logged_in, product_url, ssh_peer, monkeypatch):
    page = logged_in
    form = add_form(page, product_url)
    original = host_keys.probe

    def unavailable(*args):
        raise host_keys.HostKeyError('Cannot read the SSH host key.')

    monkeypatch.setattr(host_keys, 'probe', unavailable)
    form.locator('.ui-dialog-buttonpane button').first.click()
    expect(page.locator('.toast-message').filter(has_text='Cannot read the SSH host key')).to_be_visible()
    expect(page.locator('.ssh-host-key-dialog')).to_have_count(0)
    page.locator('#new-port').fill('2223')
    monkeypatch.setattr(host_keys, 'probe', original)
    # Rapid duplicate submissions must still produce just one review request.
    page.evaluate("() => {addServer(document.getElementById('server-add-table')); addServer(document.getElementById('server-add-table'));}")
    review = page.locator('.ssh-host-key-dialog')
    expect(review).to_be_visible()
    expect(review).to_contain_text('2223')
    assert ssh_peer.probes == [('192.0.2.33', 2223)]
    review.locator('..').locator('.ui-dialog-buttonpane button').last.click()
    expect(review).to_have_count(0)
    assert not ssh_peer.scans
