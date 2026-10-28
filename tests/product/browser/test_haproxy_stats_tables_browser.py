"""Stick-table UI with real routes, authentication and synthetic TCP replies."""
import os
import threading

import pytest
from playwright.sync_api import expect

from app.modules.config import runtime
from app.modules.db.db_model import UserGroups
from tests.fixtures.haproxy_tables import tables_host  # noqa: F401
from tests.product.browser.test_haproxy_stats_browser import select_stats_option


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def open_tables(page, product_url):
    page.goto(product_url + '/stats/haproxy/192.0.2.11?view=tables')
    expect(page.locator('.hs-stick-row')).to_have_count(2)
    select_stats_option(page, 'interval', '0')


def entry_menu(page, index=0):
    row = page.locator('.hs-stick-row').nth(index)
    row.scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    row.locator('.admin-actions-toggle').click()
    return row


def test_lazy_loading_search_details_refresh_ipv6_and_mobile(logged_in, product_url, tables_host, tmp_path):
    page = logged_in
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    expect(page.locator('.hs-row')).to_have_count(5)
    assert not any('table' in command for _, command in tables_host.calls)
    page.locator('#hs-tab-tables').click()
    expect(page.locator('.hs-stick-row')).to_have_count(2)
    select_stats_option(page, 'interval', '0')
    expect(page.locator('#hs-table-meta')).to_contain_text('2 / 200,000')
    page.locator('#hs-table-search').fill('203.0')
    expect(page.locator('.hs-stick-row')).to_have_count(1)
    page.locator('.hs-table-key').click()
    expect(page.locator('#hs-table-detail')).to_contain_text('http_req_rate(10000)')
    tables_host.tables['clients']['rows'][0] = tables_host.tables['clients']['rows'][0].replace('=12 ', '=19 ')
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-table-detail')).to_contain_text('19')
    expect(page.locator('#hs-table-search')).to_have_value('203.0')
    page.screenshot(path=str(tmp_path / 'tables-desktop.png'), full_page=True, animations='disabled')
    page.locator('#hs-table-select').select_option('peers/ipv6')
    expect(page.locator('.hs-table-key')).to_have_text(['2001:db8::1'])
    expect(page.locator('#hs-table-search')).to_have_value('')
    expect(page.locator('#hs-table-detail')).to_be_hidden()
    page.locator('.hs-table-key').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('.container')).to_have_css('margin-left', '0px')
    page.screenshot(path=str(tmp_path / 'tables-mobile.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_delete_cancel_and_partial_clear(logged_in, product_url, tables_host):
    page = logged_in
    open_tables(page, product_url)
    entry_menu(page).locator('[data-action=delete]').click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_contain_text('192.0.2.11 / clients / 203.0.113.42')
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert tables_host.writes == []
    entry_menu(page).locator('[data-action=delete]').click()
    dialog.get_by_role('button', name='Delete entry', exact=True).click()
    expect(page.locator('.hs-stick-row')).to_have_count(1)
    expect(page.locator('#hs-action-result')).to_contain_text('Entries observed after the operation: 1')
    page.locator('#hs-table-clear').click()
    expect(dialog).to_contain_text('Entries in use may remain')
    dialog.get_by_role('button', name='Clear table', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('Table cleanup completed.')
    expect(page.locator('#hs-action-result')).to_contain_text(': 1')
    assert tables_host.writes[-1][1] == 'clear table clients'


def test_in_use_failure_stale_state_and_switch_cancels_confirmation(logged_in, product_url, tables_host):
    page = logged_in
    open_tables(page, product_url)
    entry_menu(page, 1).locator('[data-action=delete]').click()
    page.get_by_role('dialog').get_by_role('button', name='Delete entry', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('entry is in use')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    page.locator('#hs-table-clear').click()
    # A server/view change can also arrive from navigation, not just a mouse click.
    page.evaluate("document.getElementById('hs-tab-overview').click()")
    expect(page.get_by_role('dialog')).to_have_count(0)
    assert len(tables_host.writes) == 1
    page.locator('#hs-tab-tables').click()
    expect(page.locator('#hs-refresh')).to_be_enabled()
    tables_host.read_failure = TimeoutError('private')
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-error')).to_be_visible()
    expect(page.locator('#hs-table-clear')).to_be_disabled()
    assert len(tables_host.writes) == 1


def test_reader_and_xss_keys(logged_in, product_url, product, tables_host):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    tables_host.tables['tokens']['rows'] = [r'0x400: key=<img\ src\=x\ onerror\=alert(1)> use=0 exp=1 gpc0=0']
    page = logged_in
    open_tables(page, product_url)
    expect(page.locator('#hs-table-clear')).to_have_count(0)
    page.locator('#hs-table-select').select_option('tokens')
    expect(page.locator('.hs-table-key')).to_have_text(['<img src=x onerror=alert(1)>'])
    page.locator('.hs-table-key').click()
    expect(page.locator('#hs-table-detail')).to_be_visible()
    expect(page.locator('#hs-tables img')).to_have_count(0)
    expect(page.locator('[data-action=delete]')).to_have_count(0)
    assert tables_host.writes == []


def test_switch_ignores_late_reply(logged_in, product_url, tables_host, monkeypatch):
    page = logged_in
    open_tables(page, product_url)
    original = runtime.execute_runtime_command
    started, release = threading.Event(), threading.Event()

    def delayed(server, port, command):
        if command == 'show table clients':
            started.set()
            assert release.wait(10)
        return original(server, port, command)

    monkeypatch.setattr(runtime, 'execute_runtime_command', delayed)
    try:
        page.locator('#hs-refresh').click()
        assert started.wait(5)
        page.locator('#hs-table-select').select_option('peers/ipv6')
        expect(page.locator('.hs-table-key')).to_have_text(['2001:db8::1'])
        release.set()
        expect(page.locator('#hs-table-select')).to_have_value('peers/ipv6')
        expect(page.locator('#hs-table-meta')).to_contain_text('ipv6')
    finally:
        release.set()


def test_pagination_and_empty_catalogue(logged_in, product_url, tables_host):
    tables_host.tables['clients']['rows'] = [
        f'0x{index + 1:x}: key=192.0.2.{index} use=0 exp=30000 gpc0={index}' for index in range(120)
    ]
    page = logged_in
    page.goto(product_url + '/stats/haproxy/192.0.2.11?view=tables')
    expect(page.locator('.hs-stick-row')).to_have_count(50)
    select_stats_option(page, 'interval', '0')
    expect(page.locator('#hs-table-page')).to_have_text('1 / 3')
    page.locator('#hs-table-next').click()
    expect(page.locator('#hs-table-page')).to_have_text('2 / 3')
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-refresh')).to_be_enabled()
    expect(page.locator('#hs-table-page')).to_have_text('2 / 3')
    page.locator('#hs-table-search').fill('192.0.2.119')
    expect(page.locator('.hs-table-key')).to_have_text(['192.0.2.119'])
    expect(page.locator('#hs-table-pages')).to_be_hidden()
    tables_host.tables.clear()
    page.reload()
    expect(page.locator('#hs-table-empty')).to_have_text('No stick tables are configured on this node.')
    expect(page.locator('#hs-table-clear')).to_be_disabled()


def test_refresh_recovers_after_selected_table_is_removed(logged_in, product_url, tables_host):
    page = logged_in
    open_tables(page, product_url)
    del tables_host.tables['clients']
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-error')).to_contain_text('table is no longer available')
    expect(page.locator('#hs-table-clear')).to_be_disabled()
    page.locator('#hs-refresh').click()
    expect(page.locator('.hs-table-key')).to_have_text(['2001:db8::1'])
    expect(page.locator('#hs-table-select')).to_have_value('peers/ipv6')
    expect(page.locator('#hs-error')).to_be_hidden()


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_translations_and_removed_runtime_tab(logged_in, product_url, tables_host, locale, app):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.haproxy_stats
    page.goto(product_url + '/stats/haproxy/192.0.2.11?view=tables')
    expect(page.locator('.hs-stick-row')).to_have_count(2)
    expect(page.locator('#hs-tab-tables')).to_have_text(labels['tables_tab'])
    page.locator('#hs-table-clear').click()
    expect(page.get_by_role('dialog')).to_contain_text(labels['table_clear_hint'])
    page.get_by_role('dialog').get_by_role('button', name=labels['cancel'], exact=True).click()
    page.goto(product_url + '/runtimeapi')
    expect(page.locator('#table')).to_have_count(0)
    expect(page.locator('#lists')).to_have_count(1)
    assert tables_host.writes == []
