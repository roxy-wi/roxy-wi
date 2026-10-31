import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


def choose(page, field, value, label):
    locator = page.locator('#audit-receiver-'+field)
    if locator.is_visible():
        locator.select_option(value)
    else:
        page.locator('#audit-receiver-'+field+'-button').click()
        page.locator('#audit-receiver-'+field+'-menu').get_by_role('option', name=label, exact=True).click()


def test_receiver_create_edit_and_safe_connection_check(logged_in, product_url, monkeypatch):
    monkeypatch.setattr('app.routes.admin.audit_routes.check_connection',
                        lambda value: {'status': 'connected', 'detail': 'Connection checked'})
    page = logged_in
    page.goto(product_url+'/admin/audit')
    page.get_by_role('button', name='New audit receiver', exact=True).click()
    form = page.locator('#audit-receiver-form')
    expect(form).to_be_visible()
    expect(form.locator('#audit-profile-select')).not_to_be_visible()
    form.get_by_label('Name', exact=True).fill('Central security audit')
    choose(page, 'transport', 'https', 'HTTPS')
    form.get_by_label('HTTPS receiver URL', exact=True).fill('https://audit.example.test/events')
    choose(page, 'auth', 'bearer', 'Bearer')
    form.get_by_label('Token or API key', exact=True).fill('SyntheticBrowserToken!')
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Audit receiver saved.')
    row = page.locator('#audit-receiver-table tr').filter(has_text='Central security audit')
    expect(row).to_have_count(1)
    row.get_by_role('button', name='Edit', exact=True).click()
    expect(form.get_by_label('Token or API key', exact=True)).to_have_value('')
    expect(page.locator('#audit-receiver-queue')).to_contain_text('Waiting')
    expect(form.locator('[data-configured="token"]')).to_have_text('Configured')
    form.get_by_label('Name', exact=True).fill('Updated security audit')
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Audit receiver saved.')
    row = page.locator('#audit-receiver-table tr').filter(has_text='Updated security audit')
    expect(row).to_have_count(1)
    row.get_by_role('button', name='Test connection', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Connection checked')
    expect(page.locator('body')).not_to_contain_text('SyntheticBrowserToken!')
    assert 'SyntheticBrowserToken!' not in page.request.get(product_url+'/admin/audit-receivers').text()
    def confirm_requeue(dialog):
        assert 'pending and failed' in dialog.message and 'CURRENT' in dialog.message
        assert 'duplicated' in dialog.message
        dialog.accept()
    page.once('dialog', confirm_requeue)
    with page.expect_request(lambda request: request.url.endswith('/retry') and request.method == 'POST') as requeue:
        row.get_by_role('button', name='Requeue undelivered', exact=True).click()
    assert requeue.value.post_data_json == {'revision': 2, 'include_pending': True}
    expect(page.locator('#audit-receiver-status')).to_contain_text('Requeued:')
    capture = os.environ.get('ROXYWI_CAPTURE_AUDIT_SCREENSHOTS')
    if capture:
        folder = Path(capture)
        folder.mkdir(parents=True, exist_ok=True)
        row.get_by_role('button', name='Edit', exact=True).click()
        expect(form.get_by_label('Token or API key', exact=True)).to_have_value('')
        expect(page.locator('#nprogress')).to_have_count(0)
        page.screenshot(path=str(folder/'external-audit-light.png'))
        page.evaluate("changeTheme('dark')")
        page.wait_for_timeout(300)
        page.screenshot(path=str(folder/'external-audit-dark.png'))


def test_receiver_name_is_text_and_defaults_to_tls(logged_in, product_url):
    page = logged_in
    page.goto(product_url+'/admin/audit')
    page.get_by_role('button', name='New audit receiver', exact=True).click()
    form = page.locator('#audit-receiver-form')
    expect(form.locator('[name="transport"]')).to_have_value('tcp_tls')
    expect(form.get_by_label('Port', exact=True)).to_have_value('6514')
    name = '<img src=x onerror=alert(1)>'
    form.get_by_label('Name', exact=True).fill(name)
    form.get_by_label('Host', exact=True).fill('audit.example.test')
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Audit receiver saved.')
    expect(page.locator('#audit-receiver-table')).to_contain_text(name)
    expect(page.locator('#audit-receiver-table img')).to_have_count(0)


def test_disabled_receiver_delete_preserves_pending_work_then_allows_safe_cleanup(logged_in, product_url, product):
    from app.modules.db.db_model import AuditDelivery, AuditDestination, AuditEvent
    page = logged_in
    page.goto(product_url+'/admin/audit')
    page.get_by_role('button', name='New audit receiver', exact=True).click()
    form = page.locator('#audit-receiver-form')
    form.get_by_label('Name', exact=True).fill('Retired audit receiver')
    form.get_by_label('Host', exact=True).fill('retired.example.test')
    form.get_by_role('button', name='Save', exact=True).click()
    row = page.locator('#audit-receiver-table tr').filter(has_text='Retired audit receiver')
    expect(row.get_by_role('button', name='Delete', exact=True)).to_have_count(0)
    row.get_by_role('button', name='Edit', exact=True).click()
    form.locator('[name="enabled"]').uncheck(force=True)
    form.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Audit receiver saved.')
    def confirm(dialog):
        assert 'Audit event history is retained' in dialog.message
        dialog.accept()
    page.on('dialog', confirm)
    row.get_by_role('button', name='Delete', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_contain_text('Undelivered work must finish')
    assert AuditDestination.select().count() == 1 and AuditDelivery.select().count() > 0
    AuditDelivery.update(status='receiver_accepted', claim_token=None, claim_expires_at=None).execute()
    row.get_by_role('button', name='Delete', exact=True).click()
    expect(page.locator('#audit-receiver-status')).to_have_text('Audit receiver deleted.')
    expect(row).to_have_count(0)
    assert AuditDestination.select().count() == AuditDelivery.select().count() == 0
    assert AuditEvent.select().where(AuditEvent.event_type == 'audit.receiver.deleted').exists()
