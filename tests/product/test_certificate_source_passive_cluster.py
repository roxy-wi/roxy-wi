"""Real source API/worker/journals with a passive Pacemaker member.

SSH status and Runtime sockets are deterministic substitutes; certificate parsing,
authorization, target selection, durable recovery and filesystem writes are real.
"""
from types import SimpleNamespace
import shutil

import pytest

from app.modules.connectors.certificates import CertWarden
from app.modules.db import db_model as models
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.pacemaker import service as clusters
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.service import certificate_sources as sources, certificates
from app.scripts import certificate_cluster_remote as cluster,certificate_remote as remote
from tests.product.test_certificate_source_workflows import API,source_body
from tests.unit.certificates.test_passive_certificate_cluster import CIB,STATUS


@pytest.fixture
def passive_cluster(product,certificate_host,monkeypatch):
    host=certificate_host
    second=models.Server.create(server_id=33,hostname='second',ip='192.0.2.33',group_id=1,haproxy=1,cred_id=11)
    host.add(second.ip,host.old)
    registered=clusters.register(ClusterCreate(name='fixture',members=[
        dict(server_id=11,name='first',address=product.server.ip,nodeid=1),
        dict(server_id=33,name='second',address=second.ip,nodeid=2)]),1)
    original=certificates.remote
    def settings(server,name,**kwargs):
        data=dict(host.settings(server.ip),pem_name=name or 'site.pem',service_unit='haproxy',root=str(host.files[server.ip].parent))
        main=host.files[server.ip].parent/'haproxy.cfg'
        if not main.exists():main.write_text('global\ndefaults\n mode tcp\n timeout connect 1s\n timeout client 1s\n timeout server 1s\nfrontend tls\n bind 127.0.0.1:10443 ssl crt '+str(host.files[server.ip])+'\n')
        data.update(config_path=str(main),validation=dict(service='haproxy',action='check',target=str(main),main=str(main),root=data['root'],sources=[str(main)],container=''))
        return data
    monkeypatch.setattr(certificates,'deployment_settings',settings)
    monkeypatch.setattr(clusters,'connection',lambda _cluster:(SimpleNamespace(run=lambda argv,**kw:STATUS),CIB))
    monkeypatch.setattr(cluster,'run',lambda argv,**kw:{'cibadmin':CIB,'crm_mon':STATUS,'corosync-cmapctl':'totem.cluster_name (str) = fixture','systemctl':'ActiveState=inactive\nMainPID=0','pgrep':''}[argv[0]])
    monkeypatch.setattr(cluster.discovery,'systemd_sources',lambda _unit:([str(host.files[second.ip].parent/'haproxy.cfg')],[],False))
    if not shutil.which('haproxy'):
        monkeypatch.setattr(cluster,'validate_offline',lambda data:True)
        monkeypatch.setattr(remote.passive,'validate_material',lambda *args:None)
    host.passive_writes=[];host.fail_passive=False
    def transport(server,data):
        if server.server_id!=33:return original(server,data)
        data=dict(data)
        if data.get('update_directory'):data['update_directory']=str(host.files[second.ip].parent)
        operation=data['operation']
        if operation=='passive-context':return cluster.context(data)
        if operation=='passive-inspect':return remote.passive.inspect(data,remote)
        if operation=='deploy':
            host.passive_writes.append(operation)
            result=remote.deploy(data)
            if host.fail_passive:
                host.fail_passive=False
                raise certificates.CertificateError('Lost passive acknowledgement','remote_failed')
            return result
        if operation in ('commit','rollback'):return remote.finish_deployment(data)
        pytest.fail('Passive node must not use running certificate catalog or Runtime API: '+operation)
    monkeypatch.setattr(certificates,'remote',transport)
    active_request=host.request
    def request(data,command):
        if data.get('fixture_host')==second.ip:pytest.fail('Passive Runtime API must never be called')
        return active_request(data,command)
    monkeypatch.setattr(remote,'runtime_request',request)
    monkeypatch.setattr(CertWarden,'fetch',lambda _:host.new)
    return registered,second,host


@pytest.mark.parametrize('failure',[False,True])
def test_source_selected_on_passive_member_uses_active_primary_and_recovers_every_target(product_client,passive_cluster,failure):
    registered,second,host=passive_cluster
    response=product_client.post(API,json=dict(source_body(33),cluster_id=registered.id))
    assert response.status_code==201,response.text
    source=response.json['data']['id'];host.fail_passive=failure
    response=product_client.post(f'{API}/{source}/sync',json={})
    assert response.status_code==202,response.text
    assert sources.execute(models.InstallationTasks.get_by_id(response.json['task_id']))==('failed' if failure else 'completed')
    row=models.CertificateSource.get_by_id(source)
    child=models.InstallationTasks.get_by_id(row.deployment_task_id)
    payload=deserialize_operation_payload(child.operation_payload)
    assert payload['server_id']==11 and payload['phase']=='done'
    for file in host.files.values():assert file.read_text()==(host.old if failure else host.new)
    assert all(value==host.old if failure else value==host.new for key,value in host.active.items() if '192.0.2.11' in key)
    assert host.passive_writes==['deploy']
    assert not list(host.root.rglob('pending.json'))
    history=product_client.get('/service/haproxy/certificates/operations/'+str(child.id))
    assert history.status_code==200
    passive=next(item for item in history.json['targets'] if item['address']==second.ip)
    assert passive['verification']=='disk-staged'
    assert 'PRIVATE KEY' not in history.text and 'cluster_proof' not in history.text
    if not failure:
        queued=product_client.post(f'{API}/{source}/sync',json={})
        assert sources.execute(models.InstallationTasks.get_by_id(queued.json['task_id']))=='completed'
        assert models.InstallationTasks.select().where(models.InstallationTasks.operation_type=='certificate').count()==1
        assert host.passive_writes==['deploy']
