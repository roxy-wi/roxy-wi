"""Exercise the real authenticated Tools tab and its refresh behavior."""
import json
import os
from datetime import timedelta

import pytest
from playwright.sync_api import expect

from app.modules.common.time import utc_now
from app.modules.db.db_model import RoxyTool, WorkerState


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


@pytest.fixture()
def update_data(product, monkeypatch):
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'compose')
    path = product.root / 'deployment-inventory.json'
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    now = utc_now()
    path.write_text(json.dumps({
        'schema':1, 'complete':True, 'observed_at':now.isoformat()+'Z',
        'services':[{'service':'roxy-wi-prometheus-exporter','version':'1.6','running':False}],
    }))
    WorkerState.create(worker_id='update-browser-metrics', service='metrics', instance_id='update-browser',
                       status='running', version='4.0.0', last_heartbeat=now,
                       expires_at=now+timedelta(minutes=5), group_ids=[1])
    for name, latest in [('roxy-wi-metrics','4.0.0'),('roxy-wi-prometheus-exporter','1.6')]:
        RoxyTool.update(current_version='1.0',new_version=latest).where(RoxyTool.name==name).execute()
    return path


@pytest.mark.parametrize('locale', ['en','ru','fr','es-ES','pt-br','zh'])
def test_tools_tab_uses_verified_versions_without_package_actions(logged_in, product_url, update_data, locale):
    page = logged_in
    page.context.add_cookies([{'name':'lang','value':locale,'url':product_url}])
    page.goto(product_url+'/admin#tools')
    metrics = page.locator('#roxy-wi-metrics')
    expect(metrics.locator('#current-version-roxy-wi-metrics')).to_have_text('4.0.0')
    exporter = page.locator('#roxy-wi-prometheus-exporter')
    expect(exporter.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_text('1.6')
    expect(page.locator('#services_table [onclick^="updateService"]')).to_have_count(0)
    expect(page.locator('#admin-tabs a[href="#updatehapwi"], #updatehapwi')).to_have_count(0)
    expect(metrics.locator('.admin-version-cell').nth(1)).to_have_text('4.0.0')
    expect(page.locator('#current-version-roxy-wi-keep_alive')).to_have_count(0)
    expect(page.locator('.toast-error')).to_have_count(0)


def test_refresh_expires_inventory_without_hiding_active_worker(logged_in, product_url, update_data):
    page = logged_in
    page.goto(product_url+'/admin#tools')
    expect(page.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_text('1.6')
    payload = json.loads(update_data.read_text())
    payload['observed_at'] = (utc_now()-timedelta(minutes=3)).isoformat()+'Z'
    update_data.write_text(json.dumps(payload))
    page.locator('#services_table .refresh').click()
    expect(page.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_count(0)
    expect(page.locator('#current-version-roxy-wi-metrics')).to_have_text('4.0.0')
    expect(page.locator('.toast-error')).to_have_count(0)


@pytest.mark.parametrize('distribution,install_command', [
    ('ubuntu', ['sudo', 'apt-get', 'install', 'roxy-wi', '-y']),
    ('debian', ['sudo', 'apt-get', 'install', 'roxy-wi', '-y']),
    ('rocky', ['sudo', '-S', 'yum', '-y', 'install', 'roxy-wi']),
])
def test_package_upgrade_from_roxywi_row_uses_existing_updater(
        logged_in, product_url, monkeypatch, distribution, install_command):
    from app.modules.db import roxy as catalog
    from app.modules.tools import common as tools
    from app.version import get_service_version

    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'package')
    monkeypatch.setattr(tools, 'update_cur_tool_versions', lambda: None)
    monkeypatch.setattr(tools, 'is_tool_active', lambda _: 'inactive')
    monkeypatch.setattr(tools.distro, 'id', lambda: distribution)
    commands = []

    def upgrade(command):
        commands.append(command)
        return {'rc': 0, 'output': ['Unpacking roxy-wi'], 'error': ''}

    monkeypatch.setattr(tools.server_mod, 'subprocess_execute_with_rc', upgrade)
    monkeypatch.setattr(tools.server_mod, 'subprocess_execute', lambda _: (['99.0.0'], ''))
    catalog.update_app_versions(get_service_version(), '99.0.0')
    page = logged_in
    page.goto(product_url + '/admin#tools')
    row = page.locator('#roxy-wi')
    expect(row.locator('.admin-version-cell').first).to_have_text(get_service_version())
    expect(row.locator('.admin-version-cell').last).to_have_text('99.0.0')
    row.get_by_role('button', name='Actions').click()
    with page.expect_response('**/admin/tools/update/roxy-wi') as response:
        row.get_by_role('button', name='Update', exact=True).click()
    assert response.value.status == 200
    assert len(commands) == 1
    assert commands[0].split('&&')[-1].split() == install_command
    catalog.update_app_versions(get_service_version(), get_service_version())
    page.locator('#services_table .refresh').click()
    expect(row.locator('.admin-version-cell').last).to_have_text(get_service_version())
    row.get_by_role('button', name='Actions').click()
    expect(row.get_by_role('button', name='Update', exact=True)).to_have_count(0)
