"""Real proxy configuration, HTTP statistics and reloads on isolated Podman networks.

Opt-in: requires rootful Podman in a disposable Linux container. No host units
or native services are changed. Debian/EL VM installation qualification is separate.
"""
import base64
import importlib.util
import os
from pathlib import Path
import pwd
import subprocess
import shlex
import time
from uuid import uuid4

import pytest
from app.modules.config import candidate
from app.modules.connectors import containers
from app.modules.service import haproxy_runtime

pytestmark = pytest.mark.skipif(os.environ.get('ROXYWI_TEST_PODMAN_PROXY') != '1', reason='Requires disposable Linux Podman integration environment')


@pytest.mark.parametrize('service,image,check,expected', [
    ('haproxy','docker.io/haproxytech/haproxy-alpine:3.0.10',['haproxy','-c'],'Statistics Report'),
    ('nginx','docker.io/library/nginx:stable-alpine',['nginx','-t'],'Active connections'),
    ('apache','docker.io/library/httpd:2.4-alpine',['httpd','-t'],'Server Status'),
])
def test_managed_proxy_serves_statistics_and_survives_reload(tmp_path,service,image,check,expected):
    assert os.geteuid()==0,'Run only inside the disposable integration container as root'
    assert Path('/run/.containerenv').exists() or Path('/.dockerenv').exists(),'Do not run on a general-purpose host'
    source=Path(__file__).resolve().parents[2]/'app/scripts/ansible/roles/podman_proxy/files/proxy.py'
    spec=importlib.util.spec_from_file_location('real_podman_proxy_recipe',source)
    recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
    recipe.run(['podman','pull',image],timeout=600)
    image_id=recipe.run(['podman','image','inspect','--format','{{.Id}}',image])
    directory=tmp_path/'config';directory.mkdir()
    certs=tmp_path/'certs';logs=tmp_path/'logs';logs.mkdir()
    name='roxywi-proxy-test-'+uuid4().hex
    data=dict(service=service,image=image,name=name,directory=str(directory),config=str(directory/(service+'.conf')),
              certificates=str(certs),log_directory=str(logs),stats_port=18085,runtime_port=11999,stats_page='stats',
              stats_user='product-test',stats_password='disposable-test-password',user=pwd.getpwuid(os.geteuid()).pw_name)
    recipe.configure(data,image_id,directory)
    # The same generated unit must be accepted by the actual installed generator.
    units=tmp_path/'units';units.mkdir();(units/'proxy.container').write_text(recipe.render_unit(data,image_id))
    generated=subprocess.run([str(recipe.GENERATOR),'--dryrun'],env={**os.environ,'QUADLET_UNIT_DIRS':str(units)},capture_output=True,text=True,timeout=30)
    assert generated.returncode==0 and 'failed to' not in generated.stderr.lower(),generated.stderr
    command=next(shlex.split(line.removeprefix('ExecStart=')) for line in generated.stdout.splitlines() if line.startswith('ExecStart='))
    mounts=[command[index+1] for index,argument in enumerate(command[:-1]) if argument in ('-v','--volume')]
    assert str(directory)+':'+str(directory)+':rw,Z' in mounts
    assert str(certs)+':'+str(certs)+':rw,Z' in mounts
    mount=[]
    for path in (directory,certs,logs): mount += ['--volume',str(path)+':'+str(path)+':rw,Z']
    if service=='nginx': mount += ['--volume',str(directory)+':/etc/nginx:rw,Z']
    if service=='apache': mount += ['--volume',str(directory)+':/usr/local/apache2/conf:rw,Z']
    base=['podman','run','--network','none','--user','0',*mount]
    recipe.run([*base,'--rm',image_id,*check,'-f' if service!='nginx' else '-c',data['config']])
    launch={'haproxy':['haproxy','-W','-db','-f'],'nginx':['nginx','-g','daemon off;','-c'],
            'apache':['httpd','-DFOREGROUND','-f']}[service]
    auth=base64.b64encode(b'product-test:disposable-test-password').decode()
    fetch=['podman','exec',name,'wget','-qO-','--header=Authorization: Basic '+auth,'http://127.0.0.1:18085/stats']
    try:
        recipe.run([*base,'--detach','--name',name,image_id,*launch,data['config']])
        for _ in range(30):
            reply=subprocess.run(fetch,capture_output=True,text=True,timeout=5)
            if reply.returncode==0: break
            time.sleep(.2)
        assert reply.returncode==0,recipe.run(['podman','logs',name])
        assert expected in reply.stdout
        if service == 'haproxy':
            probe=Path(haproxy_runtime.__file__).read_text()+'\nimport json,sys\nprint(execute_runtime_command(**json.load(sys.stdin)),end="")\n'
            info=containers.in_network(dict(engine='podman',owner='root'),name,probe,
                dict(server='127.0.0.1',port=11999,command='show info'))
            assert 'Version:' in info and 'Process_num:' in info
        else:
            assert int(containers.service_status(dict(engine='podman'),name,service)['Process'])>0
        main=Path(data['config']); original=main.read_bytes()
        upload=tmp_path/'candidate.conf';upload.write_text('invalid proxy directive\n')
        transaction=dict(service=service,main=str(main),root=str(directory),target=str(main),candidate=str(upload),
                         container=name,container_runtime=dict(engine='podman',owner='root',unit=''),
                         action='save',sources=[str(main)])
        rejected=candidate.execute(transaction)
        assert rejected['status']!='ok' and main.read_bytes()==original,rejected
        upload.write_bytes(original+b'\n# verified Podman configuration transaction\n')
        transaction.update(action='reload',action_command='podman kill --signal '+('USR2' if service=='haproxy' else 'HUP')+' '+name)
        applied=candidate.execute(transaction)
        assert applied=={'status':'ok'},applied
        assert main.read_bytes()==original+b'\n# verified Podman configuration transaction\n'
        recipe.run(containers.lifecycle(dict(engine='podman'),name,'haproxy-reload' if service=='haproxy' else 'reload'))
        for _ in range(30):
            reply=subprocess.run(fetch,capture_output=True,text=True,timeout=5)
            if reply.returncode==0 and expected in reply.stdout: break
            time.sleep(.2)
        assert reply.returncode==0 and expected in reply.stdout
        if service!='haproxy': assert (logs/'access.log').exists()
    finally:
        subprocess.run(['podman','rm','--force',name],capture_output=True,timeout=30)
