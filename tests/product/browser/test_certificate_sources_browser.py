"""Provider forms use native controls and keep secrets out of the page."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.connectors.certificates import CertWarden
from app.modules.db.db_model import CertificateSource, InstallationTasks
from app.modules.service import certificate_sources as sources
from tests.product.test_certificate_source_workflows import source_body

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


def test_source_form_save_edit_sync_and_mobile_layout(logged_in, product_url, product, certificate_host, monkeypatch):
    page = logged_in
    monkeypatch.setattr(CertWarden, 'fetch', lambda _: certificate_host.new)
    page.goto(product_url + '/service/certificate-sources')
    page.get_by_role('button', name='Add certificate source', exact=True).click()
    assert page.locator('#source-setting-ca_pem').evaluate('(field) => field.getBoundingClientRect().width >= field.parentElement.clientWidth * .9')
    page.locator('#source-name').fill('Public TLS')
    page.locator('#source-setting-url').fill('https://certwarden.example.test')
    page.locator('#source-setting-certificate').fill('example.test')
    page.locator('#source-setting-certificate_api_key').fill('SyntheticCertificateKey')
    page.locator('#source-setting-private_key_api_key').fill('SyntheticPrivateKey')
    assert page.locator('#source-setting-private_key_api_key').get_attribute('type') == 'password'
    page.locator('#source-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=True).click()
    page.locator('#source-pem').fill('site.pem')
    page.locator('#source-domains').fill('example.test')
    page.get_by_role('button', name='Save source', exact=True).click()
    expect(page.locator('#source-rows')).to_contain_text('Public TLS')
    page.get_by_role('button', name='Actions', exact=True).click()
    page.get_by_role('menuitem', name='Edit', exact=True).click()
    expect(page.locator('#source-setting-private_key_api_key')).to_have_value('')
    expect(page.locator('#source-setting-certificate_api_key')).to_have_value('')
    expect(page.locator('#source-setting-url')).to_have_value('https://certwarden.example.test')
    page.set_viewport_size({'width':390, 'height':844})
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    form = page.locator('#source-form')
    assert form.evaluate('(node) => node.scrollWidth <= node.clientWidth')
    for field in ('name','pem','domains','server-button','cluster-button','destination-button'):
        bounds = page.locator('#source-' + field).bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
    page.set_viewport_size({'width':1440,'height':1000})
    page.get_by_role('button', name='Cancel', exact=True).click()
    page.get_by_role('button', name='Actions', exact=True).click()
    page.get_by_role('menuitem', name='Synchronize', exact=True).click()
    page.get_by_role('dialog').get_by_role('button', name='Confirm', exact=True).click()
    expect(page.locator('#source-message')).to_contain_text('queued')
    row = CertificateSource.get()
    task = InstallationTasks.get_by_id(sources.get(row.id,1).active_task_id)
    assert sources.execute(task) == 'completed'
    page.get_by_role('button', name='Refresh', exact=True).click()
    expect(page.locator('#source-rows')).to_contain_text('current')
    assert certificate_host.files[product.server.ip].read_text() == certificate_host.new

    for secret in ('SyntheticCertificateKey','SyntheticPrivateKey','PRIVATE KEY'):
        assert secret not in page.content()
    page.get_by_role('button', name='Actions', exact=True).click()
    page.get_by_role('menuitem', name='Remove source', exact=True).click()
    page.get_by_role('dialog').get_by_role('button', name='Confirm', exact=True).click()
    expect(page.locator('#source-rows tr')).to_have_count(0)
    assert certificate_host.files[product.server.ip].read_text() == certificate_host.new


@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
def test_source_shared_layout_and_refresh_preserve_geometry(logged_in, product_url, product_client, width, theme, tmp_path):
    page = logged_in
    assert product_client.post('/service/certificate-sources/api', json=source_body()).status_code == 201
    data = product_client.get('/service/certificate-sources/api').json
    page.set_viewport_size({'width': width, 'height': 1000})
    page.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(product_url + '/service/certificate-sources')
    expect(page.locator('#source-rows')).to_contain_text('Public TLS')
    expect(page.locator('#certificate-sources')).to_have_attribute('aria-busy', 'false')
    selectors = ['#source-refresh', '#source-new', '#source-rows']
    boxes = {selector: page.locator(selector).bounding_box() for selector in selectors}
    held = []
    endpoint = product_url + '/service/certificate-sources/api'
    page.route(endpoint, lambda route: held.append(route))
    try:
        page.locator('#source-refresh').click()
        expect(page.locator('#certificate-sources')).to_have_attribute('aria-busy', 'true')
        expect(page.locator('#source-refresh')).to_be_disabled()
        expect(page.locator('#source-rows')).to_contain_text('Public TLS')
        for selector, box in boxes.items():
            assert page.locator(selector).bounding_box() == box
        page.locator('#source-refresh').dispatch_event('click')
        assert len(held) == 1
    finally:
        for route in held:
            route.fulfill(status=200, json=data)
        page.unroute(endpoint)
    expect(page.locator('#certificate-sources')).to_have_attribute('aria-busy', 'false')
    page.get_by_role('button', name='Add certificate source', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
    for field in ('name','pem','domains','server-button','cluster-button','destination-button'):
        bounds = page.locator('#source-' + field).bounding_box()
        parent = page.locator('#source-' + field).locator('..').bounding_box()
        assert bounds['width'] <= parent['width'] + 1
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    assert page.locator('#source-rows tr').first.evaluate('node => getComputedStyle(node).backgroundColor') == page.locator('#source-editor').evaluate('node => getComputedStyle(node).backgroundColor')
    page.locator('#source-name').fill('Readable text')
    page.locator('#source-interval').fill('360')
    assert page.locator('#source-name').evaluate('node => getComputedStyle(node).color') == page.locator('#source-editor').evaluate('node => getComputedStyle(node).color')
    assert page.locator('#source-interval').evaluate('node => getComputedStyle(node).color') == page.locator('#source-editor').evaluate('node => getComputedStyle(node).color')
    page.screenshot(path=str(tmp_path / f'certificate-sources-{theme}-{width}.png'), full_page=True, animations='disabled')


def test_source_initial_load_and_refresh_failures_can_be_retried(logged_in, product_url, product_client):
    page = logged_in
    assert product_client.post('/service/certificate-sources/api', json=source_body()).status_code == 201
    choices = product_url + '/service/certificate-sources/choices'
    page.route(choices, lambda route: route.fulfill(status=503, json={'error':'Synthetic choices unavailable'}))
    page.goto(product_url + '/service/certificate-sources')
    expect(page.locator('#source-message')).to_have_text('Synthetic choices unavailable')
    expect(page.locator('#source-refresh')).to_be_enabled()
    expect(page.locator('#source-new')).to_be_disabled()
    page.unroute(choices)
    page.locator('#source-refresh').click()
    expect(page.locator('#source-rows')).to_contain_text('Public TLS')
    expect(page.locator('#source-message')).to_have_text('')
    endpoint = product_url + '/service/certificate-sources/api'
    page.route(endpoint, lambda route: route.fulfill(status=503, json={'error':'Synthetic refresh unavailable'}))
    page.locator('#source-refresh').click()
    expect(page.locator('#source-message')).to_have_text('Synthetic refresh unavailable')
    expect(page.locator('#source-rows')).to_contain_text('Public TLS')
    page.unroute(endpoint)
    page.locator('#source-refresh').click()
    expect(page.locator('#source-message')).to_have_text('')


def test_orphaned_source_can_be_rebound_from_the_form(logged_in, product_url, product_client, product):
    from app.modules.db.db_model import Server
    assert product_client.post('/service/certificate-sources/api', json=source_body()).status_code == 201
    Server.get_by_id(product.server.server_id).delete_instance()
    replacement = Server.create(hostname='Replacement HAProxy', ip='192.0.2.44', group_id='1', cred_id=11, haproxy=1)
    page = logged_in
    page.goto(product_url + '/service/certificate-sources')
    expect(page.locator('#source-rows')).to_contain_text('Target registration is unavailable')
    page.get_by_role('button', name='Actions', exact=True).click()
    expect(page.get_by_role('menuitem', name='Synchronize', exact=True)).to_be_disabled()
    page.get_by_role('menuitem', name='Edit', exact=True).click()
    expect(page.locator('#source-server')).to_have_value('')
    page.locator('#source-server-button').click()
    page.get_by_role('option', name='Replacement HAProxy', exact=True).click()
    page.get_by_role('button', name='Save source', exact=True).click()
    expect(page.locator('#source-editor')).to_be_hidden()
    row = CertificateSource.get()
    assert sources.configuration(row)['server_id'] == replacement.server_id
    expect(page.locator('#source-rows')).not_to_contain_text('Target registration is unavailable')
