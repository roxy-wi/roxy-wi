"""Cluster health is based on each VIP, with real group authorization."""
import copy

import pytest

from app.modules.db.db_model import (
    HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip, Server, User,
    UserGroups,
)
from app.modules.service import ha_readiness


@pytest.fixture
def cluster_status(product, monkeypatch):
    Server.create(server_id=33, hostname='Standby', ip='192.0.2.33',
                  group_id='1', cred_id=11)
    cluster = HaCluster.create(name='VIP status', group_id=1, description='Fixture')
    router = HaClusterRouter.create(cluster_id=cluster, default=1)
    vip = HaClusterVip.create(cluster_id=cluster, router_id=router,
                             vip='192.0.2.100/24')
    for ident in (11, 33):
        HaClusterSlave.create(cluster_id=cluster, router_id=router,
                              server_id=ident)
    observations = {
        ident: dict(id=ident, active=True,
                    addresses=['192.0.2.100'] if ident == 11 else [],
                    instances=[dict(name=f'VI_{router.id}',
                                    state='MASTER' if ident == 11 else 'BACKUP')])
        for ident in (11, 33)
    }
    calls = []

    def observe(_cluster, _name, server):
        calls.append(server.server_id)
        result = observations[server.server_id]
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)

    monkeypatch.setattr(ha_readiness, 'keepalived_node', observe)
    return cluster, router, vip, observations, calls


@pytest.mark.parametrize('condition,expected', (
    ('healthy', 'ok'), ('two-owners', 'error'), ('no-owner', 'error'),
    ('two-masters', 'error'), ('two-backups', 'error'),
    ('faulty-backup', 'warning'), ('stopped-backup', 'warning'),
    ('unreachable', 'unknown'), ('stopped-owner', 'error'),
    ('missing-instance', 'unknown'),
))
def test_cluster_status_requires_unique_healthy_vip_owner(
    product_client, cluster_status, condition, expected,
):
    cluster, _router, _vip, observations, calls = cluster_status
    if condition == 'two-owners':
        observations[33]['addresses'] = ['192.0.2.100']
    elif condition == 'no-owner':
        observations[11]['addresses'] = []
    elif condition == 'two-masters':
        observations[33]['instances'][0]['state'] = 'MASTER'
    elif condition == 'two-backups':
        observations[11]['instances'][0]['state'] = 'BACKUP'
        observations[11]['addresses'] = []
    elif condition == 'faulty-backup':
        observations[33]['instances'][0]['state'] = 'FAULT'
    elif condition == 'stopped-backup':
        observations[33].update(active=False, instances=[])
    elif condition == 'unreachable':
        observations[33] = RuntimeError('Private SSH detail')
    elif condition == 'stopped-owner':
        observations[11].update(active=False, instances=[])
    elif condition == 'missing-instance':
        observations[33]['instances'][0]['name'] = 'UNREGISTERED'

    response = product_client.get(f'/ha/cluster/{cluster.id}/status')
    assert response.status_code == 200, response.text
    assert response.json['status'] == expected
    assert response.json['vips'][0]['status'] == expected
    assert response.json['message']
    assert 'Private SSH detail' not in response.text
    assert calls == [11, 33]


def test_status_checks_all_vips_and_allows_different_masters(
    product_client, cluster_status,
):
    cluster, _router, _vip, observations, _calls = cluster_status
    second = HaClusterRouter.create(cluster_id=cluster)
    HaClusterVip.create(cluster_id=cluster, router_id=second,
                        vip='2001:db8::100/64')
    for ident in (11, 33):
        HaClusterSlave.create(cluster_id=cluster, router_id=second,
                              server_id=ident)
        observations[ident]['instances'].append(dict(
            name=f'VI_{second.id}', state='MASTER' if ident == 33 else 'BACKUP',
        ))
    observations[33]['addresses'].append('2001:0db8:0:0:0:0:0:100')
    url = f'/ha/cluster/{cluster.id}/status'
    assert product_client.get(url).json['status'] == 'ok'

    observations[11]['addresses'].append('2001:db8::100')
    response = product_client.get(url)
    assert response.json['status'] == 'error'
    assert [row['status'] for row in response.json['vips']] == ['ok', 'error']


@pytest.mark.parametrize('outside', ('cluster', 'member'))
def test_cluster_status_never_probes_another_group(
    product_client, cluster_status, outside,
):
    cluster, _router, _vip, _observations, calls = cluster_status
    if outside == 'cluster':
        cluster.group_id = 2
        cluster.save()
    else:
        Server.update(group_id='2').where(Server.server_id == 33).execute()
    response = product_client.get(f'/ha/cluster/{cluster.id}/status')
    assert response.status_code == 404
    assert calls == []


def test_cluster_status_no_vips_is_unknown(product_client, cluster_status):
    cluster, _router, vip, _observations, _calls = cluster_status
    vip.delete_instance()
    assert product_client.get(f'/ha/cluster/{cluster.id}/status').json['status'] == 'unknown'


def test_viewer_can_read_status(product_client, product, cluster_status):
    cluster = cluster_status[0]
    UserGroups.update(user_role_id=4).where(
        UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.get(f'/ha/cluster/{cluster.id}/status')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'


@pytest.mark.parametrize('service', ('cluster', 'haproxy'))
def test_status_requires_keepalived_permission(
    product_client, product, cluster_status, service,
):
    cluster, _router, _vip, _observations, calls = cluster_status
    User.update(user_services='1 4').where(
        User.user_id == product.admin.user_id).execute()
    response = product_client.get(f'/ha/{service}/{cluster.id}/status')
    assert response.status_code == 403
    assert calls == []


def test_membership_change_during_probe_cannot_report_healthy(
    product_client, cluster_status, monkeypatch,
):
    cluster, _router, vip, observations, _calls = cluster_status

    def observe(_cluster, _name, server):
        HaClusterVip.update(vip='192.0.2.101').where(
            HaClusterVip.id == vip.id).execute()
        return observations[server.server_id]

    monkeypatch.setattr(ha_readiness, 'keepalived_node', observe)
    response = product_client.get(f'/ha/cluster/{cluster.id}/status')
    assert response.json == {
        'status': 'unknown', 'message': 'Cluster changed during the check',
    }
