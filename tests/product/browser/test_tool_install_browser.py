"""Install each optional service from its existing row menu, in every locale."""
import json
import os

import pytest
from playwright.sync_api import expect

from tests.product.test_tool_install import pipeline


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Requires Chromium')]


def open_service(page, component):
    row = page.locator('#roxy-wi-' + component)
    row.locator('.admin-actions-toggle').click()
    row.locator('[data-tool-install]').click()
    dialog = page.locator('.tool-install-dialog')
    expect(dialog).to_be_visible()
    return dialog


@pytest.fixture
def service_page(logged_in, product_url, monkeypatch):
    monkeypatch.setattr('app.modules.tools.common.update_cur_tool_versions', lambda: None)
    monkeypatch.setattr('app.modules.tools.common.is_tool_active', lambda _tool: 'inactive')
    return logged_in


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_install_dialog(service_page, product_url, pipeline, locale, tmp_path):
    page = service_page
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    response = page.goto(product_url + '/admin#tools')
    assert response.status == 200
    expect(page.locator('#tool-install-open')).to_have_count(0)
    expect(page.locator('#tool-install-history')).to_have_count(0)
    dialog = open_service(page, 'checker')
    expect(dialog.locator('.ui-dialog-title')).to_contain_text('Checker')
    expect(page.locator('#tool-install-target')).to_have_value('')
    expect(page.locator('#tool-install-socket-options')).to_be_hidden()
    expect(dialog.locator('[name="rabbit_host"], [name="image"], [name="start"], [name="enabled"], select[name="component"]')).to_have_count(0)
    expect(page.locator('#tool-install-engine')).to_be_enabled()
    page.locator('#tool-install-engine-button').click()
    page.get_by_role('option', name='Docker', exact=True).click()
    expect(page.locator('#tool-install-container-options')).to_be_visible()
    expect(page.locator('#tool-install-version')).to_have_value('5.1.0')
    expect(page.locator('#tool-install-current')).to_contain_text('5.1.0')
    page.locator('#tool-install-target-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#tool-install-current')).to_contain_text('docker')
    expect(page.locator('#tool-install-engine')).to_have_value('docker')
    page.screenshot(path=str(tmp_path / ('tool-install-' + locale + '.png')))
    with page.expect_response('**/admin/tools/update/roxy-wi-checker') as installed:
        dialog.locator('.ui-dialog-buttonpane button').nth(0).click()
    assert installed.value.status == 202, installed.value.text()
    request = installed.value.request.post_data_json
    assert request['version'] == '5.1.0'
    assert not {'image', 'rabbit_host', 'start', 'enabled'} & request.keys()
    expect(dialog).to_be_visible()
    assert pipeline.run(installed.value.json()['tasks_ids'][0]) == 'completed'
    assert pipeline.calls[-1][0] == 11
    assert pipeline.calls[-1][2]['engine'] == 'docker'
    labels = json.loads(page.locator('#tool-install-messages').text_content())
    expect(page.locator('#tool-install-check-result')).to_have_text(labels['completed'])
    expect(page.locator('.toast-success')).to_contain_text('roxy-wi-checker')
    dialog.locator('.ui-dialog-buttonpane button').nth(1).click()
    expect(dialog).to_be_hidden()
    expect(page.locator('#tool-install-history')).to_have_count(0)
    # Opening another service shows neither the previous selection nor its history.
    dialog = open_service(page, 'socket')
    expect(page.locator('#tool-install-history-section')).to_have_count(0)
    expect(page.locator('#tool-install-socket-options')).to_be_visible()
    expect(page.locator('#tool-install-state-db')).to_be_hidden()


def test_all_five_service_menus_and_error_toast(service_page, product_url, pipeline, monkeypatch, tmp_path):
    page = service_page
    page.goto(product_url + '/admin#tools')
    expect(page.locator('[data-tool-install]')).to_have_count(5)
    for component in ('checker', 'metrics', 'portscanner', 'socket', 'keep_alive'):
        dialog = open_service(page, component)
        expect(page.locator('[name="component"]')).to_have_value(component)
        if component != 'keep_alive':
            dialog.locator('.ui-dialog-buttonpane button').nth(1).click()
    expect(page.locator('#tool-install-worker-options')).to_be_hidden()
    expect(page.locator('#tool-install-target')).to_be_disabled()
    expect(page.locator('#tool-install-target')).to_have_value('')
    expect(page.locator('#tool-install-engine')).to_be_disabled()
    expect(page.locator('#tool-install-engine')).to_have_value('native')
    expect(page.locator('#tool-install-container-options')).to_be_hidden()
    from app.modules.tools import common as tools
    from app.modules.roxywi.exception import RoxywiValidationError
    def fail(*args):
        raise RoxywiValidationError('local_execution_failed')
    monkeypatch.setattr(tools, 'inspect_tool', fail)
    dialog.locator('.ui-dialog-buttonpane button').nth(1).click()
    dialog = open_service(page, 'keep_alive')
    expect(page.locator('.toast-error')).to_contain_text('Local execution failed')
    expect(dialog).to_be_visible()
    dialog.locator('.ui-dialog-buttonpane button').nth(1).click()
    page.screenshot(path=str(tmp_path / 'tools-table.png'))


def test_update_toast_shows_plain_text_package_error(service_page, product_url, pipeline):
    page = service_page
    page.goto(product_url + '/admin#tools')
    message = 'Error: Unable to find a match: roxy-wi-prometheus-exporter'
    page.route('**/admin/tools/update/roxy-wi-prometheus-exporter', lambda route: route.fulfill(
        status=502, content_type='text/plain', body=message))
    page.evaluate("updateService('roxy-wi-prometheus-exporter')")
    expect(page.locator('.toast-error')).to_contain_text('Unable to find a match: roxy-wi-prometheus-exporter')
    expect(page.locator('#ajax-update')).to_be_empty()


def test_ansible_error_uses_existing_task_polling_and_localized_toast(service_page, product_url, pipeline, monkeypatch):
    from app.modules.service import installation
    page = service_page
    page.goto(product_url + '/admin#tools')
    dialog = open_service(page, 'keep_alive')
    expect(dialog.locator('.ui-dialog-buttonpane button').first).to_be_enabled()
    def fail(*args):
        raise RuntimeError('roxywi_error:package_version')
    monkeypatch.setattr(installation, 'run_ansible_locally', fail)
    with page.expect_response('**/admin/tools/update/roxy-wi-keep_alive') as response:
        dialog.locator('.ui-dialog-buttonpane button').first.click()
    assert pipeline.run(response.value.json()['tasks_ids'][0]) == 'failed'
    labels = json.loads(page.locator('#tool-install-messages').text_content())
    expect(page.locator('.toast-error').first).to_contain_text(labels['package_version'])
    expect(page.locator('#tool-install-check-result')).to_have_text(labels['failed'])
    assert page.evaluate('getInstallationTasksFromSessionStorage()') == []


def test_missing_release_version_shows_toast_without_queuing_task(service_page, product_url, pipeline):
    from app.modules.db.db_model import RoxyTool, InstallationTasks
    RoxyTool.update(new_version='0').where(RoxyTool.name == 'roxy-wi-checker').execute()
    page = service_page
    page.goto(product_url + '/admin#tools')
    dialog = open_service(page, 'checker')
    expect(page.locator('#tool-install-engine')).to_be_enabled()
    page.locator('#tool-install-engine-button').click()
    page.get_by_role('option', name='Docker', exact=True).click()
    expect(page.locator('#tool-install-version option')).to_have_count(0)
    dialog.locator('.ui-dialog-buttonpane button').first.click()
    labels = json.loads(page.locator('#tool-install-messages').text_content())
    expect(page.locator('.toast-error')).to_contain_text(labels['version_unavailable'])
    assert not InstallationTasks.select().exists()


def test_server_selector_waits_for_inspection_without_losing_target(service_page, product_url, pipeline):
    page = service_page
    pending = []
    page.route('**/admin/tools/install/check', lambda route: pending.append(route))
    page.goto(product_url + '/admin#tools')
    open_service(page, 'checker')
    expect(page.locator('#tool-install-target-button')).to_have_attribute('aria-disabled', 'true')
    assert len(pending) == 1
    pending.pop().fulfill(json=dict(installed=True, engine='native', version='5.1.0', state='active'))
    expect(page.locator('#tool-install-target-button')).to_have_attribute('aria-disabled', 'false')
    page.locator('#tool-install-target-button').click()
    page.get_by_role('option', name='Product HAProxy', exact=False).click()
    expect(page.locator('#tool-install-target-button')).to_have_attribute('aria-disabled', 'true')
    assert len(pending) == 1
    pending.pop().fulfill(json=dict(installed=True, engine='docker', version='5.1.0', state='active'))
    expect(page.locator('#tool-install-target-button')).to_have_attribute('aria-disabled', 'false')
    expect(page.locator('#tool-install-target')).to_have_value('11')
    expect(page.locator('#tool-install-engine')).to_have_value('docker')
