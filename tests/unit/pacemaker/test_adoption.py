import json

import pytest

from app.modules.db.db_model import PacemakerCluster, PacemakerChange, Server
from app.modules.pacemaker import adoption, service
from app.modules.pacemaker.schemas import Adoption, CorosyncCandidate, Member
from app.modules.pacemaker.xml import digest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound

CIB = '<cib><configuration><crm_config/><nodes><node id="1" uname="adopt-node-1"/><node id="2" uname="adopt-node-2"/></nodes><resources><primitive id="fence"><instance_attributes id="attrs"><nvpair id="secret" name="password" value="keep-this-secret"/></instance_attributes></primitive></resources><constraints/></configuration></cib>'
STATUS = '<pacemaker-result><summary><current_dc name="adopt-node-1" with_quorum="true"/></summary><nodes/><resources/></pacemaker-result>'
CMAP = '''totem.cluster_name (str) = adopt-test
nodelist.node.0.name (str) = adopt-node-1
nodelist.node.0.nodeid (u32) = 1
nodelist.node.0.ring0_addr (str) = 192.0.2.211
nodelist.node.1.name (str) = adopt-node-2
nodelist.node.1.nodeid (u32) = 2
nodelist.node.1.ring0_addr (str) = 192.0.2.212
quorum.device.model (str) = net
quorum.device.net.host (str) = witness.example.test
totem.token (u32) = 3000
'''


@pytest.fixture
def running_cluster(monkeypatch):
    servers = [Server.create(hostname=f'adopt-node-{i}', ip=f'192.0.2.{210+i}', group_id='1') for i in (1, 2)]
    calls = []
    state = {'cmap': CMAP, 'xml': CIB, 'status': STATUS, 'config': 'custom transport and witness configuration'}

    class Remote:
        def __init__(self, server):
            self.server = server

        def run(self, args, **kwargs):
            calls.append((self.server.server_id, args))
            if args == ['corosync-cmapctl', 'runtime.votequorum.this_node_id']:
                return f'runtime.votequorum.this_node_id (u32) = {servers.index(self.server) + 1}\n'
            assert args == ['python3', '-c', adoption.INSPECT]
            return json.dumps(state)

    monkeypatch.setattr(adoption, 'Remote', Remote)
    yield servers, calls, state
    for cluster in PacemakerCluster.select().where(PacemakerCluster.name == 'adopt-test'):
        cluster.delete_instance(recursive=True)
    for server in servers:
        server.delete_instance()


def body_for(servers):
    found = adoption.discover(servers[0].server_id, 1)
    return Adoption(name=found['name'], members=found['members'], seed_server_id=servers[0].server_id,
                    base_digest=found['base_digest'], topology_digest=found['topology_digest'])


def test_discovery_maps_registered_servers_and_does_not_expose_cib_secrets(running_cluster):
    servers, calls, _state = running_cluster
    found = adoption.discover(servers[0].server_id, 1)
    assert [member['server_id'] for member in found['members']] == [server.server_id for server in servers]
    assert found['settings']['qdevice_host'] == 'witness.example.test'
    assert 'keep-this-secret' not in json.dumps(found)
    assert 'xml' not in found and 'config' not in found
    assert len(calls) == 1


def test_adoption_verifies_all_nodes_and_keeps_an_encrypted_baseline(running_cluster):
    servers, calls, _state = running_cluster
    body = body_for(servers)
    cluster = adoption.adopt(body, 1, 1)
    settings = json.loads(cluster.corosync_settings)
    assert settings['adopted'] and settings['membership_managed'] is False
    assert settings['qdevice_host'] == 'witness.example.test'
    baseline = PacemakerChange.get(PacemakerChange.cluster == cluster.id)
    assert baseline.status == 'applied' and baseline.base_digest == digest(CIB)
    assert 'keep-this-secret' not in baseline.previous + baseline.candidate + baseline.details
    assert service.decrypt(baseline.candidate) == CIB
    assert len(json.loads(service.decrypt(baseline.details))['corosync']) == 2
    assert {server_id for server_id, _args in calls} == {server.server_id for server in servers}
    assert adoption.discover(servers[0].server_id, 1)['existing_cluster_id'] == cluster.id


@pytest.mark.parametrize('field', ['xml', 'cmap'])
def test_adoption_rejects_changes_since_discovery_without_registering(running_cluster, field):
    servers, _calls, state = running_cluster
    body = body_for(servers)
    state[field] = state[field].replace('adopt-node-2', 'changed-node')
    with pytest.raises(RoxywiConflictError):
        adoption.adopt(body, 1, 1)
    assert not PacemakerCluster.select().where(PacemakerCluster.name == 'adopt-test').exists()


def test_swapped_node_mapping_is_rejected(running_cluster):
    servers, _calls, _state = running_cluster
    body = body_for(servers)
    body.members[0].server_id, body.members[1].server_id = body.members[1].server_id, body.members[0].server_id
    with pytest.raises(ValueError, match='wrong Corosync node ID'):
        adoption.adopt(body, 1, 1)
    assert not PacemakerCluster.select().where(PacemakerCluster.name == 'adopt-test').exists()


def test_discovery_rejects_a_server_outside_the_group_before_ssh(running_cluster):
    servers, calls, _state = running_cluster
    with pytest.raises(RoxywiResourceNotFound):
        adoption.discover(servers[0].server_id, 2)
    assert not calls


def test_adopted_transport_and_witness_cannot_be_overwritten(running_cluster):
    from app.modules.pacemaker.corosync import draft
    from app.modules.pacemaker.bootstrap import provision
    servers, calls, _state = running_cluster
    body = body_for(servers)
    cluster = adoption.adopt(body, 1, 1)
    count = len(calls)
    with pytest.raises(ValueError, match='Adopted Corosync settings are preserved'):
        draft(cluster, 1, CorosyncCandidate(name=body.name, members=body.members))
    with pytest.raises(ValueError, match='cannot be bootstrapped'):
        provision(cluster, 1)
    assert len(calls) == count


def test_unmapped_or_ambiguous_nodes_need_explicit_mapping(running_cluster):
    servers, _calls, _state = running_cluster
    Server.update(hostname='different-name', ip='198.51.100.8').where(Server.server_id == servers[1].server_id).execute()
    found = adoption.discover(servers[0].server_id, 1)
    assert found['members'][1]['server_id'] is None


@pytest.mark.parametrize('path', ['/pacemaker/api/discover', '/pacemaker/api/adopt'])
def test_viewer_cannot_discover_or_adopt(client, authenticated, path):
    authenticated[0]['role'] = 4
    assert client.post(path, headers=authenticated[1], json={}).status_code == 403


def test_import_accepts_dns_addresses_and_fqdn_node_names():
    member = Member(server_id=1, name='node-1.example.test', address='cluster-1.example.test', nodeid=1)
    assert member.address == 'cluster-1.example.test'


def test_installation_no_longer_has_cluster_setup(client, authenticated):
    response = client.get('/install', headers=authenticated[1])
    assert response.status_code == 200
    assert 'id="pacemaker-installation"' not in response.text
    assert '/install/pacemaker' not in response.text
    authenticated[0]['user_services'] = '1 2 3 4 6'
    response = client.get('/install', headers=authenticated[1])
    assert response.status_code == 200
    assert 'id="pacemaker-installation"' not in response.text


def test_discovery_and_adoption_http_flow(client, authenticated, running_cluster):
    servers, _calls, _state = running_cluster
    response = client.post('/pacemaker/api/discover', headers=authenticated[1], json={'server_id': servers[0].server_id})
    assert response.status_code == 200
    found = response.json['data']
    response = client.post('/pacemaker/api/adopt', headers=authenticated[1], json={
        'name': found['name'], 'members': found['members'], 'seed_server_id': servers[0].server_id,
        'base_digest': found['base_digest'], 'topology_digest': found['topology_digest'],
    })
    assert response.status_code == 201
    assert response.json['data']['corosync_settings']['adopted'] is True
