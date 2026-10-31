import os
import re
import json
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.product.test_ha_readiness import readiness_cluster, run
from app.modules.service import ha_readiness as audit
from app.modules.db.db_model import InstallationTasks, OperationalAssessment
from app.modules.operations.queue import serialize_operation_payload
from app.modules.common.time import utc_now
from datetime import timedelta

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_native_audit_gui_queues_displays_evidence_and_saves_domains(logged_in,product_url,product,readiness_cluster,tmp_path):
    page=logged_in;page.goto(product_url+'/ha/readiness')
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-settings"]').click()
    expect(page.locator('#ha-domain-11-hypervisor')).to_be_visible()
    page.locator('#ha-domain-11-hypervisor').fill('pve-shared')
    page.locator('#ha-domain-33-hypervisor').fill('pve-shared')
    with page.expect_response('**/profile') as response:page.get_by_role('button',name='Save failure domains',exact=True).click()
    assert response.value.status==200
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-check"]').click()
    with page.expect_response('**/run') as queued:page.get_by_role('button',name='Run readiness audit',exact=True).click()
    assert queued.value.status==202
    assert audit.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    expect(page.get_by_role('button',name='Refresh',exact=True)).to_have_count(0)
    expect(page.locator('#ha-audit-checks')).to_contain_text('fencing')
    expect(page.locator('#ha-audit-checks')).to_contain_text('configured')
    expect(page.locator('#ha-audit-verification')).to_contain_text('unknown')
    expect(page.locator('#ha-audit-message')).to_contain_text('completed')
    dialog = page.locator('.ha-cluster-dialog:visible').bounding_box()
    assert dialog['y'] >= 0
    assert dialog['y'] + dialog['height'] <= page.viewport_size['height']
    observed = page.locator('#ha-audit-time').bounding_box()
    status = page.locator('#ha-audit-message').bounding_box()
    assert observed['y'] == pytest.approx(status['y'], abs=1)
    toolbar = page.locator('#ha-readiness-check > .rw-table-toolbar').bounding_box()
    table = page.locator('#ha-readiness-check > .rw-table-shell').bounding_box()
    assert 0 <= table['y'] - (toolbar['y'] + toolbar['height']) <= 40
    page.locator('#ha-readiness').screenshot(path=str(tmp_path / 'readiness-compact-desktop.png'))
    assert 'NeverExposeThisSecret' not in page.content()
    if os.environ.get('ROXYWI_CAPTURE_HA_DOCS')=='1':
        page.wait_for_load_state('networkidle');page.evaluate('window.scrollTo(0,0)')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/ha-readiness';folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'overview.png'))
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-settings"]').click()
    page.get_by_text('Record an external test',exact=True).click()
    page.locator('#ha-test-at').fill((utc_now()-timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'))
    page.locator('#ha-test-note').fill('External test <img src=x onerror=alert(1)> evidence')
    with page.expect_response('**/attest') as attested:page.get_by_role('button',name='Record operator attestation',exact=True).click()
    assert attested.value.status==200
    expect(page.locator('#ha-audit-tests')).to_contain_text('operator attestation')
    assert page.locator('#ha-audit-tests img').count()==0
    page.set_viewport_size(dict(width=390,height=844))
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    dialog = page.locator('.ha-cluster-dialog:visible').bounding_box()
    assert dialog['y'] >= 0
    assert dialog['y'] + dialog['height'] <= page.viewport_size['height']
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
    page.locator('#ha-readiness').screenshot(path=str(tmp_path / 'readiness-compact-mobile.png'))


def test_polling_retains_unsaved_domains_and_their_revision(logged_in,product_url,product,readiness_cluster):
    page=logged_in;page.goto(product_url+'/ha/readiness')
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-settings"]').click()
    field=page.locator('#ha-domain-11-hypervisor');expect(field).to_be_visible()
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-check"]').click()
    with page.expect_response('**/run'):page.get_by_role('button',name='Run readiness audit',exact=True).click()
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-settings"]').click()
    field.fill('unsaved-hypervisor')
    # A background refresh must retain both the edit and its optimistic revision.
    with page.expect_response('**/ha/api/readiness/pacemaker/*'):pass
    expect(field).to_have_value('unsaved-hypervisor')
    expect(page.locator('#ha-audit-message')).to_be_visible()
    audit.save_profile('pacemaker',readiness_cluster.cluster.id,1,audit.ProfileRequest(revision=0,domains={}))
    with page.expect_response('**/ha/api/readiness/pacemaker/*'):pass
    expect(field).to_have_value('unsaved-hypervisor')
    with page.expect_response('**/profile') as response:page.get_by_role('button',name='Save failure domains',exact=True).click()
    assert response.value.status==409
    expect(field).to_have_value('unsaved-hypervisor')
    expect(page.locator('#ha-audit-message')).to_be_visible()


def test_history_loads_older_audits_and_keeps_selection_during_polling(
    logged_in, product_url, product_client, readiness_cluster,
):
    oldest, report = run(product_client, readiness_cluster)
    for index in range(21):
        newer_report = json.loads(json.dumps(report))
        newer_report['checks'][0]['message'] = f'Newer report {index}'
        OperationalAssessment.create(group_id=1, user_id=oldest.user_id, kind=oldest.kind,
                                     subject=oldest.subject, result=serialize_operation_payload(newer_report), status='completed')
    page = logged_in
    page.goto(product_url + f'/ha/cluster?panel=readiness&provider=pacemaker&cluster={readiness_cluster.cluster.id}')
    with page.expect_response('**/run') as queued:
        page.get_by_role('button', name='Run readiness audit', exact=True).click()
    page.locator('#ha-readiness-tabs a[href="#ha-readiness-history"]').click()
    page.get_by_role('button', name='Load older audits', exact=True).click()
    oldest_button = page.locator('#ha-audit-history').get_by_role('button', name=re.compile(r'^#' + str(oldest.id) + r' ·'))
    expect(oldest_button).to_be_visible()
    oldest_button.click()
    expect(page.locator('#ha-readiness-check')).to_be_visible()
    checks = page.locator('#ha-audit-checks').inner_text()
    assert 'Newer report' not in checks
    with page.expect_response('**/ha/api/readiness/pacemaker/*'):
        pass
    assert page.locator('#ha-audit-checks').inner_text() == checks
    page.locator('.ha-cluster-dialog:visible .ui-dialog-titlebar-close').click()
    # Closing the dialog leaves the worker task queued and removes its poll timer.
    task = InstallationTasks.get_by_id(queued.value.json()['task_id'])
    assert task.status == 'created'
    assert audit.execute(task) == 'completed'
    card = page.locator('[data-ha-provider="pacemaker"]')
    card.get_by_role('button', name='Actions', exact=True).click()
    card.get_by_role('menuitem', name='HA readiness', exact=True).click()
    expect(page.locator('#ha-audit-message')).to_contain_text('completed')
    expect(page.get_by_role('button', name='Run readiness audit', exact=True)).to_be_enabled()
