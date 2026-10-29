import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.product.test_ha_readiness import readiness_cluster
from app.modules.service import ha_readiness as audit
from app.modules.db.db_model import InstallationTasks
from app.modules.common.time import utc_now
from datetime import timedelta

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_native_audit_gui_queues_displays_evidence_and_saves_domains(logged_in,product_url,product,readiness_cluster):
    page=logged_in;page.goto(product_url+'/ha/readiness')
    page.locator('#ha-audit-cluster-button').click()
    page.get_by_role('option',name='product-ha · pacemaker',exact=True).click()
    expect(page.locator('#ha-domain-11-hypervisor')).to_be_visible()
    page.locator('#ha-domain-11-hypervisor').fill('pve-shared')
    page.locator('#ha-domain-33-hypervisor').fill('pve-shared')
    with page.expect_response('**/profile') as response:page.get_by_role('button',name='Save failure domains',exact=True).click()
    assert response.value.status==200
    with page.expect_response('**/run') as queued:page.get_by_role('button',name='Run readiness audit',exact=True).click()
    assert queued.value.status==202
    assert audit.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh',exact=True).click()
    expect(page.locator('#ha-audit-checks')).to_contain_text('fencing')
    expect(page.locator('#ha-audit-checks')).to_contain_text('configured')
    expect(page.locator('#ha-audit-verification')).to_contain_text('unknown')
    assert 'NeverExposeThisSecret' not in page.content()
    if os.environ.get('ROXYWI_CAPTURE_HA_DOCS')=='1':
        page.wait_for_load_state('networkidle');page.evaluate('window.scrollTo(0,0)')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/ha-readiness';folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'overview.png'))
    page.get_by_text('Record an external test',exact=True).click()
    page.locator('#ha-test-at').fill((utc_now()-timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'))
    page.locator('#ha-test-note').fill('External test <img src=x onerror=alert(1)> evidence')
    with page.expect_response('**/attest') as attested:page.get_by_role('button',name='Record operator attestation',exact=True).click()
    assert attested.value.status==200
    expect(page.locator('#ha-audit-tests')).to_contain_text('operator attestation')
    assert page.locator('#ha-audit-tests img').count()==0
    page.set_viewport_size(dict(width=390,height=844))
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')


def test_polling_retains_unsaved_domains_and_their_revision(logged_in,product_url,product,readiness_cluster):
    page=logged_in;page.goto(product_url+'/ha/readiness')
    page.locator('#ha-audit-cluster-button').click()
    page.get_by_role('option',name='product-ha · pacemaker',exact=True).click()
    field=page.locator('#ha-domain-11-hypervisor');expect(field).to_be_visible()
    with page.expect_response('**/run'):page.get_by_role('button',name='Run readiness audit',exact=True).click()
    field.fill('unsaved-hypervisor')
    # A background refresh must retain both the edit and its optimistic revision.
    with page.expect_response('**/ha/api/readiness/pacemaker/*'):pass
    expect(field).to_have_value('unsaved-hypervisor')
    audit.save_profile('pacemaker',readiness_cluster.cluster.id,1,audit.ProfileRequest(revision=0,domains={}))
    with page.expect_response('**/ha/api/readiness/pacemaker/*'):pass
    expect(field).to_have_value('unsaved-hypervisor')
    with page.expect_response('**/profile') as response:page.get_by_role('button',name='Save failure domains',exact=True).click()
    assert response.value.status==409
    expect(field).to_have_value('unsaved-hypervisor')
