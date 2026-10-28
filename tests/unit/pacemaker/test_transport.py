import json
from types import SimpleNamespace
import pytest
from app.modules.pacemaker import transport,service,operations
from app.modules.db.db_model import Server,InstallationTasks
from app.modules.pacemaker.schemas import ClusterCreate

TOKEN='f'*32


def test_recovery_restores_corosync_without_starting_pacemaker(tmp_path,monkeypatch):
    ns={};exec(transport.BASE,ns);ns.update(ROOT=tmp_path,CONFIG=tmp_path/'corosync.conf')
    directory=ns['folder'](TOKEN);directory.mkdir();(directory/'before.conf').write_text('old')
    ns['CONFIG'].write_text('candidate');ns['save'](TOKEN,dict(phase='verifying'))
    calls=[];ns['command']=lambda args,**_:(calls.append(args) or 'loaded')
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    monkeypatch.setattr(ns['shutil'],'which',lambda _:None)
    assert ns['recover'](TOKEN)['phase']=='rolled-back'
    assert ns['CONFIG'].read_text()=='old'
    assert ['systemctl','start','corosync'] in calls
    assert ['systemctl','start','pacemaker'] not in calls


def test_committed_transport_cannot_be_undone_by_late_timer(tmp_path):
    ns={};exec(transport.BASE,ns);ns['ROOT']=tmp_path
    directory=ns['folder'](TOKEN);directory.mkdir();ns['save'](TOKEN,dict(phase='committed'))
    ns['command']=lambda *_args,**_kwargs:pytest.fail('Late timer modified a committed transport')
    assert ns['recover'](TOKEN)['phase']=='committed'


def test_safety_checks_require_stopped_managed_applications_and_fencing(monkeypatch):
    cluster=SimpleNamespace()
    state=dict(quorate=True,nodes=[dict(online='true',unclean='false',standby='true')],resources=[dict(resource_agent='ocf:heartbeat:Dummy',managed='true',active='true',role='Started')])
    monkeypatch.setattr(service,'status',lambda _:state)
    xml='<cib><configuration><crm_config/><resources/></configuration></cib>'
    monkeypatch.setattr(service,'connection',lambda _:(None,xml))
    with pytest.raises(Exception,match='Quiesce'):transport.safe_state(cluster,stopped=True)
    state['resources'][0].update(active='false',role='Stopped');transport.safe_state(cluster,stopped=True)
    state['resources'][0]['managed']='false'
    with pytest.raises(Exception,match='unmanaged'):transport.safe_state(cluster)
    state['resources']=[]
    monkeypatch.setattr(service,'connection',lambda _:(None,xml.replace('<crm_config/>','<crm_config><cluster_property_set><nvpair name="stonith-enabled" value="false"/></cluster_property_set></crm_config>')))
    with pytest.raises(Exception,match='fencing'):transport.safe_state(cluster)


def test_node_programs_compile():
    compile(transport.BASE,'recovery','exec');compile(transport.REMOTE,'remote','exec')


@pytest.fixture
def cluster():
    nodes=[Server.create(hostname=f'transport-node-{n}',ip=f'192.0.2.{220+n}',group_id=1) for n in (1,2)]
    cluster=service.register(ClusterCreate(name='transport-test',members=[dict(server_id=s.server_id,name=s.hostname,address=s.ip,nodeid=n) for n,s in enumerate(nodes,1)]),1)
    yield cluster
    InstallationTasks.delete().where(InstallationTasks.service_name.contains('transport-test')).execute()
    cluster.delete_instance(recursive=True)
    for node in nodes:node.delete_instance()


def test_pending_transport_blocks_other_actions_but_allows_recovery(cluster):
    cluster.corosync_settings=json.dumps(dict(transport_pending=dict(id=TOKEN)));cluster.save()
    with pytest.raises(Exception,match='unfinished transport'):operations.enqueue(cluster,1,'operate',dict(action='online',target='transport-node-1'))
    assert operations.enqueue(cluster,1,'transport-recover',dict(confirm=cluster.name)).id


def test_transport_api_is_operator_only_and_requires_explicit_cluster_confirmation(cluster,client,authenticated,monkeypatch):
    monkeypatch.setattr(transport,'plan',lambda *_:dict(eligible=True,plan_digest='a'*64,pending=None))
    url=f'/pacemaker/api/{cluster.id}/transport'
    assert client.get(url,headers=authenticated[1]).status_code==200
    assert client.post(url,headers=authenticated[1],json=dict(token=1500,plan_digest='a'*64,confirm='wrong')).status_code==400
    assert client.post(url,headers=authenticated[1],json=dict(token=1500,plan_digest='b'*64,confirm=cluster.name)).status_code==409
    assert client.post(url+'/quiesce',headers=authenticated[1],json=dict(confirm='wrong')).status_code==400
    assert client.post(url,headers=authenticated[1],json=dict(token=1500,plan_digest='a'*64,confirm=cluster.name)).status_code==202
    authenticated[0]['role']=4
    assert client.get(url,headers=authenticated[1]).status_code==403
    assert client.post(url+'/quiesce',headers=authenticated[1],json=dict(confirm=cluster.name)).status_code==403
