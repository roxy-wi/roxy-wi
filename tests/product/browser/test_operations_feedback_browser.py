"""Visible task progress, retry and context changes use real authenticated pages."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import InstallationTasks
from app.modules.service import ha_readiness, proxy_assessments
from tests.product.test_ha_readiness import readiness_cluster, keepalived_registration
from tests.product.test_proxy_diagnostics import diagnostic_host
from tests.product.browser.test_proxy_diagnostics_browser import open_diagnostics, close_diagnostics, select_card


pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium'),
]


@pytest.fixture(params=['readiness', 'diagnostics'])
def operation(request, logged_in, product_url, product, monkeypatch):
    page = logged_in
    if request.param == 'readiness':
        request.getfixturevalue('readiness_cluster')
        cluster = keepalived_registration(product, monkeypatch)
        # Card status polling is unrelated to the queued audit and has no real
        # SSH targets in this fixture.
        monkeypatch.setattr('app.modules.server.server.ssh_command', lambda *_args, **_kwargs: 'active\n')
        monkeypatch.setattr('app.modules.pacemaker.service.status', lambda _cluster: dict(
            quorate=True, dc='one', failures=0, nodes=[], resources=[]))
        page.goto(product_url + f'/ha/cluster?panel=readiness&provider=keepalived&cluster={cluster.id}')
        prefix = '#ha-audit-'
        select = 'cluster'
        choice = 'product-vrrp · keepalived'
        endpoint = f'**/ha/api/readiness/keepalived/{cluster.id}/run'
        execute = ha_readiness.execute
        starting = 'Starting readiness audit'
    else:
        request.getfixturevalue('diagnostic_host')
        request.getfixturevalue('service_worker_controls')
        request.getfixturevalue('host_metrics')
        open_diagnostics(page, product_url)
        prefix = '#diagnostics-'
        select = 'server'
        choice = 'Product HAProxy (192.0.2.11)'
        endpoint = '**/insights/api/diagnostics'
        execute = proxy_assessments.execute
        starting = 'Starting request diagnostics'
    if request.param == 'diagnostics':
        page.locator('#diagnostics-url').fill('https://example.test/')
    expect(page.locator(prefix + 'run')).to_be_enabled()
    return dict(page=page, prefix=prefix, select=select, endpoint=endpoint,
                execute=execute, starting=starting)


def test_start_queue_run_complete_and_retry_are_visible(operation):
    page, prefix = operation['page'], operation['prefix']
    button, message = page.locator(prefix + 'run'), page.locator(prefix + 'message')
    requests = []
    page.route(operation['endpoint'], lambda route: requests.append(route))
    box = button.bounding_box()
    try:
        button.click()
        expect(message).to_contain_text(operation['starting'])
        expect(message.locator('.fa-spinner')).to_be_visible()
        expect(button).to_be_disabled()
        expect(button).to_have_attribute('aria-busy', 'true')
        assert button.bounding_box() == box
        button.dispatch_event('click')
        expect(page.locator(prefix + 'refresh')).to_have_count(0)
        expect(message).to_contain_text(operation['starting'])
        assert len(requests) == 1
        requests.pop().fulfill(status=503, json={'error': 'Worker temporarily unavailable'})
        expect(message).to_contain_text('Worker temporarily unavailable')
        expect(button).to_be_enabled()
        expect(message.locator('.fa-spinner')).to_have_count(0)
    finally:
        for route in requests:
            route.abort()
        page.unroute(operation['endpoint'])

    with page.expect_response(operation['endpoint']) as response:
        button.click()
    assert response.value.status == 202
    task = InstallationTasks.get_by_id(response.value.json()['task_id'])
    expect(message).to_contain_text('queued')
    expect(button).to_be_disabled()
    InstallationTasks.update(status='running').where(InstallationTasks.id == task.id).execute()
    expect(message).to_contain_text('running', timeout=10000)
    assert operation['execute'](InstallationTasks.get_by_id(task.id)) == 'completed'
    expect(message).to_contain_text('completed', timeout=10000)
    expect(button).to_be_enabled()
    expect(message.locator('.fa-spinner')).to_have_count(0)


def test_late_start_error_does_not_overwrite_new_selection(operation):
    page, prefix = operation['page'], operation['prefix']
    requests = []
    page.route(operation['endpoint'], lambda route: requests.append(route))
    try:
        page.locator(prefix + 'run').click()
        expect(page.locator(prefix + 'message')).to_contain_text(operation['starting'])
        if prefix == '#diagnostics-':
            close_diagnostics(page)
        else:
            page.locator('.ha-cluster-dialog:visible .ui-dialog-titlebar-close').click()
            card = page.locator('[data-ha-provider="pacemaker"]')
            card.get_by_role('button', name='Actions', exact=False).click()
            card.get_by_role('menuitem', name='HA readiness', exact=True).click()
            expect(page.locator(prefix + 'message')).to_have_text('Ready to run an audit.')
        requests.pop().fulfill(status=503, json={'error': 'Stale operation error'})
        page.wait_for_load_state('networkidle')
        if prefix == '#diagnostics-':
            select_card(page, 11)
            expect(page.locator(prefix + 'message')).to_have_text('Ready to run diagnostics.')
        expect(page.locator(prefix + 'message')).not_to_contain_text('Stale operation error')
        expect(page.locator(prefix + 'run')).to_be_enabled()
        expect(page.locator(prefix + 'message .fa-spinner')).to_have_count(0)
    finally:
        for route in requests:
            route.abort()
        page.unroute(operation['endpoint'])


@pytest.mark.parametrize('route', ['/ha/readiness', '/ha/maintenance', '/service/certificate-sources'])
@pytest.mark.parametrize('width', [1440, 390])
def test_workspace_help_is_at_bottom_and_navigation_is_not_duplicated(logged_in, product_url, route, width, tmp_path):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 900})
    response = page.goto(product_url + route)
    assert response.status == 200
    help_box = page.locator('main > .alert.alert-info:last-child')
    expect(help_box).to_be_visible()
    expect(page.locator('[data-nav-group="operations"] a[href*="/insights/diagnostics"]')).to_have_count(0)
    expect(page.locator('[data-nav-group="services"] a[href*="/insights/diagnostics"]')).to_have_count(0)
    expect(page.locator('#ha-provider')).to_have_count(0)
    if route in ('/ha/readiness', '/ha/maintenance'):
        expect(page.get_by_role('button', name='Refresh', exact=True)).to_have_count(0)
        expect(page.locator('main a[href="/ha/readiness"]')).to_have_count(0)
    page.wait_for_load_state('networkidle')
    assert page.locator('main').evaluate('(element) => element.scrollWidth <= element.clientWidth + 1')
    page.screenshot(path=str(tmp_path / f'workspace-{width}.png'), full_page=True, animations='disabled')


@pytest.mark.parametrize('route', ['/ha/cluster', '/pacemaker'])
def test_ha_pages_remove_standalone_readiness_navigation(logged_in, product_url, route):
    page = logged_in
    assert page.goto(product_url + route).status == 200
    expect(page.locator('.container a[href="/ha/readiness"]')).to_have_count(0)
    expect(page.locator('[data-nav-group="operations"] a[href="/ha/readiness"]')).to_have_count(0)
