"""Real pages and requests. External SSH/ACME are covered separately by integration tests."""
import importlib
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import BackupSchedule, LetsEncrypt, S3Backup, Server


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


def selectmenu(page, selector, label):
    page.locator(selector + '-button').click()
    page.locator(selector + '-menu').get_by_role('option', name=label, exact=True).click()


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_overview_logs_match_other_tiles(logged_in, product_url, product, host_metrics, locale):
    journal = product.root / 'journal'
    journal.mkdir()
    timestamp = datetime.now(timezone.utc).isoformat()
    (journal / 'rwi-product.log').write_text(''.join(
        json.dumps(dict(timestamp=timestamp, message=f'Event {index}: configuration updated',
                        level='INFO', process_role='service-events')) + '\n'
        for index in range(6)
    ), encoding='utf-8')
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    # Server status is unrelated to the tile layout; synthetic hosts have no SSH listener.
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    assert page.goto(product_url + '/overview').status == 200
    tile = page.locator('#overview-logs')
    expect(tile.locator('.log-row:visible')).to_have_count(3)
    for width in (1440, 1000):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert abs(tile.bounding_box()['width'] - page.locator('#overview-roles').bounding_box()['width']) <= 1
        assert tile.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
    page.locator('#overview-log-expand').click()
    expect(tile.locator('.log-row:visible')).to_have_count(6)
    tile.locator('.log-row summary').first.click()
    expect(tile.locator('.log-detail').first).to_be_visible()
    page.locator('#overview-log-expand').click()
    expect(tile.locator('.log-row:visible')).to_have_count(3)
    page.set_viewport_size({'width': 390, 'height': 1000})
    assert tile.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')


def backup_tab(page, url):
    response = page.goto(url + '/admin')
    assert response.status == 200, response.text()
    page.locator('#admin-tabs-backup').click()
    page.locator('#backup-backup-li').click()
    expect(page.locator('#ajax-backup-s3-table')).to_be_visible()


def test_login_and_empty_service_list(page, product_url, product):
    Server.delete().execute()
    page.goto(product_url + '/login?next=/admin')
    page.locator('#login').fill('admin')
    page.locator('#pass').fill('TestBootstrapPassword!')
    page.locator('#enter').click()
    expect(page).to_have_url(product_url + '/admin')
    expect(page.locator('#admin-tabs')).to_be_visible()
    assert page.goto(product_url + '/logs/haproxy').status == 200
    expect(page.locator('#serv option:not([disabled])')).to_have_count(0)
    expect(page.locator('#log-output .log-row')).to_have_count(0)
    expect(page.locator('.toast-error')).to_have_count(0)


def test_backup_tab_renders_legacy_configuration_outside_error_toast(logged_in, product_url, product, monkeypatch):
    # Filesystem/S3 backups must remain accessible without the optional Git tool.
    monkeypatch.setattr('app.routes.server.routes.common.is_tool', lambda _name: False)
    row = S3Backup.create(server_id='11', s3_server='https://s3.example.test', bucket='old-backup',
                          access_key='synthetic-access', secret_key='synthetic-secret', time='weekly',
                          description='error: old description <b>must remain text</b>')
    migration = importlib.import_module('app.modules.db.migrations.20260916000000_backup_schedules')
    migration.up()
    backup_tab(logged_in, product_url)
    entry = logged_in.locator(f'#s3-backup-table-{row.id}')
    expect(entry).to_contain_text('old-backup')
    expect(entry).to_contain_text('Waiting for schedule migration')
    expect(entry).to_contain_text('<b>must remain text</b>')
    expect(entry.locator('b')).to_have_count(0)
    expect(logged_in.locator('.toast-error')).to_have_count(0)
    assert BackupSchedule.get().legacy_pending


def test_create_backup_and_refresh_preserves_row_and_next_run(logged_in, product_url, product):
    page = logged_in
    backup_tab(page, product_url)
    page.locator('#add-backup-s3-button').click()
    selectmenu(page, '#s3-backup-server', 'Product HAProxy')
    page.locator('#s3_server').fill('https://s3.example.test')
    page.locator('#s3_bucket').fill('ui-backup')
    page.locator('#s3_access_key').fill('synthetic-access')
    page.locator('#s3_secret_key').fill('synthetic-secret')
    page.locator('#s3-backup-description').fill('Nightly backup')
    with page.expect_response(lambda response: response.url.endswith('/server/backup/s3') and response.request.method == 'POST') as request:
        page.get_by_role('dialog').get_by_role('button', name='Add', exact=True).click()
    assert request.value.status == 202, request.value.text()
    row = S3Backup.get()
    expect(page.locator(f'#s3-backup-table-{row.id}')).to_contain_text('ui-backup')
    assert BackupSchedule.get().next_run_at
    backup_tab(page, product_url)
    expect(page.locator(f'#s3-backup-table-{row.id}')).to_contain_text('ui-backup')
    expect(page.locator('.toast-error')).to_have_count(0)
    assert S3Backup.select().count() == BackupSchedule.select().count() == 1


def test_create_certificate_draft_and_refresh(logged_in, product_url, product):
    page = logged_in
    response = page.goto(product_url + '/service/haproxy/ssl')
    assert response.status == 200, response.text()
    page.locator('.add-button', has_text='Create').click()
    selectmenu(page, '#new-le-server_id', 'Product HAProxy')
    page.locator('#new-le-domain').fill('Example.COM, example.com')
    page.locator('#new-le-email').fill('admin@example.com')
    page.locator('#new-le-description').fill('Production certificate')
    with page.expect_response(lambda response: response.url.endswith('/service/letsencrypt') and response.request.method == 'POST') as request:
        page.get_by_role('dialog').get_by_role('button', name='Save draft', exact=True).click()
    assert request.value.status == 201, request.value.text()
    row = LetsEncrypt.get()
    expect(page.locator(f'#lets-{row.id}')).to_contain_text('draft')
    page.reload()
    entry = page.locator(f'#lets-{row.id}')
    expect(entry).to_contain_text('example.com')
    expect(entry).to_contain_text('Production certificate')
    entry.locator('.admin-actions-toggle').click()
    expect(entry.get_by_role('button', name='Issue certificate', exact=True)).to_be_disabled()
    expect(entry.get_by_role('button', name='Check setup (staging)', exact=True)).to_be_enabled()
    page.keyboard.press('Escape')
    expect(entry.locator('.admin-actions-menu')).to_be_hidden()
    expect(page.locator('.toast-error')).to_have_count(0)
    assert LetsEncrypt.select().count() == 1


def test_time_range_change_and_invalid_dates_preserve_visible_logs(logged_in, product_url, product):
    journal = product.root / 'journal'
    journal.mkdir()
    now = datetime.now(timezone.utc)
    records = [dict(timestamp=stamp.isoformat(), message=message) for stamp, message in (
        (now - timedelta(hours=2), 'Older event'), (now, 'Recent event'))]
    (journal / 'rwi-product.log').write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    page = logged_in
    assert page.goto(product_url + '/logs/internal').status == 200
    expect(page.locator('#log-output .log-row')).to_have_count(1)
    page.locator('#log-time-picker summary').click()
    page.locator('[data-log-relative="86400"]').click()
    expect(page.locator('#log-output .log-row')).to_have_count(2)
    page.locator('#log-time-picker summary').click()
    page.locator('#log-timezone').select_option('UTC')
    page.locator('#log-from-date').fill('2026-09-25')
    page.locator('#log-from-time').fill('12:00:00')
    page.locator('#log-to-date').fill('2026-09-24')
    page.locator('#log-to-time').fill('12:00:00')
    page.locator('#log-apply-time').click()
    expect(page.locator('#log-status')).to_contain_text('From before To')
    expect(page.locator('#log-output .log-row')).to_have_count(2)


def test_large_log_result_is_bounded_and_can_be_filtered(logged_in, product_url, product):
    journal = product.root / 'journal'
    journal.mkdir()
    timestamp = datetime.now(timezone.utc).isoformat()
    records = [dict(timestamp=timestamp, message=f'Event {number:04d} ' + 'long message ' * 3) for number in range(1100)]
    (journal / 'rwi-product.log').write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    page = logged_in
    assert page.goto(product_url + '/logs/internal').status == 200
    expect(page.locator('#log-output .log-row')).to_have_count(100)
    page.locator('#log-filters summary').click()
    page.locator('#log-limit').fill('1000')
    page.locator('#log-apply-filters').click()
    expect(page.locator('#log-output .log-row')).to_have_count(1000)
    page.locator('#log-search').fill('Event 1099')
    page.locator('#log-refresh').click()
    expect(page.locator('#log-output .log-row')).to_have_count(1)
    expect(page.locator('#log-output mark')).to_have_text('Event 1099')


def test_logs_parse_json_and_legacy_lines_highlight_search_and_show_empty_result(logged_in, product_url, product):
    journal = product.root / 'journal'
    journal.mkdir()
    timestamp = datetime.now(timezone.utc).isoformat()
    (journal / 'rwi-product.log').write_text(
        json.dumps(dict(timestamp=timestamp, message='needle structured event', level='ERROR', process_role='web')) + '\n'
        + f'{timestamp} needle legacy event\n', encoding='utf-8')
    page = logged_in
    response = page.goto(product_url + '/logs/internal')
    assert response.status == 200, response.text()
    expect(page.locator('#log-output .log-row')).to_have_count(2)
    expect(page.locator('#log-output .log-message').first).not_to_contain_text('"timestamp"')
    page.locator('#log-search').fill('needle')
    page.locator('#log-refresh').click()
    expect(page.locator('#log-output mark')).to_have_count(2)
    page.locator('#log-search').fill('no matching records')
    page.locator('#log-refresh').click()
    expect(page.locator('#log-empty')).to_be_visible()
    expect(page.locator('#log-output .log-row')).to_have_count(0)
    expect(page.locator('.toast-error')).to_have_count(0)
