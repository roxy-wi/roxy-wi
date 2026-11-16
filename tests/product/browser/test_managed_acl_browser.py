import os
import re
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.db.db_model import InstallationTasks,ManagedAclVersion
from app.modules.service import managed_acl
from tests.product.test_managed_acl import acl_host
from tests.product.test_ha_maintenance import approve

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_acl_gui_discovers_lists_and_reviews_version_without_automatic_apply(logged_in,product_url,acl_host,app):
    page=logged_in;page.goto(product_url+'/insights/acl-feeds');page.get_by_role('button',name='New managed feed',exact=True).click()
    page.locator('#acl-name').fill('Reviewed IP feed');page.locator('#acl-url').fill('https://feeds.example.test/ips.txt')
    page.locator('#acl-server-button').click();page.get_by_role('option',name='Product HAProxy (192.0.2.11)',exact=True).click()
    page.get_by_role('button',name='Discover IP lists',exact=True).click()
    page.locator('#acl-path-button').click();page.get_by_role('option',name='/etc/haproxy/black/list.lst · 1 entries',exact=True).click()
    page.get_by_role('button',name='Add target',exact=True).click();page.get_by_role('button',name='Save feed',exact=True).click()
    expect(page.locator('#acl-rows')).to_contain_text('Source approval required')
    page.get_by_role('button',name='Approve source and targets',exact=True).click()
    expect(page.locator('#acl-rows')).to_contain_text('Source revision approved')
    with page.expect_response('**/fetch') as queued:page.get_by_role('button',name='Fetch candidate',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click();page.get_by_role('button',name='Versions',exact=True).click()
    expect(page.locator('#acl-versions')).to_contain_text('downloaded')
    with page.expect_response('**/review') as reviewed:page.get_by_role('button',name='Review deployment',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(reviewed.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click()
    expect(page.locator('#acl-versions')).to_contain_text('pending_approval')
    assert not any(action=='apply' for _,action,_ in acl_host.remote)
    page.get_by_role('button',name='View content / diff',exact=True).click()
    expect(page.locator('#acl-diff')).to_contain_text('192.0.2.0/24')
    if os.environ.get('ROXYWI_CAPTURE_ACL_DOCS')=='1':
        page.wait_for_load_state('networkidle');folder=Path(__file__).resolve().parents[3]/'docs/screenshots/managed-acl';folder.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(folder/'feeds.png'))
    row=ManagedAclVersion.get()
    page.goto(product_url+'/insights/acl-feeds?change='+str(row.change_id))
    expect(page.locator('#acl-selected')).to_contain_text('Reviewed IP feed')
    expect(page.locator('#acl-diff')).to_contain_text('192.0.2.0/24')
    approve(app,row,acl_host.reviewer)
    page.get_by_role('button',name='Refresh feeds',exact=True).click()
    with page.expect_response('**/apply') as applied:page.get_by_role('button',name='Apply approved version',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(applied.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click();expect(page.locator('#acl-versions')).to_contain_text('deployed')
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')


def open_feed_dialog(page, product_url):
    page.goto(product_url + '/insights/acl-feeds')
    page.get_by_role('button', name='New managed feed', exact=True).click()
    dialog = page.get_by_role('dialog', name='New managed feed', exact=True)
    expect(dialog).to_be_visible()
    page.locator('#acl-name').fill('Reviewed IP feed')
    page.locator('#acl-url').fill('https://feeds.example.test/ips.txt')
    return dialog


def add_acl_target(page):
    page.locator('#acl-server-button').click()
    page.get_by_role('option', name='Product HAProxy (192.0.2.11)', exact=True).click()
    page.get_by_role('button', name='Discover IP lists', exact=True).click()
    page.locator('#acl-path-button').click()
    page.get_by_role('option', name='/etc/haproxy/black/list.lst · 1 entries', exact=True).click()
    page.get_by_role('button', name='Add target', exact=True).click()


@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
def test_acl_layout_modal_navigation_and_editing(logged_in, product_url, product_client, acl_host, width, theme):
    from tests.product.test_managed_acl import create

    row = create(product_client)
    page = logged_in
    page.set_viewport_size(dict(width=width, height=1000))
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(product_url + '/insights/acl-feeds')
    expect(page.locator('#acl-rows')).to_contain_text(row['name'])
    page.wait_for_load_state('networkidle')
    expect(page.locator('#nprogress')).to_have_count(0)
    link = page.locator('#app-navigation a[href="/insights/acl-feeds"]')
    expect(link).to_have_count(1)
    assert link.evaluate("node => node.closest('.nav-service').querySelector('#menu-haproxy') !== null")
    expect(link).to_have_class(re.compile('menu-active'))
    assert page.locator('#acl-help').evaluate('node => node === node.parentElement.lastElementChild')
    assert page.locator('#acl-help').evaluate(r'''node => {
        const luminance = color => {
            const channels = color.match(/[\d.]+/g).slice(0, 3).map(value => {
                const channel = Number(value) / 255;
                return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
            });
            return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
        };
        const text = luminance(getComputedStyle(node.querySelector('p')).color);
        const background = luminance(getComputedStyle(node).backgroundColor);
        return (Math.max(text, background) + 0.05) / (Math.min(text, background) + 0.05);
    }''') >= 4.5
    assert page.locator('#acl-table th').last.get_attribute('aria-sort') is None
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=f'.test-artifacts/acl-page-{theme}-{width}.png', full_page=True, animations='disabled')

    page.get_by_role('button', name='Edit', exact=True).click()
    dialog = page.get_by_role('dialog', name='Edit managed feed', exact=True)
    expect(dialog).to_be_visible()
    expect(page.locator('#acl-name')).to_have_value(row['name'])
    expect(page.locator('#acl-targets')).to_contain_text('/etc/haproxy/black/list.lst')
    assert dialog.locator('#acl-form').count() == 1
    bounds = dialog.bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    assert dialog.evaluate('node => { const box = node.getBoundingClientRect(); return node.contains(document.elementFromPoint(box.x + 24, box.y + 20)); }')
    assert dialog.locator('#acl-dialog').evaluate('node => node.scrollWidth <= node.clientWidth + 1')
    page.screenshot(path=f'.test-artifacts/acl-dialog-{theme}-{width}.png', full_page=True, animations='disabled')
    page.get_by_text('Source limits and TLS settings', exact=True).click()
    expect(page.locator('#acl-max')).to_have_value('50000')
    assert page.locator('#acl-dialog').evaluate('node => node.scrollWidth <= node.clientWidth + 1')
    page.locator('#acl-name').fill('Updated feed')
    page.get_by_role('button', name='Save feed', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('#acl-rows')).to_contain_text('Updated feed')


def test_acl_actions_headers_do_not_sort_feeds_or_versions(
        logged_in, product_url, product_client, acl_host):
    from app.modules.db.db_model import Server
    from tests.product.test_managed_acl import API, approve as approve_source, body, create, step

    feed = approve_source(product_client, create(product_client))
    step(product_client, feed, 'fetch')
    acl_host.content = '203.0.113.0/24\n'
    step(product_client, feed, 'fetch')
    Server.create(server_id=33, hostname='Peer', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    response = product_client.post(API, json=body(
        name='Second feed', targets=[dict(server_id=33, path='/etc/haproxy/black/list.lst')]))
    assert response.status_code == 201, response.text

    page = logged_in
    page.goto(product_url + '/insights/acl-feeds')
    expect(page.locator('#acl-rows tr')).to_have_count(2)
    page.locator('#acl-rows tr').filter(has_text=feed['name']).get_by_role(
        'button', name='Versions', exact=True).click()
    expect(page.locator('#acl-versions tr')).to_have_count(2)

    for table_id in ('acl-table', 'acl-versions-table'):
        table = page.locator('#' + table_id)
        identities = table.locator('tbody tr td:first-child strong')
        names = sorted(identities.all_text_contents())
        first_header = table.locator('thead th').first
        first_header.click()
        expect(first_header).to_have_attribute('aria-sort', 'ascending')
        expect(identities).to_have_text(names)
        first_header.press('Enter')
        expect(first_header).to_have_attribute('aria-sort', 'descending')
        expect(identities).to_have_text(list(reversed(names)))

        actions_header = table.locator('thead th').last
        for attribute in ('role', 'tabindex', 'aria-sort'):
            assert actions_header.get_attribute(attribute) is None
        assert actions_header.evaluate('node => getComputedStyle(node).cursor') != 'pointer'
        assert actions_header.evaluate('node => getComputedStyle(node).backgroundImage') == 'none'
        assert actions_header.evaluate('node => getComputedStyle(node, "::after").content') == 'none'

        actions_header.click()
        expect(identities).to_have_text(list(reversed(names)))
        expect(first_header).to_have_attribute('aria-sort', 'descending')
        for key in ('Enter', ' '):
            actions_header.dispatch_event('keydown', {'key': key, 'bubbles': True})
            expect(identities).to_have_text(list(reversed(names)))
            expect(first_header).to_have_attribute('aria-sort', 'descending')


def test_acl_save_failure_uses_toast_preserves_form_and_allows_retry(logged_in, product_url, acl_host):
    page = logged_in
    dialog = open_feed_dialog(page, product_url)
    add_acl_target(page)
    endpoint = product_url + '/insights/api/acl-feeds'
    held = []

    def delay_save(route):
        if route.request.method == 'POST':
            held.append(route)
        else:
            route.continue_()

    page.route(endpoint, delay_save)
    try:
        page.get_by_role('button', name='Save feed', exact=True).click()
        expect(page.locator('#acl-save')).to_be_disabled()
        page.locator('#acl-form').dispatch_event('submit')
        assert len(held) == 1
        held[0].fulfill(status=503, json={'error': 'Source backend unavailable <test>'})
        expect(page.locator('#toast-container .toast-error')).to_contain_text('Source backend unavailable <test>')
        expect(dialog).to_be_visible()
        expect(page.locator('#acl-name')).to_have_value('Reviewed IP feed')
        expect(page.locator('#acl-targets')).to_contain_text('/etc/haproxy/black/list.lst')
        expect(page.locator('#acl-save')).to_be_enabled()
        expect(page.locator('#acl-message')).not_to_contain_text('Source backend unavailable')
    finally:
        page.unroute(endpoint)
    page.get_by_role('button', name='Save feed', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('#acl-rows tr')).to_have_count(1)


def test_acl_closed_dialog_ignores_late_discovery(logged_in, product_url, acl_host):
    page = logged_in
    dialog = open_feed_dialog(page, product_url)
    page.locator('#acl-server-button').click()
    page.get_by_role('option', name='Product HAProxy (192.0.2.11)', exact=True).click()
    endpoint = product_url + '/insights/api/acl-feeds/discover'
    held = []
    page.route(endpoint, lambda route: held.append(route))
    try:
        page.get_by_role('button', name='Discover IP lists', exact=True).click()
        expect(page.locator('#acl-discover')).to_be_disabled()
        page.get_by_role('button', name='Cancel', exact=True).click()
        expect(dialog).not_to_be_visible()
        page.get_by_role('button', name='New managed feed', exact=True).click()
        expect(page.locator('#acl-name')).to_have_value('')
        with page.expect_response(endpoint):
            held[0].fulfill(status=200, json={'lists': [{'path': '/old-node.lst', 'entries': 1}]})
        expect(page.locator('#acl-path-button')).to_contain_text('Discover lists first')
        expect(page.locator('#acl-path option[value="/old-node.lst"]')).to_have_count(0)
        expect(page.locator('#acl-discover')).to_be_enabled()
    finally:
        page.unroute(endpoint)


def test_acl_refresh_errors_use_toasts_and_keep_last_successful_rows(logged_in, product_url, product_client, acl_host):
    from tests.product.test_managed_acl import create

    row = create(product_client)
    page = logged_in
    page.goto(product_url + '/insights/acl-feeds')
    expect(page.locator('#acl-rows')).to_contain_text(row['name'])
    endpoint = product_url + '/insights/api/acl-feeds'
    page.route(endpoint, lambda route: route.fulfill(status=502, json={'error': 'ACL backend unavailable'}))
    page.get_by_role('button', name='Refresh feeds', exact=True).click()
    expect(page.locator('#toast-container .toast-error')).to_contain_text('ACL backend unavailable')
    expect(page.locator('#acl-rows')).to_contain_text(row['name'])
    expect(page.locator('#acl-message')).not_to_contain_text('ACL backend unavailable')
    page.unroute(endpoint)
    page.get_by_role('button', name='Refresh feeds', exact=True).click()
    expect(page.locator('#acl-message')).to_contain_text('1 managed feed')
