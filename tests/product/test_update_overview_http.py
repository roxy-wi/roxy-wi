import json
from datetime import timedelta

from app.modules.common.time import utc_now
from app.modules.db.db_model import RoxyTool, UserGroups, WorkerState


def test_update_endpoint_uses_live_worker_evidence_and_stopped_inventory(product_client, product, monkeypatch):
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'compose')
    now = utc_now()
    WorkerState.create(worker_id='update-metrics', service='metrics', instance_id='update-metrics',
                       status='running', version='4.0.0', group_ids=[1],
                       last_heartbeat=now, expires_at=now + timedelta(minutes=5))
    path = product.root / 'deployment-inventory.json'
    path.write_text(json.dumps({
        'schema':1, 'complete':True, 'observed_at':now.isoformat()+'Z',
        'services':[{'service':'roxy-wi-prometheus-exporter', 'version':'1.6', 'running':False}],
    }))
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(path))
    RoxyTool.update(new_version='4.0.0',current_version='1.0').where(RoxyTool.name=='roxy-wi-metrics').execute()
    RoxyTool.update(new_version='1.6',current_version='1.0').where(RoxyTool.name=='roxy-wi-prometheus-exporter').execute()

    response = product_client.get('/admin/update')

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'current-version-roxy-wi-metrics' in response.text
    assert '>4.0.0</b>' in response.text
    exporter = response.text.split('data-update-service="roxy-wi-prometheus-exporter"',1)[1].split('</tr>',1)[0]
    assert '>1.6</b>' in exporter
    assert 'Stopped' in exporter
    assert 'updateService(' not in response.text
    assert RoxyTool.get(RoxyTool.name=='roxy-wi-metrics').current_version == '1.0'


def test_update_endpoint_does_not_claim_seeded_components_are_installed(product_client, product, monkeypatch):
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_MODE', 'compose')
    monkeypatch.setenv('ROXYWI_DEPLOYMENT_INVENTORY_FILE', str(product.root / 'missing.json'))
    response = product_client.get('/admin/update')
    assert response.status_code == 200
    assert 'current-version-roxy-wi-metrics' not in response.text
    assert 'current-version-roxy-wi-keep_alive' not in response.text
    assert 'No current report' in response.text


def test_non_admin_cannot_read_deployment_versions(product_client, product, monkeypatch):
    monkeypatch.setattr('app.modules.tools.updates.load_inventory', lambda: (_ for _ in ()).throw(
        AssertionError('inventory read before authorization')))
    UserGroups.update(user_role_id=2).where(UserGroups.user_id==product.admin.user_id).execute()
    response = product_client.get('/admin/update')
    assert response.status_code == 403
