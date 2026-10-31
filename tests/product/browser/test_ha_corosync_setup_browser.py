"""Cluster setup uses the existing APIs inside a persistent HA dialog."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import InstallationTasks, PacemakerCluster, Server, UserGroups
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.pacemaker import install_log, service
from tests.unit.pacemaker.test_adoption import running_cluster

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


def close_setup(page):
    page.locator('.ha-cluster-dialog:has(#ha-corosync-dialog) .ui-dialog-titlebar-close').click()


def choose(page, control, label):
    control.click()
    page.get_by_role('option', name=label, exact=True).click()


def test_new_cluster_keeps_form_and_running_installation_when_closed(
    logged_in, product_url, product, monkeypatch,
):
    second = Server.create(hostname='Second node', ip='192.0.2.33', group_id='1', cred_id=11)
    servers = [product.server, second]

    def facts(server_id, _group):
        server = next(server for server in servers if server.server_id == server_id)
        return dict(hostname=f'node-{server_id}', fqdn=f'node-{server_id}',
                    active_cluster_services=[], existing_witness_data=False,
                    addresses=[dict(interface='eth0', address=server.ip, prefix=24)])

    monkeypatch.setattr('app.modules.pacemaker.facts.read', facts)
    monkeypatch.setattr(service, 'status', lambda _cluster: dict(
        quorate=True, dc='node-11', failures=0, nodes=[], resources=[]))
    page = logged_in
    page.goto(product_url + '/ha/cluster')
    page.get_by_role('button', name='Create Corosync cluster', exact=True).click()
    expect(page.locator('#pcmk-registration')).to_be_hidden()
    page.get_by_role('button', name='Create new cluster', exact=True).click()
    page.locator('#pcmk-name').fill('new-ha')
    for index, server in enumerate(servers):
        row = page.locator('#pcmk-members tr').nth(index)
        choose(page, row.locator('.ui-selectmenu-button').first, f'{server.hostname} ({server.ip})')
        expect(row.locator('[data-field=name]')).to_have_value(f'node-{server.server_id}')
        choose(page, row.locator('.ui-selectmenu-button').nth(1), f'eth0: {server.ip}/24')
    close_setup(page)
    page.get_by_role('button', name='Create Corosync cluster', exact=True).click()
    expect(page.locator('#pcmk-name')).to_have_value('new-ha')
    page.get_by_role('button', name='Save registration', exact=True).click()
    expect(page.locator('#pcmk-bootstrap-panel')).to_be_visible()
    expect(page.locator('#pcmk-message')).to_contain_text('Registration saved')
    assert PacemakerCluster.select().count() == 1
    assert InstallationTasks.select().count() == 0
    page.get_by_role('button', name='Install cluster on empty nodes', exact=True).click()
    dialog = page.get_by_role('dialog', name='Confirm cluster operation')
    dialog.get_by_label('Type new-ha to confirm').fill('new-ha')
    with page.expect_response('**/pacemaker/api/*/bootstrap') as response:
        dialog.get_by_role('button', name='Continue', exact=True).click()
    task = InstallationTasks.get_by_id(response.value.json()['task_id'])
    payload = deserialize_operation_payload(task.operation_payload)
    assert payload['action'] == 'bootstrap'
    expect(page.locator('#pcmk-installation-status')).to_contain_text('created')
    close_setup(page)
    expect(page.locator('.ha-installation-status')).to_contain_text('Installing')
    page.locator('.ha-installation-status').click()
    expect(page.locator('#pcmk-installation-status')).to_contain_text(f'#{task.id}')
    assert InstallationTasks.select().count() == 1
    install_log.recorder(task, payload)('node-11', 'Repositories', 'error', 'Repository unavailable')
    InstallationTasks.update(status='failed', error='See installation log').where(InstallationTasks.id == task.id).execute()
    expect(page.locator('#pcmk-installation-status')).to_contain_text('failed')
    expect(page.locator('#pcmk-installation-output')).to_contain_text('Repository unavailable')
    close_setup(page)
    expect(page.locator('.ha-installation-status')).to_contain_text('Installation failed')
    page.reload()
    page.locator('.ha-installation-status').click()
    expect(page.locator('#pcmk-installation-output')).to_contain_text('Repository unavailable')
    expect(page.locator('#pcmk-bootstrap')).to_be_enabled()


def test_adoption_uses_discovery_and_returns_to_cluster_cards(
    logged_in, product_url, product, running_cluster, monkeypatch,
):
    servers, calls, _state = running_cluster
    monkeypatch.setattr(service, 'status', lambda _cluster: dict(
        quorate=True, dc='adopt-node-1', failures=0, nodes=[], resources=[]))
    page = logged_in
    page.goto(product_url + '/ha/cluster?setup=adopt')
    expect(page.locator('#pcmk-discovery-server-button')).to_have_text('Select an existing cluster node')
    expect(page.locator('#pcmk-discovery-server')).to_have_value('')
    page.get_by_role('button', name='Discover cluster', exact=True).click()
    expect(page.locator('#pcmk-message')).to_have_text('Select an existing cluster node')
    choose(page, page.locator('#pcmk-discovery-server-button'), f'{servers[0].hostname} ({servers[0].ip})')
    page.get_by_role('button', name='Discover cluster', exact=True).click()
    expect(page.locator('#pcmk-registration')).to_be_visible()
    expect(page.locator('#pcmk-discovery-result')).to_contain_text('2 nodes')
    expect(page.locator('#pcmk-message')).to_be_empty()
    page.get_by_role('button', name='Adopt verified cluster', exact=True).click()
    page.get_by_role('dialog', name='Confirm cluster operation').get_by_role('button', name='Continue', exact=True).click()
    expect(page.locator('#ha-corosync-dialog')).to_be_hidden()
    expect(page.locator('.ha-cluster-card')).to_contain_text('adopt-test')
    assert PacemakerCluster.select().count() == 1
    assert InstallationTasks.select().count() == 0
    assert calls  # All remote calls are checked as reads by running_cluster.


def test_viewer_cannot_open_setup_and_old_installer_is_removed(
    logged_in, product_url, product, product_client,
):
    assert product_client.get('/install/pacemaker').status_code == 404
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = logged_in
    page.goto(product_url + '/ha/cluster?setup=new')
    expect(page.locator('#ha-corosync-dialog')).to_have_count(0)
    expect(page.get_by_role('button', name='Create Corosync cluster', exact=True)).to_have_count(0)
