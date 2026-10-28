import json
from types import SimpleNamespace

import pytest
from defusedxml.common import DefusedXmlException

from app.modules.db.db_model import PacemakerCluster, Server
from app.modules.pacemaker import agents, service, operations, facts
from app.modules.pacemaker.editor import Edit, Resource, build
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.pacemaker.xml import configuration
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError

METADATA = '''<?xml version="1.0"?><!DOCTYPE resource-agent SYSTEM "ra-api-1.dtd">
<resource-agent name="IPaddr2"><shortdesc>Virtual IP</shortdesc><parameters>
<parameter name="ip" required="1"><shortdesc>IP address</shortdesc><content type="string"/></parameter>
<parameter name="cidr_netmask"><content type="string" default="24"/></parameter>
<parameter name="password"><content type="string" default="do-not-disclose"/></parameter>
</parameters><actions><action name="start" timeout="20s"/><action name="monitor" interval="10s" timeout="30s"/></actions></resource-agent>'''


@pytest.fixture
def cluster():
    servers = [Server.create(hostname=f'agent-node-{n}', ip=f'192.0.2.{80+n}', group_id='1') for n in (1, 2)]
    cluster = service.register(ClusterCreate(name='agent-lab', members=[dict(server_id=s.server_id,
        name=s.hostname, address=s.ip, nodeid=n) for n, s in enumerate(servers, 1)]), 1)
    yield cluster
    cluster.delete_instance(recursive=True)
    for server in servers: server.delete_instance()


def test_metadata_accepts_native_dtd_but_blocks_entities_and_masks_secret_defaults():
    data = agents.parse_metadata(METADATA)
    assert data['parameters'][0]['required']
    assert data['parameters'][1]['default'] == '24'
    assert data['parameters'][2]['secret'] and data['parameters'][2]['default'] is None
    assert 'do-not-disclose' not in json.dumps(data)
    with pytest.raises(DefusedXmlException):
        agents.parse_metadata('<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]><resource-agent>&leak;</resource-agent>')


def test_inventory_excludes_incomplete_and_unreachable_nodes_from_ready_agents(cluster, monkeypatch):
    def run(remote, argv, **kwargs):
        return json.dumps(['ocf:heartbeat:Dummy'] + (['stonith:fence_pve'] if remote.server.hostname.endswith('1') else []))
    monkeypatch.setattr(agents.Remote, 'run', run)
    found = agents.inventory(cluster)
    assert next(a for a in found['agents'] if a['id'].endswith('Dummy'))['ready']
    assert not next(a for a in found['agents'] if a['id'].startswith('stonith:'))['ready']
    def unreachable(*args, **kwargs): raise TimeoutError('private SSH diagnostics')
    monkeypatch.setattr(agents.Remote, 'run', unreachable)
    found = agents.inventory(cluster)
    assert found['agents'] == [] and all(n['error'] for n in found['nodes'])
    assert 'private SSH' not in json.dumps(found)


def test_resource_requires_discovered_agent_and_metadata_parameters(cluster, monkeypatch):
    real_metadata = agents.metadata
    monkeypatch.setattr(agents, 'metadata', lambda *_args: agents.parse_metadata(METADATA))
    with pytest.raises(RoxywiValidationError, match='ip'):
        agents.validate_resource(cluster, Resource(id='vip', agent='ocf:heartbeat:IPaddr2'))
    agents.validate_resource(cluster, Resource(id='vip', agent='ocf:heartbeat:IPaddr2', parameters={'ip':'192.0.2.100'}))
    monkeypatch.setattr(agents, 'inventory', lambda _c: {'agents': []})
    with pytest.raises(RoxywiValidationError, match='every cluster node'):
        real_metadata(cluster, 'ocf:heartbeat:NotInstalled')


def test_metadata_drift_rejects_incompatible_required_fields(cluster, monkeypatch):
    monkeypatch.setattr(agents, 'inventory', lambda _c: {'agents':[{'id':'ocf:heartbeat:IPaddr2','ready':True}]})
    def run(remote, _argv, **_kwargs):
        return METADATA if remote.server.hostname.endswith('1') else METADATA.replace('name="ip"', 'name="other"')
    monkeypatch.setattr(agents.Remote, 'run', run)
    with pytest.raises(RoxywiValidationError, match='differ'):
        agents.metadata(cluster, 'ocf:heartbeat:IPaddr2')


def test_package_plan_tracks_each_node_and_rejects_stale_or_unavailable_candidates(cluster, monkeypatch):
    def run(remote, _argv, **kwargs):
        return json.dumps({'error':None,'packages':[{'name':'fence-agents-pve', 'candidate':'4.10-1',
                            'installed':'4.10-1' if remote.server.hostname.endswith('1') else None}]})
    monkeypatch.setattr(agents.Remote, 'run', run)
    result = agents.packages(cluster)['packages'][0]
    assert result['ready'] and result['needed'] and len(result['nodes']) == 2
    assert agents.plan(cluster, result['package'], result['plan_digest']) == result
    with pytest.raises(RoxywiConflictError): agents.plan(cluster, result['package'], '0'*64)
    with pytest.raises(RoxywiValidationError): agents.plan(cluster, '--allow-unauthenticated', '0'*64)
    monkeypatch.setattr(agents.Remote, 'run', lambda *_args, **_kwargs: json.dumps({'packages':[], 'error':'cache unavailable'}))
    with pytest.raises(RoxywiValidationError): agents.plan(cluster, result['package'], result['plan_digest'])


def test_worker_executes_agent_install_through_identity_and_permission_checks(cluster, monkeypatch):
    calls = []
    monkeypatch.setattr(operations.User, 'get_or_none', lambda *_args: SimpleNamespace(user_id=1, enabled=True))
    monkeypatch.setattr(operations.user_sql, 'select_user_services', lambda _id: '5')
    monkeypatch.setattr(operations.user_sql, 'get_user_role_in_group', lambda *_args: 1)
    monkeypatch.setattr(agents, 'install', lambda *args: calls.append(args))
    task = operations.enqueue(cluster, 1, 'agent-install', {'package':'fence-agents-pve','plan_digest':'a'*64})
    assert operations.execute(task) == 'completed' and len(calls) == 1
    task.delete_instance()


@pytest.mark.parametrize('endpoint', ['/agents','/agents/metadata?agent=ocf:heartbeat:Dummy','/agents/packages','/choices'])
def test_discovery_apis_reject_viewers_and_other_groups(cluster, client, authenticated, endpoint):
    authenticated[0]['role'] = 4
    assert client.get(f'/pacemaker/api/{cluster.id}'+endpoint, headers=authenticated[1]).status_code == 403
    authenticated[0]['role'] = 1; authenticated[0]['group_id'] = 2
    assert client.get(f'/pacemaker/api/{cluster.id}'+endpoint, headers=authenticated[1]).status_code == 404


def test_host_facts_are_group_scoped_and_operator_only(cluster, client, authenticated, monkeypatch):
    server = service.members(cluster)[0][1]
    monkeypatch.setattr(facts.Remote, 'run', lambda *_args, **_kwargs: json.dumps({'hostname':'native-name','addresses':[]}))
    url=f'/pacemaker/api/servers/{server.server_id}/facts'
    assert client.get(url, headers=authenticated[1]).json['data']['hostname']=='native-name'
    authenticated[0]['group_id']=2
    assert client.get(url, headers=authenticated[1]).status_code == 404
    authenticated[0]['role']=4
    assert client.get(url, headers=authenticated[1]).status_code == 403


def test_choice_response_contains_ids_but_no_resource_secrets(cluster, client, authenticated, monkeypatch):
    xml='<cib><configuration><resources><primitive id="vip" class="ocf" type="IPaddr2"><instance_attributes><nvpair name="password" value="secret-value"/></instance_attributes></primitive></resources><constraints><rsc_location id="place-vip" rsc="vip"/></constraints></configuration></cib>'
    monkeypatch.setattr(service, 'get_config', lambda _c: {'xml':xml})
    response=client.get(f'/pacemaker/api/{cluster.id}/choices', headers=authenticated[1])
    assert response.status_code==200 and response.json['data']['resources']==[{'id':'vip','type':'primitive'}]
    assert 'secret-value' not in response.text and 'password' not in response.text


def test_operation_timings_from_metadata_are_preserved_in_resource_draft():
    result=build('<cib><configuration/></cib>',Edit(base_digest='a'*64,kind='resource',data={
        'id':'dummy','agent':'ocf:heartbeat:Dummy','start_timeout':'20s','stop_timeout':'25s','monitor_timeout':'30s'}))
    ops=configuration(result.xml).find('./resources/primitive/operations')
    assert {op.get('name'):op.get('timeout') for op in ops}=={'start':'20s','stop':'25s','monitor':'30s'}


def test_package_post_rejects_arbitrary_names_and_requires_reviewed_confirmation(cluster, client, authenticated, monkeypatch):
    calls=[]
    monkeypatch.setattr(operations, 'enqueue', lambda *_args: calls.append(_args) or SimpleNamespace(id=90,status='created'))
    monkeypatch.setattr(agents, 'plan', lambda *_args: {'ready':True})
    url=f'/pacemaker/api/{cluster.id}/agents/packages'
    for name in ('bash', '--allow-unauthenticated', 'fence-agents-pve;id'):
        assert client.post(url,headers=authenticated[1],json={'package':name,'plan_digest':'a'*64,'confirm':cluster.name}).status_code==400
    assert client.post(url,headers=authenticated[1],json={'package':'fence-agents-pve','plan_digest':'a'*64,'confirm':'wrong'}).status_code==400
    assert not calls
    assert client.post(url,headers=authenticated[1],json={'package':'fence-agents-pve','plan_digest':'a'*64,'confirm':cluster.name}).status_code==202
    assert calls[0][2:] == ('agent-install',{'package':'fence-agents-pve','plan_digest':'a'*64})
    authenticated[0]['role']=4
    assert client.post(url,headers=authenticated[1],json={}).status_code==403


def test_dnf_repository_parser_handles_wrapped_package_names_and_versions():
    namespace={}; exec(agents.PACKAGES,namespace)
    namespace['platform_profile']=lambda: {'manager':'dnf'}
    namespace['subprocess']=SimpleNamespace(run=lambda *_args,**_kwargs: SimpleNamespace(returncode=0,stdout='''Installed Packages
fence-agents-common.noarch 4.10-1 @appstream
Available Packages
fence-agents-very-long-vendor-device.x86_64
                       4.10-2 appstream
fence-agents-common.noarch 4.10-2 appstream
'''))
    packages={p['name']:p for p in namespace['native_packages']()}
    assert packages['fence-agents-very-long-vendor-device']['candidate']=='4.10-2'
    assert packages['fence-agents-common']['installed']=='4.10-1'
    assert packages['fence-agents-common']['candidate']=='4.10-2'


def test_install_refuses_changed_repository_plan_before_mutating_any_node(cluster, monkeypatch):
    monkeypatch.setattr(agents,'plan',lambda *_args: (_ for _ in ()).throw(RoxywiConflictError('changed')))
    monkeypatch.setattr(agents.Remote,'run',lambda *_args,**_kwargs: pytest.fail('A stale plan executed a remote write'))
    with pytest.raises(RoxywiConflictError): agents.install(cluster,1,{'package':'fence-agents-pve','plan_digest':'a'*64})
