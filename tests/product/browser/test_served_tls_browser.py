import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.db.db_model import InstallationTasks
from app.modules.service import served_tls
from tests.product.test_served_tls import tls_host,diagnostic_host
from tests.product.test_service_map import discover

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_served_tls_monitor_uses_discovered_targets_and_displays_evidence(logged_in,product_url,product_client,tls_host):
    discover(product_client)
    page=logged_in;page.goto(product_url+'/insights/tls');page.get_by_role('button',name='New TLS monitor',exact=True).click()
    page.locator('#tls-name').fill('Application TLS')
    page.locator('#tls-domain-button').click();page.get_by_role('option',name='example.test',exact=True).click()
    page.locator('#tls-targets input').check()
    page.get_by_role('button',name='Save TLS monitor',exact=True).click()
    expect(page.locator('#tls-rows')).to_contain_text('Application TLS')
    with page.expect_response('**/run') as queued:page.get_by_role('button',name='Check served TLS',exact=True).click()
    assert queued.value.status==202
    assert served_tls.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    expect(page.locator('#tls-rows')).to_contain_text('verified',timeout=10000)
    page.get_by_role('button',name='View report',exact=True).click()
    expect(page.locator('#tls-summary')).to_contain_text('verified')
    expect(page.locator('#tls-endpoints')).to_contain_text(tls_host.metadata['fingerprint'])
    if os.environ.get('ROXYWI_CAPTURE_TLS_DOCS')=='1':
        page.wait_for_load_state('networkidle');folder=Path(__file__).resolve().parents[3]/'docs/screenshots/served-tls';folder.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(folder/'tls.png'))
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
