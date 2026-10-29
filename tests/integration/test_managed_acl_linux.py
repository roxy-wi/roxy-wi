"""Real HAProxy runtime transactions, persistence, lost responses and rollback."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4
import pytest
from app.modules.config import candidate
from app.scripts import certificate_remote

pytestmark=pytest.mark.skipif(sys.platform!='linux' or not shutil.which('haproxy'),reason='Linux HAProxy required')


@pytest.fixture
def acl_host(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'roxywi_config_candidate',candidate)
    monkeypatch.setitem(sys.modules,'roxywi_certificate_remote',certificate_remote)
    spec=importlib.util.spec_from_file_location('test_acl_helper',Path(candidate.__file__).parents[2]/'scripts/acl_feed_remote.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    def port():
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));return listener.getsockname()[1]
    runtime_port=port();http_port=port();acl=tmp_path/'blocked.lst';acl.write_text('# original metadata\n192.0.2.0/24\n');acl.chmod(0o640)
    os.setxattr(acl,'user.roxywi-test',b'preserve')
    main=tmp_path/'haproxy.cfg';main.write_text(f'''global
 stats socket ipv4@127.0.0.1:{runtime_port} level admin
defaults
 mode http
 timeout connect 1s
 timeout client 2s
 timeout server 2s
frontend public
 bind 127.0.0.1:{http_port}
 acl denied src -f {acl}
 http-request deny if denied
 http-request return status 200 content-type text/plain string healthy
''')
    process=subprocess.Popen(['haproxy','-W','-db','-f',str(main)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    data=dict(root=str(tmp_path),path=str(acl),validation=dict(main=str(main),sources=[str(main)],container='',action='check'),
        transport=dict(docker=False,runtime_port=runtime_port),transaction=str(uuid4()),content='127.0.0.1/32\n')
    def status():
        try:
            with urlopen('http://127.0.0.1:'+str(http_port),timeout=2) as response:return response.status
        except HTTPError as error:return error.code
    deadline=time.monotonic()+5
    while True:
        try:
            if status()==200:break
        except OSError:pass
        if time.monotonic()>deadline:pytest.fail('Isolated HAProxy did not start')
        time.sleep(.05)
    try:yield helper,data,acl,main,status
    finally:
        process.terminate()
        try:process.communicate(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)


def call(host,operation,**changes):
    helper,data,*_=host
    return helper.handle(dict(data,operation=operation,**changes))


def test_real_atomic_runtime_apply_persists_file_and_rollback_restores_original_metadata(acl_host):
    helper,data,acl,main,status=acl_host
    original=acl.read_bytes();data['expected']=call(acl_host,'preview')
    assert call(acl_host,'discover')['lists'][0]['path']==str(acl)
    assert call(acl_host,'prepare')['prepared'] and status()==200
    assert call(acl_host,'apply')['applied'] and status()==403
    assert acl.read_text()==data['content'] and acl.stat().st_mode&0o777==0o640
    assert os.getxattr(acl,'user.roxywi-test')==b'preserve'
    assert call(acl_host,'rollback')['finished'] and status()==200 and acl.read_bytes()==original
    assert call(acl_host,'rollback')['finished'] # repeated recovery is safe


def test_lost_response_after_file_write_is_recoverable_without_overwriting_unknown_edits(acl_host):
    helper,data,acl,main,status=acl_host
    data['expected']=call(acl_host,'preview');call(acl_host,'prepare')
    # The worker dies after its durable intent and file replacement, before CLI commit.
    journal=acl.parent/'.roxywi-acl-feeds'/data['transaction']/'state.json'
    saved=json.loads(journal.read_text());saved['state']='applying';journal.write_text(json.dumps(saved));acl.write_text(data['content'])
    assert call(acl_host,'rollback')['finished'] and status()==200
    acl.write_text('198.51.100.0/24\n')
    with pytest.raises(ValueError,match='outside this transaction'):call(acl_host,'rollback')


def test_commit_is_idempotent_and_new_rollback_requires_a_new_review(acl_host):
    helper,data,acl,main,status=acl_host
    data['expected']=call(acl_host,'preview');call(acl_host,'prepare');call(acl_host,'apply')
    assert call(acl_host,'commit')['state']=='committed'
    assert call(acl_host,'commit')['state']=='committed'
    assert status()==403
    with pytest.raises(ValueError,match='newly reviewed rollback'):call(acl_host,'rollback')


def test_configuration_drift_after_review_prevents_mutation(acl_host):
    helper,data,acl,main,status=acl_host
    data['expected']=call(acl_host,'preview');original=acl.read_bytes();main.write_text(main.read_text()+'\n# edited after review\n')
    with pytest.raises(ValueError,match='changed since review'):call(acl_host,'prepare')
    assert acl.read_bytes()==original and status()==200


def test_exact_framed_ssh_helper_runs_without_an_application_install_on_the_host(acl_host,monkeypatch,tmp_path):
    from app.modules.service import managed_acl
    helper,data,acl,main,status=acl_host
    class LocalTransport:
        def __init__(self,server):pass
        def run(self,argv,**kwargs):
            environment={key:value for key,value in os.environ.items() if key!='PYTHONPATH'}
            result=subprocess.run([sys.executable,*argv[1:]],input=kwargs['data'],cwd=tmp_path,env=environment,capture_output=True,text=True,timeout=30)
            assert result.returncode==0,result.stderr
            return result.stdout
    monkeypatch.setattr(managed_acl,'Remote',LocalTransport)
    spec={key:data[key] for key in ('root','validation','transport')}
    found=managed_acl.remote(None,'discover',spec=spec)
    assert found['lists'][0]['path']==str(acl)
