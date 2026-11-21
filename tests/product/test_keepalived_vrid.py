"""Real HA mutation APIs allocate VRIDs atomically and retain them on edits."""
import pytest

from app.modules.db import ha_cluster as ha_sql
from app.modules.db.db_model import (
    HaCluster, HaClusterRouter, HaClusterService, HaClusterSlave, HaClusterVip, Server,
)


@pytest.fixture
def members(product):
    Server.create(server_id=33, hostname='Standby', ip='192.0.2.33', group_id='1', cred_id=11)
    return [dict(id=11, eth='eth0', master=True), dict(id=33, eth='eth0', master=False)]


def cluster_body(members):
    return dict(name='New VRRP cluster', description='VRID regression', syn_flood=False,
                services={'haproxy': {'enabled': True}}, servers=members,
                vip='192.0.2.100', virt_server=False, reconfigure=False)


def vip_body(members, address='192.0.2.101'):
    return dict(vip=address, virt_server=False, servers=members)


def test_cluster_and_vip_use_independent_stable_vrids(product_client, members):
    other = HaCluster.create(name='Existing', group_id=2, description='Other group')
    HaClusterRouter.create(id=1000, cluster_id=other, vrid=1)
    response = product_client.post('/api/ha/cluster', json=cluster_body(members))
    assert response.status_code == 201, response.text
    cluster_id = response.json['id']
    router = HaClusterRouter.get(HaClusterRouter.cluster_id == cluster_id)
    assert router.id == 1001 and router.vrid == 1
    response = product_client.post(f'/api/ha/cluster/{cluster_id}/vip', json=vip_body(members))
    assert response.status_code == 201, response.text
    second = HaClusterVip.get_by_id(response.json['id']).router_id
    assert second.id == 1002 and second.vrid == 2
    body = cluster_body(members)
    body.update(name='Edited cluster', return_master=False)
    response = product_client.put(f'/api/ha/cluster/{cluster_id}', json=body)
    assert response.status_code == 201, response.text
    assert HaClusterRouter.get_by_id(router.id).vrid == 1
    assert HaClusterRouter.get_by_id(second.id).vrid == 2


@pytest.mark.parametrize('operation', ('cluster', 'vip'))
def test_exhausted_pool_is_local_to_one_cluster(product_client, members, operation):
    owner = HaCluster.create(name='Existing', group_id=1, description='Full pool')
    HaClusterRouter.insert_many([
        {'cluster_id': owner.id, 'vrid': vrid} for vrid in range(1, 256)
    ]).execute()
    if operation == 'cluster':
        response = product_client.post('/api/ha/cluster', json=cluster_body(members))
        assert response.status_code == 201, response.text
        router = HaClusterRouter.get(HaClusterRouter.cluster_id == response.json['id'])
        assert router.vrid == 1
        assert HaCluster.select().count() == 2
        return
    else:
        response = product_client.post(f'/api/ha/cluster/{owner.id}/vip', json=vip_body(members))
    assert response.status_code == 409, response.text
    assert 'No free Keepalived VRID' in response.text
    assert HaCluster.select().count() == 1
    assert HaClusterRouter.select().count() == 255
    assert HaClusterVip.select().count() == 0
    assert HaClusterSlave.select().count() == 0
    assert HaClusterService.select().count() == 0


def test_failed_member_creation_rolls_back_cluster_and_vrid(product_client, members, monkeypatch):
    insert = ha_sql.insert_or_update_slave

    def fail_second_member(cluster_id, server_id, *args):
        if server_id == 33:
            raise RuntimeError('Simulated member write failure')
        return insert(cluster_id, server_id, *args)

    with monkeypatch.context() as patch:
        patch.setattr(ha_sql, 'insert_or_update_slave', fail_second_member)
        response = product_client.post('/api/ha/cluster', json=cluster_body(members))
        assert response.status_code >= 400, response.text
    for model in (HaCluster, HaClusterRouter, HaClusterVip, HaClusterSlave, HaClusterService):
        assert model.select().count() == 0
    response = product_client.post('/api/ha/cluster', json=cluster_body(members))
    assert response.status_code == 201, response.text
    assert HaClusterRouter.get().vrid == 1


def test_failed_vip_creation_releases_only_its_new_reservation(product_client, members):
    response = product_client.post('/api/ha/cluster', json=cluster_body(members))
    assert response.status_code == 201, response.text
    cluster_id = response.json['id']
    response = product_client.post(f'/api/ha/cluster/{cluster_id}/vip',
                                   json=vip_body(members, '192.0.2.100'))
    assert response.status_code >= 400, response.text
    assert HaClusterRouter.select().count() == 1
    assert HaClusterVip.select().count() == 1
    assert HaClusterSlave.select().count() == 2
    assert HaClusterRouter.get().vrid == 1
    response = product_client.post(f'/api/ha/cluster/{cluster_id}/vip', json=vip_body(members))
    assert response.status_code == 201, response.text
    assert HaClusterVip.get_by_id(response.json['id']).router_id.vrid == 2


def test_manual_create_and_edit_round_trip_and_preserve_omitted_values(product_client, members):
    body = dict(cluster_body(members), vrid=42)
    response = product_client.post('/api/ha/cluster', json=body)
    assert response.status_code == 201, response.text
    cluster_id = response.json['id']
    assert product_client.get(f'/api/ha/cluster/{cluster_id}').json['vrid'] == 42
    body['vrid'] = 43
    response = product_client.put(f'/api/ha/cluster/{cluster_id}', json=body)
    assert response.status_code == 201, response.text
    assert product_client.get(f'/api/ha/cluster/{cluster_id}').json['vrid'] == 43
    response = product_client.post(f'/api/ha/cluster/{cluster_id}/vip', json=dict(vip_body(members), vrid=255))
    assert response.status_code == 201, response.text
    vip_id = response.json['id']
    url = f'/api/ha/cluster/{cluster_id}/vip/{vip_id}'
    assert product_client.get(url).json['vrid'] == 255
    for value in ({'vrid': 44}, {'vrid': None}, {}):
        response = product_client.put(url, json=dict(vip_body(members), **value))
        assert response.status_code == 201, response.text
        assert product_client.get(url).json['vrid'] == 44
    # An explicit VRID can also update the default router without changing members.
    body.pop('servers')
    body['vrid'] = 45
    response = product_client.put(f'/api/ha/cluster/{cluster_id}', json=body)
    assert response.status_code == 201, response.text
    assert product_client.get(f'/api/ha/cluster/{cluster_id}').json['vrid'] == 45
    response = product_client.get(f'/api/ha/cluster/{cluster_id}/vips')
    assert response.status_code == 200, response.text
    assert {vip['vip']: vip['vrid'] for vip in response.json} == {
        '192.0.2.100': 45, '192.0.2.101': 44,
    }


def test_conflicting_manual_values_leave_cluster_and_vip_unchanged(product_client, members):
    response = product_client.post('/api/ha/cluster', json=dict(cluster_body(members), vrid=10))
    assert response.status_code == 201, response.text
    cluster_id = response.json['id']
    base = f'/api/ha/cluster/{cluster_id}'
    conflict = product_client.post(base + '/vip', json=dict(vip_body(members), vrid=10))
    assert conflict.status_code == 409 and 'already used in this cluster' in conflict.text
    assert HaClusterRouter.select().count() == 1
    response = product_client.post(base + '/vip', json=dict(vip_body(members), vrid=20))
    assert response.status_code == 201, response.text
    vip_id = response.json['id']
    original = product_client.get(base).json
    edited = dict(cluster_body(members), vrid=20, name='Must roll back', services={})
    edited['servers'] = [dict(member, eth='eth9') for member in members]
    response = product_client.put(base, json=edited)
    assert response.status_code == 409 and 'already used in this cluster' in response.text
    assert product_client.get(base).json == original
    response = product_client.put(base + f'/vip/{vip_id}', json=dict(vip_body(members), vrid=10))
    assert response.status_code == 409, response.text
    assert HaClusterVip.get_by_id(vip_id).router_id.vrid == 20


@pytest.mark.parametrize('operation', ('cluster', 'vip'))
@pytest.mark.parametrize('vrid', (0, -1, 256, True, 1.5, '42', ''))
def test_api_rejects_invalid_manual_vrid(product_client, members, operation, vrid):
    if operation == 'cluster':
        response = product_client.post('/api/ha/cluster', json=dict(cluster_body(members), vrid=vrid))
    else:
        owner = HaCluster.create(name='Empty cluster', group_id=1, description='Validation')
        response = product_client.post(f'/api/ha/cluster/{owner.id}/vip',
                                       json=dict(vip_body(members), vrid=vrid))
    assert response.status_code == 400, response.text
    assert HaClusterRouter.select().count() == 0
    assert HaClusterVip.select().count() == 0


def test_failed_vip_edit_rolls_back_vrid_reservation(product_client, members):
    response = product_client.post('/api/ha/cluster', json=cluster_body(members))
    assert response.status_code == 201, response.text
    base = f'/api/ha/cluster/{response.json["id"]}'
    response = product_client.post(base + '/vip', json=dict(vip_body(members), vrid=20))
    assert response.status_code == 201, response.text
    vip_id = response.json['id']
    response = product_client.put(base + f'/vip/{vip_id}',
                                  json=dict(vip_body(members, '192.0.2.100'), vrid=30))
    assert response.status_code >= 400, response.text
    assert HaClusterVip.get_by_id(vip_id).router_id.vrid == 20
    assert HaClusterVip.get_by_id(vip_id).vip == '192.0.2.101'
    response = product_client.post(base + '/vip', json=dict(vip_body(members, '192.0.2.102'), vrid=30))
    assert response.status_code == 201, response.text


def test_manual_vrid_requires_members_when_creating_cluster(product_client):
    response = product_client.post('/api/ha/cluster', json=dict(
        name='Empty', description='No router', services={}, vrid=5,
    ))
    assert response.status_code == 400, response.text
    assert 'Select cluster members' in response.text
    assert HaCluster.select().count() == 0
