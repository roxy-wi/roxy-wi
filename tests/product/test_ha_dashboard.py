"""Unified HA inventory, scoped histories and links use real group permissions."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.modules.db.db_model import (
    ConfigChange, HaCluster, HaClusterSlave, HaMaintenancePlan, OperationalAssessment,
    PacemakerCluster, Server, UserGroups,
)
from app.modules.service import ha_readiness as audit
from app.modules.pacemaker.remote import RemoteError
from tests.product.test_ha_readiness import readiness_cluster, keepalived_registration
from tests.product.test_ha_maintenance import maintenance_cluster, create


def test_inventory_includes_both_providers_and_only_current_group(
    product_client, product, readiness_cluster, monkeypatch,
):
    cluster = keepalived_registration(product, monkeypatch)
    HaClusterSlave.update(master=1).where(
        (HaClusterSlave.cluster_id == cluster.id) & (HaClusterSlave.server_id == 11)
    ).execute()
    HaCluster.create(name='Other group Keepalived', group_id=2, description='Private')
    PacemakerCluster.create(name='Other group Pacemaker', group_id=2)
    monkeypatch.setattr('app.modules.common.common.is_tool', lambda _: False)
    monkeypatch.setattr('app.modules.server.server.ssh_command', lambda *_: pytest.fail('Card inventory must not use SSH'))
    response = product_client.get('/ha/cluster/cards')
    assert response.status_code == 200, response.text
    assert f'id="cluster-{cluster.id}"' in response.text
    assert f'id="pacemaker-cluster-{readiness_cluster.cluster.id}"' in response.text
    assert 'Other group' not in response.text and 'SyntheticSSHPassword' not in response.text
    assert 'master-id-' in response.text and 'Configured master' in response.text
    assert response.text.count('data-ha-action="readiness"') == 2
    assert response.text.count('data-ha-action="maintenance"') == 4
    page = product_client.get('/ha/cluster')
    assert page.status_code == 200 and 'id="ha-clusters"' in page.text
    assert 'href="/ha/readiness"' not in page.text and 'href="/ha/maintenance"' not in page.text
    assert 'id="ha-readiness-dialog"' in page.text and 'id="ha-maintenance-dialog"' in page.text


def test_broken_member_keeps_the_card_visible_without_cross_group_names(
    product_client, readiness_cluster,
):
    Server.update(group_id='2', hostname='private-name').where(Server.server_id == 33).execute()
    response = product_client.get('/ha/cluster/cards')
    assert response.status_code == 200, response.text
    assert 'product-ha' in response.text and 'private-name' not in response.text
    assert 'Cluster member not found in the active group' in response.text


def test_viewers_can_read_cluster_cards_without_mutating_actions(product_client, product, readiness_cluster):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    page = product_client.get('/ha/cluster')
    assert page.status_code == 200
    assert 'id="ha-audit-run"' not in page.text and 'id="ha-maintenance-create"' not in page.text
    cards = product_client.get('/ha/cluster/cards')
    assert cards.status_code == 200
    assert 'data-ha-action="readiness"' in cards.text
    assert 'role="menuitem" data-ha-action="maintenance"' not in cards.text


@pytest.mark.parametrize('condition,expected', [
    ('healthy', 'healthy'), ('quorum', 'quorum-lost'), ('node', 'node-unavailable'),
    ('resource', 'resource-failed'), ('witness', 'witness-unavailable'),
])
def test_live_pacemaker_health_without_background_monitoring(
    product_client, maintenance_cluster, condition, expected,
):
    cluster = maintenance_cluster.cluster
    cluster.monitor_enabled = False
    cluster.health = 'stale-observation'
    cluster.save()
    state = maintenance_cluster.live
    if condition == 'quorum':
        state['quorate'] = False
    elif condition == 'node':
        state['nodes'][0]['online'] = 'false'
    elif condition == 'resource':
        state['resources'][0]['failed'] = 'true'
    elif condition == 'witness':
        state['quorum_details']['votes'] = 0
    response = product_client.get(f'/pacemaker/api/{cluster.id}/status')
    assert response.status_code == 200, response.text
    assert response.json['health'] == expected
    assert response.json['data'] == state
    # Reading a card must not enable monitoring or overwrite its saved observation.
    saved = PacemakerCluster.get_by_id(cluster.id)
    assert saved.monitor_enabled is False and saved.health == 'stale-observation'


def test_live_status_failure_and_cross_group_access(product_client, maintenance_cluster, monkeypatch):
    calls = []

    def unavailable(cluster):
        calls.append(cluster.id)
        raise RemoteError('Private SSH detail')

    monkeypatch.setattr('app.modules.pacemaker.service.status', unavailable)
    cluster = maintenance_cluster.cluster
    response = product_client.get(f'/pacemaker/api/{cluster.id}/status')
    assert response.status_code == 502
    assert 'Private SSH detail' not in response.text and 'health' not in response.json
    cluster.group_id = 2
    cluster.save()
    assert product_client.get(f'/pacemaker/api/{cluster.id}/status').status_code == 404
    assert calls == [cluster.id]


@pytest.mark.parametrize('query', ['provider=pacemaker', 'cluster_id=1', 'provider=other&cluster_id=1',
                                   'provider=pacemaker&cluster_id=0', 'before=-1'])
def test_history_filter_validation(product_client, query):
    assert product_client.get('/ha/api/maintenance?' + query).status_code == 400


def test_maintenance_history_keeps_old_active_plan_and_paginates_terminal_plans(
    product_client, maintenance_cluster, product, monkeypatch,
):
    active = create(product_client, maintenance_cluster)
    # More history than one page must not hide an older unfinished plan.
    for index in range(53):
        row = create(product_client, maintenance_cluster)
        ConfigChange.update(status='cancelled').where(ConfigChange.id == row.change_id).execute()
    other = keepalived_registration(product, monkeypatch)
    response = product_client.get(f'/ha/api/maintenance?provider=keepalived&cluster_id={other.id}')
    assert response.json['data'] == []
    url = f'/ha/api/maintenance?provider=pacemaker&cluster_id={maintenance_cluster.cluster.id}'
    first = product_client.get(url)
    assert first.status_code == 200, first.text
    assert len(first.json['data']) == 51 and first.json['data'][0]['id'] == active.id
    second = product_client.get(url + '&before=' + str(first.json['next_before']))
    assert len(second.json['data']) == 4 and second.json['next_before'] is None
    assert second.json['data'][0]['id'] == active.id
    assert len({plan['id'] for plan in first.json['data'] + second.json['data']}) == 54
    # Direct links also find an old history entry outside the first page.
    oldest = second.json['data'][-1]
    linked = product_client.get(url + '&change_id=' + str(oldest['change_id']))
    assert oldest['id'] in [plan['id'] for plan in linked.json['data']]
    summary = product_client.get('/ha/api/maintenance/active')
    assert [plan['id'] for plan in summary.json['data']] == [active.id]
    assert 'capacity_evidence' not in summary.json['data'][0]
    maintenance_cluster.cluster.readiness_key = 'f' * 32
    maintenance_cluster.cluster.save()
    assert product_client.get(url).json['data'] == []
    assert product_client.get('/ha/api/maintenance/active').json['data'] == []


def test_readiness_history_cursor_is_scoped_to_registration(product_client, readiness_cluster):
    for _ in range(23):
        OperationalAssessment.create(group_id=1, user_id=1, kind='ha-readiness',
                                     subject=audit.subject_key('pacemaker', readiness_cluster.cluster), status='failed')
    OperationalAssessment.create(group_id=2, user_id=1, kind='ha-readiness',
                                 subject=audit.subject_key('pacemaker', readiness_cluster.cluster), status='failed')
    url = f'/ha/api/readiness/pacemaker/{readiness_cluster.cluster.id}'
    first = product_client.get(url)
    assert first.status_code == 200, first.text
    assert len(first.json['assessments']) == 20
    second = product_client.get(url + '?before=' + str(first.json['next_before']))
    assert len(second.json['assessments']) == 3 and second.json['next_before'] is None
    assert not ({row['id'] for row in first.json['assessments']} & {row['id'] for row in second.json['assessments']})
    assert product_client.get(url + '?before=-1').status_code == 400


def test_old_plan_link_redirects_to_its_cluster_and_is_group_scoped(product_client, maintenance_cluster):
    row = create(product_client, maintenance_cluster)
    response = product_client.get(f'/ha/maintenance?change={row.change_id}')
    assert response.status_code == 302
    url = urlparse(response.location)
    assert url.path == '/ha/cluster'
    assert parse_qs(url.query) == dict(panel=['maintenance'], provider=['pacemaker'],
                                     cluster=[str(row.cluster_id)], change=[str(row.change_id)])
    HaMaintenancePlan.update(group_id=2).where(HaMaintenancePlan.id == row.id).execute()
    assert product_client.get(f'/ha/maintenance?change={row.change_id}').status_code == 404
    assert product_client.get('/ha/api/maintenance/active').json['data'] == []
