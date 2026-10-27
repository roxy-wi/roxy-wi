import json
from types import SimpleNamespace
import pytest
from app.modules.pacemaker import witness_trust as trust
from app.modules.db.db_model import InstallationTasks,Server

TOKEN='e'*32


def host(tmp_path,monkeypatch,role='source',phase='switching'):
    ns={};exec(trust.BASE,ns)
    root=tmp_path/'root';root.mkdir();ns.update(ROOT=root,TRUST=root/'trust',DATA=root/'data',NATIVE=root/'native')
    directory=ns['folder'](TOKEN);directory.mkdir(parents=True)
    state=dict(role=role,phase=phase,source=dict(mode='docker',restart='unless-stopped',native_enabled=False),replaced=False)
    ns['save'](TOKEN,state)
    calls=[];ns['command']=lambda args,**_:(calls.append(args) or '')
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    return ns,state,calls


def test_remote_source_recovery_never_reactivates_an_independent_arbiter(tmp_path,monkeypatch):
    ns,state,calls=host(tmp_path,monkeypatch)
    assert ns['host_recover'](TOKEN)['phase']=='rolled-back'
    assert ['docker','update','--restart=no','roxywi-qnetd'] in calls
    assert ['docker','stop','--time','20','roxywi-qnetd'] in calls
    assert not any(args[:2]==['docker','start'] for args in calls)


def test_manual_target_recovery_proves_stopped_even_after_its_watchdog_already_ran(tmp_path,monkeypatch):
    ns,state,calls=host(tmp_path,monkeypatch,'target','rolled-back')
    ns['host_recover'](TOKEN,force=True)
    assert ['docker','stop','--time','20','roxywi-qnetd'] in calls


def test_rotation_restores_host_local_ca_and_original_restart_policy(tmp_path,monkeypatch):
    ns,state,calls=host(tmp_path,monkeypatch,'rotation')
    state['replaced']=True;ns['save'](TOKEN,state)
    ns['DATA'].mkdir();(ns['DATA']/'ca').write_text('new')
    backup=ns['folder'](TOKEN)/'before';backup.mkdir();(backup/'ca').write_text('old')
    monkeypatch.setattr(ns['os'],'chown',lambda *_:None)
    assert ns['host_recover'](TOKEN)['phase']=='rolled-back'
    assert (ns['DATA']/'ca').read_text()=='old'
    assert ['docker','update','--restart=unless-stopped','roxywi-qnetd'] in calls
    assert ['docker','start','roxywi-qnetd'] in calls


def test_committed_witness_cannot_be_undone_by_late_timer(tmp_path,monkeypatch):
    ns,state,calls=host(tmp_path,monkeypatch,'rotation','committed')
    assert ns['host_recover'](TOKEN)['phase']=='committed';assert not calls


def test_preparation_abort_does_not_stop_running_client(tmp_path,monkeypatch):
    ns={};exec(trust.NODE_BASE,ns);ns['ROOT']=tmp_path
    directory=ns['folder'](TOKEN);directory.mkdir();ns['save'](TOKEN,dict(phase='prepared',rotation=False,active=True,replaced=False))
    ns['command']=lambda *_args,**_kwargs:pytest.fail('Preparing certificates must not stop an existing client')
    assert ns['recover'](TOKEN)['phase']=='rolled-back'


def test_every_remote_script_and_host_timer_program_compiles():
    for source in (trust.HOST,trust.HOST_RECOVERY,trust.NODE,trust.NODE_BASE):compile(source,'trust','exec')


@pytest.fixture
def target():
    server=Server.create(hostname='trust-test-witness',ip='192.0.2.239',group_id=1)
    yield server
    InstallationTasks.delete().where(InstallationTasks.service_name=='Corosync witness: trust-test-witness').execute()
    server.delete_instance()


def test_api_requires_operator_review_and_explicit_source_confirmation(target,client,authenticated,monkeypatch):
    monkeypatch.setattr(trust,'plan',lambda *_:dict(server=target.hostname,eligible=True,pending=[],plan_digest='a'*64))
    url=f'/pacemaker/api/witness/{target.server_id}/trust'
    body=dict(target_id=target.server_id,rotate_ca=True,plan_digest='a'*64,confirm='wrong')
    assert client.get(url+'/'+str(target.server_id)+'?rotate=1',headers=authenticated[1]).status_code==200
    assert client.post(url,headers=authenticated[1],json=body).status_code==400
    body.update(confirm=target.hostname,plan_digest='b'*64)
    assert client.post(url,headers=authenticated[1],json=body).status_code==409
    body['plan_digest']='a'*64
    assert client.post(url,headers=authenticated[1],json=body).status_code==202
    authenticated[0]['role']=4
    assert client.get(url+'/'+str(target.server_id),headers=authenticated[1]).status_code==403
    assert client.post(url,headers=authenticated[1],json=body).status_code==403
