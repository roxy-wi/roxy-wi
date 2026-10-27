"""Sessions UI against the real routes and synthetic HAProxy transport."""
import os
import threading

import pytest
from playwright.sync_api import expect

from app.modules.config import runtime
from app.modules.db.db_model import Server, UserGroups
from tests.fixtures.haproxy_sessions import sessions_host  # noqa: F401
from tests.product.browser.test_haproxy_stats_browser import select_stats_option


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def open_sessions(page, product_url):
    page.goto(product_url + '/stats/haproxy/192.0.2.11?view=sessions')
    expect(page.locator('.hs-session-row')).to_have_count(3)
    select_stats_option(page, 'interval', '0')


def session_menu(page, session_id='0x7f001'):
    row = page.locator(f'.hs-session-row[data-session-id="{session_id}"]')
    row.scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    row.locator('.admin-actions-toggle').click()
    return row


def test_sessions_lazy_loading_scope_search_details_refresh_and_raw_text(logged_in, product_url, sessions_host, tmp_path):
    page = logged_in
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    expect(page.locator('.hs-row')).to_have_count(5)
    assert all(command != 'show sess' for _, command in sessions_host.calls)
    select_stats_option(page, 'interval', '0')
    page.locator('.hs-row').filter(has=page.locator('button[aria-label="Details: web/one"]')).locator('.hs-session-count-link').click()
    expect(page.locator('.hs-session-row')).to_have_count(1)
    expect(page.locator('#hs-session-scope')).to_have_text('web/one ×')
    page.locator('#hs-session-scope').click()
    expect(page.locator('.hs-session-row')).to_have_count(3)
    page.locator('#hs-session-search').fill('2001:db8')
    expect(page.locator('.hs-session-row')).to_have_count(1)
    sessions_host.detail_override = 'Unknown <img src=x onerror="window.sessionXss=true"> raw format\n'
    page.locator('.hs-session-row .hs-session-link').click()
    expect(page.locator('#hs-session-detail')).to_contain_text('2001:db8::20:60421')
    expect(page.locator('#hs-session-detail')).to_contain_text('viewing only')
    page.locator('#hs-session-detail summary').click()
    expect(page.locator('#hs-session-detail pre')).to_have_text(sessions_host.detail_override)
    assert page.locator('#hs-session-detail img').count() == 0
    assert page.evaluate('window.sessionXss === undefined')
    sessions_host.rows[1]['age'] = '55s'
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-session-detail')).to_contain_text('55s')
    expect(page.locator('#hs-session-search')).to_have_value('2001:db8')
    expect(page.locator('#hs-session-detail pre')).to_be_visible()
    page.screenshot(path=str(tmp_path / 'sessions-desktop.png'), full_page=True, animations='disabled')
    page.locator('#hs-session-search').fill('')
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('.container')).to_have_css('margin-left', '0px')
    page.screenshot(path=str(tmp_path / 'sessions-mobile.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_session_confirmation_cancel_terminate_and_gone(logged_in, product_url, sessions_host):
    page = logged_in
    open_sessions(page, product_url)
    session_menu(page).locator('[data-action=terminate]').click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_contain_text('203.0.113.42:51832')
    expect(dialog).to_contain_text('192.0.2.11')
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert sessions_host.writes == []
    page.locator('#hs-session-detail .hs-session-terminate').click()
    expect(dialog).to_be_visible()
    dialog.get_by_role('button', name='Terminate session', exact=True).click()
    expect(page.locator('.hs-session-row')).to_have_count(2)
    expect(page.locator('#hs-action-result')).to_contain_text('terminated')
    assert sessions_host.writes == [('192.0.2.11', 'shutdown session 0x7f001')]
    sessions_host.rows = []
    page.locator('.hs-session-row .hs-session-link').first.click()
    expect(page.locator('#hs-action-result')).to_contain_text('no longer available')
    expect(page.locator('#hs-session-empty')).to_be_visible()


def test_read_only_user_and_stale_snapshot(logged_in, product_url, product, sessions_host):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = logged_in
    open_sessions(page, product_url)
    row = session_menu(page)
    expect(row.locator('[data-action=terminate]')).to_have_count(0)
    row.locator('[data-action=details]').click()
    expect(page.locator('#hs-session-detail')).to_be_visible()
    expect(page.locator('.hs-session-terminate')).to_have_count(0)
    sessions_host.read_failure = ConnectionRefusedError('private')
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-error')).to_contain_text('Data is stale')
    expect(page.locator('.hs-session-row .hs-session-link').first).to_be_disabled()
    sessions_host.read_failure = None
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-error')).to_be_hidden()
    expect(page.locator('.hs-session-row .hs-session-link').first).to_be_enabled()


def test_pagination_auto_refresh_and_tab_switch_cancel_confirmation(logged_in, product_url, sessions_host):
    page = logged_in
    open_sessions(page, product_url)
    template = sessions_host.rows[0]
    sessions_host.rows += [{**template, 'id': hex(0x8000 + index), 'src': f'192.0.2.{index}:50000'} for index in range(51)]
    page.locator('#hs-refresh').click()
    expect(page.locator('.hs-session-row')).to_have_count(50)
    page.locator('#hs-session-next').click()
    expect(page.locator('.hs-session-row')).to_have_count(4)
    expect(page.locator('#hs-session-page')).to_have_text('2 / 2')
    page.locator('#hs-session-prev').click()
    session_menu(page).locator('[data-action=terminate]').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    # Trigger navigation while a modal is open, as a server change can also do.
    page.locator('#hs-tab-overview').dispatch_event('click')
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(page.locator('#hs-overview')).to_be_visible()
    assert sessions_host.writes == []
    page.locator('#hs-tab-sessions').click()
    select_stats_option(page, 'interval', '5')
    sessions_host.rows = sessions_host.rows[:3]
    expect(page.locator('.hs-session-row')).to_have_count(3, timeout=10000)
    expect(page.locator('#hs-session-pages')).to_be_hidden()


def test_switch_node_discards_pending_session_details(logged_in, product_url, sessions_host, monkeypatch):
    Server.create(server_id=33, hostname='Second HAProxy', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    page = logged_in
    open_sessions(page, product_url)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = runtime.show_session

    def delayed(server, session_id, *, sock_port):
        entered.set()
        try:
            assert release.wait(10), 'Test did not release the old session detail'
            return original(server, session_id, sock_port=sock_port)
        finally:
            finished.set()

    monkeypatch.setattr(runtime, 'show_session', delayed)
    try:
        page.locator('.hs-session-row .hs-session-link').first.click()
        assert entered.wait(5)
        select_stats_option(page, 'server', '192.0.2.33')
        expect(page.locator('.hs-session-row')).to_have_count(3)
        expect(page.locator('#hs-refresh')).to_be_enabled()
    finally:
        release.set()
    assert finished.wait(5)
    expect(page.locator('#hs-session-detail')).to_be_hidden()
    expect(page).to_have_url(product_url + '/stats/haproxy/192.0.2.33?view=sessions')
    assert sessions_host.writes == []


@pytest.mark.parametrize('language', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_session_translations(logged_in, product_url, app, sessions_host, language):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': language, 'url': product_url}])
    open_sessions(page, product_url)
    labels = app.jinja_env.get_template(f'languages/{language}.html').module.haproxy_stats
    expect(page.locator('#hs-tab-sessions')).to_have_text(labels['sessions_tab'])
    page.locator('.hs-session-row .hs-session-link').first.click()
    expect(page.locator('#hs-session-detail .hs-session-terminate')).to_have_text(labels['session_terminate'])
    page.locator('#hs-session-detail .hs-session-terminate').click()
    expect(page.get_by_role('dialog')).to_contain_text(labels['session_terminate_hint'])
    page.get_by_role('dialog').get_by_role('button', name=labels['cancel'], exact=True).click()
