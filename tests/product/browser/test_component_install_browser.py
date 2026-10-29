import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import InstallationTasks
from app.modules.operations.queue import deserialize_operation_payload

pytestmark = [pytest.mark.browser, pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


@pytest.mark.parametrize('service,button', [('haproxy','install'),('nginx','nginx_install'),('apache','apache_install')])
def test_existing_installation_form_queues_the_selected_podman_proxy(logged_in,product_url,product,monkeypatch,service,button):
    monkeypatch.setattr('app.modules.common.common.is_tool',lambda *_:True)
    page=logged_in
    page.route('**/service/'+service+'/192.0.2.11/status',lambda route:route.fulfill(json={'status':'failed'}))
    page.goto(product_url+'/install#service')
    page.locator('#'+service+'_container_engine-button').click()
    page.get_by_role('option',name='Podman',exact=True).click()
    expect(page.locator('#'+service+'_container_engine')).to_have_value('podman')
    page.locator('#'+service+'addserv-button').click()
    page.get_by_role('option',name='Product HAProxy',exact=True).click()
    expect(page.locator('#cur_'+service+'_ver')).to_contain_text('not installed')
    if service=='haproxy': expect(page.locator('#hapver')).to_have_value('3.3.1-1')
    if os.environ.get('ROXYWI_CAPTURE_CONTAINER_DOCS')=='1' and service=='haproxy':
        page.wait_for_load_state('networkidle')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/managed-containers'
        folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'installation.png'))
    with page.expect_response('**/install/'+service+'/192.0.2.11') as response:
        page.locator('#'+button).click()
    assert response.value.status==202,response.value.text()
    task=InstallationTasks.get_by_id(response.value.json()['tasks_ids'][0])
    payload=deserialize_operation_payload(task.operation_payload)
    assert payload['ansible_role']=='podman_proxy'
    host=payload['inventory']['server']['hosts'][product.server.ip]
    assert host['service']==service and host['CONTAINER_ENGINE']=='podman'
    if service=='haproxy': assert host['IMAGE']=='docker.io/haproxytech/haproxy-alpine:3.3.1'
    assert host['CERT_DIR']=='/var/lib/roxy-wi/certificates/'+service
    assert payload['success_action']['request']['services'][service]['container_engine']=='podman'


def test_witness_installation_uses_the_same_engine_selector(logged_in,product_url,product):
    page=logged_in
    product.server.hostname='Product witness';product.server.save()
    page.goto(product_url+'/install/pacemaker?setup=witness')
    page.locator('#pcmk-witness-engine-button').click()
    page.get_by_role('option',name='Podman',exact=True).click()
    expect(page.locator('#pcmk-witness-engine')).to_have_value('podman')
    page.locator('#pcmk-witness-server-button').click()
    page.get_by_role('option',name='Product witness',exact=False).click()
    if os.environ.get('ROXYWI_CAPTURE_CONTAINER_DOCS')=='1':
        page.wait_for_load_state('networkidle')
        folder=Path(__file__).resolve().parents[3]/'docs/screenshots/managed-containers'
        folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/'witness.png'))
    page.locator('#pcmk-witness-install').click()
    with page.expect_response('**/pacemaker/api/witness/install') as response:
        page.get_by_role('button',name='Continue',exact=True).click()
    assert response.value.status==202,response.value.text()
    task=InstallationTasks.get_by_id(response.value.json()['task_id'])
    assert deserialize_operation_payload(task.operation_payload)['container_engine']=='podman'
