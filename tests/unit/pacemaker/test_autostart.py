import json
from types import SimpleNamespace
import pytest
from app.modules.pacemaker import autostart,service
from app.modules.db.db_model import Server, InstallationTasks
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.roxywi.exception import RoxywiValidationError

XML='<cib><configuration><resources><primitive id="web" class="systemd" type="haproxy"/><primitive id="nginx" class="ocf" provider="heartbeat" type="nginx"/></resources></configuration></cib>'


def test_only_actual_cluster_owned_applications_are_guarded():
    assert autostart.owned_services(XML)=={'haproxy','nginx'}


@pytest.fixture
def cluster():
    nodes=[Server.create(hostname=f'autostart-node-{n}',ip=f'192.0.2.{230+n}',group_id='1') for n in (1,2)]
    cluster=service.register(ClusterCreate(name='autostart-lab',members=[dict(server_id=s.server_id,name=s.hostname,address=s.ip,nodeid=n) for n,s in enumerate(nodes,1)]),1)
    yield cluster
    InstallationTasks.delete().where(InstallationTasks.service_name.contains('autostart-lab')).execute()
    cluster.delete_instance(recursive=True)
    for node in nodes:node.delete_instance()


def test_legacy_proxy_controls_cannot_restart_a_pacemaker_resource(cluster,monkeypatch):
    member=service.members(cluster)[0][0]
    monkeypatch.setattr(service,'connection',lambda _:(None,XML))
    with pytest.raises(RoxywiValidationError,match='managed by Pacemaker'):autostart.assert_unmanaged(member.server_id,'haproxy')
    autostart.assert_unmanaged(member.server_id,'apache')


def test_failed_policy_write_restores_every_attempted_node(cluster,monkeypatch):
    before=[dict(unit='corosync',source=None,digest='a'*64)]
    calls=[]
    monkeypatch.setattr(autostart,'read_node',lambda _:before)
    monkeypatch.setattr(autostart,'conflicts',lambda _:[])
    def run(remote,_args,**kwargs):
        data=json.loads(kwargs['data']);calls.append((remote.server.server_id,data['action']))
        if data['action']=='set' and len(calls)==2:raise RuntimeError('connection lost')
        return '[]'
    monkeypatch.setattr(autostart.Remote,'run',run)
    with pytest.raises(RoxywiValidationError,match='previous settings restored'):
        autostart.apply(cluster,1,dict(policy='on-failure',confirm=cluster.name))
    assert [action for _id,action in calls]==['set','set','restore','restore']


def test_proxy_conflicts_require_explicit_coordination(cluster,monkeypatch):
    monkeypatch.setattr(autostart,'read_node',lambda _:[])
    monkeypatch.setattr(autostart,'conflicts',lambda _:[dict(server_id=1,service='haproxy',node='node')])
    monkeypatch.setattr(autostart.Remote,'run',lambda *_args,**_kwargs:pytest.fail('Unreviewed conflict reached a host write'))
    with pytest.raises(RoxywiValidationError,match='conflicting'):
        autostart.apply(cluster,1,dict(policy='on-failure',coordinate_proxy_autostart=False,confirm=cluster.name))


def test_autostart_api_is_operator_only_and_requires_cluster_confirmation(cluster,client,authenticated,monkeypatch):
    monkeypatch.setattr(autostart,'status',lambda _:dict(nodes=[],proxy_conflicts=[]))
    url=f'/pacemaker/api/{cluster.id}/autostart'
    assert client.get(url,headers=authenticated[1]).status_code==200
    assert client.post(url,headers=authenticated[1],json={'policy':'on-failure','confirm':'wrong'}).status_code==400
    assert client.post(url,headers=authenticated[1],json={'policy':'on-failure','confirm':cluster.name}).status_code==202
    authenticated[0]['role']=4
    assert client.get(url,headers=authenticated[1]).status_code==403
    assert client.post(url,headers=authenticated[1],json={'policy':'on-failure','confirm':cluster.name}).status_code==403
