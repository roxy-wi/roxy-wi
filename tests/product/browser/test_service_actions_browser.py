"""Start/Stop follow polled state on service lists and individual server pages."""
import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache', 'keepalived'])
@pytest.mark.parametrize('detail', [False, True], ids=['overview', 'detail'])
def test_start_stop_follow_status_and_recover_after_missing_poll(
    logged_in, product_url, product, service_worker_controls, host_metrics, monkeypatch, app, service, detail,
):
    setattr(product.server, service, 1)
    product.server.save()
    if not detail:
        Server.create(server_id=33, hostname='Secondary service server', ip='192.0.2.33', group_id='1',
                      cred_id=11, **{service: 1})
    # The Keepalived page also reads its VRRP state through SSH.
    monkeypatch.setattr('app.routes.service.routes.server_mod.ssh_command', lambda *args, **kwargs: '')
    page = logged_in
    page.set_viewport_size({'width': 2160, 'height': 1000})
    page.clock.install()
    state = {'status': 'running'}
    server_id = product.server.server_id

    def status_response(route):
        result = {'server_id': server_id, 'status': state['status']}
        route.fulfill(json={'data': [] if state['status'] == 'missing' else [result]})

    page.route('**/service/*/statuses', status_response)
    page.route('**/service/*/*/status', lambda route: route.fulfill(json={
        'server_id': server_id, 'status': state['status'],
    }))
    page.route('**/service/*/*/last-edit', lambda route: route.fulfill(body=''))
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/service/*/*/backend', lambda route: route.fulfill(json={'data': ''}))
    for path in ('bytes', 'connections', 'become-master'):
        page.route(f'**/service/*/{path}/*', lambda route: route.fulfill(body=''))
    url = product_url + '/service/' + service + ('/' + product.server.ip if detail else '')
    response = page.goto(url)
    assert response.status == 200
    card = page.locator('#div-server-' + str(server_id))
    expect(card).to_be_visible()
    assert card.bounding_box()['width'] <= 500
    if not detail:
        search = page.locator('#service-server-search')
        search.fill('no matching server')
        expect(card).to_be_hidden()
        search.fill(product.server.ip)
        expect(card).to_be_visible()
        search.fill('')
        expect(page.locator('#service-status-filter')).to_be_enabled()
        page.locator('#service-status-filter-button').click()
        page.get_by_role('option', name='Stopped', exact=True).click()
        expect(card).to_be_hidden()
        page.locator('#service-status-filter-button').click()
        page.get_by_role('option', name='All', exact=True).click()
        expect(card).to_be_visible()
    start = card.locator('[data-action="start"]')
    stop = card.locator('[data-action="stop"]')
    dialog = page.locator('.ui-dialog').filter(has=page.locator('#dialog-confirm'))
    messages = app.jinja_env.get_template('languages/en.html').module
    for current in ('running', 'stopped', 'running', 'unavailable', 'stopped', 'missing'):
        if state['status'] != current:
            state['status'] = current
            with page.expect_response(lambda response: response.url.endswith('/statuses')):
                page.clock.fast_forward(11000)
        expect(card).to_have_attribute('data-service-status', 'stale' if current == 'missing' else current)
        expect(start).to_be_disabled() if current == 'running' else expect(start).to_be_enabled()
        expect(stop).to_be_disabled() if current == 'stopped' else expect(stop).to_be_enabled()
        if current not in ('running', 'stopped'):
            continue
        enabled_action = 'stop' if current == 'running' else 'start'
        if detail:
            # Keyboard shortcuts must use the same availability and server ID as the menu.
            page.locator('body').click(position={'x': 1, 'y': 1})
            page.keyboard.press('a' if current == 'running' else 's')
            expect(dialog).not_to_be_visible()
            page.keyboard.press('s' if current == 'running' else 'a')
        else:
            card.locator('.service-actions-toggle').click()
            card.locator('[data-action="' + enabled_action + '"]').click()
        expect(dialog).to_be_visible()
        expect(dialog.locator('.ui-dialog-title')).to_have_text(
            messages.words[enabled_action].title() + ' ' + product.server.hostname + '?')
        dialog.get_by_role('button', name=messages.words['cancel'].title(), exact=True).click()
