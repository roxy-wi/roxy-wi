"""Exercise the real authenticated Update tab and its refresh behavior."""
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
def test_update_tab_uses_verified_versions_without_package_actions(logged_in, product_url, update_data, locale):
    page = logged_in
    page.context.add_cookies([{'name':'lang','value':locale,'url':product_url}])
    page.goto(product_url+'/admin#updatehapwi')
    metrics = page.locator('[data-update-service="roxy-wi-metrics"]')
    expect(metrics.locator('#current-version-roxy-wi-metrics')).to_have_text('4.0.0')
    exporter = page.locator('[data-update-service="roxy-wi-prometheus-exporter"]')
    expect(exporter.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_text('1.6')
    expect(page.locator('#ajax-updatehapwi-body button')).to_have_count(0)
    expect(page.locator('#current-version-roxy-wi-keep_alive')).to_have_count(0)
    expect(page.locator('.toast-error')).to_have_count(0)


def test_refresh_expires_inventory_without_hiding_active_worker(logged_in, product_url, update_data):
    page = logged_in
    page.goto(product_url+'/admin#updatehapwi')
    expect(page.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_text('1.6')
    payload = json.loads(update_data.read_text())
    payload['observed_at'] = (utc_now()-timedelta(minutes=3)).isoformat()+'Z'
    update_data.write_text(json.dumps(payload))
    page.locator('#updatehapwi .refresh:not(.service-restart)').click()
    expect(page.locator('#current-version-roxy-wi-prometheus-exporter')).to_have_count(0)
    expect(page.locator('#current-version-roxy-wi-metrics')).to_have_text('4.0.0')
    expect(page.locator('.toast-error')).to_have_count(0)
