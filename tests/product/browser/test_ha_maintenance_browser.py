"""Maintenance checks, independent approval and execution stay in one workflow."""
import os

import pytest
from playwright.sync_api import expect

from tests.product.test_ha_readiness import readiness_cluster
from tests.product.test_ha_maintenance import (
    maintenance_cluster, keepalived_maintenance, create, step,
)
from app.modules.db.db_model import InstallationTasks, HaMaintenancePlan, ConfigChange
from app.modules.pacemaker import operations
from app.modules.service import ha_maintenance as maintenance

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium'),
]


def select(page, field, name):
    if field == 'cluster':
        if page.locator('#ha-maintenance-dialog').is_visible():
            page.locator('.ha-cluster-dialog:visible .ui-dialog-titlebar-close').click()
        cluster_name, provider = name.split(' · ')
        card = page.locator(f'[data-ha-provider="{provider}"][data-ha-name="{cluster_name}"]')
        card.get_by_role('button', name='Actions', exact=False).click()
        card.get_by_role('menuitem', name='Node maintenance', exact=True).click()
        expect(page.locator('#ha-maintenance-dialog')).to_be_visible()
        return
    page.locator(f'#maintenance-{field}-button').click()
    page.get_by_role('option', name=name, exact=True).click()


@pytest.mark.parametrize('missing', ['node', 'loading-nodes'])
def test_required_select_focuses_visible_control_and_recovers_after_selection(
    logged_in, product_url, maintenance_cluster, missing,
):
    page = logged_in
    console_errors, posts, held = [], [], []
    page.on('console', lambda event: console_errors.append(event.text) if event.type == 'error' else None)
    page.on('request', lambda request: posts.append(request) if request.method == 'POST' and request.url.endswith('/api/maintenance') else None)
    endpoint = '**/ha/api/readiness/pacemaker/*'
    if missing == 'loading-nodes':
        page.route(endpoint, lambda route: held.append(route))
    try:
        page.goto(product_url + '/ha/maintenance')
        page.locator('#maintenance-title').fill('OS')
        page.locator('#maintenance-capacity').fill('#7')
        page.locator('label[for="maintenance-confirm-capacity"]').click()
        page.get_by_role('button', name='Create maintenance plan', exact=True).click()
        field = 'node'
        expect(page.locator('#ha-maintenance-message')).to_have_text(f'Select a {field}.')
        expect(page.locator(f'#maintenance-{field}-button')).to_be_focused()
        expect(page.locator(f'#maintenance-{field}-button')).to_have_attribute('aria-invalid', 'true')
        assert not posts and HaMaintenancePlan.select().count() == 0
        assert not any('not focusable' in error for error in console_errors)
        if missing == 'loading-nodes':
            assert len(held) == 1
            held.pop().continue_()
        expect(page.locator('#maintenance-node option[value="11"]')).to_have_count(1)
        select(page, 'node', 'one')
        expect(page.locator('#ha-maintenance-message')).to_have_text('')
        expect(page.locator('[aria-invalid="true"]')).to_have_count(0)
        with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/api/maintenance')) as created:
            page.get_by_role('button', name='Create maintenance plan', exact=True).click()
        assert created.value.status == 201, created.value.text()
        assert created.value.json()['data']['server_id'] == 11
        assert len(posts) == 1
        assert not any('not focusable' in error for error in console_errors)
    finally:
        for route in held:
            route.abort()
        if missing == 'loading-nodes':
            page.unroute(endpoint)


def queued_step(page, label, action, execute):
    with page.expect_response(f'**/api/maintenance/*/{action}') as queued:
        page.get_by_role('button', name=label, exact=True).click()
    assert queued.value.status == 202, queued.value.text()
    task = InstallationTasks.get_by_id(queued.value.json()['task_id'])
    expect(page.locator('[data-plan]')).to_contain_text('Queued')
    assert execute(task) == 'completed'


@pytest.fixture
def reviewer_page(browser, browser_context_args, product_url, maintenance_cluster):
    context = browser.new_context(**browser_context_args)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    response = page.request.post(product_url + '/login', data={
        'login': 'reviewer', 'pass': 'TestBootstrapPassword!', 'next': '/ha/maintenance',
    })
    assert response.status == 200, response.text()
    yield page
    context.close()
    assert not errors, '\n'.join(errors)


@pytest.mark.parametrize('provider', ['pacemaker', 'keepalived'])
def test_checks_approval_drain_and_return_without_leaving_maintenance(
    logged_in, reviewer_page, product_url, product, maintenance_cluster,
    keepalived_maintenance, provider, tmp_path,
):
    page = logged_in
    page.goto(product_url + '/ha/maintenance')
    expect(page.get_by_role('button', name='Refresh', exact=True)).to_have_count(0)
    expect(page.locator('main a[href="/ha/readiness"]')).to_have_count(0)
    select(page, 'cluster', 'product-ha · pacemaker' if provider == 'pacemaker' else 'product-vrrp · keepalived')
    select(page, 'node', 'one' if provider == 'pacemaker' else 'Product HAProxy')
    page.locator('#maintenance-title').fill('OS')
    page.locator('#maintenance-capacity').fill('#7')
    page.locator('label[for="maintenance-confirm-capacity"]').click()
    with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/api/maintenance')) as created:
        page.get_by_role('button', name='Create maintenance plan', exact=True).click()
    assert created.value.status == 201, created.value.text()
    plan = created.value.json()['data']
    execute = operations.execute if provider == 'pacemaker' else maintenance.execute
    queued_step(page, 'Run drain checks', 'review', execute)
    panel = page.locator('[data-plan]')
    expect(panel).to_contain_text('Drain awaiting approval', timeout=15000)
    expect(panel).to_contain_text('You created this plan and cannot approve it.')
    expect(panel.locator('p').filter(has_text='Eligible approvers:')).to_contain_text('reviewer')
    expect(panel.get_by_role('button', name='Approve drain', exact=True)).to_have_count(0)
    expect(panel.get_by_role('button', name='Drain node', exact=True)).to_have_count(0)
    assert maintenance_cluster.commands == [] and keepalived_maintenance.actions == []
    page.screenshot(path=str(tmp_path / 'maintenance-review-desktop.png'), full_page=True)

    # Polling keeps expanded history and existing controls in place while waiting.
    panel.get_by_text('History', exact=True).click()
    panel.evaluate('(element) => { window.maintenancePanel = element; }')
    with page.expect_response('**/ha/api/maintenance?*'):
        pass
    assert panel.evaluate('(element) => element === window.maintenancePanel')
    expect(panel.locator('[data-maintenance-detail="history"]')).to_have_attribute('open', '')

    reviewer_page.goto(product_url + f'/ha/maintenance?change={plan["change_id"]}')
    for returning in (False, True):
        label = 'Approve return' if returning else 'Approve drain'
        if returning:
            queued_step(page, 'Run return checks', 'review-return', execute)
            expect(panel).to_contain_text('Return awaiting approval', timeout=15000)
            expect(panel.get_by_role('button', name='Return node', exact=True)).to_have_count(0)
        reviewer_panel = reviewer_page.locator('[data-plan]')
        expect(reviewer_panel.get_by_role('button', name=label, exact=True)).to_be_visible(timeout=15000)
        with reviewer_page.expect_response(f'**/changes/api/{plan["change_id"]}/approve') as approved:
            reviewer_panel.get_by_role('button', name=label, exact=True).click()
        assert approved.value.status == 200, approved.value.text()
        expect(panel).to_contain_text('Approved by reviewer.', timeout=15000)
        queued_step(page, 'Return node' if returning else 'Drain node', 'resume' if returning else 'drain', execute)
        if returning:
            expect(page.locator('#maintenance-history')).to_contain_text('Completed', timeout=15000)
            page.locator('#ha-maintenance-tabs a[href="#ha-maintenance-history"]').click()
        else:
            expect(panel).to_contain_text('Ready for maintenance', timeout=15000)
    assert HaMaintenancePlan.get_by_id(plan['id']).status == 'completed'
    assert ConfigChange.get_by_id(plan['change_id']).status == 'deployed'

    page.set_viewport_size(dict(width=390, height=844))
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    page.locator('#ha-maintenance-tabs a[href="#ha-maintenance-current"]').click()
    assert page.locator('#maintenance-capacity').evaluate('(field) => field.getBoundingClientRect().width >= field.parentElement.clientWidth * .9')
    page.screenshot(path=str(tmp_path / 'maintenance-completed-mobile.png'), full_page=True)


def test_change_center_details_show_checks_and_allow_independent_approval(
    logged_in, reviewer_page, product_url, product_client, maintenance_cluster, tmp_path,
):
    row = step(product_client, create(product_client, maintenance_cluster), 'review')
    page = logged_in
    page.goto(product_url + f'/changes?change={row.change_id}')
    dialog = page.locator('#change-details-dialog')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text('You created this plan and cannot approve it.')
    expect(dialog.get_by_role('button', name='Approve drain', exact=True)).to_have_count(0)
    expect(page.get_by_role('link', name='Maintenance wizard', exact=True)).to_have_count(0)

    reviewer_page.goto(product_url + f'/changes?change={row.change_id}')
    dialog = reviewer_page.locator('#change-details-dialog')
    expect(dialog).to_contain_text('Quorum: 2 votes remain; 2 required.')
    expect(dialog).to_contain_text('vip: two')
    expect(dialog.locator('#change-details-rollout')).to_be_hidden()
    expect(dialog.locator('#change-details-diff')).to_be_hidden()
    reviewer_page.wait_for_load_state('networkidle')
    reviewer_page.screenshot(path=str(tmp_path / 'change-center-maintenance-review.png'))
    with reviewer_page.expect_response(f'**/changes/api/{row.change_id}/approve') as response:
        dialog.get_by_role('button', name='Approve drain', exact=True).click()
    assert response.value.status == 200, response.value.text()
    expect(dialog).to_contain_text('Approved by reviewer.')
    expect(dialog.get_by_role('button', name='Approve drain', exact=True)).to_have_count(0)
    assert maintenance_cluster.commands == []


def test_creating_plan_shows_progress_blocks_duplicates_and_can_retry(
    logged_in, product_url, maintenance_cluster,
):
    page = logged_in
    page.goto(product_url + '/ha/maintenance')
    select(page, 'cluster', 'product-ha · pacemaker')
    select(page, 'node', 'one')
    page.locator('#maintenance-title').fill('OS')
    page.locator('#maintenance-capacity').fill('#7')
    page.locator('label[for="maintenance-confirm-capacity"]').click()
    requests = []
    endpoint = '**/ha/api/maintenance'

    def hold_creation(route):
        if route.request.method == 'POST':
            requests.append(route)
        else:
            route.continue_()

    page.route(endpoint, hold_creation)
    button = page.get_by_role('button', name='Create maintenance plan', exact=True)
    try:
        button.click()
        expect(page.locator('#ha-maintenance-message')).to_contain_text('Creating maintenance plan')
        expect(page.locator('#ha-maintenance-message .fa-spinner')).to_be_visible()
        expect(button).to_be_disabled()
        page.locator('#ha-maintenance-create').dispatch_event('submit')
        assert len(requests) == 1
        requests.pop().fulfill(status=503, json={'error': 'Temporarily unavailable'})
        expect(page.locator('#ha-maintenance-message')).to_have_text('Temporarily unavailable')
        expect(button).to_be_enabled()
        expect(button).not_to_have_class('ui-state-disabled')
        expect(page.locator('#maintenance-capacity')).to_have_value('#7')
    finally:
        for route in requests:
            route.abort()
        page.unroute(endpoint, hold_creation)
    with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/api/maintenance')) as created:
        button.click()
    assert created.value.status == 201, created.value.text()
    expect(page.locator('[data-plan]')).to_have_count(1)
    assert HaMaintenancePlan.select().count() == 1
