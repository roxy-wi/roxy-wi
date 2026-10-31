"""Cluster cards own their operational dialogs and retain async state safely."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import ConfigChange, HaCluster, HaClusterService, HaMaintenancePlan, PacemakerCluster
from tests.product.test_ha_readiness import readiness_cluster
from tests.product.test_ha_maintenance import maintenance_cluster, keepalived_maintenance, create, ka_create

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


def open_panel(page, provider, panel):
    card = page.locator(f'.ha-cluster-card[data-ha-provider="{provider}"]')
    card.get_by_role('button', name='Actions', exact=False).click()
    card.get_by_role('menuitem', name='HA readiness' if panel == 'readiness' else 'Node maintenance', exact=True).click()
    expect(page.locator(f'#ha-{panel}-dialog')).to_be_visible()


def close_panel(page):
    page.locator('.ha-cluster-dialog:visible .ui-dialog-titlebar-close').click()


@pytest.fixture
def cluster_service_state(monkeypatch):
    def ssh(_ip, command):
        assert command == 'systemctl is-active keepalived.service'
        return 'active\n'
    monkeypatch.setattr('app.modules.server.server.ssh_command', ssh)


@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'light'), (1440, 'dark')])
def test_common_cards_and_scoped_plan_history(
    logged_in, product_url, product_client, maintenance_cluster, keepalived_maintenance,
    cluster_service_state, width, theme, tmp_path,
):
    active = create(product_client, maintenance_cluster)
    terminal = ka_create(product_client, keepalived_maintenance)
    HaClusterService.create(cluster_id=keepalived_maintenance.cluster.id, service_id='1')
    ConfigChange.update(status='cancelled').where(ConfigChange.id == terminal.change_id).execute()
    page = logged_in
    page.set_viewport_size(dict(width=width, height=1000))
    page.route('**/api/service/haproxy/192.0.2.100/status', lambda route: route.fulfill(json={'status': 'running'}))
    page.goto(product_url + '/ha/cluster')
    expect(page.locator('.ha-cluster-card')).to_have_count(2)
    page.evaluate('(theme) => changeTheme(theme)', theme)
    pm = page.locator('[data-ha-provider="pacemaker"]')
    ka = page.locator('[data-ha-provider="keepalived"]')
    expect(pm.locator('.ha-plan-status')).to_contain_text('one · Draft')
    expect(ka.locator('.ha-plan-status')).to_be_hidden()
    expect(ka.locator('[data-ha-health]')).to_have_text('UP')
    expect(pm.locator('[data-ha-health]')).to_have_text('UP')
    expect(ka.locator('[data-ha-service="haproxy"]')).to_have_attribute('data-state', 'up')
    expect(page.locator('.ha-cluster-card .admin-actions-toggle svg')).to_have_count(2)
    for card in (pm, ka):
        expect(card.locator('.admin-action-item svg')).to_have_count(card.locator('.admin-action-item').count())
    assert page.locator('main').evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    # Metadata polling must keep unchanged cards, focus and open menus in place.
    pm.evaluate('(node) => { window.originalClusterCard = node; }')
    pm.get_by_role('button', name='Actions', exact=False).click()
    with page.expect_response('**/ha/cluster/cards'):
        page.evaluate('RoxywiHAClusters.refresh()')
    assert pm.evaluate('(node) => node === window.originalClusterCard')
    expect(pm.get_by_role('menuitem', name='Node maintenance', exact=True)).to_be_visible()
    page.keyboard.press('Escape')
    page.wait_for_load_state('networkidle')
    page.screenshot(path=str(tmp_path / f'ha-clusters-{width}-{theme}.png'), full_page=True)
    pm.locator('.ha-plan-status').click()
    expect(page.locator(f'#maintenance-plans [data-plan="{active.id}"]')).to_be_visible()
    expect(page.locator('#maintenance-new')).to_be_hidden()
    close_panel(page)
    open_panel(page, 'keepalived', 'maintenance')
    expect(page.locator('#maintenance-plans [data-plan]')).to_have_count(0)
    expect(page.locator('#maintenance-new')).to_be_visible()
    page.locator('#ha-maintenance-tabs a[href="#ha-maintenance-history"]').click()
    expect(page.locator(f'#maintenance-history [data-plan="{terminal.id}"]')).to_be_visible()
    expect(page.locator('#maintenance-history')).not_to_contain_text('Maintain product node')
    assert page.locator('#ha-maintenance-dialog').evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    page.screenshot(path=str(tmp_path / f'ha-history-{width}.png'), full_page=True)
    close_panel(page)
    # A reused cluster id must never retain the preceding registration's history.
    keepalived_maintenance.cluster.readiness_key = 'f' * 32
    keepalived_maintenance.cluster.save()
    open_panel(page, 'keepalived', 'maintenance')
    expect(page.locator('#maintenance-history [data-plan]')).to_have_count(0)
    close_panel(page)
    # Removing the last registrations must remove every stale card.
    HaCluster.delete().where(HaCluster.id == keepalived_maintenance.cluster.id).execute()
    PacemakerCluster.delete().where(PacemakerCluster.id == maintenance_cluster.cluster.id).execute()
    with page.expect_response('**/ha/cluster/cards'):
        page.evaluate('RoxywiHAClusters.refresh()')
    expect(page.locator('.ha-cluster-card')).to_have_count(0)
    expect(page.locator('#ha-clusters-empty')).to_be_visible()


def test_live_status_failure_clears_previous_health_and_recovers(
    logged_in, product_url, maintenance_cluster, monkeypatch,
):
    from app.modules.pacemaker.remote import RemoteError

    maintenance_cluster.live['dc'] = 'one'
    page = logged_in
    page.goto(product_url + '/ha/cluster')
    card = page.locator('[data-ha-provider="pacemaker"]')
    badge = card.locator('[data-ha-health]')
    expect(badge).to_have_text('UP')
    expect(card.locator('[data-ha-node="one"] [data-ha-node-status]')).to_have_text('Online')
    expect(card.locator('[data-ha-quorum]')).to_have_text('Available')
    expect(card.locator('[data-ha-coordinator]')).to_have_text('one')
    expect(card.locator('[data-ha-resources]')).to_have_text('1 / 1 active')
    expect(card.locator('[data-ha-failures]')).to_have_text('0')
    assert 'div-server-head-up' in card.get_attribute('class')
    maintenance_cluster.live['quorate'] = False
    maintenance_cluster.live['nodes'][0]['standby'] = 'true'
    maintenance_cluster.live['nodes'][1]['online'] = 'false'
    maintenance_cluster.live['resources'][0].update(active='false', failed='true', blocked='true')
    maintenance_cluster.live['failures'] = 2
    with page.expect_response('**/pacemaker/api/*/status'):
        page.evaluate('RoxywiHAClusters.refresh()')
    expect(badge).to_have_text('No quorum')
    expect(card.locator('[data-ha-node="one"] [data-ha-node-status]')).to_have_text('Standby')
    expect(card.locator('[data-ha-node="two"] [data-ha-node-status]')).to_have_text('Offline')
    expect(card.locator('[data-ha-quorum]')).to_have_text('No quorum')
    expect(card.locator('[data-ha-resources]')).to_have_text('0 / 1 active · 1 failed / blocked')
    expect(card.locator('[data-ha-failures]')).to_have_text('2')
    assert 'div-server-head-down' in card.get_attribute('class')

    def unavailable(_cluster):
        raise RemoteError('Private SSH detail')

    with monkeypatch.context() as patch:
        patch.setattr('app.modules.pacemaker.service.status', unavailable)
        with page.expect_response('**/pacemaker/api/*/status') as response:
            page.evaluate('RoxywiHAClusters.refresh()')
        assert response.value.status == 502
        expect(badge).to_have_text('Unknown')
        expect(card.locator('[data-ha-node-status]')).to_have_text(['Unknown', 'Unknown'])
        expect(card.locator('[data-ha-quorum]')).to_have_text('Unknown')
        for field in ('coordinator', 'resources', 'failures'):
            expect(card.locator(f'[data-ha-{field}]')).to_have_text('—')
        assert 'div-server-head-dis' in card.get_attribute('class')
        assert 'Private SSH detail' not in page.content()
    maintenance_cluster.live['quorate'] = True
    maintenance_cluster.live['nodes'][0]['standby'] = 'false'
    maintenance_cluster.live['nodes'][0]['maintenance'] = 'true'
    maintenance_cluster.live['nodes'][1]['online'] = 'true'
    maintenance_cluster.live['resources'] = []
    maintenance_cluster.live['failures'] = 0
    maintenance_cluster.live['dc'] = '<img src=x onerror=alert(1)>'
    with page.expect_response('**/pacemaker/api/*/status'):
        page.evaluate('RoxywiHAClusters.refresh()')
    expect(badge).to_have_text('UP')
    expect(card.locator('[data-ha-node="one"] [data-ha-node-status]')).to_have_text('Maintenance')
    expect(card.locator('[data-ha-resources]')).to_have_text('0 / 0 active')
    expect(card.locator('[data-ha-coordinator]')).to_have_text('<img src=x onerror=alert(1)>')
    expect(card.locator('[data-ha-coordinator] img')).to_have_count(0)


def test_maintenance_inflight_create_survives_close_without_duplicates(
    logged_in, product_url, maintenance_cluster,
):
    page = logged_in
    page.goto(product_url + '/ha/cluster')
    open_panel(page, 'pacemaker', 'maintenance')
    page.locator('#maintenance-node-button').click()
    page.get_by_role('option', name='one', exact=True).click()
    page.locator('#maintenance-title').fill('OS')
    page.locator('#maintenance-capacity').fill('#7')
    page.locator('label[for="maintenance-confirm-capacity"]').click()
    held = []
    page.route('**/ha/api/maintenance', lambda route: held.append(route))
    try:
        page.get_by_role('button', name='Create maintenance plan', exact=True).click()
        expect(page.locator('#ha-maintenance-message')).to_contain_text('Creating')
        close_panel(page)
        open_panel(page, 'pacemaker', 'maintenance')
        expect(page.locator('#maintenance-capacity')).to_have_value('#7')
        page.locator('#ha-maintenance-create').dispatch_event('submit')
        assert len(held) == 1
        held.pop().continue_()
        expect(page.locator('#maintenance-plans [data-plan]')).to_have_count(1)
        assert HaMaintenancePlan.select().count() == 1
        close_panel(page)
        expect(page.locator('.ha-plan-status')).to_contain_text('Draft')
    finally:
        for route in held:
            route.abort()
        page.unroute('**/ha/api/maintenance')
