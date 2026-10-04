from datetime import timedelta
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.common.time import utc_now
from app.modules.db.db_model import ServiceAssignment, WorkerState


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


@pytest.fixture
def diagnostic_worker(product, monkeypatch):
    monkeypatch.setattr('app.modules.tools.common.update_cur_tool_versions', lambda: None)
    monkeypatch.setattr('app.modules.tools.common.is_tool_active', lambda _tool: 'active')
    now = utc_now()
    ServiceAssignment.create(assignment_id='metrics:nginx:server-11', target_service='metrics',
                             server_id=11, service='nginx', user_group=1, payload='{}')
    return WorkerState.create(worker_id='metrics-ui', service='metrics', hostname='worker-ui',
                              status='degraded', last_heartbeat=now, expires_at=now + timedelta(minutes=5),
                              metadata={'assignment_errors': {'metrics:nginx:server-11': 'Connection refused'}})


@pytest.mark.parametrize('locale,title', [
    ('en', 'Service diagnostics'), ('ru', 'Диагностика сервиса'),
    ('es-ES', 'Diagnóstico del servicio'), ('fr', 'Diagnostic du service'),
    ('pt-br', 'Diagnóstico do serviço'), ('zh', '服务诊断'),
])
def test_status_opens_localized_diagnostics_and_refreshes(logged_in, product_url, diagnostic_worker, locale, title):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/admin#tools')
    trigger = page.locator('#roxy-wi-metrics .admin-tool-status-cell button')
    expect(trigger).to_be_visible()
    trigger.focus()
    page.keyboard.press('Enter')
    dialog = page.get_by_role('dialog', name=title + ': Metrics', exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.locator('.sd-worker')).to_have_attribute('data-worker-status', 'degraded')
    expect(dialog).to_contain_text('Product HAProxy')
    dialog.locator('summary').click()
    expect(dialog.locator('pre')).to_have_text('Connection refused')
    WorkerState.update(status='running', metadata={}).where(WorkerState.worker_id == diagnostic_worker.worker_id).execute()
    dialog.locator('.sd-refresh').click()
    expect(dialog.locator('.sd-worker')).to_have_attribute('data-worker-status', 'running')
    expect(dialog.locator('.sd-issue')).to_have_count(0)
    page.set_viewport_size({'width': 390, 'height': 800})
    assert dialog.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    page.keyboard.press('Escape')
    expect(dialog).to_be_hidden()
    expect(trigger).to_be_focused()


def test_overview_status_and_stale_count_open_diagnostics(logged_in, product_url, diagnostic_worker):
    page = logged_in
    # Only unrelated external requests are stubbed; status and diagnostics use real routes.
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/metrics/*', lambda route: route.fulfill(status=503, json={'error': 'Synthetic host metrics unavailable'}))
    now = utc_now()
    WorkerState.create(worker_id='metrics-old', service='metrics', hostname='worker-ui', status='running',
                       last_heartbeat=now - timedelta(days=2), expires_at=now - timedelta(days=2))
    page.goto(product_url + '/overview')
    trigger = page.locator('.services-overview-name button[data-service-name="Metrics"]')
    trigger.click()
    dialog = page.get_by_role('dialog', name='Service diagnostics: Metrics', exact=True)
    expect(dialog.locator('.sd-worker')).to_have_count(2)
    expect(dialog).to_contain_text('This may be a replaced worker')
    page.keyboard.press('Escape')
    page.locator('.services-overview-meta button[data-service-name="Metrics"]').click()
    expect(dialog).to_be_visible()
    page.route('**/admin/tools/roxy-wi-metrics/diagnostics', lambda route: route.fulfill(status=503, body='unavailable'))
    dialog.locator('.sd-refresh').click()
    expect(dialog).to_contain_text('Could not load diagnostics')
    page.unroute('**/admin/tools/roxy-wi-metrics/diagnostics')
    dialog.locator('.sd-refresh').click()
    expect(dialog.locator('.sd-worker')).to_have_count(2)


@pytest.mark.parametrize('source', ['/admin#tools', '/overview'])
def test_diagnostic_server_settings_navigate_to_exact_server(logged_in, product_url, diagnostic_worker, source):
    page = logged_in
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/metrics/*', lambda route: route.fulfill(status=503, json={'error': 'Synthetic host metrics unavailable'}))
    page.goto(product_url + source)
    trigger = page.locator('button[data-service-name="Metrics"]').first
    trigger.click()
    dialog = page.get_by_role('dialog', name='Service diagnostics: Metrics', exact=True)
    dialog.get_by_role('link', name='Server settings', exact=True).click()
    expect(page).to_have_url(product_url + '/admin?server_id=11#servers')
    expect(dialog).to_be_hidden()
    expect(page.locator('#servers')).to_be_visible()
    expect(page.locator('#server-11.admin-server-target')).to_be_visible()
    expect(page.locator('#hostname-11')).to_be_focused()
    # The deep link also works after reload and when followed a second time
    # from Tools, with server_id already present in the current URL.
    page.reload()
    expect(page.locator('#hostname-11')).to_be_focused()
    page.locator('#admin-tabs a[href="#tools"]').click()
    page.reload()
    page.locator('button[data-service-name="Metrics"]').first.click()
    dialog.get_by_role('link', name='Server settings', exact=True).click()
    expect(page.locator('#hostname-11')).to_be_focused()
    expect(dialog).to_be_hidden()


def test_diagnostic_manage_services_link_closes_dialog(logged_in, product_url, diagnostic_worker):
    page = logged_in
    page.goto(product_url + '/admin#tools')
    page.locator('button[data-service-name="Metrics"]').first.click()
    dialog = page.get_by_role('dialog', name='Service diagnostics: Metrics', exact=True)
    dialog.get_by_role('link', name='Manage services', exact=True).click()
    expect(dialog).to_be_hidden()
    expect(page.locator('#tools')).to_be_visible()
    expect(page.locator('#admin-tabs a[href="#tools"]')).to_be_focused()


def test_change_timeline_icons_stay_inside_scroll_area(page):
    root = Path(__file__).resolve().parents[3]
    page.set_viewport_size({'width': 460, 'height': 600})
    page.set_content('<div class="change-timeline">' + ''.join(
        '<div class="change-timeline-item"><span class="change-timeline-icon">!</span>'
        '<div class="change-timeline-content"><strong>Configuration drift check failed on a target</strong>'
        '<span>drift.check_failed</span><time>30 days ago</time></div></div>' for _ in range(20)
    ) + '</div>')
    page.add_style_tag(path=str(root / 'app/static/css/change-center.css'))
    timeline = page.locator('.change-timeline')
    for scroll_to in (0, 100000):
        timeline.evaluate('(node, top) => { node.scrollTop = top; }', scroll_to)
        assert timeline.evaluate('''node => {
            const bounds = node.getBoundingClientRect();
            return [...node.querySelectorAll('.change-timeline-icon')].every(icon => {
                const box = icon.getBoundingClientRect();
                const text = icon.nextElementSibling.getBoundingClientRect();
                return box.left >= bounds.left && box.right <= bounds.right && box.right <= text.left;
            }) && node.scrollWidth <= node.clientWidth;
        }''')
