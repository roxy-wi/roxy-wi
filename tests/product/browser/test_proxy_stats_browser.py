"""Exercise the actual Stats page with deterministic remote snapshots."""

import os
from datetime import timedelta

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server, UserGroups
from tests.fixtures.proxy_stats import APACHE_BASIC, status_host  # noqa: F401


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def open_stats(page, product_url, service):
    page.goto(f'{product_url}/stats/{service}/192.0.2.11')
    expect(page.locator('#ps-data')).to_be_visible()
    assert page.locator('#ps-interval').input_value() == '30'
    page.locator('#ps-interval-button').click()
    page.get_by_role('option', name='Paused', exact=True).click()


def refresh(page):
    with page.expect_response(lambda r: '/stats/view/' in r.url):
        page.locator('#ps-refresh').click()
    expect(page.locator('#ps-refresh')).to_be_enabled()


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_snapshots_rates_errors_reset_and_layout(logged_in, product_url, status_host, service, tmp_path):
    page = logged_in
    open_stats(page, product_url, service)
    rate = page.locator('[data-metric=rps] strong')
    expect(rate).to_have_text('—')
    assert page.locator('.hs-card-label').first.get_attribute('title')
    expected = (['active', 'connection_rate', 'rps', 'gap'] if service == 'nginx' else
                ['version', 'uptime', 'connections', 'rps', 'bps'])
    assert page.locator('#ps-summary .hs-card').evaluate_all(
        'cards => cards.map(card => card.dataset.metric)',
    ) == expected
    labels = page.locator('#ps-summary .hs-card-label').all_text_contents()
    assert not set(labels) & set(page.locator('#ps-details dt').all_text_contents())
    expect(page.locator('#proxy-stats .admin-actions-toggle')).to_have_count(0)
    if service == 'apache':
        expect(page.locator('[data-metric=version] strong')).to_have_text('2.4.62')
        expect(page.locator('[data-metric=connections] strong')).to_have_text('5')
    else:
        expect(page.locator('[data-metric=connection_rate] strong')).to_have_text('—')
    # Keep the same summary elements during polling, as on HAProxy Stats.
    page.evaluate("window.statsCard = document.querySelector('[data-metric=rps]')")
    ids = page.evaluate('Object.keys(Chart.instances)')
    status_host.now += timedelta(seconds=30)
    status_host.content[service] = status_host.content[service].replace(b'20', b'80')
    if service == 'nginx':
        status_host.content[service] = status_host.content[service].replace(b'10 9 80', b'70 67 80')
    refresh(page)
    expect(rate).to_have_text('2')
    assert page.evaluate("window.statsCard === document.querySelector('[data-metric=rps]')")
    if service == 'nginx':
        expect(page.locator('[data-metric=connection_rate] strong')).to_have_text('2')
        expect(page.locator('[data-metric=gap] strong')).to_have_text('2')
    assert page.evaluate('Object.keys(Chart.instances)') == ids
    assert page.evaluate("Chart.getChart('ps-requests-chart').data.datasets[0].data") == [None, 2]
    status_host.status = 403
    refresh(page)
    expect(page.locator('#ps-error')).to_contain_text('access denied')
    expect(page.locator('#ps-status')).to_contain_text('stale')
    expect(rate).to_have_text('2')
    status_host.status = 200
    status_host.now += timedelta(seconds=30)
    refresh(page)
    expect(rate).to_have_text('—')
    expect(page.locator('#ps-error')).to_be_hidden()
    status_host.content[service] = status_host.content[service].replace(b'80', b'1')
    status_host.now += timedelta(seconds=30)
    refresh(page)
    expect(page.locator('#ps-note')).to_contain_text('Counters reset')
    expect(rate).to_have_text('—')
    if service == 'nginx':
        expect(page.locator('[data-metric=connection_rate] strong')).to_have_text('—')
    if service == 'apache':
        expect(page.locator('#ps-scoreboard-legend')).to_contain_text('Sending response: 1')
    page.locator('#proxy-stats').screenshot(path=str(tmp_path / f'{service}-stats.png'))
    page.set_viewport_size({'width': 650, 'height': 900})
    page.wait_for_function('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / f'{service}-mobile.png'), full_page=True)
    overflow = page.evaluate('''() => [...document.querySelectorAll('body *')]
        .filter(el => el.getBoundingClientRect().right > innerWidth + 1)
        .slice(0, 12).map(el => [el.tagName, el.id, el.className, el.getBoundingClientRect().right])''')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), overflow


def test_apache_basic_keeps_unavailable_summary_values(logged_in, product_url, status_host):
    status_host.content['apache'] = APACHE_BASIC
    page = logged_in
    open_stats(page, product_url, 'apache')
    expect(page.locator('#ps-note')).to_contain_text('ExtendedStatus')
    expect(page.locator('[data-metric=bps] strong')).to_have_text('—')
    expect(page.locator('[data-metric=version] strong')).to_have_text('—')
    expect(page.locator('[data-metric=uptime] strong')).to_have_text('—')
    expect(page.locator('[data-metric=connections] strong')).to_have_text('—')
    expect(page.locator('#ps-scoreboard-legend')).to_contain_text('Waiting for connection: 2')


def test_late_response_cannot_restore_previous_server(logged_in, product_url, product, status_host):
    Server.create(server_id=33, hostname='Second NGINX', ip='192.0.2.33', group_id='1',
                  cred_id=11, nginx=1)
    page = logged_in
    open_stats(page, product_url, 'nginx')
    # Deliberately ignore AbortSignal to exercise the generation guard as well.
    page.evaluate('''() => {
        window.pendingStats = [];
        window.fetch = url => new Promise(resolve => pendingStats.push({url, resolve}));
    }''')
    page.locator('#ps-refresh').click()
    page.locator('#serv-button').click()
    page.get_by_role('option', name='Second NGINX', exact=True).click()
    page.wait_for_function('pendingStats.length === 2')
    page.evaluate('''() => {
        const reply = requests => ({ok: true, status: 200, json: async () => ({status: 'ok', service: 'nginx',
            observed_at: '2026-11-04T12:01:00Z', counters: {active: requests, accepts: 10, handled: 9,
            requests, reading: 0, writing: 1, waiting: 2}})});
        pendingStats[1].resolve(reply(33));
        pendingStats[0].resolve(reply(999));
    }''')
    expect(page.locator('[data-metric=active] strong')).to_have_text('33')
    expect(page.locator('[data-metric=rps] strong')).to_have_text('—')
    assert page.evaluate("Chart.getChart('ps-requests-chart').data.labels.length") == 1
    expect(page).to_have_url(product_url + '/stats/nginx/192.0.2.33')


def test_default_polling_and_pause(logged_in, product_url, status_host):
    page = logged_in
    page.clock.install()
    page.goto(product_url + '/stats/nginx/192.0.2.11')
    expect(page.locator('#ps-data')).to_be_visible()
    expect(page.locator('#ps-refresh')).to_be_enabled()
    status_host.now += timedelta(seconds=30)
    status_host.content['nginx'] = status_host.content['nginx'].replace(b'20', b'80')
    with page.expect_response(lambda response: '/stats/view/' in response.url):
        page.clock.fast_forward(30001)
    expect(page.locator('[data-metric=rps] strong')).to_have_text('2')
    page.locator('#ps-interval-button').click()
    page.get_by_role('option', name='Paused', exact=True).click()
    count = len(status_host.calls)
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.clock.fast_forward(60000)
    assert len(status_host.calls) == count


def test_no_selection_does_not_poll(logged_in, product_url, status_host):
    page = logged_in
    page.clock.install()
    page.goto(product_url + '/stats/nginx/')
    expect(page.locator('#ps-refresh')).to_be_disabled()
    page.locator('#ps-interval-button').click()
    page.get_by_role('option', name='5 sec', exact=True).click()
    page.clock.fast_forward(6000)
    assert status_host.calls == []
    expect(page.locator('#ps-error')).to_be_hidden()


def test_reader_can_refresh_without_config_action(logged_in, product_url, product, status_host):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = logged_in
    open_stats(page, product_url, 'nginx')
    refresh(page)
    expect(page.locator('#ps-config')).to_have_count(0)
    expect(page.locator('#ps-error')).to_be_hidden()
