from datetime import timedelta

import pytest

from app.modules.common.time import utc_now
from app.modules.db.db_model import UserGroups, WorkerState


@pytest.mark.parametrize('service,canvas', [('haproxy', '192.0.2.11'),
                                          ('nginx', 'nginx_192.0.2.11'),
                                          ('apache', 'apache_192.0.2.11')])
def test_metrics_page_uses_remote_worker_without_local_package(
    product_client, product, service_worker_controls, service, canvas,
):
    setattr(product.server, service, 1)
    setattr(product.server, service + '_metrics', 1)
    product.server.save()
    response = product_client.get('/metrics/' + service)
    assert response.status_code == 200
    assert f'<canvas id="{canvas}"' in response.text
    assert service_worker_controls.commands == []


@pytest.mark.parametrize('status', ['stopped', 'stale', 'degraded'])
def test_registered_worker_keeps_historical_metrics_available(
    product_client, product, service_worker_controls, status,
):
    product.server.nginx_metrics = 1
    product.server.save()
    WorkerState.update(status='running' if status == 'stale' else status,
                       expires_at=utc_now() + timedelta(minutes=-1 if status == 'stale' else 5)).where(
        WorkerState.service == 'metrics').execute()
    response = product_client.get('/metrics/nginx')
    assert response.status_code == 200
    assert '<canvas id="nginx_192.0.2.11"' in response.text


def test_metrics_page_scopes_worker_availability_to_the_selected_group(
    product_client, product, service_worker_controls,
):
    product.admin.group_id = 2
    product.admin.save()
    UserGroups.create(user_id=product.admin.user_id, user_group_id=2, user_role_id=2)
    product.other.nginx = product.other.nginx_metrics = 1
    product.other.save()
    response = product_client.post('/login', json={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/metrics/nginx'})
    assert response.status_code == 200
    response = product_client.get('/metrics/nginx')
    assert response.status_code == 200
    assert '<canvas' not in response.text
    assert '/services/metrics#installation' in response.text
    WorkerState.update(group_ids=[2]).where(WorkerState.service == 'metrics').execute()
    response = product_client.get('/metrics/nginx')
    assert '<canvas id="nginx_192.0.2.22"' in response.text
    assert '192.0.2.11' not in response.text


def test_metrics_page_without_registered_workers_shows_installation(
    product_client, product, service_worker_controls,
):
    WorkerState.delete().execute()
    response = product_client.get('/metrics/nginx')
    assert response.status_code == 200
    assert '/services/metrics#installation' in response.text
    assert '<canvas' not in response.text
