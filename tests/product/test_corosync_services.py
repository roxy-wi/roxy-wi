"""Corosync access and installed-service metadata use the real admin routes."""
import importlib
import json
from uuid import uuid4

from bs4 import BeautifulSoup
import pytest

from app.modules.db.db_model import (
    ConfigChange, HaCluster, HaMaintenancePlan, InstallationTasks, PacemakerCluster,
    PacemakerEvent, Server, Services, User, UserGroups,
)
from app.modules.pacemaker import operations
from app.modules.operations.queue import deserialize_operation_payload, serialize_operation_payload
from app.modules.server import server as server_module
from app.modules.service import certificate_operations, certificates, ha_maintenance, ha_readiness, service_map
from tests.product.test_ha_readiness import readiness_cluster


def grant(product, services):
    User.update(user_services=services).where(User.user_id == product.admin.user_id).execute()


@pytest.mark.parametrize('source', ['path', 'query', 'body'])
@pytest.mark.parametrize('provider,expected', [('other', 400), ('pacemaker', 403)])
def test_ha_provider_validation_is_distinct_from_permission_denial(product_client, product, source, provider, expected):
    grant(product, '5')
    if source == 'path':
        response = product_client.get(f'/ha/api/readiness/{provider}/1')
    elif source == 'query':
        response = product_client.get('/ha/api/maintenance', query_string={'provider': provider, 'cluster_id': 1})
    else:
        response = product_client.post('/ha/api/maintenance', json={
            'provider': provider, 'cluster_id': 1, 'server_id': 11,
            'title': 'OS update', 'capacity_confirmed': True, 'capacity_evidence': 'Capacity checked',
        })
    assert response.status_code == expected


@pytest.mark.parametrize('services,allowed', [('5', False), ('7', True), ('5 7', True), ('17', False), ('', False)])
def test_corosync_access_is_independent_of_keepalived(product_client, product, readiness_cluster, services, allowed):
    HaCluster.create(name='Keepalived only', description='Separate provider', group_id=1)
    grant(product, services)
    status = 200 if allowed else 403
    assert product_client.get('/pacemaker').status_code == status
    assert product_client.get('/pacemaker/api').status_code == status
    assert product_client.get(f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}').status_code == status
    expected = ({'keepalived'} if '5' in services.split() else set()) | ({'pacemaker'} if allowed else set())
    response = product_client.get('/ha/api/readiness')
    assert response.status_code == (200 if expected else 403)
    if expected:
        assert {row['provider'] for row in response.json['data']} == expected
        cards = product_client.get('/ha/cluster/cards').text
        assert ('product-ha' in cards) == allowed
        assert ('Keepalived only' in cards) == ('keepalived' in expected)
        dashboard = BeautifulSoup(product_client.get('/ha/cluster').text, 'html.parser')
        assert bool(dashboard.select('[data-ha-setup]')) == allowed
    page = BeautifulSoup(product_client.get('/admin').text, 'html.parser')
    assert bool(page.select('#menu-pacemaker')) == allowed


def test_user_service_dialog_saves_and_revokes_corosync(product_client, product):
    ident = product.admin.user_id
    grant(product, '1 2 3 4 5 6')
    page = BeautifulSoup(product_client.get(f'/user/services/{ident}').text, 'html.parser')
    assert page.select_one('#all_services #add_service-7').get_text(' ', strip=True).startswith('Corosync / Pacemaker')
    for values, allowed in [('1 5 7', True), ('1 5', False)]:
        response = product_client.post(f'/user/services/{ident}', json={
            'username': 'admin', 'services': {str(ident): {value: {} for value in values.split()}},
        })
        assert response.status_code == 200, response.text
        assert product_client.get('/pacemaker/api').status_code == (200 if allowed else 403)
        page = BeautifulSoup(product_client.get(f'/user/services/{ident}').text, 'html.parser')
        assert bool(page.select('#checked_services #remove_service-7')) == allowed


def test_server_service_flag_is_saved_and_legacy_payload_preserves_it(product_client, product):
    flags = {'1': 1, '2': 1, '3': 0, '4': 0}
    for enabled in (1, 0, 1):
        response = product_client.post('/server/services/11', data={
            'jsonDatas': json.dumps({**flags, '7': enabled}), 'changeServerServicesServer': 'Product HAProxy',
        })
        assert response.status_code == 200 and response.text == 'ok'
        server = Server.get_by_id(11)
        assert server.corosync == enabled and server.haproxy == server.nginx == 1
        html = BeautifulSoup(product_client.get('/server/services/11').text, 'html.parser')
        assert bool(html.select('#checked_services #remove_service-7')) == bool(enabled)
        assert bool(html.select('#all_services #add_service-7')) == (not enabled)
    response = product_client.post('/server/services/11', data={
        'jsonDatas': json.dumps(flags), 'changeServerServicesServer': 'Product HAProxy',
    })
    assert response.text == 'ok'
    assert Server.get_by_id(11).corosync == 1
    assert product_client.get('/api/server/11').json['corosync'] == 1


def test_server_service_update_rejects_foreign_group_and_invalid_flags(product_client, product):
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    data = {'jsonDatas': json.dumps({'1': 1, '2': 1, '3': 0, '4': 0, '7': 1}), 'changeServerServicesServer': 'Other'}
    assert product_client.post('/server/services/22', data=data).status_code == 403
    data['jsonDatas'] = json.dumps({'1': 1, '2': 1, '3': 0, '4': 0, '7': 2})
    assert 'error:' in product_client.post('/server/services/11', data=data).text
    assert Server.get_by_id(11).corosync == Server.get_by_id(22).corosync == 0


@pytest.mark.parametrize('installed', [False, True])
def test_server_scan_detects_corosync_configuration(product, monkeypatch, installed):
    monkeypatch.setattr(server_module, 'is_file_exists', lambda ip, path: installed and path == '/etc/corosync/corosync.conf')
    monkeypatch.setattr(server_module, 'is_service_active', lambda *args: False)
    monkeypatch.setattr(server_module, 'get_system_info', lambda *args: None)
    server_module.update_server_after_creating(product.server.hostname, product.server.ip)
    assert Server.get_by_id(11).corosync == int(installed)


def test_queued_corosync_operation_rechecks_its_own_permission(product, readiness_cluster, monkeypatch):
    task = operations.enqueue(readiness_cluster.cluster, product.admin.user_id, 'agent-repositories')
    calls = []
    monkeypatch.setattr('app.modules.pacemaker.agents.refresh_repositories', lambda *args: calls.append(args))
    grant(product, '5')
    assert operations.execute(task) == 'failed'
    assert not calls
    task = operations.enqueue(readiness_cluster.cluster, product.admin.user_id, 'agent-repositories')
    grant(product, '7')
    assert operations.execute(task) == 'completed'
    assert len(calls) == 1


def test_readiness_worker_and_map_respect_corosync_permission(product, readiness_cluster):
    task = ha_readiness.enqueue('pacemaker', readiness_cluster.cluster.id, 1, product.admin.user_id)
    grant(product, '5')
    assert ha_readiness.execute(InstallationTasks.get_by_id(task.task_id)) == 'failed'
    assert readiness_cluster.calls == []
    assert service_map.ha_dependencies(1, product.admin.user_id, {11, 33}) == {}
    grant(product, '7')
    result = service_map.ha_dependencies(1, product.admin.user_id, {11, 33})
    assert result[11][0]['provider'] == 'pacemaker'


def test_maintenance_and_change_center_cannot_bypass_corosync_access(product_client, product, readiness_cluster):
    response = product_client.post('/ha/api/maintenance', json={
        'provider': 'pacemaker', 'cluster_id': readiness_cluster.cluster.id, 'server_id': 11,
        'title': 'OS update', 'capacity_confirmed': True, 'capacity_evidence': 'Capacity checked',
    })
    assert response.status_code == 201, response.text
    plan = response.json['data']
    assert ConfigChange.get_by_id(plan['change_id']).service == 'corosync'
    grant(product, '5')
    assert product_client.post(f"/ha/api/maintenance/{plan['id']}/review", json={}).status_code == 403
    assert product_client.get(f"/changes/api/{plan['change_id']}").status_code == 403
    assert product_client.get('/ha/api/maintenance').json['data'] == []
    assert product_client.get('/ha/api/maintenance/active').json['data'] == []
    grant(product, '7')
    assert product_client.get('/ha/api/maintenance').json['data'][0]['id'] == plan['id']
    assert product_client.get(f"/changes/api/{plan['change_id']}").status_code == 200


def test_query_provider_cannot_override_maintenance_body_permissions(product_client, product, readiness_cluster):
    grant(product, '5')
    response = product_client.post('/ha/api/maintenance?provider=keepalived', json={
        'provider': 'pacemaker', 'cluster_id': readiness_cluster.cluster.id, 'server_id': 11,
        'title': 'OS update', 'capacity_confirmed': True, 'capacity_evidence': 'Capacity checked',
    })
    assert response.status_code == 403
    assert HaMaintenancePlan.select().count() == 0


def test_maintenance_approvers_need_access_to_the_selected_provider(product):
    grant(product, '5')
    reviewer = User.create(username='corosync-reviewer', email='reviewer@example.test', role_id=2,
                           group_id=1, user_services='7')
    UserGroups.create(user_id=reviewer.user_id, user_group_id=1, user_role_id=2)
    keepalived = {row['id'] for row in ha_maintenance.approvers(1, 'keepalived')}
    corosync = {row['id'] for row in ha_maintenance.approvers(1, 'pacemaker')}
    assert product.admin.user_id in keepalived and product.admin.user_id not in corosync
    assert reviewer.user_id in corosync and reviewer.user_id not in keepalived


def test_cluster_certificate_operations_recheck_corosync_access(product, readiness_cluster, monkeypatch):
    grant(product, '1 5')
    with pytest.raises(certificates.CertificateError) as denied:
        certificate_operations.enqueue(11, 1, product.admin.user_id, 'site.pem', '', '', str(uuid4()),
                                       cluster_id=readiness_cluster.cluster.id)
    assert denied.value.code == 'permission_denied'
    payload = dict(server_id=11, cluster_id=readiness_cluster.cluster.id, name='site.pem', phase='apply', targets={})
    task = InstallationTasks.create(service_name='HAProxy certificates', operation_type='certificate',
                                    operation_id=str(uuid4()), operation_payload=serialize_operation_payload(payload),
                                    server_ids=[11], group_id=1, user_id=product.admin.user_id, status='created')
    monkeypatch.setattr(certificates, 'targets_for', lambda *args, **kwargs: pytest.fail('Must not contact revoked targets'))
    assert certificate_operations.execute(task) == 'failed'
    result = deserialize_operation_payload(InstallationTasks.get_by_id(task.id).operation_payload)
    assert result['error_code'] == 'permission_denied'


def test_corosync_migration_preserves_access_children_and_manual_choices(product, readiness_cluster):
    migration = importlib.import_module('app.modules.db.migrations.20261114010000_corosync_service')
    Services.delete().where(Services.service_id == 7).execute()
    grant(product, '1 5')
    user = User.create(username='no-ha', email='no-ha@example.test', role_id=4, group_id=1, user_services='1 17')
    # Simulate a database from before the new field while retaining real child rows.
    product.db.execute_sql('CREATE TABLE corosync_child (server_id INTEGER REFERENCES servers(id) ON DELETE CASCADE)')
    product.db.execute_sql('INSERT INTO corosync_child VALUES (11)')
    product.db.execute_sql('ALTER TABLE servers DROP COLUMN corosync')
    PacemakerEvent.create(cluster=readiness_cluster.cluster, user_id=product.admin.user_id, action='bootstrap', status='completed')
    PacemakerCluster.create(name='Draft cluster', group_id=2, servers=json.dumps([{'server_id': 22}]))
    change = ConfigChange.create(server_id=11, group_id=1, user_id=product.admin.user_id, service='cluster',
                                 action='ha-maintenance', title='Legacy plan', remote_path='', draft_path='', rollback_path='')
    HaMaintenancePlan.create(group_id=1, user_id=product.admin.user_id, provider='pacemaker',
                             cluster_id=readiness_cluster.cluster.id, server_id=11, change_id=change.id, payload='{}')
    migration.up()
    assert User.get_by_id(product.admin.user_id).user_services.split() == ['1', '5', '7']
    assert User.get_by_id(user.user_id).user_services == '1 17'
    assert Server.get_by_id(11).corosync == Server.get_by_id(33).corosync == 1
    assert Server.get_by_id(22).corosync == 0
    assert ConfigChange.get_by_id(change.id).service == 'corosync'
    assert product.db.execute_sql('SELECT server_id FROM corosync_child').fetchall() == [(11,)]
    grant(product, '1 5')
    Server.update(corosync=0).where(Server.server_id == 11).execute()
    migration.up()
    assert User.get_by_id(product.admin.user_id).user_services == '1 5'
    assert Server.get_by_id(11).corosync == 0
    assert Services.select().where(Services.service_id == 7).count() == 1
    assert '7' in User.create(username='new', email='new@example.test', role_id=4, group_id=1).user_services.split()
