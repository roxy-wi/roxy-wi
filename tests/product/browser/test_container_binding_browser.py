import os

import pytest
from playwright.sync_api import expect

from app.modules.service import container_settings
from app.modules.db.db_model import ServiceSetting

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Requires Chromium')]


def test_native_service_dialog_discovers_and_adopts_podman(logged_in,product_url,product,host_metrics,last_config_edit,monkeypatch):
    page=logged_in
    monkeypatch.setattr('app.routes.service.routes.server_mod.subprocess_execute',lambda _:(['0'],''))
    seen=[]
    def discover(server,spec):
        seen.append((server.server_id,spec))
        return dict(version='podman version 5.4',cgroup_v2=True,containers=[dict(name='proxy-lab',image='example/proxy',running=True,unit='proxy-lab.service')])
    monkeypatch.setattr(container_settings,'discover',discover)
    page.route('**/service/haproxy/statuses',lambda route:route.fulfill(json={'data':[]}))
    page.route('**/overview/server/**',lambda route:route.fulfill(body=''))
    page.route('**/service/haproxy/*/backend',lambda route:route.fulfill(json={'data':''}))
    page.goto(product_url+'/service/haproxy')
    card=page.locator('#div-server-11')
    card.locator('.service-actions-toggle').click()
    card.locator('.service-settings-command').click()
    dialog=page.locator('#dialog-settings-service')
    dialog.locator('#haproxy-container-engine-button').click()
    page.get_by_role('option',name='Podman',exact=True).click()
    dialog.locator('[name="container_owner"]').fill('proxy')
    dialog.get_by_role('button',name='Discover containers',exact=True).click()
    expect(dialog.locator('[data-container-result]')).to_contain_text('podman version 5.4')
    dialog.locator('#haproxy-container-choice-button').click()
    page.get_by_role('option',name='proxy-lab · running · example/proxy',exact=True).click()
    expect(dialog.locator('[name="container_name"]')).to_have_value('proxy-lab')
    expect(dialog.locator('[name="container_unit"]')).to_have_value('proxy-lab.service')
    expect(dialog.locator('[name="dockerized"]')).to_be_checked()
    page.set_viewport_size(dict(width=390,height=844))
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    assert dialog.evaluate('(node)=>node.scrollWidth<=node.clientWidth+1')
    bounds=dialog.locator('..').bounding_box()
    assert bounds['x']>=0 and bounds['x']+bounds['width']<=390
    page.set_viewport_size(dict(width=1440,height=1000))
    with page.expect_event('load'):
        dialog.locator('..').locator('.ui-dialog-buttonpane button').first.click()
    assert container_settings.runtime(11,'haproxy')==dict(engine='podman',owner='proxy',unit='proxy-lab.service')
    assert seen==[(11,dict(engine='podman',owner='proxy',unit=''))]
