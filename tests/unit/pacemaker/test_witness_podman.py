import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.pacemaker import qdevice, operations, witness_migration
from app.modules.pacemaker.schemas import WitnessInstall
from app.modules.pacemaker.witness_docker import RUNTIME, RECIPE


def runtime(tmp_path):
    root = tmp_path/'witness'
    code = {}; exec(RUNTIME.replace("ROOT = pathlib.Path('/var/lib/roxy-wi/qnetd')", f'ROOT = pathlib.Path({str(root)!r})'),code)
    code.update(ROOT=root, DATA=root/'data', CERT=root/'data/nssdb/qnetd-cacert.crt',
                ENGINE_FILE=root/'engine.json', ENGINE='podman', WITNESS_UNIT=tmp_path/'roxywi-qnetd.service')
    return code


def test_podman_install_is_explicit_and_survives_worker_dispatch(monkeypatch):
    assert WitnessInstall(server_id=1,container_engine='podman').container_engine=='podman'
    with pytest.raises(ValidationError): WitnessInstall(server_id=1,container_engine='podman; id')
    calls=[]
    monkeypatch.setattr(qdevice,'witness_server',lambda *_:SimpleNamespace(ip='192.0.2.1',port=22,cred_id=7,server_id=1))
    monkeypatch.setattr(qdevice,'install_witness',lambda *args,**kw:calls.append((args,kw)))
    monkeypatch.setattr(operations.User,'get_or_none',lambda *_:SimpleNamespace(user_id=1,enabled=True))
    monkeypatch.setattr(operations.user_sql,'select_user_services',lambda _:'5')
    monkeypatch.setattr(operations.user_sql,'get_user_role_in_group',lambda *_:1)
    monkeypatch.setattr(operations.InstallationTasks,'update',lambda **_:SimpleNamespace(where=lambda *_:SimpleNamespace(execute=lambda:None)))
    payload=dict(server_id=1,container_engine='podman',identity=dict(ip='192.0.2.1',port=22,cred_id=7))
    assert operations.execute_witness(SimpleNamespace(id=987,user_id_id=1,group_id_id=1),payload)=='completed'
    assert calls==[((1,1),{'container_engine':'podman'})]


def test_podman_launch_keeps_nss_state_and_has_only_one_restart_owner(tmp_path):
    code=runtime(tmp_path); calls=[]
    code['command']=lambda args,**_:calls.append(args) or ''
    code['ensure_supervisor']=lambda:calls.append(['supervisor'])
    code['launch_docker']('sha256:'+'a'*64,migration='b'*32)
    args=calls[0]
    assert args[:2]==['podman','run'] and 'docker' not in args
    assert args[args.index('--restart')+1]=='no'
    assert '--read-only' in args and '--cap-drop' in args
    assert str(code['DATA'])+':/etc/corosync/qnetd:rw,Z' in args
    assert calls[-1]==['systemctl','start','roxywi-qnetd.service']


def test_engine_switch_cannot_rebind_existing_certificate_data(tmp_path):
    code=runtime(tmp_path); code['ENGINE']='docker'
    code['DATA'].mkdir(parents=True)
    with pytest.raises(ValueError,match='reviewed engine migration'):
        code['select_engine']('podman')
    assert not code['ENGINE_FILE'].exists()


def test_podman_supervisor_cannot_replace_or_stop_an_unmanaged_unit(tmp_path,monkeypatch):
    code=runtime(tmp_path)
    code['WITNESS_UNIT'].write_text('[Service]\nExecStart=/some/other/service\n')
    monkeypatch.setattr(code['subprocess'],'run',lambda *_a,**_kw:pytest.fail('Unrelated unit was controlled'))
    with pytest.raises(ValueError,match='unmanaged'): code['ensure_supervisor']()
    with pytest.raises(ValueError,match='unmanaged'): code['command'](['podman','stop','roxywi-qnetd'])


def test_build_for_podman_preserves_the_dockerfile_healthcheck(tmp_path,monkeypatch):
    code=runtime(tmp_path);calls=[]
    monkeypatch.setattr(code['subprocess'],'run',lambda args,**kwargs:calls.append(args) or SimpleNamespace(stdout='built'))
    assert code['command'](['podman','build','-t','test','/build'])=='built'
    assert calls==[['podman','build','--format=docker','-t','test','/build']]


def test_existing_minimal_podman_gets_its_build_network_tool_without_enabling_a_firewall(tmp_path,monkeypatch):
    code=runtime(tmp_path);installed=[]
    monkeypatch.setattr(code['shutil'],'which',lambda tool: '/usr/bin/'+tool if tool=='podman' or installed else None)
    code['install_packages']=lambda role:installed.append(role)
    monkeypatch.setattr(code['subprocess'],'run',lambda *_a,**_kw:pytest.fail('Must not enable a firewall or Docker service'))
    code['ensure_engine']()
    assert installed==['witness-podman']


def test_podman_status_proves_qnetd_not_only_a_running_container(tmp_path,monkeypatch):
    code=runtime(tmp_path);code['CERT'].parent.mkdir(parents=True);code['CERT'].write_bytes(b'original-ca')
    calls=[]
    code['command']=lambda args,**_:calls.append(args) or '3.0'
    monkeypatch.setattr(code['subprocess'],'run',lambda args,**kw:calls.append(args) or SimpleNamespace(returncode=1))
    status=code['docker_status']({'State':{'Running':True},'Image':'sha256:fixed'})
    assert status['mode']=='podman' and status['active'] is False
    assert status['ca_fingerprint']==hashlib.sha256(b'original-ca').hexdigest()
    assert all(args[0]=='podman' for args in calls)


def test_migration_review_digest_binds_the_destination_engine(monkeypatch):
    server=SimpleNamespace(server_id=9,hostname='Witness',ip='192.0.2.9',port=22,cred_id=4)
    monkeypatch.setattr(qdevice,'witness_server',lambda *_:server)
    monkeypatch.setattr(witness_migration,'call',lambda *_:{'source':{'clusters':[],'ca_fingerprint':'preserved'}})
    monkeypatch.setattr(witness_migration,'attachments',lambda *_:[])
    monkeypatch.setattr(witness_migration,'verify',lambda *_:None)
    docker=witness_migration.plan(9,1,'docker');podman=witness_migration.plan(9,1,'podman')
    assert podman['container_engine']=='podman'
    assert docker['plan_digest']!=podman['plan_digest']
    with pytest.raises(Exception,match='plan changed'):
        witness_migration.migrate(9,1,docker['plan_digest'],container_engine='podman')
