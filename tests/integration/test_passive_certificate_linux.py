"""Real framed host helper, native HAProxy -c and isolated OCI syntax checks.

Cluster CLI responses are fixture metadata, not a running Pacemaker cluster.
Real Debian/EL membership/failover qualification is a separate VM test phase.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from app.modules.service import certificates
from app.scripts import certificate_cluster_remote as cluster
from tests.fixtures.certificate_runtime import make_pem
from tests.unit.certificates.test_passive_certificate_cluster import CIB,STATUS,proof


pytestmark=pytest.mark.skipif(sys.platform!='linux' or not shutil.which('haproxy'),reason='Linux and real HAProxy binary required')


@pytest.fixture
def framed(tmp_path):
    certs=tmp_path/'certs';certs.mkdir();file=certs/'site.pem';file.write_text(make_pem(1))
    main=tmp_path/'haproxy.cfg';main.write_text('global\ndefaults\n mode tcp\n timeout connect 1s\n timeout client 1s\n timeout server 1s\nfrontend tls\n bind 127.0.0.1:10443 ssl crt '+str(file)+'\n')
    tools=tmp_path/'bin';tools.mkdir()
    outputs={'cibadmin':CIB,'crm_mon':STATUS,'corosync-cmapctl':'totem.cluster_name (str) = fixture','pgrep':''}
    for name,text in outputs.items():
        script=tools/name
        script.write_text('#!'+sys.executable+'\nimport sys\nprint('+repr(text)+')\n')
        script.chmod(0o700)
    script=tools/'systemctl';script.write_text('#!'+sys.executable+'\nimport sys\n'
        'assert sys.argv[1]=="show", "No service actions allowed"\n'
        'print('+repr('LoadState=loaded\nActiveState=inactive\nMainPID=0\nWorkingDirectory=/\nEnvironment=\nEnvironmentFiles=\nExecStart={ path=/usr/sbin/haproxy ; argv[]=/usr/sbin/haproxy -f '+str(main)+' ; ignore_errors=no ; }')+')\n');script.chmod(0o700)
    source=certificates.remote_source().replace("ROOT = Path('/var/lib/roxy-wi/letsencrypt')",'ROOT = Path('+repr(str(tmp_path/'journals'))+')')
    # Protect against a source-size regression at the actual framing boundary.
    assert len(source.encode())<=512*1024
    data=dict(cert_dir=str(certs),pem_name='site.pem',config_path=str(main),root=str(tmp_path),service_unit='haproxy',
        docker=False,runtime_port=1999,apply_mode='disk_stage',cluster_proof=proof(),transaction='native-framed',pem=make_pem(2))
    def invoke(data):
        stream=format(len(source.encode()),'x')+'\n'+source+json.dumps(data)
        result=subprocess.run([sys.executable,'-c',certificates.REMOTE_BOOTSTRAP],input=stream,text=True,capture_output=True,
            timeout=45,env=dict(os.environ,PATH=str(tools)+os.pathsep+os.environ['PATH']))
        reply=json.loads(result.stdout)
        assert result.returncode==0,reply
        return reply
    data['validation']=invoke(dict(data,operation='passive-context'))
    return data,file,invoke


@pytest.mark.parametrize('phase',['commit','rollback'])
def test_real_framed_passive_certificate_transaction(framed,phase):
    data,file,invoke=framed;old=file.read_text()
    observed=invoke(dict(data,operation='passive-inspect'))
    data.update(passive_binding=observed['binding'],expected_revision=observed['revision'])
    assert invoke(dict(data,operation='deploy'))['verification']=='disk-staged'
    assert file.read_text()==data['pem']
    invoke(dict(data,operation='deploy'))
    finished=dict(data,operation=phase,expected_digest=hashlib.sha256(data['pem'].encode()).hexdigest())
    invoke(finished);invoke(finished)
    assert file.read_text()==(data['pem'] if phase=='commit' else old)


@pytest.mark.parametrize('engine',['docker','podman'])
@pytest.mark.skipif(os.environ.get('ROXYWI_TEST_PASSIVE_OCI')!='1',reason='Opt-in disposable Linux OCI environment required')
def test_removed_ocf_container_is_validated_without_starting_resource(tmp_path,monkeypatch,engine):
    assert os.geteuid()==0 and (Path('/run/.containerenv').exists() or Path('/.dockerenv').exists())
    image='docker.io/haproxytech/haproxy-alpine:3.0.10'
    subprocess.run([engine,'image','inspect',image],check=True,capture_output=True,timeout=30)
    certs=tmp_path/'certs';certs.mkdir();file=certs/'site.pem';file.write_text(make_pem())
    main=tmp_path/'haproxy.cfg';main.write_text('global\ndefaults\n mode tcp\n timeout connect 1s\n timeout client 1s\n timeout server 1s\nfrontend tls\n bind 127.0.0.1:10443 ssl crt /fixture/certs/site.pem\n')
    name='roxywi-passive-'+uuid4().hex
    declared=dict(id='proxy',**{'class':'ocf','provider':'heartbeat','type':engine},parameters=dict(
        name=name,image=image,run_opts='--network none -v '+str(tmp_path)+':/fixture',run_cmd='haproxy -W -db -f /fixture/haproxy.cfg'))
    data=dict(docker=True,container=name,container_runtime=dict(engine=engine,owner='root',unit=''),root=str(tmp_path),
        config_path=str(main),cluster_proof=dict(proof(),declaration=declared))
    monkeypatch.setattr(cluster,'verify',lambda *args,**kwargs:'passive')
    data['validation']=cluster.context(data)
    record=cluster.container_record(data)
    assert record['_declared'] is True
    original_run=subprocess.run
    errors=[]
    def capture(argv,**kwargs):
        result=original_run(argv,**kwargs)
        if argv[:2]==[engine,'run'] and result.returncode:errors.append(result.stderr)
        return result
    with monkeypatch.context() as diagnostics:
        diagnostics.setattr(cluster.subprocess,'run',capture)
        try:assert cluster.validate_offline(data)
        except ValueError:pytest.fail('Isolated syntax validator failed: '+repr(errors[-1:]))
    check=subprocess.run([engine,'container','inspect',name],capture_output=True,timeout=20)
    assert check.returncode!=0 # the managed resource was never created or started
    file.write_text('invalid')
    with pytest.raises(ValueError,match='configuration is invalid'):cluster.validate_offline(data)
