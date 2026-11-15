import os
import re
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.db.db_model import InstallationTasks
from app.modules.service import proxy_assessments
from tests.product.test_proxy_diagnostics import diagnostic_host

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


@pytest.mark.parametrize('locale,title', [('en', 'Service map'), ('ru', 'Карта сервисов')])
def test_map_is_first_in_services_and_has_localized_title(logged_in, product_url, locale, title):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/insights/services')
    expect(page).to_have_title(title)
    expect(page.locator('h2 .rw-workspace-title')).to_have_text(title)
    services = page.locator('[data-nav-group="services"] > .nav-group-items')
    expect(services.locator(':scope > li').first.get_by_role('link')).to_have_text(title)
    expect(services.locator(':scope > li').first.get_by_role('link')).to_have_class(re.compile('menu-active'))
    expect(page.locator('[data-nav-group="operations"] a[href="/insights/services"]')).to_have_count(0)


def test_actions_heading_does_not_reorder_rows(logged_in, product_url, product_client, product, diagnostic_host):
    from app.modules.db.db_model import Server
    from tests.product.test_service_map import discover, confirm
    assert confirm(product_client, discover(product_client)).status_code == 201
    Server.create(server_id=44, hostname='Another proxy', ip='192.0.2.44', group_id='1', cred_id=11, haproxy=1)
    queued = product_client.post('/insights/api/services/discover', json=dict(service='haproxy', server_id=44))
    assert queued.status_code == 202
    assert proxy_assessments.execute(InstallationTasks.get_by_id(queued.json['task_id'])) == 'completed'
    page = logged_in
    page.goto(product_url + '/insights/services')
    rows = page.locator('#map-rows tr')
    expect(rows).to_have_count(2)
    proxy_header = page.locator('#map-table th').nth(2)
    proxy_header.click()
    expect(proxy_header).to_have_attribute('aria-sort', 'ascending')
    assert rows.first.locator('td').nth(2).inner_text().startswith('Another proxy')
    before = rows.all_text_contents()
    page.locator('#map-table th').last.click()
    expect(proxy_header).to_have_attribute('aria-sort', 'ascending')
    assert rows.all_text_contents() == before


def test_publication_map_discovery_confirmation_and_impact_use_native_controls(logged_in,product_url,diagnostic_host):
    page=logged_in;page.goto(product_url+'/insights/services')
    page.locator('#map-server-button').click();page.get_by_role('option',name='Product HAProxy (192.0.2.11)',exact=True).click()
    with page.expect_response('**/services/discover') as queued:page.get_by_role('button',name='Discover proxy configuration').click()
    assert queued.value.status==202
    assert proxy_assessments.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    expect(page.locator('#map-rows')).to_contain_text('example.test',timeout=10000)
    page.get_by_role('button',name='Confirm relationship',exact=True).click()
    page.locator('#map-note').fill('Confirmed against application inventory')
    page.get_by_role('button',name='Record confirmation',exact=True).click()
    expect(page.locator('#map-rows')).to_contain_text('confirmed')
    if os.environ.get('ROXYWI_CAPTURE_MAP_DOCS')=='1':
        page.wait_for_load_state('networkidle');folder=Path(__file__).resolve().parents[3]/'docs/screenshots/service-map';folder.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(folder/'map.png'))
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
    page.get_by_role('button',name='Retract confirmation',exact=True).click()
    expect(page.locator('#map-rows .rw-status-badge').first).to_have_text('discovered')


@pytest.mark.parametrize('width,theme', [(1440,'light'), (1440,'dark'), (390,'dark')])
def test_map_uses_compact_actions_dialog_and_responsive_layout(logged_in, product_url, product_client, diagnostic_host, width, theme):
    from tests.product.test_service_map import discover, confirm
    assert confirm(product_client, discover(product_client)).status_code == 201
    page = logged_in
    page.set_viewport_size(dict(width=width, height=1000))
    page.add_init_script("localStorage.setItem('theme', '" + theme + "')")
    page.goto(product_url + '/insights/services')
    expect(page.locator('#published-services')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#map-table')).to_have_class(re.compile('rw-table-responsive'))
    expect(page.locator('.rw-table-search-toolbar input')).to_have_class(re.compile('form-control'))
    actions = page.locator('#map-rows .map-row-actions')
    expect(actions.locator('svg')).to_have_count(3)
    expect(actions.get_by_role('link', name='Diagnose', exact=True)).to_be_visible()
    expect(actions.get_by_role('button', name='Retract confirmation', exact=True)).to_be_visible()
    assert actions.evaluate('(row) => row.scrollWidth <= row.clientWidth')
    bounds = [button.bounding_box() for button in actions.locator('a, button').all()]
    assert max(box['y'] for box in bounds) - min(box['y'] for box in bounds) <= 1
    assert all(box['width'] == 34 for box in bounds)
    header = page.locator('#map-table th').last
    assert header.get_attribute('role') is None
    assert header.get_attribute('aria-sort') is None
    assert header.get_attribute('tabindex') is None
    assert header.evaluate("node => getComputedStyle(node, '::after').content") == 'none'
    if width > 720:
        assert header.bounding_box()['width'] <= 140
        header.click()
        assert header.get_attribute('aria-sort') is None
    page.screenshot(path=f'.test-artifacts/service-map-{theme}-{width}.png', full_page=True, animations='disabled')
    page.get_by_role('button', name='Confirm relationship', exact=True).click()
    dialog = page.get_by_role('dialog', name='Confirm publication relationship', exact=True)
    expect(dialog).to_be_visible()
    assert 'rw-dialog-responsive' in dialog.get_attribute('class')
    assert page.locator('dialog').count() == 0
    page.locator('#map-note').fill('Operator evidence in the standard dialog')
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
    bounds = dialog.bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    if os.environ.get('ROXYWI_CAPTURE_MAP_DOCS') == '1':
        folder = Path(__file__).resolve().parents[3]/'docs/screenshots/service-map'
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder/f'confirmation-{theme}-{width}.png'), full_page=True, animations='disabled')
    page.get_by_role('button', name='Cancel', exact=True).click()
    expect(dialog).not_to_be_visible()
    search = page.locator('.rw-table-search-toolbar input')
    search.fill('no-such-publication')
    expect(page.locator('.rw-table-empty')).to_be_visible()
    search.fill('')
    expect(page.locator('#map-rows tr')).to_be_visible()
    if os.environ.get('ROXYWI_CAPTURE_MAP_DOCS') == '1':
        name = 'map.png' if theme == 'light' else f'map-{theme}-{width}.png'
        page.screenshot(path=str(folder/name), full_page=True, animations='disabled')


def test_empty_map_error_and_refresh_use_shared_feedback_without_losing_data(logged_in, product_url, product_client, diagnostic_host):
    from tests.product.test_service_map import discover
    page = logged_in
    page.goto(product_url + '/insights/services')
    expect(page.locator('.rw-table-empty')).to_be_visible()
    discover(product_client)
    page.get_by_role('button', name='Refresh map', exact=True).click()
    expect(page.locator('#map-rows')).to_contain_text('example.test')
    endpoint = product_url + '/insights/api/services'
    page.route(endpoint, lambda route: route.fulfill(status=502, json={'error':'Discovery backend unavailable'}))
    page.get_by_role('button', name='Refresh map', exact=True).click()
    expect(page.locator('#map-message')).to_have_class(re.compile('rw-error-state'))
    expect(page.locator('#map-message')).to_contain_text('last successful refresh')
    expect(page.locator('#map-rows')).to_contain_text('example.test')
    page.unroute(endpoint)
    page.get_by_role('button', name='Refresh map', exact=True).click()
    expect(page.locator('#map-message')).not_to_have_class(re.compile('rw-error-state'))


@pytest.mark.usefixtures('service_worker_controls','host_metrics')
def test_map_diagnose_link_opens_upstream_service_card_dialog(logged_in, product_url, product_client, diagnostic_host):
    from tests.product.test_service_map import discover
    from tests.product.browser.test_proxy_diagnostics_browser import open_diagnostics, close_diagnostics
    page = logged_in
    open_diagnostics(page, product_url)
    close_diagnostics(page)
    discover(product_client)
    page.goto(product_url + '/insights/services')
    expect(page.locator('#map-rows')).to_contain_text('example.test')
    page.get_by_role('link', name='Diagnose', exact=True).click()
    expect(page).to_have_url(product_url + '/service/haproxy?diagnostics=11')
    expect(page.locator('.proxy-diagnostics-dialog')).to_be_visible()
    expect(page.locator('.proxy-diagnostics-dialog .ui-dialog-title')).to_contain_text('Product HAProxy (192.0.2.11)')
