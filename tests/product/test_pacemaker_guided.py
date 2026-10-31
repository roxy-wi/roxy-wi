from types import SimpleNamespace
import pytest
from app.modules.db.db_model import Server,PacemakerChange,InstallationTasks,UserGroups
from app.modules.pacemaker import service,agents
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.pacemaker.xml import digest,configuration
from tests.unit.pacemaker.test_guided_editor import CIB


@pytest.fixture
def guided_cluster(product,monkeypatch):
    second=Server.create(server_id=12,hostname='second',ip='192.0.2.12',cred_id=11,group_id='1',haproxy=1)
    cluster=service.register(ClusterCreate(name='guided-test',members=[dict(server_id=11,name='one',address=product.server.ip,nodeid=1),dict(server_id=12,name='two',address=second.ip,nodeid=2)]),1)
    calls=[]
    def run(argv,**kwargs):calls.append(argv);return CIB
    monkeypatch.setattr(service,'connection',lambda _cluster:(SimpleNamespace(run=run),CIB))
    monkeypatch.setattr(service,'status',lambda _cluster:dict(quorate=True,nodes=[],resources=[],failures=0))
    monkeypatch.setattr(agents,'metadata',lambda _cluster,agent:dict(agent=agent,parameters=[],actions=[dict(name='monitor',timeout='30s',interval='10s'),dict(name='start',timeout='60s',interval='0s')]))
    return SimpleNamespace(cluster=cluster,calls=calls)


@pytest.mark.parametrize('kind,data',[
 ('topology',dict(node='one',levels=[dict(index=1,devices=['fence-a'])])),
 ('collection',dict(id='web',kind='group',members=['vip','proxy'])),
 ('location-rule',dict(id='prefer',resource='proxy',conditions=[dict(attribute='#uname',value='one')])),
 ('operation',dict(resource='proxy',name='monitor',interval='10s',timeout='30s')),
 ('bundle',dict(id='bundle',engine='podman',image='example/app:1')),
 ('meta',dict(resource='vip',values={'resource-stickiness':'100'}))])
def test_authenticated_guided_edits_create_encrypted_drafts_without_actions(product_client,guided_cluster,kind,data):
    ident=guided_cluster.cluster.id;url=f'/pacemaker/api/{ident}/guided'
    catalog=product_client.get(url)
    assert catalog.status_code==200 and catalog.json['data']['base_digest']==digest(CIB)
    response=product_client.post(url,json=dict(base_digest=digest(CIB),kind=kind,data=data))
    assert response.status_code==201,response.text
    change=PacemakerChange.get_by_id(response.json['id'])
    assert change.status=='draft' and change.candidate.startswith('gAAAA')
    assert service.decrypt(change.candidate)!=CIB
    assert not InstallationTasks.select().exists() and guided_cluster.calls==[]
    assert product_client.get('/pacemaker/wizard').status_code==200


@pytest.mark.parametrize('condition',['stale','foreign','viewer','csrf','action'])
def test_guided_requests_enforce_scope_role_csrf_and_validation(product_client,product,guided_cluster,condition,monkeypatch):
    ident=guided_cluster.cluster.id;body=dict(base_digest=digest(CIB),kind='topology',data=dict(node='one',levels=[]))
    if condition=='stale':body['base_digest']='0'*64;expected=409
    elif condition=='foreign':guided_cluster.cluster.group_id=2;guided_cluster.cluster.save();expected=404
    elif condition=='viewer':UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute();expected=403
    elif condition=='csrf':product_client.environ_base.pop('HTTP_X_CSRF_TOKEN');expected=401
    else:
        body.update(kind='operation',data=dict(resource='proxy',name='stop',interval='0s'))
        monkeypatch.setattr(agents,'metadata',lambda *_:dict(actions=[dict(name='start')]))
        expected=400
    result=product_client.post(f'/pacemaker/api/{ident}/guided',json=body)
    assert result.status_code==expected,result.text
    assert not PacemakerChange.select().exists() and not guided_cluster.calls
    if condition=='viewer':assert product_client.get('/pacemaker/wizard').status_code==403


def test_draft_is_rechecked_under_existing_lock_before_persistence(product_client,guided_cluster,monkeypatch):
    original=service.connection;calls=[]
    def connection(cluster):
        calls.append(True)
        remote,xml=original(cluster)
        return remote,xml if len(calls)==1 else xml.replace('<constraints/>','<constraints><rsc_location id="new" rsc="vip" node="one" score="1"/></constraints>')
    monkeypatch.setattr(service,'connection',connection)
    response=product_client.post(f'/pacemaker/api/{guided_cluster.cluster.id}/guided',json=dict(base_digest=digest(CIB),kind='meta',data=dict(resource='vip',values={'resource-stickiness':'100'})))
    assert response.status_code==409 and not PacemakerChange.select().exists()
