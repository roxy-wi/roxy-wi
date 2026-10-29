"""Build the fixed qnetd recipe on Podman and retain its generated NSS identity.

This checks the actual image and restart path; cluster votes need the final VM
qualification. Only enabled explicitly inside a disposable Linux container.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest

from app.modules.pacemaker.witness_docker import DOCKERFILE, ENTRYPOINT, RECIPE, RUNTIME

pytestmark=pytest.mark.skipif(os.environ.get('ROXYWI_TEST_PODMAN_WITNESS')!='1',reason='Requires disposable Podman witness integration environment')


def test_fixed_podman_witness_image_retains_its_ca_across_restart(tmp_path):
    assert os.geteuid()==0 and (Path('/run/.containerenv').exists() or Path('/.dockerenv').exists())
    build=tmp_path/'build';build.mkdir()
    (build/'Dockerfile').write_text(DOCKERFILE);(build/'entrypoint').write_text(ENTRYPOINT)
    def run(args,timeout=60):
        return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()
    image='localhost/roxywi-qnetd:integration-'+RECIPE[:20]
    found=subprocess.run(['podman','image','exists',image],capture_output=True)
    if found.returncode:
        # The outer isolated CI container's DNS stub is not reachable from a
        # second nested build bridge. This shares only that disposable network.
        run(['podman','build','--network=host','--format=docker','--label','org.roxy-wi.recipe='+RECIPE,'-t',image,str(build)],timeout=900)
    ident=run(['podman','image','inspect','--format','{{.Id}}',image])
    data=tmp_path/'data';data.mkdir(mode=0o700);os.chown(data,65532,65532)
    name='roxywi-witness-test-'+uuid4().hex
    code={};exec(RUNTIME,code)
    cert=data/'nssdb/qnetd-cacert.crt'
    code.update(ENGINE='podman',CONTAINER=name,DATA=data,CERT=cert)
    try:
        run(['podman','run','--detach','--name',name,'--label','org.roxy-wi.role=qnetd',
             '--label','org.roxy-wi.recipe='+RECIPE,'--network','none','--user','65532:65532','--read-only',
             '--cap-drop','ALL','--security-opt','no-new-privileges',
             '--mount','type=tmpfs,destination=/run/corosync-qnetd,tmpfs-mode=0700,tmpfs-size=4194304,U=true',
             '--tmpfs','/tmp:rw,nosuid,nodev,noexec,mode=1777,size=16m',
             '--volume',str(data)+':/etc/corosync/qnetd:rw,Z',ident])
        for _ in range(60):
            state=code['container_state']()
            if state and code['docker_status'](state)['active'] and cert.is_file():break
            time.sleep(.5)
        else:pytest.fail(run(['podman','logs',name]))
        before=hashlib.sha256(cert.read_bytes()).hexdigest()
        run(['podman','stop','--time','20',name]);run(['podman','start',name])
        for _ in range(60):
            state=code['container_state']();status=code['docker_status'](state)
            if status['active']:break
            time.sleep(.5)
        assert status['active'] and status['mode']=='podman'
        assert status['ca_fingerprint']==before
        assert state['Config']['User']=='65532:65532'
    finally:
        subprocess.run(['podman','rm','--force',name],capture_output=True,timeout=30)


def test_podman_supervisor_stops_for_reviewed_replacement_and_restarts_the_restored_container(tmp_path):
    assert os.geteuid()==0 and (Path('/run/.containerenv').exists() or Path('/.dockerenv').exists())
    unit=Path('/etc/systemd/system/roxywi-qnetd.service')
    assert not unit.exists(),'Do not replace an existing deployment in this test'
    assert subprocess.run(['podman','container','exists','roxywi-qnetd'],capture_output=True).returncode==1
    code={};exec(RUNTIME,code)
    root=tmp_path/'witness';data=root/'data';data.mkdir(parents=True,mode=0o700);os.chown(data,65532,65532)
    code.update(ENGINE='podman',ROOT=root,DATA=data,CERT=data/'nssdb/qnetd-cacert.crt')
    image='localhost/roxywi-qnetd:integration-'+RECIPE[:20]
    original='roxywi-qnetd-previous-'+uuid4().hex
    def ready():
        for _ in range(60):
            observed=code['container_state']()
            if observed and code['docker_status'](observed)['active']:return
            time.sleep(.2)
        pytest.fail('Managed Podman witness did not become ready')
    try:
        code['launch_docker'](image);ready()
        fingerprint=hashlib.sha256(code['CERT'].read_bytes()).hexdigest()
        assert code['command'](['systemctl','is-active','roxywi-qnetd.service'])=='active'
        code['command'](['podman','stop','--time','20','roxywi-qnetd'])
        assert subprocess.run(['systemctl','is-active','--quiet','roxywi-qnetd.service'],capture_output=True).returncode!=0
        code['command'](['podman','rename','roxywi-qnetd',original])
        code['launch_docker'](image,migration='a'*32);ready()
        assert code['docker_status'](code['container_state']())['ca_fingerprint']==fingerprint
        # Restore the retained original using the same engine wrapper as recovery.
        code['command'](['podman','rm','-f','roxywi-qnetd'])
        code['command'](['podman','rename',original,'roxywi-qnetd'])
        code['command'](['podman','start','roxywi-qnetd']);ready()
        assert code['command'](['systemctl','is-active','roxywi-qnetd.service'])=='active'
        assert hashlib.sha256(code['CERT'].read_bytes()).hexdigest()==fingerprint
    finally:
        if unit.exists() and unit.read_text().startswith(code['UNIT_MARKER']):
            subprocess.run(['systemctl','disable','--now','roxywi-qnetd.service'],capture_output=True,timeout=60)
            unit.unlink();subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=30)
        for name in ('roxywi-qnetd',original):
            subprocess.run(['podman','rm','--force',name],capture_output=True,timeout=30)
