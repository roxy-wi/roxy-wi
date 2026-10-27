import hashlib
import json
from types import SimpleNamespace

import pytest

from app.modules.pacemaker import witness_migration as migration, operations
from app.modules.pacemaker.witness_docker import RUNTIME
from app.modules.db.db_model import InstallationTasks, Server

TOKEN='b'*32


def host(tmp_path, monkeypatch):
    ns={}
    exec(RUNTIME + migration.RECOVERY + migration.HELPERS, ns)
    root=tmp_path/'managed'; native=tmp_path/'native'
    root.mkdir(); (native/'nssdb').mkdir(parents=True)
    (native/'nssdb/qnetd-cacert.crt').write_bytes(b'preserved-ca')
    ns.update(ROOT=root,DATA=root/'data',CERT=root/'data/nssdb/qnetd-cacert.crt',NATIVE=native)
    directory=ns['folder'](TOKEN); directory.mkdir(parents=True)
    fingerprint=hashlib.sha256(b'preserved-ca').hexdigest()
    state={'phase':'prepared','enabled':'enabled','ca_fingerprint':fingerprint,
           'database_digest':ns['tree_digest'](native),'image_id':'sha256:test','clusters':[]}
    ns['save'](TOKEN,state)
    ns.update(container_state=lambda:None,platform_profile=lambda:None)
    return ns,state


def test_stale_source_is_refused_before_docker_preparation(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    ns['pending']=lambda:[]
    ns['source_info']=lambda:{'database_digest':'changed'}
    ns['install_packages']=lambda *_:pytest.fail('Stale source reached package installation')
    with pytest.raises(ValueError,match='changed'): ns['prepare'](TOKEN,state)


def test_recovery_preserves_original_ca_and_quarantines_docker_data(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    ns['DATA'].mkdir(); (ns['DATA']/'copy').write_text('backup')
    calls=[]; ns['command']=lambda args,**_:calls.append(args)
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    result=ns['recover'](TOKEN)
    assert result['phase']=='rolled-back'
    assert not ns['DATA'].exists()
    assert (ns['folder'](TOKEN)/'docker-stopped/copy').read_text()=='backup'
    assert (ns['NATIVE']/'nssdb/qnetd-cacert.crt').read_bytes()==b'preserved-ca'
    before=list(calls); ns['recover'](TOKEN); assert calls==before


def test_recovery_never_removes_an_unrelated_container(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    ns['container_state']=lambda:{'Config':{'Labels':{'org.roxy-wi.migration':'another'}}}
    ns['command']=lambda *_args,**_kwargs:pytest.fail('An unrelated container was modified')
    with pytest.raises(ValueError,match='unrelated'):ns['recover'](TOKEN)
    assert ns['load'](TOKEN)['phase']=='recovery-required'


def test_failed_switch_arms_host_recovery_and_restores_native(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    ns['source_info']=lambda *_args:dict(database_digest=state['database_digest'])
    ns['copy_state'](ns['NATIVE'],ns['folder'](TOKEN)/'backup')
    monkeypatch.setattr(ns['os'],'chown',lambda *_:None)
    ns['launch_docker']=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError('failed startup'))
    calls=[];ns['command']=lambda args,**_:calls.append(args)
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError):ns['switch'](TOKEN)
    assert ns['load'](TOKEN)['phase']=='rolled-back'
    timer=next(args for args in calls if args[0]=='systemd-run')
    assert '--on-active=180s' in timer
    assert calls.index(timer)<calls.index(['systemctl','stop','corosync-qnetd'])
    assert ['systemctl','start','corosync-qnetd'] in calls


def test_commit_refuses_ca_changes(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    state['phase']='verifying';ns['save'](TOKEN,state)
    ns['CERT'].parent.mkdir(parents=True);ns['CERT'].write_bytes(b'different-ca')
    ns['docker_status']=lambda _:dict(active=True)
    ns['command']=lambda *_args,**_kwargs:pytest.fail('Changed CA reached native disablement')
    with pytest.raises(ValueError,match='CA changed'):ns['commit'](TOKEN)


def test_tree_digest_rejects_symlinks(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    (ns['NATIVE']/'linked').symlink_to('/etc/passwd')
    with pytest.raises(ValueError,match='unsupported file'):ns['tree_digest'](ns['NATIVE'])


def test_connected_unregistered_or_other_group_clusters_are_refused(monkeypatch):
    server=SimpleNamespace(server_id=1)
    monkeypatch.setattr(migration.PacemakerCluster,'select',lambda:[])
    with pytest.raises(Exception,match='Register every'):migration.attachments(server,1,['unknown'])
    monkeypatch.setattr(migration.PacemakerCluster,'select',lambda:[SimpleNamespace(group_id=2,name='foreign',corosync_settings=json.dumps({'qdevice_server_id':1}))])
    with pytest.raises(Exception,match='outside'):migration.attachments(server,1)


@pytest.fixture
def target():
    server=Server.create(hostname='migration-test-witness',ip='192.0.2.236',group_id=1)
    yield server
    InstallationTasks.delete().where(InstallationTasks.service_name=='Corosync witness: migration-test-witness').execute()
    server.delete_instance()


def test_migration_api_requires_reviewed_digest_and_typed_confirmation(target,client,authenticated,monkeypatch):
    monkeypatch.setattr(migration,'plan',lambda *_:dict(server=target.hostname,eligible=True,plan_digest='a'*64,pending=[]))
    url=f'/pacemaker/api/witness/{target.server_id}/migration'
    assert client.get(url,headers=authenticated[1]).status_code==200
    assert client.post(url,headers=authenticated[1],json={'plan_digest':'a'*64,'confirm':'wrong'}).status_code==400
    assert client.post(url,headers=authenticated[1],json={'plan_digest':'b'*64,'confirm':target.hostname}).status_code==409
    assert client.post(url,headers=authenticated[1],json={'plan_digest':'a'*64,'confirm':target.hostname}).status_code==202
    authenticated[0]['role']=4
    assert client.get(url,headers=authenticated[1]).status_code==403
    assert client.post(url,headers=authenticated[1],json={'plan_digest':'a'*64,'confirm':target.hostname}).status_code==403


def test_committed_migration_cannot_be_undone_by_late_watchdog(tmp_path,monkeypatch):
    ns,state=host(tmp_path,monkeypatch)
    state['phase']='verifying'; ns['save'](TOKEN,state)
    ns['CERT'].parent.mkdir(parents=True);ns['CERT'].write_bytes(b'preserved-ca')
    ns['docker_status']=lambda _:dict(active=True)
    calls=[];ns['command']=lambda args,**_:calls.append(args)
    monkeypatch.setattr(ns['subprocess'],'run',lambda *_args,**_kwargs:SimpleNamespace(returncode=0))
    assert ns['commit'](TOKEN)['phase']=='committed'
    assert json.loads((ns['ROOT']/'mode.json').read_text())['ca_fingerprint']==state['ca_fingerprint']
    assert ['systemctl','disable','corosync-qnetd'] in calls
    old=list(calls);assert ns['recover'](TOKEN)['phase']=='committed';assert calls==old
