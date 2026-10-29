"""Evidence appears inside the existing certificate screens, without a monitor UI."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.connectors.certificates import CertWarden
from app.modules.db.db_model import InstallationTasks
from app.modules.service import certificate_sources as sources
from tests.product.test_runtime_certificates import update_body, run
from tests.product.test_certificate_source_workflows import source_body

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


@pytest.mark.parametrize('locale', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_certificate_history_contains_deployment_evidence(logged_in, product_url, product_client,
        product, certificate_host, app, locale):
    queued = product_client.post('/service/haproxy/certificates/11', json=update_body(certificate_host, product.server))
    assert run(queued.json['id']) == 'completed'
    page = logged_in
    page.context.add_cookies([{'name':'lang', 'value':locale, 'url':product_url}])
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    page.locator('#cert-history').click()
    evidence = page.locator('#cert-operations [data-certificate-verification="verified"]')
    expect(evidence).to_be_visible()
    labels = app.jinja_env.get_template('languages/' + locale + '.html').module.certificate_verification
    expect(evidence.locator('summary')).to_contain_text(labels['verified'])
    evidence.locator('summary').click()
    expect(evidence).to_contain_text('SHA-256')
    expect(evidence).to_contain_text('example.test')
    page.set_viewport_size({'width':390, 'height':844})
    assert evidence.evaluate('(element) => element.scrollWidth <= element.clientWidth')
    assert not page.locator('a[href="/insights/tls"]').count()


@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
def test_provider_status_reports_mismatch_in_existing_source_row(logged_in, product_url, product_client,
        product, certificate_host, monkeypatch, width, theme):
    monkeypatch.setattr(CertWarden, 'fetch', lambda _: certificate_host.new)
    certificate_host.served_overrides[11] = dict(tcp='connected', tls='verified', fingerprint='f'*64)
    api = '/service/certificate-sources/api'
    ident = product_client.post(api, json=source_body()).json['data']['id']
    task = product_client.post(f'{api}/{ident}/sync', json={}).json['task_id']
    assert sources.execute(InstallationTasks.get_by_id(task)) == 'completed'
    page = logged_in
    page.set_viewport_size({'width':width, 'height':1000})
    page.add_init_script(f"localStorage.setItem('theme','{theme}')")
    page.goto(product_url + '/service/certificate-sources')
    evidence = page.locator('#source-rows [data-certificate-verification="mismatch"]')
    expect(evidence).to_be_visible()
    evidence.locator('summary').click()
    expect(evidence).to_contain_text('f'*64)
    expect(page.locator('#source-rows')).to_contain_text('current')
    assert evidence.evaluate('(element) => element.scrollWidth <= element.clientWidth')
    assert 'PRIVATE KEY' not in page.content()
