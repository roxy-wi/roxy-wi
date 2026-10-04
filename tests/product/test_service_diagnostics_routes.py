"""Authenticated diagnostics use real persisted heartbeats and current roles."""
from datetime import timedelta

import pytest

from app.modules.common.time import utc_now
from app.modules.db.db_model import ServiceAssignment, UserGroups, WorkerState
from app.modules.tools.diagnostics import service_diagnostics


def seed_diagnostics(server_id=11):
    now = utc_now()
    ServiceAssignment.create(assignment_id='metrics:nginx:server-11', target_service='metrics',
                             server_id=server_id, service='nginx', user_group=1, payload='{}')
    WorkerState.create(worker_id='metrics-live', service='metrics', instance_id='demo-worker',
                       hostname='demo-worker', status='degraded', version='1.0', last_heartbeat=now,
                       expires_at=now + timedelta(seconds=30), active_assignments=2, capacity=20,
                       metadata={'assignment_errors': {'metrics:nginx:server-11':
                           'Connection refused <script>alert(1)</script> http://user:secret@host/stats?token=hidden password="private value"'},
                           'unrelated_secret': 'never-render-this'})
    WorkerState.create(worker_id='metrics-old', service='metrics', instance_id='demo-worker',
                       hostname='demo-worker', status='running', last_heartbeat=now - timedelta(days=2),
                       expires_at=now - timedelta(days=2) + timedelta(seconds=30))


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
def test_diagnostics_real_route_locales_redaction_and_stale(product_client, product, locale):
    seed_diagnostics()
    product_client.set_cookie('lang', locale)
    response = product_client.get('/admin/tools/roxy-wi-metrics/diagnostics')
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'no-store'
    text = response.get_data(as_text=True)
    assert 'Product HAProxy' in text
    assert 'href="/admin?server_id=11#servers"' in text
    assert 'metrics:nginx:server-11' in text
    assert 'data-worker-status="degraded"' in text
    assert 'data-worker-status="stale"' in text
    assert '&lt;script&gt;' in text and '<script>' not in text
    for value in ('user:secret', 'token=hidden', 'private value', 'never-render-this'):
        assert value not in text
    data = service_diagnostics('roxy-wi-metrics')
    assert data['workers'][0]['issues'][0]['reason'] == 'refused'
    assert data['workers'][0]['issues'][0]['server_id'] == 11
    assert data['workers'][1]['reason'] == 'possibly_replaced'
    assert WorkerState.select().count() == 2


def test_diagnostics_denies_non_admin_and_unknown_tool(product_client, product):
    seed_diagnostics()
    assert product_client.get('/admin/tools/arbitrary-service/diagnostics').status_code == 404
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.get('/admin/tools/roxy-wi-metrics/diagnostics')
    assert response.status_code == 403
    assert b'metrics-live' not in response.data


def test_diagnostics_requires_login(client, product):
    response = client.get('/admin/tools/roxy-wi-metrics/diagnostics', headers={'Accept': 'application/json'})
    assert response.status_code == 401


def test_missing_details_and_no_heartbeats(product_client, product):
    response = product_client.get('/admin/tools/roxy-wi-service-events/diagnostics')
    assert response.status_code == 200
    assert b'No worker heartbeats' in response.data
    now = utc_now()
    WorkerState.create(worker_id='events', service='roxy-wi-service-events', status='degraded',
                       last_heartbeat=now, expires_at=now + timedelta(seconds=75), metadata={'last_error': None})
    response = product_client.get('/admin/tools/roxy-wi-service-events/diagnostics')
    assert b'did not provide an error description' in response.data


def test_expired_error_is_labeled_as_old_and_unrelated_assignment_is_not_resolved(product_client, product):
    seed_diagnostics()
    ServiceAssignment.update(target_service='checker').execute()
    WorkerState.update(expires_at=utc_now() - timedelta(seconds=1)).execute()
    data = service_diagnostics('roxy-wi-metrics')
    assert data['workers'][0]['status'] == 'stale'
    assert data['workers'][0]['issues'][0]['server'] is None
    response = product_client.get('/admin/tools/roxy-wi-metrics/diagnostics')
    assert b'the current state is unknown' in response.data


def test_diagnostics_bounds_total_error_details(product, monkeypatch):
    monkeypatch.setattr('app.modules.tools.diagnostics.MAX_ISSUES', 2)
    now = utc_now()
    for index in range(3):
        WorkerState.create(worker_id=f'worker-{index}', service='metrics', status='degraded',
                           last_heartbeat=now, expires_at=now + timedelta(seconds=30),
                           metadata={'assignment_errors': {f'task-{index}': 'Connection refused'}, 'last_error': 'timeout'})
    data = service_diagnostics('roxy-wi-metrics')
    assert data['limited']
    assert sum(len(worker['issues']) for worker in data['workers']) == 2
