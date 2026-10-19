"""Real WAF log pages, routes and parsing; replace only remote log transport."""
from datetime import datetime, timezone
import os

import pytest
from playwright.sync_api import expect

from app.modules.roxywi import log_follow, log_snapshot
from app.scripts import log_reader


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('service', ['nginx', 'haproxy'])
def test_waf_log_selection_raw_search_and_live(logged_in, product_url, product, app, monkeypatch, locale, service):
    timestamp = datetime.now(timezone.utc)
    events = f'{timestamp.isoformat()} ModSecurity: event journal\n'.encode()
    boundary = '---nginx---' if service == 'nginx' else '--haproxy-'
    def audit(uri):
        stamp = timestamp.strftime('%d/%b/%Y:%H:%M:%S.%f %z' if service == 'haproxy' else '%d/%b/%Y:%H:%M:%S %z')
        version = '1.1' if service == 'haproxy' else 'HTTP/1.1'
        return (f'{boundary}A--\n[{stamp}] test\n'
                f'{boundary}B--\nGET /{uri} {version}\nHost: localhost\n'
                f'{boundary}E--\n<script>window.auditInjected = true</script>\n'
                f'{boundary}H--\nMessage: ModSecurity: denied [id "920280"]\n{boundary}Z--\n').encode()
    path = product.root / 'audit.log'
    path.write_bytes(audit('first'))
    calls = []
    def snapshot(slug, server, filename, waf, query):
        host, resolved = log_snapshot.remote_source(slug, server, filename, waf)
        calls.append((host, filename, resolved))
        assert filename == ('error.log' if slug == 'nginx' else 'waf.log')
        return log_snapshot.filter_snapshot(events, query)
    def remote(host, filename, position, limit, record_format):
        calls.append((host, 'audit.log', filename))
        assert filename == f'/var/log/{service}/waf/audit.log'
        return log_reader.read_log(str(path), position, limit, record_format)
    monkeypatch.setattr(log_snapshot, 'remote_snapshot', snapshot)
    monkeypatch.setattr(log_follow, 'remote_read', remote)
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.log_viewer
    response = page.goto(product_url + f'/logs/{service}/waf?serv=192.0.2.11&grep=ModSecurity&file=' + ('error.log' if service == 'nginx' else 'waf.log'))
    assert response.status == 200
    expect(page.locator('#log-output .log-row')).to_have_count(1)
    expect(page.locator('.log-message')).to_contain_text('event journal')
    expect(page.locator('#log_files option')).to_have_text([labels['waf_events'], labels['waf_audit']])
    with page.expect_response(lambda r: '/logs/query/' in r.url) as request:
        page.locator('#log_files').select_option('audit.log')
    assert request.value.status == 200
    expect(page.locator('.log-message')).to_contain_text('GET /first')
    expect(page.locator('.log-message')).not_to_contain_text('<script>')
    page.locator('.log-row summary').click()
    expect(page.locator('.log-raw')).to_contain_text('<script>window.auditInjected = true</script>')
    assert page.evaluate('window.auditInjected') is None
    page.locator('#log-search').fill('not present')
    page.locator('#log-refresh').click()
    expect(page.locator('#log-empty')).to_be_visible()
    page.locator('#log-search').fill('')
    page.locator('#log-live').click()
    expect(page.locator('#log-live')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.log-row')).to_have_count(1)
    with path.open('ab') as stream:
        stream.write(audit('live-append'))
    expect(page.locator('.log-row')).to_have_count(2)
    expect(page.locator('.log-message').last).to_contain_text('/live-append')
    page.locator('#log_files').select_option('error.log' if service == 'nginx' else 'waf.log')
    expect(page.locator('#log-live')).to_have_attribute('aria-pressed', 'false')
    expect(page.locator('.log-row')).to_have_count(1)
    expect(page.locator('.log-message')).to_contain_text('event journal')
    assert all(host == '192.0.2.11' for host, _, _ in calls)
