import pytest
from flask_jwt_extended import create_access_token

import app.api.routes.routes as api
import app.views.install.views as install
import app.views.ha.views as ha
from app.modules.db.db_model import InstallationTasks, Groups


@pytest.fixture()
def api_headers(app, monkeypatch):
    monkeypatch.setattr(api.roxywi_common, 'return_user_subscription',
                        lambda: {'user_status': 1, 'user_plan': 'support'})
    monkeypatch.setattr(api.roxywi_common, 'get_users_params',
                        lambda **_: {'user_id': 1, 'user': 'admin', 'role': 1, 'group_id': 1, 'lang': 'en'})
    monkeypatch.setattr(api.roxywi_common, 'check_user_group_for_flask', lambda: True)
    monkeypatch.setattr(api.roxywi_auth, 'is_admin', lambda **_: True)
    monkeypatch.setattr(api.roxywi_auth, 'is_access_permit_to_service', lambda _: True)
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}


@pytest.fixture()
def operation():
    task = InstallationTasks.create(service_name='Synthetic operation', group_id=1, server_ids=[],
                                    status='failed', error='private worker output', operation_payload='private payload')
    yield task
    task.delete_instance()


def test_operation_status_requires_authentication(client, api_headers, operation):
    assert client.get(f'/api/operations/{operation.id}').status_code == 401


def test_operation_status_requires_admin(client, monkeypatch, api_headers, operation):
    monkeypatch.setattr(api.roxywi_auth, 'is_admin', lambda **_: False)
    assert client.get(f'/api/operations/{operation.id}', headers=api_headers).status_code == 403


def test_operation_status_excludes_private_worker_data(client, api_headers, operation):
    response = client.get(f'/api/operations/{operation.id}', headers=api_headers)
    assert response.status_code == 200
    assert response.get_json() == {'task_id': operation.id, 'status': 'failed'}


def test_operation_status_is_group_scoped(client, api_headers, operation):
    group = Groups.create(name='terraform-test-other-group')
    try:
        operation.group_id = group.group_id
        operation.save()
        response = client.get(f'/api/operations/{operation.id}', headers=api_headers)
        assert response.status_code == 404
        assert 'private' not in response.get_data(as_text=True)
    finally:
        operation.group_id = 1
        operation.save()
        group.delete_instance()


def test_missing_operation_returns_404(client, api_headers):
    assert client.get('/api/operations/2147483647', headers=api_headers).status_code == 404


def test_installation_returns_id_and_operation(client, monkeypatch, api_headers):
    monkeypatch.setattr(install.SupportClass, 'return_server_ip_or_id', lambda self, server_id: server_id)
    monkeypatch.setattr(install.service_mod, 'install_service', lambda *_: 123)
    monkeypatch.setattr(install.service_sql, 'update_hapwi_server', lambda *_: None)
    monkeypatch.setattr(install.service_command_sql, 'queue_checker_assignment', lambda *_: None)
    monkeypatch.setattr(install.service_command_sql, 'queue_metrics_assignment', lambda *_: None)
    response = client.post('/api/service/haproxy/10/install', headers=api_headers, json={'docker': True})
    assert response.status_code == 201
    assert response.get_json() == {'id': '10-haproxy', 'tasks_ids': [123]}


@pytest.mark.parametrize('reconfigure', [True, False])
def test_cluster_create_preserves_id_and_returns_operations(client, monkeypatch, api_headers, reconfigure):
    monkeypatch.setattr(ha.ha_cluster, 'create_cluster', lambda *_: 12)
    monkeypatch.setattr(ha.ha_cluster, 'get_services_dict', lambda _: {'haproxy': {'enabled': True}})
    calls = []

    def install_service(service, *_):
        calls.append(service)
        return 100 + len(calls)

    monkeypatch.setattr(ha.service_mod, 'install_service', install_service)
    response = client.post('/api/ha/cluster', headers=api_headers,
                           json={'name': 'test', 'services': {'haproxy': {'enabled': True}},
                                 'reconfigure': reconfigure})
    assert response.status_code == 201
    assert response.get_json() == {'id': 12, 'tasks_ids': [101, 102] if reconfigure else []}
    assert calls == (['keepalived', 'haproxy'] if reconfigure else [])
