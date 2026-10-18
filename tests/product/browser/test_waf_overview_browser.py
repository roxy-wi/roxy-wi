import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import HaCluster, HaClusterRouter, HaClusterSlave, Server, Waf


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_cards_keep_localized_controls_and_fit_desktop_and_mobile(logged_in, product_url, product,
                                                                waf_modes, app, locale, service):
    page = logged_in
    Server.create(server_id=33, hostname='Secondary WAF server', ip='192.0.2.33', group_id='1',
                  cred_id=11, haproxy=1, nginx=1)
    cluster = HaCluster.create(name='Product HA cluster', group_id=1, description='WAF cluster')
    router = HaClusterRouter.create(cluster_id=cluster.id)
    HaClusterSlave.create(cluster_id=cluster.id, server_id=product.server.server_id, router_id=router.id)
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    page.set_viewport_size({'width': 2160, 'height': 1000})
    page.goto(f'{product_url}/waf/{service}')
    cards = page.locator('[data-waf-card]')
    expect(cards).to_have_count(2)
    installed = cards.filter(has=page.locator('[data-waf-diagnostics]'))
    absent = cards.filter(has=page.locator('[onclick^="installWaf"]'))
    expect(installed).to_contain_text(product.server.hostname)
    expect(installed).to_contain_text(product.server.ip)
    address = installed.locator('.server-desc > strong')
    expect(address).to_have_text('IP: ' + product.server.ip)
    assert int(address.evaluate('(node) => getComputedStyle(node).fontWeight')) >= 600
    expect(installed.locator('.server-desc a')).to_have_text(cluster.name)
    expect(installed.locator('.server-desc a')).to_have_attribute('href', f'/ha/cluster/{cluster.id}')
    expect(absent.locator('.server-desc')).to_contain_text(messages.phrases['not_in_cluster'])
    expect(page.locator('label[for="service-server-search"]')).to_contain_text(messages.ux['search'])
    expect(page.locator('#service-status-filter')).to_be_enabled()
    expect(installed.locator('.service-feature')).to_have_count(0)
    expect(installed.locator('summary.rw-status-running')).to_have_text(messages.waf_diagnostics['process_running'])
    expect(installed.locator('[data-waf-mode] > label')).to_have_text(messages.waf_mode['label'])
    expect(installed.locator('[data-waf-apply-label]')).to_have_text(messages.waf_apply['unknown'])
    expect(installed.get_by_role('link', name=messages.words['logs'].title(), exact=True)).to_be_visible()
    expect(installed.locator(f'a[href="/waf/{service}/{product.server.ip}/rules"]')).to_be_visible()
    expect(installed.locator('.ajaxwafstatus')).to_have_count(1 if service == 'haproxy' else 0)
    if service == 'haproxy':
        expect(installed.locator('.ajaxwafstatus label')).to_be_visible()
        expect(installed.locator('.ajaxwafstatus label')).to_have_text(messages.words['metrics'].title())
        expect(installed.locator('.ajaxwafstatus input')).not_to_be_checked()
        for row in (installed.locator('.ajaxwafstatus'), installed.locator('footer')):
            expect(row).to_have_css('border-top-width', '0px')
            expect(row).to_have_css('border-bottom-width', '0px')
    expect(absent).to_contain_text('192.0.2.33')
    expect(absent.locator('[data-waf-mode], [data-waf-apply]')).to_have_count(0)
    expect(absent.locator('.rw-status-badge.rw-status-stale')).to_be_visible()
    for card in (installed, absent):
        assert card.bounding_box()['width'] <= 500
    mode = installed.locator('.ui-selectmenu-button')
    assert mode.bounding_box()['width'] <= 200
    label_box = installed.locator('[data-waf-mode] > label').bounding_box()
    mode_box = mode.bounding_box()
    assert label_box['x'] + label_box['width'] <= mode_box['x']
    assert abs(label_box['y'] + label_box['height'] / 2 - mode_box['y'] - mode_box['height'] / 2) <= 1
    header = installed.locator('header').bounding_box()
    assert 0 <= address.bounding_box()['y'] - header['y'] - header['height'] <= 4
    if service == 'haproxy':
        assert abs(installed.locator('.ajaxwafstatus label').bounding_box()['x'] - address.bounding_box()['x']) <= 1
    page.set_viewport_size({'width': 1440, 'height': 1000})
    expect(installed.locator('[data-waf-apply-button]')).not_to_be_visible()
    installed.locator('.admin-actions-toggle').click()
    expect(installed.locator('[data-waf-apply-button]')).to_be_visible()
    for action, icon in [('start', 'play'), ('stop', 'stop'),
                         ('restart' if service == 'haproxy' else 'reload', 'redo' if service == 'haproxy' else 'sync')]:
        control = installed.locator('.' + action + '-waf')
        label = {'start': 'enable', 'stop': 'disable'}.get(action, action) if service == 'nginx' else action
        expect(control).to_have_text(messages.words[label].title())
        expect(control.locator('.fa-' + icon)).to_be_visible()
    page.keyboard.press('Escape')
    expect(installed.locator('[data-waf-apply-button]')).not_to_be_visible()
    first, second = (card.bounding_box() for card in (installed, absent))
    assert abs(first['y'] - second['y']) < 2
    assert abs(first['x'] - second['x']) > first['width']
    if locale == 'ru':
        path = Path('.test-artifacts') / f'waf-overview-{service}-desktop.png'
        path.parent.mkdir(exist_ok=True)
        page.locator('.service-overview-page').screenshot(path=str(path))
    page.set_viewport_size({'width': 1250, 'height': 1000})
    first, second = (card.bounding_box() for card in (installed, absent))
    assert abs(first['y'] - second['y']) < 2
    assert 390 <= first['width'] <= 500
    assert abs(second['x'] - first['x'] - first['width'] - 14) <= 1
    page.set_viewport_size({'width': 390, 'height': 844})
    # The shared shell animates its sidebar margin when crossing the breakpoint.
    page.wait_for_function('getComputedStyle(document.querySelector(".container")).marginLeft === "0px"')
    page.wait_for_function('''() => Array.from(document.querySelectorAll('[data-waf-card]')).every(card => {
        const box = card.getBoundingClientRect();
        return box.x >= 0 && box.right <= window.innerWidth;
    })''')
    for card in (installed, absent):
        box = card.bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= 391
    assert mode.bounding_box()['width'] <= 200
    first, second = (card.bounding_box() for card in (installed, absent))
    assert abs(first['x'] - second['x']) < 2
    assert abs(first['y'] - second['y']) >= min(first['height'], second['height'])
    installed.locator('.admin-actions-toggle').click()
    menu = installed.locator('.admin-actions-menu').bounding_box()
    assert menu['x'] >= 0 and menu['x'] + menu['width'] <= 391
    page.keyboard.press('Escape')
    if locale == 'ru':
        page.locator('.service-overview-page').screenshot(path=f'.test-artifacts/waf-overview-{service}-mobile.png')


@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_shared_search_and_status_filter_follow_waf_refresh(logged_in, product_url, product, waf_modes, app, service):
    page = logged_in
    Server.create(server_id=33, hostname='Secondary WAF server', ip='192.0.2.33', group_id='1',
                  cred_id=11, haproxy=1, nginx=1)
    page.goto(f'{product_url}/waf/{service}')
    expect(page.locator('[data-waf-card]')).to_have_count(2)
    card = page.locator('[data-waf-card]').filter(has_text=product.server.hostname)
    absent = page.locator('[data-waf-slot]').filter(has_text='Secondary WAF server')
    search = page.locator('#service-server-search')
    search.fill('SECONDARY')
    expect(card).to_be_hidden()
    expect(absent).to_be_visible()
    search.fill(product.server.ip)
    expect(card).to_be_visible()
    expect(absent).to_be_hidden()
    search.fill('')
    messages = app.jinja_env.get_template('languages/en.html').module

    def status(value):
        label = messages.words['running'].title() if value == 'running' else messages.ux[value]
        page.locator('#service-status-filter-button').click()
        page.get_by_role('option', name=label, exact=True).click()

    status('running')
    expect(card).to_be_visible()
    expect(absent).to_be_hidden()
    original = dict(waf_modes.diagnostics[service])
    for values, expected in [({'process': 'stopped', 'check': 'not_checked'}, 'stopped'),
                             ({'check': 'unready' if service == 'haproxy' else 'invalid'}, 'unavailable'),
                             ({'process': 'unknown'}, 'stale'), ({}, 'running')]:
        waf_modes.diagnostics[service] = {**original, **values}
        with page.expect_response(lambda response: f'/waf/overview/{service}/{product.server.ip}' in response.url):
            page.locator('[data-waf-refresh]').click()
        expect(card).to_have_attribute('data-service-status', expected)
        expect(card).to_be_visible() if expected == 'running' else expect(card).to_be_hidden()
        status(expected)
        expect(card).to_be_visible()
        expect(absent).to_be_visible() if expected == 'stale' else expect(absent).to_be_hidden()
        status('running')
    page.route(f'**/waf/overview/{service}/{product.server.ip}', lambda route: route.fulfill(status=500))
    page.locator('[data-waf-refresh]').click()
    expect(card).to_have_attribute('data-service-status', 'stale')
    expect(card).to_be_hidden()
    status('stale')
    expect(card).to_be_visible()
    expect(page.locator('[data-waf-error]:visible')).to_have_count(1)
    page.unroute(f'**/waf/overview/{service}/{product.server.ip}')
    page.locator('[data-waf-retry]:visible').click()
    expect(card).to_have_attribute('data-service-status', 'running')
    expect(card).to_be_hidden()
    status('all')
    expect(card).to_be_visible()
    expect(absent).to_be_visible()


def test_failed_refresh_preserves_card_and_retry_recovers(logged_in, product_url, product, waf_modes, app):
    page = logged_in
    page.goto(product_url + '/waf/nginx')
    card = page.locator('[data-waf-card]')
    expect(card).to_be_visible()
    request_url = f'**/waf/overview/nginx/{product.server.ip}'
    requests = []
    page.route(request_url, lambda route: requests.append(route))
    page.locator('[data-waf-refresh]').click()
    expect(page.locator('[data-waf-slot]')).to_have_attribute('aria-busy', 'true')
    page.locator('[data-waf-refresh]').click()
    expect(card).to_contain_text(product.server.hostname)
    assert len(requests) == 1
    requests[0].fulfill(status=500, body='failed')
    expect(page.locator('[data-waf-error]')).to_be_visible()
    expect(page.locator('[data-waf-retry]')).to_have_text(app.jinja_env.get_template('languages/en.html').module.config_viewer['retry'])
    expect(card).to_be_visible()
    page.unroute(request_url)
    page.locator('[data-waf-retry]').click()
    expect(page.locator('[data-waf-error]')).not_to_be_visible()
    expect(card.locator('[data-confirmed-mode]')).to_have_attribute('data-confirmed-mode', 'On')
    # Refresh must not register the shared menu handler more than once.
    card.locator('.admin-actions-toggle').click()
    expect(card.locator('.admin-actions-menu')).to_be_visible()
    page.keyboard.press('Escape')
    expect(card.locator('.admin-actions-menu')).not_to_be_visible()


def test_refresh_keeps_existing_haproxy_metric_chart(logged_in, product_url, product, waf_modes):
    page = logged_in
    Waf.update(metrics=1).where(Waf.server_id == product.server.server_id).execute()
    page.route('**/metrics/waf/*', lambda route: route.fulfill(json={
        'chartData': {'curr_con': '1,2,,', 'labels': '00:00,00:01,,', 'server': product.server.hostname},
    }))
    page.goto(product_url + '/waf/haproxy')
    expect(page.locator('[data-waf-card]')).to_be_visible()
    page.wait_for_function('Chart.getChart(document.querySelector("canvas")) !== undefined')
    chart_id = page.evaluate('Chart.getChart(document.querySelector("canvas")).id')
    for _ in range(2):
        with page.expect_response(lambda response: '/waf/overview/haproxy/' in response.url):
            page.locator('[data-waf-refresh]').click()
    assert page.evaluate('Chart.getChart(document.querySelector("canvas")).id') == chart_id
    expect(page.locator('.ajaxwafstatus input')).to_be_checked()


def test_metrics_toggle_persists_and_updates_charts(logged_in, product_url, product, waf_modes):
    page = logged_in
    page.route('**/metrics/waf/*', lambda route: route.fulfill(json={
        'chartData': {'curr_con': '1,2,,', 'labels': '00:00,00:01,,', 'server': product.server.hostname},
    }))
    page.goto(product_url + '/waf/haproxy')
    checkbox = page.locator('.ajaxwafstatus input')
    expect(checkbox).not_to_be_checked()
    expect(page.locator('canvas')).to_have_count(0)
    for enabled in (True, False):
        with page.expect_navigation(wait_until='domcontentloaded'):
            page.locator('.ajaxwafstatus label').click()
        expect(checkbox).to_be_checked(checked=enabled)
        assert bool(Waf.get(Waf.server_id == product.server.server_id).metrics) == enabled
        expect(page.locator('canvas')).to_have_count(int(enabled))
        if enabled:
            page.wait_for_function('Chart.getChart(document.querySelector("canvas")) !== undefined')


@pytest.mark.parametrize('suffix', ['?', '?from=login#status'])
@pytest.mark.parametrize('service', ['haproxy', 'nginx'])
def test_overview_and_install_ignore_query_and_fragment(logged_in, product_url, product, waf_modes, service, suffix):
    page = logged_in
    Server.create(server_id=33, hostname='Secondary WAF server', ip='192.0.2.33', group_id='1',
                  cred_id=11, haproxy=1, nginx=1)
    page.goto(f'{product_url}/waf/{service}{suffix}')
    expect(page.locator('[data-waf-card]')).to_have_count(2)
    expect(page.locator('summary.rw-status-running')).to_be_visible()
    url = f'**/install/waf/{service}/192.0.2.33'
    page.route(url, lambda route: route.fulfill(json={'status': 'failed', 'error': 'Installation fixture'}))
    with page.expect_request(url):
        page.locator('[onclick^="installWaf"]').click()
    expect(page.locator('.toast-message')).to_have_text('Installation fixture')


@pytest.mark.parametrize('failure', ['http', 'invalid_response', 'rejected'])
def test_metrics_failure_restores_toggle_and_allows_retry(logged_in, product_url, product, waf_modes, app, failure):
    page = logged_in
    page.goto(product_url + '/waf/haproxy')
    checkbox = page.locator('.ajaxwafstatus input')
    expect(checkbox).to_be_enabled()
    requests = []
    page.route('**/waf/metric/enable/**', lambda route: requests.append(route))
    page.locator('.ajaxwafstatus label').click()
    expect(checkbox).to_be_disabled()
    # Refresh cannot replace a tile while its metrics request is in progress.
    page.locator('[data-waf-refresh]').click()
    expect(checkbox).to_be_disabled()
    assert len(requests) == 1
    if failure == 'http':
        requests[0].fulfill(status=503, body='unavailable')
    else:
        requests[0].fulfill(json={} if failure == 'invalid_response' else {'status': 'failed', 'error': '<b>Denied</b>'})
    expect(checkbox).to_be_enabled()
    expect(checkbox).not_to_be_checked()
    message = '<b>Denied</b>' if failure == 'rejected' else app.jinja_env.get_template('languages/en.html').module.errors['waf_metrics']
    expect(page.locator('.toast-message')).to_have_text(message)
    expect(page.locator('.toast-message b')).to_have_count(0)
    page.locator('.ajaxwafstatus label').click()
    expect(checkbox).to_be_disabled()
    assert len(requests) == 2
    requests[1].fulfill(status=503, body='unavailable')
    expect(checkbox).to_be_enabled()
