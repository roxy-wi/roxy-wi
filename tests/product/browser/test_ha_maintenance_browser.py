import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.product.test_ha_readiness import readiness_cluster
from tests.product.test_ha_maintenance import maintenance_cluster
from app.modules.db.db_model import InstallationTasks,HaMaintenancePlan
from app.modules.pacemaker import operations

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_native_maintenance_gui_creates_and_reviews_a_plan_without_drain(logged_in,product_url,product,maintenance_cluster):
    page=logged_in;page.goto(product_url+'/ha/maintenance')
    assert page.locator('#maintenance-capacity').evaluate('(field)=>field.getBoundingClientRect().width>=field.parentElement.clientWidth*.9')
    page.locator('#maintenance-cluster-button').click();page.get_by_role('option',name='product-ha · pacemaker',exact=True).click()
    page.locator('#maintenance-node-button').click();page.get_by_role('option',name='one',exact=True).click()
    page.locator('#maintenance-title').fill('Planned node maintenance')
    page.locator('#maintenance-capacity').fill('Application load test with one surviving node')
    page.locator('label[for="maintenance-confirm-capacity"]').click()
    expect(page.locator('#maintenance-confirm-capacity')).to_be_checked()
    with page.expect_response('**/api/maintenance') as created:page.get_by_role('button',name='Create maintenance plan',exact=True).click()
    assert created.value.status==201
    ident=created.value.json()['data']['id']
    with page.expect_response('**/review') as queued:page.get_by_role('button',name='Review drain',exact=True).click()
    assert queued.value.status==202
    assert operations.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh',exact=True).click()
    expect(page.locator('[data-plan]')).to_contain_text('pending_approval')
    expect(page.get_by_role('button',name='Drain approved node',exact=True)).to_be_disabled()
    assert maintenance_cluster.commands==[]
    if os.environ.get('ROXYWI_CAPTURE_MAINTENANCE_DOCS')=='1':
        page.wait_for_load_state('networkidle');page.evaluate('window.scrollTo(0,0)')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/ha-maintenance';folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'review.png'))
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
    assert page.locator('#maintenance-capacity').evaluate('(field)=>field.getBoundingClientRect().width>=field.parentElement.clientWidth*.9')
