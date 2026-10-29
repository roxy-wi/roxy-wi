import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.product.test_proxy_diagnostics import diagnostic_host
from app.modules.db.db_model import InstallationTasks
from app.modules.service import proxy_assessments

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_native_diagnostic_form_runs_and_explains_backend_failure(logged_in,product_url,product,diagnostic_host):
    page=logged_in;page.goto(product_url+'/insights/diagnostics?service=haproxy')
    page.locator('#diagnostics-server-button').click();page.get_by_role('option',name='Product HAProxy (192.0.2.11)',exact=True).click()
    page.locator('#diagnostics-url').fill('https://example.test/')
    with page.expect_response('**/api/diagnostics') as queued:page.get_by_role('button',name='Diagnose request path',exact=True).click()
    assert queued.value.status==202
    assert proxy_assessments.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    expect(page.locator('#diagnostics-summary')).to_contain_text('backend refuses',timeout=10000)
    expect(page.locator('#diagnostics-stages')).to_contain_text('TLS / SNI')
    if os.environ.get('ROXYWI_CAPTURE_DIAGNOSTICS_DOCS')=='1':
        page.wait_for_load_state('networkidle');page.evaluate('window.scrollTo(0,0)')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/proxy-diagnostics';folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'path.png'))
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
