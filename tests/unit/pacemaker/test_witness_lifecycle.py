import hashlib
import json
from types import SimpleNamespace
import pytest
from app.modules.pacemaker import witness_lifecycle as lifecycle
from app.modules.pacemaker.witness_docker import RUNTIME
from app.modules.db.db_model import InstallationTasks,Server

TOKEN='d'*32

def host(tmp_path,monkeypatch,operation='image-upgrade'):
    ns={};exec(RUNTIME+lifecycle.COMMON+'\nRECOVER_CODE=""\n'+lifecycle.HELPERS,ns)
    root=tmp_path/'root';root.mkdir();data=root/'data';data.mkdir();(data/'ca').write_text('original')
    ns.update(ROOT=root,DATA=data,CERT=data/'ca',NATIVE=tmp_path/'native')
    folder=ns['folder'](TOKEN);folder.mkdir(parents=True);ns['copy_state'](data,folder/'docker-before')
    state=dict(operation=operation,phase='prepared',old_container='previous-'+TOKEN,image_id='sha256:original',native_enabled=False,native_replaced=False,switched=False,clusters=[],ca_fingerprint=hashlib.sha256(b'original').hexdigest())
    ns['save'](TOKEN,state)
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    return ns,state


def test_preparation_rejects_changed_witness_before_packages_or_build(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch);ns['pending']=lambda:[];ns['snapshot']=lambda:dict(changed=True)
    ns['install_packages']=lambda *_:pytest.fail('Stale witness reached package installation')
    with pytest.raises(ValueError,match='changed'):ns['prepare'](TOKEN,dict(changed=False),'native')


def test_recovery_before_switch_only_starts_original_container(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch);calls=[]
    ns['container_state']=lambda:dict(Image=state['image_id'],Config=dict(Labels={}))
    ns['command']=lambda args,**_:(calls.append(args) or '')
    result=ns['recover'](TOKEN)
    assert result['phase']=='rolled-back'
    assert ['docker','start','roxywi-qnetd'] in calls
    assert not any(args[:2]==['docker','rm'] for args in calls)
    assert (ns['DATA']/'ca').read_text()=='original'


def test_recovery_handles_connection_loss_after_rename_before_journal_update(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch);calls=[]
    ns['container_state']=lambda:None
    ns['command']=lambda args,**_:(calls.append(args) or (state['old_container'] if args[:2]==['docker','ps'] else ''))
    (ns['DATA']/'ca').write_text('candidate')
    assert not state['switched']
    assert ns['recover'](TOKEN)['phase']=='rolled-back'
    assert (ns['DATA']/'ca').read_text()=='original'
    assert ['docker','rename',state['old_container'],'roxywi-qnetd'] in calls


def test_recovery_refuses_unrelated_container(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    ns['container_state']=lambda:dict(Image='sha256:unrelated',Config=dict(Labels={}))
    ns['command']=lambda args,**_:'' if args[:2]==['docker','ps'] else pytest.fail('Unrelated container modified')
    with pytest.raises(ValueError,match='unrelated'):ns['recover'](TOKEN)
    assert ns['load'](TOKEN)['phase']=='recovery-required'


def test_native_commit_archives_docker_storage_and_late_timer_cannot_undo_it(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch,'native');state['phase']='verifying';ns['save'](TOKEN,state)
    (ns['NATIVE']/'nssdb').mkdir(parents=True);(ns['NATIVE']/'nssdb/qnetd-cacert.crt').write_text('original')
    calls=[];ns['command']=lambda args,**_:(calls.append(args) or '')
    assert ns['commit'](TOKEN)['phase']=='committed'
    assert not ns['DATA'].exists()
    assert (ns['folder'](TOKEN)/'docker-retained/ca').read_text()=='original'
    assert json.loads((ns['ROOT']/'mode.json').read_text())['mode']=='native'
    old=list(calls);assert ns['recover'](TOKEN)['phase']=='committed';assert calls==old


@pytest.fixture
def target():
    server=Server.create(hostname='lifecycle-test',ip='192.0.2.238',group_id=1)
    yield server
    InstallationTasks.delete().where(InstallationTasks.service_name=='Corosync witness: lifecycle-test').execute()
    server.delete_instance()


def test_api_requires_operator_reviewed_digest_and_typed_name(target,client,authenticated,monkeypatch):
    monkeypatch.setattr(lifecycle,'plan',lambda *_:dict(server=target.hostname,eligible=True,plan_digest='a'*64,pending=[]))
    url=f'/pacemaker/api/witness/{target.server_id}/lifecycle/native'
    assert client.get(url,headers=authenticated[1]).status_code==200
    assert client.post(url,headers=authenticated[1],json=dict(plan_digest='a'*64,confirm='wrong')).status_code==400
    assert client.post(url,headers=authenticated[1],json=dict(plan_digest='b'*64,confirm=target.hostname)).status_code==409
    assert client.post(url,headers=authenticated[1],json=dict(plan_digest='a'*64,confirm=target.hostname)).status_code==202
    authenticated[0]['role']=4
    assert client.get(url,headers=authenticated[1]).status_code==403
    assert client.post(url,headers=authenticated[1],json=dict(plan_digest='a'*64,confirm=target.hostname)).status_code==403


def test_remote_code_and_independent_recovery_compile():
    compile(lifecycle.REMOTE,'remote','exec');compile(lifecycle.RECOVER_CODE,'recovery','exec')


def test_committed_refresh_updates_the_recipe_tag_used_by_later_conversions(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    state.update(phase='verifying',candidate_image='sha256:updated');ns['save'](TOKEN,state)
    ns['container_state']=lambda:{};ns['docker_status']=lambda _:dict(active=True)
    calls=[];ns['command']=lambda args,**_:(calls.append(args) or '')
    assert ns['commit'](TOKEN)['phase']=='committed'
    assert ['docker','tag','sha256:updated','roxywi-qnetd:'+ns['RECIPE'][:20]] in calls
