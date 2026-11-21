"""Manual/automatic VRIDs are usable through the real cluster and VIP dialogs."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import HaClusterRouter, HaClusterVip, InstallationTasks
from tests.product.test_keepalived_vrid import members, cluster_body


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


@pytest.fixture
def cluster_page(logged_in, product_url, members, monkeypatch):
    # Replace external package/probe availability; keep forms and mutation APIs real.
    monkeypatch.setattr('app.modules.common.common.is_tool', lambda _name: True)
    page = logged_in
    page.route('**/api/service/**/status', lambda route: route.fulfill(
        json={'status': 'running', 'Version': '2.2.8'}))
    page.route('**/ha/cluster/*/status', lambda route: route.fulfill(json={'status': 'ok'}))
    page.route('**/server/show/if/**', lambda route: route.fulfill(body='eth0'))
    page.goto(product_url + '/ha/cluster')
    return page


def action(card, name):
    card.get_by_role('button', name='Actions', exact=False).click()
    card.get_by_role('menuitem', name=name, exact=True).click()


def test_create_cluster_with_manual_vrid_and_load_it_for_edit(cluster_page, tmp_path):
    page = cluster_page
    page.get_by_role('button', name='Create Keepalived cluster', exact=True).click()
    page.locator('#ha-cluster-name').fill('Manual-VRID')
    page.locator('#ha-cluster-desc').fill('Browser regression')
    page.locator('#ha-cluster-master-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=True).click()
    page.locator('#ha-cluster-master-interface').fill('eth0')
    page.locator('#vrrp-ip').fill('192.0.2.100')
    page.locator('#add_check-33 .check-button').click()
    page.locator('#slave_int-33').fill('eth0')
    field = page.locator('#ha-cluster-vrid')
    expect(field).to_have_value('')
    field.fill('256')
    page.get_by_role('button', name='Next', exact=True).click()
    expect(page.locator('.toast-error')).to_contain_text('VRID must be an integer')
    expect(page.locator('#create-ha-cluster-step-1')).to_be_visible()
    field.fill('42')
    page.screenshot(path=str(tmp_path / 'cluster-vrid.png'), full_page=True)
    page.get_by_role('button', name='Next', exact=True).click()
    page.locator('label[for="virt_server"]').click()
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/ha/cluster')) as result:
        page.get_by_role('button', name='Save', exact=True).click()
    assert result.value.status == 201, result.value.text()
    cluster_id = result.value.json()['id']
    assert HaClusterRouter.get(HaClusterRouter.cluster_id == cluster_id).vrid == 42
    expect(page.locator('#create-ha-cluster-step-2')).to_be_hidden()
    card = page.locator(f'#cluster-{cluster_id}')
    action(card, 'Edit')
    expect(field).to_have_value('42')
    page.get_by_role('button', name='Cancel', exact=True).click()
    page.get_by_role('button', name='Create Keepalived cluster', exact=True).click()
    expect(field).to_have_value('')


def test_vip_manual_conflict_edit_and_automatic_selection(cluster_page, product_client, members):
    page = cluster_page
    response = product_client.post('/api/ha/cluster', json=dict(cluster_body(members), vrid=10))
    assert response.status_code == 201, response.text
    cluster_id = response.json['id']
    page.reload()
    card = page.locator(f'#cluster-{cluster_id}')
    action(card, 'Add VIP')
    dialog = page.locator('#add-vip')
    expect(dialog.locator('#master_int-11')).to_have_value('eth0')
    page.locator('#vrrp-ip-add').fill('192.0.2.101')
    field = page.locator('#vrrp-ip-add-vrid')
    expect(field).to_have_value('')
    field.fill('10')
    page.locator('label[for="vrrp-ip-add-virt_server"]').click()
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/vip')) as result:
        page.get_by_role('button', name='Save', exact=True).click()
    assert result.value.status == 409
    expect(page.locator('.toast-error')).to_contain_text('VRID 10 is already used')
    expect(dialog).to_be_visible()
    expect(field).to_have_value('10')
    field.fill('44')
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/vip')) as result:
        page.get_by_role('button', name='Save', exact=True).click()
    assert result.value.status == 201, result.value.text()
    vip_id = result.value.json()['id']
    assert HaClusterVip.get_by_id(vip_id).router_id.vrid == 44
    expect(dialog).to_be_hidden()
    card.locator(f'[data-vip-id="{vip_id}"]').click()
    expect(field).to_have_value('44')
    field.fill('')
    with page.expect_response(lambda r: r.request.method == 'PUT' and r.url.endswith(f'/vip/{vip_id}')) as result:
        page.get_by_role('button', name='Save', exact=True).click()
    assert result.value.status == 201, result.value.text()
    assert HaClusterVip.get_by_id(vip_id).router_id.vrid == 44
    action(card, 'Add VIP')
    expect(field).to_have_value('')
    expect(dialog.locator('#master_int-11')).to_have_value('eth0')
    page.locator('#vrrp-ip-add').fill('192.0.2.102')
    with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/vip')) as result:
        page.get_by_role('button', name='Save', exact=True).click()
    assert result.value.status == 201, result.value.text()
    assert HaClusterVip.get_by_id(result.value.json()['id']).router_id.vrid == 1


def test_failed_cluster_save_does_not_apply_configuration(cluster_page, product_client, members):
    page = cluster_page
    response = product_client.post('/api/ha/cluster', json=dict(cluster_body(members), vrid=10))
    cluster_id = response.json['id']
    response = product_client.post(f'/api/ha/cluster/{cluster_id}/vip', json=dict(
        vip='192.0.2.101', virt_server=False, servers=members, vrid=20))
    assert response.status_code == 201, response.text
    page.reload()
    action(page.locator(f'#cluster-{cluster_id}'), 'Edit')
    page.locator('#ha-cluster-vrid').fill('20')
    page.get_by_role('button', name='Next', exact=True).click()
    installs = []
    page.route('**/install/*', lambda route: (
        installs.append(route.request.url), route.fulfill(json={'task_id': 999})))
    with page.expect_response(lambda r: r.request.method == 'PUT' and r.url.endswith(f'/ha/cluster/{cluster_id}')) as result:
        page.get_by_role('button', name='Apply', exact=True).click()
    assert result.value.status == 409, result.value.text()
    expect(page.locator('#create-ha-cluster-step-2')).to_be_visible()
    expect(page.locator('.toast-error')).to_contain_text('VRID 20 is already used')
    assert not installs
    assert InstallationTasks.select().count() == 0
