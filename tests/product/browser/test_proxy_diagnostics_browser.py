"""Request diagnostics use real service-card dialogs and the existing queued API."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import InstallationTasks, Server, UserGroups
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.service import proxy_assessments
from tests.product.test_proxy_diagnostics import diagnostic_host

pytestmark = [pytest.mark.browser, pytest.mark.usefixtures('service_worker_controls', 'host_metrics'), pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


def open_diagnostics(page, product_url, service='haproxy', server_id=11, detail=False):
    # Only unrelated remote status/metrics calls are replaced; the modal, history,
    # permissions, queue and assessment endpoints use the real application.
    page.route('**/service/*/statuses', lambda route: route.fulfill(json={'data': []}))
    page.route('**/service/*/*/status', lambda route: route.fulfill(json={'status': 'running'}))
    page.route('**/service/*/*/last-edit', lambda route: route.fulfill(body=''))
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/service/cpu-ram-metrics/**', lambda route: route.fulfill(body=''))
    page.route('**/service/*/*/backend', lambda route: route.fulfill(json={'data': ''}))
    for path in ('bytes', 'connections', 'become-master'):
        page.route(f'**/service/*/{path}/*', lambda route: route.fulfill(body=''))
    response = page.goto(product_url + '/service/' + service + ('/192.0.2.11' if detail else ''))
    assert response.status == 200
    select_card(page, server_id)


def select_card(page, server_id):
    card = page.locator(f'#div-server-{server_id}')
    card.get_by_role('button', name='Actions', exact=True).click()
    card.get_by_role('button', name='Request diagnostics', exact=True).click()


def close_diagnostics(page):
    page.locator('.proxy-diagnostics-dialog .ui-dialog-titlebar-close').click()


def run_diagnostics(page):
    with page.expect_response('**/insights/api/diagnostics') as queued:
        page.get_by_role('button', name='Diagnose request path', exact=True).click()
    assert queued.value.status == 202
    return InstallationTasks.get_by_id(queued.value.json()['task_id'])


def test_modal_runs_resumes_and_explains_backend_failure(logged_in, product_url, product, diagnostic_host, tmp_path):
    page = logged_in
    open_diagnostics(page, product_url)
    expect(page.locator('#diagnostics-service, #diagnostics-server')).to_have_count(0)
    expect(page.locator('.proxy-diagnostics-dialog .ui-dialog-title')).to_contain_text('HAProxy · Product HAProxy (192.0.2.11)')
    page.locator('#diagnostics-url').fill('https://example.test/')
    task = run_diagnostics(page)
    payload = deserialize_operation_payload(task.operation_payload)
    assert payload['request']['service'] == 'haproxy' and payload['request']['server_id'] == 11
    close_diagnostics(page)
    select_card(page, 11)
    expect(page.locator('#diagnostics-url')).to_have_value('https://example.test/')
    expect(page.locator('#diagnostics-message')).to_contain_text('queued')
    expect(page.locator('#diagnostics-run')).to_be_disabled()
    assert InstallationTasks.select().where(InstallationTasks.operation_type == 'proxy-assessment').count() == 1
    assert proxy_assessments.execute(task) == 'completed'
    expect(page.locator('#diagnostics-summary')).to_contain_text('backend refuses', timeout=10000)
    expect(page.locator('#diagnostics-stages')).to_contain_text('TLS / SNI')
    expect(page.locator('#diagnostics-run')).to_be_enabled()
    page.screenshot(path=str(tmp_path / 'request-diagnostics-desktop.png'))
    page.set_viewport_size(dict(width=390, height=844))
    dialog = page.locator('.proxy-diagnostics-dialog')
    expect(dialog).to_be_visible()
    assert dialog.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    box = dialog.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 391
    page.screenshot(path=str(tmp_path / 'request-diagnostics-mobile.png'))
    close_diagnostics(page)
    page.reload()
    select_card(page, 11)
    expect(page.locator('#diagnostics-summary')).to_contain_text('backend refuses')


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('detail', [False, True])
def test_context_from_list_and_detail_cards(logged_in, product_url, product, service, detail):
    Server.update(apache=1).where(Server.server_id == 11).execute()
    if not detail:
        Server.create(server_id=33, hostname='Second proxy', ip='192.0.2.33', group_id='1', cred_id=11, **{service: 1})
        Server.create(server_id=34, hostname='Virtual IP', ip='192.0.2.34', group_id='1', type_ip=1, **{service: 1})
    page = logged_in
    open_diagnostics(page, product_url, service=service, detail=detail)
    expect(page.locator('#diagnostics-message')).to_have_text('Ready to run diagnostics.')
    expect(page.locator('#div-server-34 .proxy-diagnostics-trigger')).to_have_count(0)
    page.locator('#diagnostics-url').fill('example.test')
    task = run_diagnostics(page)
    request = deserialize_operation_payload(task.operation_payload)['request']
    assert request['service'] == service and request['server_id'] == 11


def test_history_does_not_change_frontend_for_next_url(logged_in, product_url, product, diagnostic_host):
    page = logged_in
    open_diagnostics(page, product_url)
    page.locator('#diagnostics-url').fill('https://example.test/')
    first = run_diagnostics(page)
    proxy_assessments.execute(first)
    expect(page.locator('#diagnostics-run')).to_be_enabled()
    page.locator('#diagnostics-frontend-button').click()
    page.get_by_role('option', name='public', exact=True).click()
    page.locator('#diagnostics-url').fill('https://another.test/')
    expect(page.locator('#diagnostics-frontend-field')).to_be_hidden()
    page.get_by_text('Assessment history', exact=True).click()
    page.locator('#diagnostics-history button').click()
    expect(page.locator('#diagnostics-frontend-field')).to_be_hidden()
    second = run_diagnostics(page)
    assert deserialize_operation_payload(second.operation_payload)['request']['frontend_id'] is None
    page.locator('#diagnostics-history button').last.click()
    proxy_assessments.execute(second)
    expect(page.locator('#diagnostics-message')).to_contain_text('completed')
    # Reading the first report stays selected while the new assessment completes.
    expect(page.locator('#diagnostics-time')).to_contain_text('https://example.test/')


def test_poll_failure_can_retry_without_queuing_again(logged_in, product_url, product, diagnostic_host):
    page = logged_in
    open_diagnostics(page, product_url)
    page.locator('#diagnostics-url').fill('example.test')
    page.route('**/insights/api/assessments/*', lambda route: route.fulfill(status=503, json={'error': 'Temporarily unavailable'}))
    task = run_diagnostics(page)
    expect(page.locator('#diagnostics-message')).to_contain_text('Unable to refresh')
    expect(page.locator('#diagnostics-retry')).to_be_visible()
    expect(page.locator('#diagnostics-run')).to_be_disabled()
    page.unroute('**/insights/api/assessments/*')
    proxy_assessments.execute(task)
    page.locator('#diagnostics-retry').click()
    expect(page.locator('#diagnostics-summary')).to_contain_text('backend refuses')
    expect(page.locator('#diagnostics-run')).to_be_enabled()
    assert InstallationTasks.select().where(InstallationTasks.operation_type == 'proxy-assessment').count() == 1


def test_viewer_has_history_without_mutating_actions(logged_in, product_url, product, product_client, diagnostic_host):
    response = product_client.post('/insights/api/diagnostics', json=dict(service='haproxy', server_id=11, url='example.test'))
    proxy_assessments.execute(InstallationTasks.get_by_id(response.json['task_id']))
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = logged_in
    open_diagnostics(page, product_url)
    expect(page.locator('#diagnostics-run')).to_have_count(0)
    expect(page.locator('.service-action-command')).to_have_count(0)
    expect(page.locator('#diagnostics-summary')).to_contain_text('backend refuses')
    assert product_client.post('/insights/api/diagnostics', json=dict(service='haproxy', server_id=11, url='example.test')).status_code == 403


def test_late_response_cannot_leak_between_servers(logged_in, product_url, product):
    Server.create(server_id=33, hostname='Second proxy', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    page = logged_in
    open_diagnostics(page, product_url)
    requests = []
    page.route('**/insights/api/diagnostics', lambda route: requests.append(route))
    try:
        page.locator('#diagnostics-url').fill('first.example.test')
        page.locator('#diagnostics-run').click()
        expect(page.locator('#diagnostics-message')).to_contain_text('Starting')
        close_diagnostics(page)
        select_card(page, 33)
        expect(page.locator('#diagnostics-message')).to_have_text('Ready to run diagnostics.')
        expect(page.locator('#diagnostics-url')).to_have_value('')
        requests.pop().fulfill(status=503, json={'error': 'Stale operation error'})
        page.wait_for_load_state('networkidle')
        expect(page.locator('#diagnostics-message')).to_have_text('Ready to run diagnostics.')
        close_diagnostics(page)
        select_card(page, 11)
        expect(page.locator('#diagnostics-url')).to_have_value('first.example.test')
    finally:
        for route in requests:
            route.abort()
        page.unroute('**/insights/api/diagnostics')
