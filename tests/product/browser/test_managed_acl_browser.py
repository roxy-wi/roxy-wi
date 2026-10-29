import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.db.db_model import InstallationTasks,ManagedAclVersion
from app.modules.service import managed_acl
from tests.product.test_managed_acl import acl_host
from tests.product.test_ha_maintenance import approve

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_acl_gui_discovers_lists_and_reviews_version_without_automatic_apply(logged_in,product_url,acl_host,app):
    page=logged_in;page.goto(product_url+'/insights/acl-feeds');page.get_by_role('button',name='New managed feed',exact=True).click()
    page.locator('#acl-name').fill('Reviewed IP feed');page.locator('#acl-url').fill('https://feeds.example.test/ips.txt')
    page.locator('#acl-server-button').click();page.get_by_role('option',name='Product HAProxy (192.0.2.11)',exact=True).click()
    page.get_by_role('button',name='Discover IP lists',exact=True).click()
    page.locator('#acl-path-button').click();page.get_by_role('option',name='/etc/haproxy/black/list.lst · 1 entries',exact=True).click()
    page.get_by_role('button',name='Add target',exact=True).click();page.get_by_role('button',name='Save feed',exact=True).click()
    expect(page.locator('#acl-rows')).to_contain_text('Source approval required')
    page.get_by_role('button',name='Approve source and targets',exact=True).click()
    expect(page.locator('#acl-rows')).to_contain_text('Source revision approved')
    with page.expect_response('**/fetch') as queued:page.get_by_role('button',name='Fetch candidate',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(queued.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click();page.get_by_role('button',name='Versions',exact=True).click()
    expect(page.locator('#acl-versions')).to_contain_text('downloaded')
    with page.expect_response('**/review') as reviewed:page.get_by_role('button',name='Review deployment',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(reviewed.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click()
    expect(page.locator('#acl-versions')).to_contain_text('pending_approval')
    assert not any(action=='apply' for _,action,_ in acl_host.remote)
    page.get_by_role('button',name='View content / diff',exact=True).click()
    expect(page.locator('#acl-diff')).to_contain_text('192.0.2.0/24')
    if os.environ.get('ROXYWI_CAPTURE_ACL_DOCS')=='1':
        page.wait_for_load_state('networkidle');folder=Path(__file__).resolve().parents[3]/'docs/screenshots/managed-acl';folder.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(folder/'feeds.png'))
    row=ManagedAclVersion.get()
    page.goto(product_url+'/insights/acl-feeds?change='+str(row.change_id))
    expect(page.locator('#acl-selected')).to_contain_text('Reviewed IP feed')
    expect(page.locator('#acl-diff')).to_contain_text('192.0.2.0/24')
    approve(app,row,acl_host.reviewer)
    page.get_by_role('button',name='Refresh feeds',exact=True).click()
    with page.expect_response('**/apply') as applied:page.get_by_role('button',name='Apply approved version',exact=True).click()
    assert managed_acl.execute(InstallationTasks.get_by_id(applied.value.json()['task_id']))=='completed'
    page.get_by_role('button',name='Refresh feeds',exact=True).click();expect(page.locator('#acl-versions')).to_contain_text('deployed')
    page.set_viewport_size(dict(width=390,height=844));page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert page.locator('main').evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
