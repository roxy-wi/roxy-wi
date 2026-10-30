"""Cluster layouts use real routes and widgets, with only host status substituted."""
import os
import threading
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server, UserGroups
from app.modules.pacemaker import agents, service
from app.modules.pacemaker.schemas import ClusterCreate


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.fixture
def cluster_host(product, monkeypatch):
    second = Server.create(hostname='Cluster node two', ip='192.0.2.33', group_id='1', cred_id=11)
    members = [{'server_id': server.server_id, 'name': f'node-{index}',
                'address': server.ip, 'nodeid': index}
               for index, server in enumerate([product.server, second], 1)]
    cluster = service.register(ClusterCreate(name='Production_cluster_with_a_long_name', members=members), 1)
    state = SimpleNamespace(cluster=cluster, calls=0, hold=None, failure=False, entered=threading.Event())
    state.status = {
        'quorate': True, 'dc': 'node-1', 'source': 'node-1', 'failures': 0,
        'quorum_details': {'configured': True, 'votes': 1},
        'nodes': [{'name': member['name'], 'online': 'true', 'standby': 'false',
                   'maintenance': 'false', 'unclean': 'false'} for member in members],
        'resources': [{'id': 'frontend-vip', 'resource_agent': 'ocf:heartbeat:IPaddr2',
                       'role': 'Started', 'nodes': ['node-1'], 'failed': 'false', 'blocked': 'false'}],
    }

    def status(_cluster):
        state.calls += 1
        if state.hold is not None:
            state.entered.set()
            assert state.hold.wait(10), 'Browser did not release the status request'
        if state.failure:
            raise RuntimeError('Synthetic host unavailable')
        return state.status

    monkeypatch.setattr(service, 'status', status)
    monkeypatch.setattr(service, 'get_config', lambda _cluster: {
        'xml': '<cib><configuration><resources><primitive id="frontend-vip" class="ocf" '
               'provider="heartbeat" type="IPaddr2"/></resources><constraints/></configuration></cib>',
        'digest': 'a' * 64,
    })
    monkeypatch.setattr(agents, 'inventory', lambda _cluster: {
        'agents': [{'id': 'ocf:heartbeat:IPaddr2', 'ready': True}],
        'nodes': [{'name': member['name'], 'agents': ['ocf:heartbeat:IPaddr2']} for member in members],
    })
    return state


def open_cluster(page, product_url, view='overview'):
    page.goto(product_url + '/pacemaker' + ('' if view == 'overview' else '/' + view))
    expect(page.locator('#pcmk-updated')).not_to_have_text('—')
    expect(page.locator('#pcmk-dashboard')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#nprogress')).to_have_count(0)


def assert_no_page_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
    title = page.locator('.pcmk-page-title').bounding_box()
    assert title['x'] + title['width'] <= page.viewport_size['width']


@pytest.mark.parametrize('width', [1440, 390])
def test_installation_logs_survive_reload_and_render_output_as_text(
        logged_in, product_url, product, cluster_host, width, tmp_path):
    from app.modules.db.db_model import InstallationTasks
    from app.modules.operations.queue import deserialize_operation_payload
    from app.modules.pacemaker import operations, install_log

    task = operations.enqueue(cluster_host.cluster, product.admin.user_id, 'bootstrap')
    payload = deserialize_operation_payload(task.operation_payload)
    install_log.recorder(task, payload)('node-1', 'Repositories', 'error',
        'Packages unavailable: pacemaker\nhttps://user:SecretPassword@example.test/repo?token=HiddenToken\n'
        '<img src=x onerror="window.logInjection=true">')
    InstallationTasks.update(status='failed', error='Open the installation log').where(InstallationTasks.id == task.id).execute()
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 900})
    for _ in range(2):
        open_cluster(page, product_url, 'logs')
        expect(page.locator('#pcmk-installation-output')).to_contain_text('Packages unavailable: pacemaker')
        expect(page.locator('#pcmk-installation-status')).to_contain_text(f'Installation #{task.id}: failed')
        assert 'SecretPassword' not in page.locator('#pcmk-installation-output').inner_text()
        assert 'HiddenToken' not in page.locator('#pcmk-installation-output').inner_text()
        assert page.locator('#pcmk-installation-output img').count() == 0
        assert page.evaluate('window.logInjection !== true')
        assert_no_page_overflow(page)
        page.locator('#pcmk-installation-panel').screenshot(path=str(tmp_path / f'installation-log-{width}.png'))
        page.reload()


def test_running_installation_updates_without_replacing_selected_history(logged_in, product_url, product, cluster_host):
    from app.modules.db.db_model import InstallationTasks
    from app.modules.operations.queue import deserialize_operation_payload
    from app.modules.pacemaker import operations, install_log

    previous = operations.enqueue(cluster_host.cluster, product.admin.user_id, 'bootstrap')
    install_log.recorder(previous, deserialize_operation_payload(previous.operation_payload))(
        'node-1', 'Repositories', 'error', 'Historical package failure')
    InstallationTasks.update(status='failed').where(InstallationTasks.id == previous.id).execute()
    current = operations.enqueue(cluster_host.cluster, product.admin.user_id, 'bootstrap')
    record = install_log.recorder(current, deserialize_operation_payload(current.operation_payload))
    record('node-1', 'Packages', 'info', 'Installing packages')
    InstallationTasks.update(status='running').where(InstallationTasks.id == current.id).execute()
    page = logged_in
    open_cluster(page, product_url, 'logs')
    output = page.locator('#pcmk-installation-output')
    expect(output).to_contain_text('Installing packages')
    record('node-2', 'Packages', 'info', 'Second node packages complete')
    expect(output).to_contain_text('Second node packages complete', timeout=10000)
    page.locator('#pcmk-installation-task-button').click()
    page.locator('#pcmk-installation-task-menu [role=option]').filter(has_text=f'#{previous.id} ·').click()
    expect(output).to_contain_text('Historical package failure')
    with page.expect_response(lambda response: response.url.endswith(f'/tasks/{current.id}')):
        InstallationTasks.update(status='completed').where(InstallationTasks.id == current.id).execute()
    page.evaluate('() => new Promise(requestAnimationFrame)')
    expect(output).to_contain_text('Historical package failure')
    expect(output).not_to_contain_text('Second node packages complete')


@pytest.mark.parametrize('view', ['overview', 'resources', 'configuration', 'quorum', 'logs', 'monitoring', 'history'])
def test_cluster_pages_use_shared_layout(logged_in, product_url, cluster_host, view, tmp_path):
    page = logged_in
    open_cluster(page, product_url, view)
    expect(page.locator('#pcmk-empty')).to_be_hidden()
    expect(page.locator('#pcmk-message')).to_have_text('')
    provider = page.locator('#ha-provider-button').bounding_box()
    cluster = page.locator('#pcmk-cluster-button').bounding_box()
    refresh = page.locator('#pcmk-refresh').bounding_box()
    assert abs(provider['y'] - cluster['y']) < 2
    assert abs(provider['y'] + provider['height'] / 2 - refresh['y'] - refresh['height'] / 2) < 2
    assert_no_page_overflow(page)
    page.screenshot(path=str(tmp_path / f'pacemaker-{view}.png'), full_page=True, animations='disabled')


def test_refresh_keeps_layout_and_blocks_duplicate_requests(logged_in, product_url, cluster_host):
    page = logged_in
    open_cluster(page, product_url)
    before = {selector: page.locator(selector).bounding_box() for selector in
              ['#pcmk-node-table', '#pcmk-resource-table', '#pcmk-cluster-button', '#pcmk-refresh']}
    count = cluster_host.calls
    cluster_host.hold = threading.Event()
    try:
        page.locator('#pcmk-refresh').click()
        assert cluster_host.entered.wait(5)
        expect(page.locator('#pcmk-refresh')).to_be_disabled()
        expect(page.locator('#pcmk-cluster-button')).to_have_attribute('aria-disabled', 'true')
        expect(page.locator('#pcmk-dashboard')).to_have_attribute('aria-busy', 'true')
        for selector, box in before.items():
            assert page.locator(selector).bounding_box() == box
        page.locator('#pcmk-refresh').dispatch_event('click')
        assert cluster_host.calls == count + 1
    finally:
        cluster_host.hold.set()
    expect(page.locator('#pcmk-dashboard')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#pcmk-refresh')).to_be_enabled()
    expect(page.locator('#nprogress')).to_have_count(0)
    for selector, box in before.items():
        assert page.locator(selector).bounding_box() == box


def test_refresh_error_can_be_retried(logged_in, product_url, cluster_host):
    page = logged_in
    open_cluster(page, product_url)
    cluster_host.failure = True
    page.locator('#pcmk-refresh').click()
    expect(page.locator('#pcmk-message')).to_contain_text('Cluster operation failed')
    expect(page.locator('#pcmk-refresh')).to_be_enabled()
    expect(page.locator('#pcmk-nodes tr')).to_have_count(2)
    cluster_host.failure = False
    page.locator('#pcmk-refresh').click()
    expect(page.locator('#pcmk-message')).to_have_text('')
    expect(page.locator('#pcmk-cluster-button')).to_have_attribute('aria-disabled', 'false')


def test_empty_cluster_state_and_reload(logged_in, product_url, tmp_path):
    page = logged_in
    page.goto(product_url + '/pacemaker')
    expect(page.locator('#pcmk-empty')).to_be_visible()
    expect(page.locator('#pcmk-dashboard')).to_be_hidden()
    expect(page.locator('#pcmk-cluster-button')).to_have_attribute('aria-disabled', 'true')
    expect(page.locator('#pcmk-refresh')).to_be_enabled()
    expect(page.locator('#nprogress')).to_have_count(0)
    page.screenshot(path=str(tmp_path / 'pacemaker-empty.png'), full_page=True, animations='disabled')
    page.locator('#pcmk-refresh').click()
    expect(page.locator('#pcmk-message')).to_have_text('')
    page.get_by_role('link', name='Set up a cluster', exact=True).click()
    expect(page.locator('#pcmk-registration')).to_be_visible()
    expect(page.locator('#pcmk-members tr')).to_have_count(2)


@pytest.mark.parametrize('mode', ['new', 'adopt', 'witness'])
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
def test_setup_has_no_automatic_scroll_or_overflow(logged_in, product_url, mode, width, theme, tmp_path):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 900})
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(product_url + '/install/pacemaker?setup=' + mode)
    expect(page.locator('#pcmk-refresh')).to_be_enabled()
    expect(page.locator('#nprogress')).to_have_count(0)
    expect(page.locator(f'[data-setup="{mode}"]')).to_have_attribute('aria-pressed', 'true')
    panel = {'new': 'registration', 'adopt': 'discovery', 'witness': 'witness-panel'}[mode]
    expect(page.locator('#pcmk-' + panel)).to_be_visible()
    assert page.evaluate('window.scrollY') == 0
    assert_no_page_overflow(page)
    page.screenshot(path=str(tmp_path / f'pacemaker-setup-{mode}-{width}.png'), full_page=True, animations='disabled')
    # Changing workflows must preserve the header position and current-mode indicator.
    page.locator('[data-setup="witness"]').click()
    expect(page.locator('#pcmk-witness-panel')).to_be_visible()
    expect(page.locator('[data-setup="witness"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#pcmk-registration')).to_be_hidden()
    expect(page.locator('#pcmk-discovery')).to_be_hidden()


@pytest.mark.parametrize('view', ['overview', 'resources', 'configuration', 'quorum', 'monitoring', 'history'])
def test_cluster_pages_fit_mobile_dark_theme(logged_in, product_url, cluster_host, view, tmp_path):
    page = logged_in
    page.set_viewport_size({'width': 390, 'height': 844})
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    open_cluster(page, product_url, view)
    assert_no_page_overflow(page)
    page.screenshot(path=str(tmp_path / f'pacemaker-{view}-mobile.png'), full_page=True, animations='disabled')


def test_viewer_sees_status_without_management_actions(logged_in, product_url, cluster_host, product):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = logged_in
    open_cluster(page, product_url)
    expect(page.locator('#pcmk-nodes tr')).to_have_count(2)
    expect(page.locator('#pacemaker-app .admin-actions-toggle')).to_have_count(0)
    expect(page.locator('#pcmk-register')).to_have_count(0)


def test_initial_server_load_failure_can_be_retried(logged_in, product_url):
    page = logged_in
    endpoint = '**/pacemaker/api/servers'
    page.route(endpoint, lambda route: route.fulfill(status=502, json={'error': 'Server list unavailable'}))
    page.goto(product_url + '/install/pacemaker?setup=new')
    expect(page.locator('#pcmk-message')).to_have_text('Server list unavailable')
    expect(page.locator('#pcmk-refresh')).to_be_enabled()
    page.unroute(endpoint)
    page.locator('#pcmk-refresh').click()
    expect(page.locator('#pcmk-members tr')).to_have_count(2)
    expect(page.locator('#pcmk-members select').first).to_contain_text('Product HAProxy')
    expect(page.locator('#pcmk-message')).to_have_text('')


def test_ha_provider_still_navigates_between_services(logged_in, product_url):
    page = logged_in
    page.goto(product_url + '/ha/cluster')
    expect(page.locator('#ha-provider')).to_have_value('keepalived')
    page.locator('#ha-provider-button').click()
    page.locator('#ha-provider-menu').get_by_role('option', name='Corosync / Pacemaker', exact=True).click()
    expect(page).to_have_url(product_url + '/pacemaker')
    expect(page.locator('#pcmk-empty')).to_be_visible()
    page.locator('#ha-provider-button').click()
    page.locator('#ha-provider-menu').get_by_role('option', name='Keepalived / VRRP', exact=True).click()
    expect(page).to_have_url(product_url + '/ha/cluster')


@pytest.mark.parametrize('width', [1440, 390])
@pytest.mark.parametrize('view', ['resources', 'quorum', 'monitoring'])
def test_expanded_forms_and_menus_fit_the_workspace(logged_in, product_url, cluster_host, view, width, tmp_path):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 900})
    open_cluster(page, product_url, view)
    summaries = page.locator('#pcmk-dashboard details:not([open]):visible > summary').all_text_contents()
    for text in summaries:
        page.locator('#pcmk-dashboard').get_by_text(text, exact=True).click()
    assert_no_page_overflow(page)
    if view == 'resources':
        page.locator('#pcmk-wrapper-button').click()
        page.locator('#pcmk-wrapper-menu').get_by_role('option', name='Clone', exact=True).click()
        expect(page.locator('#pcmk-wrapper')).to_have_value('clone')
        page.locator('#pcmk-resource-form').screenshot(path=str(tmp_path / f'resource-form-{width}.png'), animations='disabled')
    else:
        page.locator('#pcmk-dashboard').screenshot(path=str(tmp_path / f'{view}-forms-{width}.png'), animations='disabled')
    for control in page.locator('#pcmk-dashboard .rw-form-field .ui-selectmenu-button:visible').all():
        box = control.bounding_box()
        parent = control.locator('..').bounding_box()
        assert box['width'] <= parent['width'] + 1
