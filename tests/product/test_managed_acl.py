import copy
from types import SimpleNamespace
import pytest
from playhouse.shortcuts import model_to_dict
from app.modules.db.db_model import ManagedAclFeed,ManagedAclVersion,InstallationTasks,ConfigChange,User,UserGroups,Server
from app.modules.operations.queue import deserialize_operation_payload as unseal
from app.modules.service import managed_acl as acl
from app.modules.roxywi.exception import RoxywiConflictError
from tests.product.test_ha_maintenance import approve as approve_change

API='/insights/api/acl-feeds'


@pytest.fixture
def acl_host(product,monkeypatch):
    values=model_to_dict(product.admin);values.pop('user_id');values.update(username='acl-reviewer',email='acl-reviewer@example.test',role_id='2')
    reviewer=User.create(**values);UserGroups.create(user_id=reviewer.user_id,user_group_id=1,user_role_id=2)
    state=SimpleNamespace(reviewer=reviewer,content='192.0.2.0/24\n',remote=[],fail_apply=False,fail_rollback=False,fetched=0)
    def fetch(settings):state.fetched+=1;return state.content
    monkeypatch.setattr(acl.ip_feeds.HttpsIpFeed,'fetch',fetch)
    monkeypatch.setattr(acl,'remote_spec',lambda server:dict(root='/etc/haproxy',server_id=server.server_id))
    def remote(server,operation,**data):
        state.remote.append((server.server_id,operation,copy.deepcopy(data)))
        before=dict(path='/etc/haproxy/black/list.lst',runtime_path='/etc/haproxy/black/list.lst',sha256='a'*64,
            content='198.51.100.0/24\n',entries=1,configuration='b'*64,mounts='c'*64,process='101')
        if operation=='discover':return dict(lists=[before],configuration='b'*64)
        if operation=='preview':return before
        if operation=='apply' and (state.fail_apply or getattr(state,'fail_node',None)==server.server_id):raise RoxywiConflictError('SECRET REMOTE OUTPUT')
        if operation=='rollback' and state.fail_rollback:raise RoxywiConflictError('SECRET ROLLBACK OUTPUT')
        return dict(applied=operation=='apply',prepared=operation=='prepare',finished=operation in ('rollback','commit'))
    monkeypatch.setattr(acl,'remote',remote)
    return state


def body(**changes):
    return dict(name='Approved IP source',settings=dict(url='https://feeds.example.test/ips.txt'),targets=[dict(server_id=11,path='/etc/haproxy/black/list.lst')]) | changes


def create(client):
    response=client.post(API,json=body());assert response.status_code==201,response.text
    return response.json['data']


def approve(client,row):
    response=client.post(API+'/'+str(row['id'])+'/approve-source',json=dict(revision=row['revision']));assert response.status_code==200,response.text
    return response.json['data']


def step(client,row,action,version=None,expected='completed'):
    response=client.post(API+'/'+str(row['id'])+'/'+action,json=dict(version_id=version) if version else {})
    assert response.status_code==202,response.text
    assert acl.execute(InstallationTasks.get_by_id(response.json['task_id']))==expected
    return client.get(API+'/'+str(row['id'])+'/versions').json['data']


def reviewed(client,app,state):
    row=approve(client,create(client));value=step(client,row,'fetch')[0];value=step(client,row,'review',value['id'])[0]
    record=ManagedAclVersion.get_by_id(value['id']);approve_change(app,record,state.reviewer)
    return row,value


def test_source_requires_explicit_approval_and_download_never_applies(product_client,acl_host):
    row=create(product_client)
    assert product_client.post(API+'/'+str(row['id'])+'/fetch',json={}).status_code==409
    assert acl_host.fetched==0
    row=approve(product_client,row);versions=step(product_client,row,'fetch')
    assert versions[0]['status']=='downloaded' and versions[0]['entries']==1
    stored=ManagedAclVersion.get_by_id(versions[0]['id']);assert stored.content.startswith('fernet:')
    assert not any(action in ('apply','prepare') for _,action,_ in acl_host.remote)
    assert step(product_client,row,'fetch')[0]['id']==stored.id # unchanged download keeps version identity


def test_review_independent_approval_and_atomic_apply_are_separate(product_client,acl_host,app):
    row=approve(product_client,create(product_client));value=step(product_client,row,'fetch')[0]
    value=step(product_client,row,'review',value['id'])[0]
    assert value['targets'][0]['added']==1 and value['targets'][0]['removed']==1
    assert product_client.post(f"/changes/api/{value['change_id']}/approve",json={}).status_code==403
    assert product_client.post(API+f"/{row['id']}/apply",json=dict(version_id=value['id'])).status_code==409
    record=ManagedAclVersion.get_by_id(value['id']);approve_change(app,record,acl_host.reviewer)
    assert product_client.post(f"/changes/api/{value['change_id']}/deploy",json={}).status_code==400
    assert step(product_client,row,'apply',value['id'])[0]['status']=='deployed'
    assert ManagedAclFeed.get_by_id(row['id']).deployed_version_id==value['id']
    assert [action for _,action,_ in acl_host.remote if action in ('prepare','apply','commit')]==['prepare','apply','commit']


def test_failed_apply_rolls_back_and_failed_compensation_blocks_edits_until_gui_recovery(product_client,acl_host,app):
    row,value=reviewed(product_client,app,acl_host);acl_host.fail_apply=True;acl_host.fail_rollback=True
    values=step(product_client,row,'apply',value['id'],expected='failed')
    assert values[0]['status']=='recovery-required'
    assert product_client.put(API+'/'+str(row['id']),json=body(revision=1)).status_code==409
    assert product_client.delete(API+'/'+str(row['id'])).status_code==409
    assert 'SECRET' not in product_client.get(API).text
    acl_host.fail_rollback=False
    assert step(product_client,row,'recover',value['id'])[0]['status']=='rolled-back'
    assert ConfigChange.get_by_id(value['change_id']).status=='auto_rolled_back'


def test_rollback_to_an_older_version_creates_a_new_independent_review(product_client,acl_host,app):
    row,value=reviewed(product_client,app,acl_host);step(product_client,row,'apply',value['id'])
    acl_host.content='203.0.113.0/24\n';new=step(product_client,row,'fetch')[0]
    assert new['id']!=value['id']
    values=step(product_client,row,'rollback-version',value['id'])
    rollback=values[0]
    assert rollback['id'] not in (value['id'],new['id']) and rollback['change_status']=='pending_approval'
    assert rollback['fingerprint']==value['fingerprint']
    assert ConfigChange.get_by_id(rollback['change_id']).approved_by is None


def test_role_tenant_unregistered_path_and_duplicate_ownership_boundaries(product_client,product,acl_host):
    data=body();data['targets'][0]['path']='/etc/shadow'
    assert product_client.post(API,json=data).status_code==400
    row=create(product_client)
    assert product_client.post(API,json=body()).status_code==409
    ManagedAclFeed.update(group_id=2).where(ManagedAclFeed.id==row['id']).execute()
    assert product_client.post(API+'/'+str(row['id'])+'/fetch',json={}).status_code==404
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert product_client.post(API,json=body()).status_code==403


def test_edit_revokes_source_approval_and_queued_permission_change_prevents_fetch(product_client,product,acl_host):
    row=approve(product_client,create(product_client));response=product_client.put(API+'/'+str(row['id']),json=body(revision=1,name='Changed source'))
    assert response.status_code==200,response.text
    assert response.json['data']['approved_revision'] is None
    row=approve(product_client,response.json['data']);queued=product_client.post(API+'/'+str(row['id'])+'/fetch',json={})
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==product.admin.user_id).execute()
    assert acl.execute(InstallationTasks.get_by_id(queued.json['task_id']))=='failed' and acl_host.fetched==0


def test_revoked_independent_approver_prevents_preparation(product_client,product,acl_host,app):
    row,value=reviewed(product_client,app,acl_host)
    UserGroups.update(user_role_id=4).where(UserGroups.user_id==acl_host.reviewer.user_id).execute()
    assert product_client.post(API+'/'+str(row['id'])+'/apply',json=dict(version_id=value['id'])).status_code==403
    assert not any(action=='prepare' for _,action,_ in acl_host.remote)


def test_reviewed_identity_change_prevents_mutation_even_if_new_queue_identity_matches(product_client,acl_host,app):
    row,value=reviewed(product_client,app,acl_host)
    Server.update(ip='192.0.2.77').where(Server.server_id==11).execute()
    step(product_client,row,'apply',value['id'],expected='failed')
    assert not any(action=='prepare' for _,action,_ in acl_host.remote)


def test_second_node_failure_compensates_every_prepared_node(product_client,product,acl_host,app):
    Server.create(server_id=33,hostname='Peer',ip='192.0.2.33',group_id='1',cred_id=11,haproxy=1)
    data=body();data['targets'].append(dict(server_id=33,path='/etc/haproxy/black/list.lst'))
    response=product_client.post(API,json=data);assert response.status_code==201
    row=approve(product_client,response.json['data']);value=step(product_client,row,'fetch')[0];value=step(product_client,row,'review',value['id'])[0]
    approve_change(app,ManagedAclVersion.get_by_id(value['id']),acl_host.reviewer);acl_host.fail_node=33
    assert step(product_client,row,'apply',value['id'],expected='failed')[0]['status']=='rolled-back'
    operations=[(node,operation) for node,operation,_ in acl_host.remote if operation in ('prepare','apply','rollback')]
    assert operations==[(11,'prepare'),(33,'prepare'),(11,'apply'),(33,'apply'),(11,'rollback'),(33,'rollback')]
    assert ManagedAclFeed.get_by_id(row['id']).deployed_version_id is None


def test_worker_redelivery_keeps_the_original_transaction_after_interruption(product_client,acl_host,app,monkeypatch):
    row,value=reviewed(product_client,app,acl_host)
    response=product_client.post(API+'/'+str(row['id'])+'/apply',json=dict(version_id=value['id']));task=InstallationTasks.get_by_id(response.json['task_id'])
    original=acl.remote
    class WorkerKilled(BaseException):pass
    def killed(server,operation,**data):
        if operation=='apply':raise WorkerKilled()
        return original(server,operation,**data)
    monkeypatch.setattr(acl,'remote',killed)
    with pytest.raises(WorkerKilled):acl.execute(task)
    current=ManagedAclVersion.get_by_id(value['id']);transaction=unseal(current.details)['transaction']
    # Process death leaves the queue task/pointer for normal worker redelivery.
    ManagedAclFeed.update(active_task_id=task.id).where(ManagedAclFeed.id==row['id']).execute()
    InstallationTasks.update(status='running').where(InstallationTasks.id==task.id).execute()
    monkeypatch.setattr(acl,'remote',original)
    assert acl.execute(InstallationTasks.get_by_id(task.id))=='completed'
    assert unseal(ManagedAclVersion.get_by_id(value['id']).details)['transaction']==transaction


def test_change_center_link_resolves_its_exact_version_beyond_recent_history(product_client,acl_host,app):
    row,value=reviewed(product_client,app,acl_host)
    original=ManagedAclVersion.get_by_id(value['id'])
    for _ in range(51):
        ManagedAclVersion.create(feed_id=row['id'],group_id=1,user_id=original.user_id,feed_revision=1,
            content=original.content,fingerprint=original.fingerprint,entries=1)
    linked=product_client.get(API+'?change='+str(value['change_id'])).json
    assert linked['selected_feed_id']==row['id'] and linked['selected_version_id']==value['id']
    values=product_client.get(API+'/'+str(row['id'])+'/versions?include_version='+str(value['id'])).json['data']
    assert len(values)==51 and values[-1]['id']==value['id']
