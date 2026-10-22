import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import InstallationTasks, Server
from app.modules.service import certificates
from tests.product.test_runtime_certificates import LOCALES, run
from tests.product.test_certificate_history import history_task


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_add_dialog_visibility_and_mobile_layout(logged_in, product_url, product, certificate_host, service):
    page = logged_in
    Server.update(apache=1).where(Server.server_id == product.server.server_id).execute()
    page.goto(product_url + f'/service/{service}/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-list')).to_contain_text('site.pem')
    page.locator('#cert-add').click()
    dialog = page.get_by_role('dialog').filter(has=page.locator('#cert-update-dialog'))
    expect(dialog).to_be_visible()
    expect(dialog.locator('[data-cert-create]')).to_be_visible()
    expect(dialog.locator('[data-cert-current]')).to_be_hidden()
    if service == 'haproxy':
        expect(dialog.locator('[data-cert-destination]')).to_be_hidden()
    else:
        expect(dialog.locator('#cert-upload-mode')).to_have_count(0)
    page.locator('#cert-new-name').fill('cancelled')
    page.locator('#cert-pem').fill(certificate_host.new)
    expect(dialog.locator('[data-cert-apply]')).to_be_enabled()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
    bounds = dialog.bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
    assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth')
    dialog.locator('.ui-dialog-buttonpane').get_by_role('button', name='Close', exact=True).click()
    expect(dialog).to_be_hidden()
    assert page.locator('#cert-pem').input_value() == ''
    assert not certificate_host.stored_on
    assert not InstallationTasks.select().where(InstallationTasks.operation_type == 'certificate').exists()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '252px'")
    page.locator('#cert-list .admin-actions-toggle').click()
    expect(page.get_by_role('menuitem', name='View', exact=True).locator('[data-icon="eye"]')).to_be_visible()
    if service == 'haproxy':
        expect(page.get_by_role('menuitem', name='Delete', exact=True)).to_be_disabled()
        page.get_by_role('menuitem', name='Update certificate', exact=True).click()
        expect(dialog.locator('[data-cert-create]')).to_be_hidden()
        expect(dialog.locator('[data-cert-current]')).to_be_visible()
        dialog.locator('.ui-dialog-buttonpane').get_by_role('button', name='Close', exact=True).click()
        page.locator('#cert-history').click()
        expect(page.locator('#cert-operations')).to_have_text('No certificate operations yet.')


def test_add_waits_for_certificate_destinations_on_slow_connections(logged_in, product_url, product, certificate_host):
    page = logged_in
    pending = []
    url = product_url + f'/service/haproxy/certificates/{product.server.server_id}'
    page.route(url, lambda route: pending.append(route))
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    with page.expect_request(url):
        page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-add')).to_be_disabled()
    expect(page.locator('#cert-message')).to_contain_text('Loading')
    assert len(pending) == 1
    pending[0].continue_()
    expect(page.locator('#cert-add')).to_be_enabled()
    page.locator('#cert-add').click()
    page.locator('#cert-upload-mode-button').click()
    page.get_by_role('option', name='Apply immediately to HAProxy without reload', exact=True).click()
    expect(page.locator('#cert-destination option')).to_have_count(2)
    expect(page.locator('[data-cert-destination]')).to_be_visible()


@pytest.mark.parametrize('locale', LOCALES)
def test_complete_certificate_history_pagination(logged_in, product_url, product, certificate_host, app, locale):
    page = logged_in
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    tasks = [history_task(product, index, status='failed' if index == 22 else 'completed') for index in range(23)]
    for index in range(55):
        history_task(product, index, servers=[111])
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    page.locator('#cert-history').click()
    history = page.get_by_role('dialog').filter(has=page.locator('#cert-history-dialog'))
    rows = history.locator('tbody tr[data-operation-id]')
    expect(rows).to_have_count(10)
    expect(rows.first).to_contain_text('certificate-022.pem')
    expect(rows.first).to_contain_text(labels['remote_failed'])
    expect(rows.first).to_contain_text('192.0.2.12')
    expect(history.locator('#cert-history-page')).to_have_text(labels['history_page'].format(page=1, pages=3))
    expect(history.locator('#cert-history-prev')).to_be_disabled()
    history.get_by_role('button', name=labels['history_next'], exact=True).click()
    expect(rows.first).to_contain_text('certificate-012.pem')
    history.get_by_role('button', name=labels['history_next'], exact=True).click()
    expect(rows).to_have_count(3)
    expect(rows.last).to_contain_text('certificate-000.pem')
    expect(history.locator('#cert-history-next')).to_be_disabled()
    expect(history.locator('#cert-history-range')).to_have_text(labels['history_range'].format(first=21, last=23, total=23))
    history.locator('#cert-history-refresh').click()
    expect(history.locator('#cert-history-page')).to_have_text(labels['history_page'].format(page=3, pages=3))
    expect(rows.last).to_have_attribute('data-operation-id', str(tasks[0].id))
    history.get_by_role('button', name=labels['history_previous'], exact=True).click()
    expect(rows.first).to_contain_text('certificate-012.pem')
    history.locator('#cert-history-size-button').click()
    page.get_by_role('option', name='25', exact=True).click()
    expect(rows).to_have_count(23)
    expect(history.locator('#cert-history-page')).to_have_text(labels['history_page'].format(page=1, pages=1))
    expect(history.locator('#cert-history-next')).to_be_disabled()
    if locale == 'ru':
        history.locator('#cert-history-size-button').click()
        page.get_by_role('option', name='10', exact=True).click()
        expect(rows).to_have_count(10)
        folder = Path('.test-artifacts/certificate-history')
        folder.mkdir(parents=True, exist_ok=True)
        history.screenshot(path=str(folder / 'history-ru.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === '0px'")
        assert history.evaluate('(element) => element.scrollWidth <= element.clientWidth')
        page.screenshot(path=str(folder / 'history-mobile-ru.png'))


def test_history_polling_preserves_page_and_refreshes_completed_operation(logged_in, product_url, product, certificate_host):
    page = logged_in
    tasks = [history_task(product, index, status='running' if index == 0 else 'completed') for index in range(11)]
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    page.locator('#cert-history').click()
    page.locator('#cert-history-next').click()
    expect(page.locator('#cert-history-page')).to_have_text('Page 2 of 2')
    expect(page.locator('#cert-operations')).to_contain_text('certificate-000.pem')
    InstallationTasks.update(status='completed').where(InstallationTasks.id == tasks[0].id).execute()
    expect(page.locator('#cert-operations')).to_contain_text('Completed', timeout=15000)
    expect(page.locator('#cert-history-page')).to_have_text('Page 2 of 2')


def test_history_available_without_waiting_for_catalog_and_recovers_from_error(logged_in, product_url, product, certificate_host):
    page = logged_in
    for index in range(11):
        history_task(product, index)
    pending = []
    url = product_url + '/service/haproxy/certificates/11'
    page.route(url, lambda route: pending.append(route))
    page.route(url + '/history?*', lambda route: route.fulfill(status=500, json={'error_code': 'operation_failed'}), times=1)
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-add')).to_be_disabled()
    page.locator('#cert-history').click()
    expect(page.locator('#cert-history-message')).not_to_be_empty()
    expect(page.locator('#cert-history-refresh')).to_be_enabled()
    page.locator('#cert-history-refresh').click()
    expect(page.locator('#cert-operations')).to_contain_text('certificate-010.pem')
    expect(page.locator('#cert-history-message')).to_be_empty()
    assert len(pending) == 1
    pending_page = []
    page.route(url + '/history?page=2&per_page=10', lambda route: pending_page.append(route))
    with page.expect_request(url + '/history?page=2&per_page=10'):
        page.locator('#cert-history-next').click()
    pending[0].continue_()
    expect(page.locator('#cert-add')).to_be_enabled()
    assert len(pending_page) == 1
    pending_page[0].continue_()
    expect(page.locator('#cert-history-page')).to_have_text('Page 2 of 2')
    expect(page.locator('#cert-operations')).to_contain_text('certificate-000.pem')


@pytest.mark.parametrize('kind', ['directory', 'crt_list'])
@pytest.mark.parametrize('locale', LOCALES)
def test_upload_and_apply_new_certificate_in_all_languages(logged_in, product_url, product, certificate_host, app, kind, locale):
    page, host = logged_in, certificate_host
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    slave = Server.create(server_id=12, hostname='Slave', ip='192.0.2.12', group_id='1',
                          master=product.server.server_id, haproxy=1)
    host.add(slave.ip, host.old)
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/service/haproxy/ssl')
    expect(page.locator('#cert-add')).to_be_disabled()
    expect(page.locator('#cert-update-dialog')).to_be_hidden()
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-list')).to_contain_text('site.pem')
    page.locator('#cert-add').click()
    dialog = page.get_by_role('dialog').filter(has=page.locator('#cert-update-dialog'))
    expect(dialog).to_be_visible()
    add_label = app.jinja_env.get_template(f'languages/{locale}.html').module.words['add'].title()
    expect(dialog.locator('[data-cert-apply]')).to_have_text(' ' + add_label)
    expect(page.locator('#cert-upload-mode')).to_have_value('disk')
    page.locator('#cert-upload-mode-button').click()
    page.get_by_role('option', name=labels['apply_now'], exact=True).click()
    expect(page.locator('#cert-upload-hint')).to_have_text(labels['sync_hint'])
    expect(dialog.locator('[data-cert-apply]')).to_have_text(' ' + add_label)
    page.locator('#new-cert-file-type-button').click()
    page.get_by_role('option', name='Crt (chain)', exact=True).click()
    expect(dialog.locator('[data-cert-apply]')).to_be_disabled()
    expect(page.locator('#cert-create-help')).to_have_text(labels['pem_required'])
    page.locator('#new-cert-file-type-button').click()
    page.get_by_role('option', name='Pem', exact=True).click()
    page.locator('#cert-new-name').fill('new.pem')
    page.locator('#cert-pem').fill(host.new)
    page.locator('#cert-destination-button').click()
    page.get_by_role('option').filter(has_text=labels[kind] + ' · ').first.click()
    expect(dialog.locator('[data-cert-preview]')).to_contain_text(labels['new_certificate'])
    page.locator('#cert-new-name').fill('../new.pem')
    expect(dialog.locator('[data-cert-apply]')).to_be_disabled()
    page.locator('#cert-new-name').fill('new.pem')
    expect(dialog.locator('[data-cert-apply]')).to_be_enabled()
    if locale == 'ru':
        folder = Path('.test-artifacts/certificates')
        folder.mkdir(parents=True, exist_ok=True)
        dialog.screenshot(path=str(folder / f'create-{kind}-ru.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        bounds = dialog.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
        assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth')
        for field in ('#cert-new-name', '#cert-destination-button', '#cert-pem', '[data-cert-preview]'):
            field_bounds = dialog.locator(field).bounding_box()
            assert field_bounds['x'] >= bounds['x']
            assert field_bounds['x'] + field_bounds['width'] <= bounds['x'] + bounds['width'], dialog.locator(field).evaluate('''element => {
                const chain = [];
                for (let e = element; e; e = e.parentElement) {
                    const s = getComputedStyle(e);
                    chain.push({id: e.id, classes: e.className, width: s.width, min: s.minWidth, display: s.display, grid: s.gridTemplateColumns});
                }
                return JSON.stringify(chain);
            }''')
        page.screenshot(path=str(folder / f'create-{kind}-mobile-ru.png'))
    dialog.locator('[data-cert-apply]').click()
    expect(dialog).to_be_hidden()
    task = InstallationTasks.get(InstallationTasks.operation_type == 'certificate')
    assert run(task.id) == 'completed'
    history = page.get_by_role('dialog').filter(has=page.locator('#cert-history-dialog'))
    expect(history).to_be_visible()
    history.locator('.ui-dialog-titlebar-close').click()
    page.locator('#cert-refresh').click()
    page.locator('#cert-history').click()
    expect(page.locator('#cert-operations')).to_contain_text(labels['completed'])
    expect(page.locator('#cert-list')).to_contain_text('new.pem')
    for server in (product.server, slave):
        target = host.files[server.ip].parent / 'new.pem'
        assert target.read_text() == host.new
        assert host.active[str(target)] == host.new
    assert not page.locator('#cert-pem').input_value()


@pytest.mark.parametrize('name', ['disk-only', 'site'])
@pytest.mark.parametrize('locale', LOCALES)
def test_save_to_disk_does_not_apply_and_preserves_master_slave_sync(
        logged_in, product_url, product, certificate_host, app, name, locale):
    page, host = logged_in, certificate_host
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    slave = Server.create(server_id=12, hostname='Slave', ip='192.0.2.12', group_id='1',
                          master=product.server.server_id, haproxy=1)
    host.add(slave.ip, host.old)
    before = dict(host.active)
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-list')).to_contain_text('site.pem')
    page.locator('#cert-add').click()
    dialog = page.get_by_role('dialog').filter(has=page.locator('#cert-update-dialog'))
    expect(page.locator('#cert-upload-mode')).to_have_value('disk')
    page.locator('#cert-upload-mode-button').click()
    page.get_by_role('option', name=labels['apply_now'], exact=True).click()
    page.locator('#cert-upload-mode-button').click()
    page.get_by_role('option', name=labels['disk_only'], exact=True).click()
    expect(page.locator('#cert-upload-hint')).to_have_text(labels['disk_hint'])
    page.locator('#cert-new-name').fill(name)
    page.locator('#cert-pem').fill(host.new)
    with page.expect_response('**/add/cert/add') as uploading:
        dialog.locator('[data-cert-apply]').click()
    assert uploading.value.status == 201, uploading.value.text()
    expect(dialog).to_be_hidden()
    row = page.locator('#cert-list tr').filter(has_text=name + '.pem')
    expect(row).to_contain_text(labels['differs'] if name == 'site' else labels['stored'])
    for server in (product.server, slave):
        assert (host.files[server.ip].parent / (name + '.pem')).read_text() == host.new
    assert set(host.stored_on) == {product.server.ip, slave.ip}
    assert host.active == before
    assert not any(command.startswith(('new ', 'set ', 'commit ', 'add ', 'del ')) for command in host.calls)
    assert not InstallationTasks.select().where(InstallationTasks.operation_type == 'certificate').exists()
    if locale == 'ru' and name == 'disk-only':
        folder = Path('.test-artifacts/certificates')
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / 'upload-choice-ru.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(folder / 'upload-choice-mobile-ru.png'), full_page=True)


@pytest.mark.parametrize('locale', LOCALES)
def test_certificate_update_search_and_operations_in_all_languages(logged_in, product_url, product, certificate_host, app, locale):
    page = logged_in
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/service/haproxy/ssl')
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#cert-list')).to_contain_text('site.pem')
    page.locator('#cert-search').fill('no-match')
    expect(page.locator('#cert-list')).to_contain_text(messages['empty'])
    page.locator('#cert-search').fill('example.test')
    page.locator('#cert-list .admin-actions-toggle').click()
    page.get_by_role('menuitem', name=messages['update'], exact=True).click()
    dialog = page.get_by_role('dialog', name=messages['update'], exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.locator('#cert-upload-hint')).to_have_text(messages['sync_hint'])
    page.locator('#cert-pem').fill('invalid PEM')
    expect(dialog.locator('[data-cert-preview]')).to_contain_text(messages['invalid_pem'])
    expect(dialog.locator('[data-cert-apply]')).to_be_disabled()
    page.locator('#cert-pem').fill(certificate_host.new)
    expect(dialog.locator('[data-cert-preview]')).to_contain_text(messages['new_certificate'])
    expect(dialog.locator('[data-cert-apply]')).to_be_enabled()
    if locale == 'ru':
        folder = Path('.test-artifacts/certificates')
        folder.mkdir(parents=True, exist_ok=True)
        dialog.screenshot(path=str(folder / 'update-ru.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        bounds = dialog.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 390
        assert dialog.evaluate('(element) => element.scrollWidth <= element.clientWidth')
        page.screenshot(path=str(folder / 'update-mobile-ru.png'))
        page.set_viewport_size({'width': 1440, 'height': 1000})
    dialog.locator('[data-cert-apply]').click()
    expect(dialog).to_be_hidden()
    task = InstallationTasks.get(InstallationTasks.operation_type == 'certificate')
    assert run(task.id) == 'completed'
    history = page.get_by_role('dialog').filter(has=page.locator('#cert-history-dialog'))
    expect(history).to_be_visible()
    history.locator('.ui-dialog-titlebar-close').click()
    page.locator('#cert-refresh').click()
    page.locator('#cert-history').click()
    expect(page.locator('#cert-operations')).to_contain_text(messages['completed'])
    assert page.locator('#cert-pem').input_value() == ''
    assert 'PRIVATE KEY' not in page.locator('body').inner_text()
    if locale == 'ru':
        folder = Path('.test-artifacts/certificates')
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / 'runtime-ru.png'), full_page=True)


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
@pytest.mark.parametrize('locale', LOCALES)
def test_uploaded_files_share_server_selection_and_existing_actions(logged_in, product_url, product, certificate_host, app, monkeypatch, locale, service):
    host = certificate_host
    second = Server.create(server_id=12, hostname='Second server', ip='192.0.2.12', group_id='1',
                           haproxy=1, nginx=1, apache=1, cred_id=11)
    host.add(second.ip, host.old)
    # Each synthetic host has its own Runtime API certificate list.
    host.active.pop(str(host.files[product.server.ip]))
    page = logged_in
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.certificates
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + f'/service/{service}/ssl')
    expect(page.locator('#serv5, #serv6, #ssl_key_view')).to_have_count(0)
    page.locator('#cert-server-button').click()
    page.get_by_role('option', name='Second server', exact=False).click()
    expect(page.locator('#cert-list')).to_contain_text('site.pem')
    page.locator('#cert-search').fill('no-match')
    expect(page.locator('#cert-list')).to_contain_text(labels['empty'])
    page.locator('#cert-search').fill('')
    page.locator('#cert-add').click()
    page.locator('#cert-new-name').fill('uploaded')
    page.locator('#new-cert-file-type-button').click()
    page.get_by_role('option', name='Crt (chain)', exact=True).click()
    chain = certificates.inspect_pem(host.new)[0]['fullchain']
    page.locator('#cert-pem').fill(chain)
    with page.expect_response('**/add/cert/add') as uploading:
        page.locator('[data-cert-apply]').click()
    assert uploading.value.status == 201, uploading.value.text()
    row = page.locator('#cert-list tr').filter(has_text='uploaded.crt')
    expect(row).to_be_visible()
    assert host.stored_on == [second.ip]
    assert not (host.files[product.server.ip].parent / 'uploaded.crt').exists()
    row.locator('.admin-actions-toggle').click()
    if service == 'haproxy':
        expect(page.get_by_role('menuitem', name=labels['update'], exact=True)).to_be_disabled()
    else:
        expect(page.get_by_role('menuitem', name=labels['update'], exact=True)).to_have_count(0)
        expect(page.locator('#cert-history-dialog')).to_have_count(0)
        page.get_by_role('menuitem', name=labels['details'], exact=True).click()
        details = page.get_by_role('dialog', name='uploaded.crt', exact=True)
        expect(details).to_contain_text('example.test')
        expect(details).not_to_contain_text(labels['in_haproxy'])
        details.locator('.ui-dialog-titlebar-close').click()
        row.locator('.admin-actions-toggle').click()
    page.get_by_role('menuitem', name=labels['view'], exact=True).click()
    dialog = page.get_by_role('dialog', name='uploaded.crt', exact=True)
    expect(dialog).to_contain_text('example.test')
    dialog.locator('.ui-dialog-titlebar-close').click()
    row.locator('.admin-actions-toggle').click()
    page.get_by_role('menuitem', name=labels['delete'], exact=True).click()
    confirm = page.get_by_role('dialog').filter(has=page.locator('#cert-details-dialog'))
    confirm.get_by_role('button', name=labels['delete'], exact=True).click()
    expect(row).to_have_count(0)
    assert not (host.files[second.ip].parent / 'uploaded.crt').exists()
    page.locator('button[onclick="openLeDialog()"]').click()
    expect(page.locator('#new-le-server_id')).to_have_value(str(second.server_id))
    le_dialog = page.get_by_role('dialog').filter(has=page.locator('#le-add-table'))
    le_dialog.locator('.ui-dialog-titlebar-close').click()
    expect(le_dialog).to_be_hidden()

    # Check real positions and overflow, including the LE controls, in both sizes.
    for width in (1440, 1024, 751, 390, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        page.wait_for_function("getComputedStyle(document.querySelector('.container')).marginLeft === (innerWidth < 900 ? '0px' : '252px')")
        if locale == 'en':
            folder = Path('.test-artifacts/certificates')
            folder.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(folder / f'unified-{service}-{width}.png'), full_page=True)
        assert page.locator('#ssl-page').evaluate('(element) => element.scrollWidth <= element.clientWidth')
        assert page.locator('html').evaluate('(element) => element.scrollWidth <= element.clientWidth')
        for link in page.locator('.footer-link').all():
            bounds = link.bounding_box()
            assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
        workspace = page.locator('#ssl-page').bounding_box()
        assert workspace['x'] + workspace['width'] <= width
        for selector in ('#runtime-certificates', '#le_table'):
            box = page.locator(selector).bounding_box()
            assert abs(box['x'] - workspace['x']) < 1
    if service != 'haproxy':
        assert host.calls == []
