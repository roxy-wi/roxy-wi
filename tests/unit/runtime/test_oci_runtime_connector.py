"""Engine/owner selection cannot fall back or operate an unrelated systemd unit."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import subprocess

from app.modules.connectors import containers
from app.modules.config import candidate, haproxy_discovery
from app.scripts import certificate_remote


@pytest.mark.parametrize('spec', [dict(engine='unknown'), dict(engine='podman;sh'), dict(owner='root;id'),
    dict(owner='-root'), dict(unit='sshd'), dict(engine='docker', unit='docker.service'),
    dict(engine='podman', unit='../bad.service'), dict(secret='value'), ['podman']])
def test_invalid_runtime_identities_are_rejected(spec):
    with pytest.raises(ValueError): containers.validate(spec)


def test_legacy_engine_is_explicit_rootful_docker():
    assert containers.argv(None, ['inspect','haproxy']) == ['docker','inspect','haproxy']
    assert containers.shell(None, container='haproxy', action='restart') == 'sudo docker restart haproxy'
    assert containers.argv({'engine':'podman'}, ['exec','haproxy','haproxy','-c']) == ['podman','exec','haproxy','haproxy','-c']


@pytest.mark.parametrize('process,accepted', [(b'haproxy\0-W\0-db\0',True),(b'haproxy\0-f\0/config.cfg\0',False),(b'tini\0haproxy\0-W\0',False)])
def test_haproxy_reload_checks_the_master_before_selecting_usr2(monkeypatch,process,accepted):
    calls=[]
    monkeypatch.setattr(containers.subprocess,'run',lambda args,**kw:calls.append(args) or SimpleNamespace(stdout=process))
    if accepted:
        assert containers.lifecycle(dict(engine='podman'),'proxy','haproxy-reload')==['podman','kill','-s','USR2','proxy']
    else:
        with pytest.raises(ValueError,match='master-worker'):
            containers.lifecycle(dict(engine='podman'),'proxy','haproxy-reload')
    assert len(calls)==1 and calls[0]==['podman','exec','proxy','cat','/proc/1/cmdline']


def test_missing_rootless_runtime_does_not_fall_back_to_root(monkeypatch):
    monkeypatch.setattr(Path, 'is_dir', lambda _: False)
    import pwd
    monkeypatch.setattr(pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=1002,pw_name='proxy',pw_dir='/home/proxy'))
    with pytest.raises(ValueError, match='runtime directory'):
        containers.argv(dict(engine='podman',owner='proxy'), ['ps'])


def test_rootless_identity_and_environment_are_resolved_on_the_host(monkeypatch):
    monkeypatch.setattr(Path, 'is_dir', lambda _: True)
    import pwd
    monkeypatch.setattr(pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=1002,pw_name='proxy',pw_dir='/home/proxy'))
    args = containers.argv(dict(engine='podman',owner='proxy'), ['inspect','haproxy'])
    assert args[:6] == ['runuser','--user','proxy','--','env','-i']
    assert 'XDG_RUNTIME_DIR=/run/user/1002' in args
    assert 'HOME=/home/proxy' in args
    assert args[-3:] == ['podman','inspect','haproxy']
    command = containers.shell(dict(engine='podman',owner='proxy'), ['inspect','haproxy'])
    assert command.startswith('sudo -n python3 -c ')
    assert '--user proxy' not in command  # Account resolution belongs to the host helper.


def test_quadlet_cannot_target_an_unrelated_system_service(monkeypatch):
    monkeypatch.setattr(containers.subprocess, 'run', lambda *_a, **_kw: SimpleNamespace(stdout='/usr/lib/systemd/system/sshd.service\n'))
    with pytest.raises(ValueError, match='Quadlet'):
        containers.lifecycle(dict(engine='podman',unit='sshd.service'), 'haproxy', 'stop')


def test_quadlet_must_define_the_exact_container(monkeypatch, tmp_path):
    path = tmp_path / 'proxy.container'
    path.write_text('[Container]\nContainerName=other-container\nImage=example.test/proxy\n')
    monkeypatch.setattr(containers.subprocess, 'run', lambda *_a, **_kw: SimpleNamespace(stdout=str(path)))
    original = Path.is_relative_to
    monkeypatch.setattr(Path, 'is_relative_to', lambda self, other: True if str(other).startswith('/etc/containers') else original(self, other))
    with pytest.raises(ValueError, match='container name'):
        containers.lifecycle(dict(engine='podman',unit='proxy.service'),'haproxy','stop')
    path.write_text('[Container]\nContainerName=haproxy\nImage=example.test/proxy\n')
    assert containers.lifecycle(dict(engine='podman',unit='proxy.service'),'haproxy','stop') == ['systemctl','stop','proxy.service']
    path.write_text('[Container]\nContainerName="haproxy"\nImage=example.test/proxy\n')
    assert containers.lifecycle(dict(engine='podman',unit='proxy.service'),'haproxy','stop') == ['systemctl','stop','proxy.service']
    path.write_text('[Container]\nImage=example.test/proxy\n')
    assert containers.lifecycle(dict(engine='podman',unit='proxy.service'),'systemd-proxy','stop') == ['systemctl','stop','proxy.service']
    path.write_text('[Container]\nContainerName=%N\nImage=example.test/proxy\n')
    with pytest.raises(ValueError, match='container name'):
        containers.lifecycle(dict(engine='podman',unit='proxy.service'),'haproxy','stop')


def test_podman_configuration_inspects_the_selected_engine(monkeypatch, tmp_path):
    calls=[]
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=b'[]')
    monkeypatch.setattr(candidate, '_run', run)
    validator=candidate._Validator(dict(container='haproxy',container_runtime=dict(engine='podman')),tmp_path/'a',tmp_path/'a')
    validator.inspect()
    assert calls == [['podman','inspect','--format','{{json .Mounts}}','haproxy']]


def test_certificate_helper_uses_the_selected_engine(monkeypatch):
    calls=[]
    def command(args, stage):
        calls.append(args)
        return b'[{"Source":"/srv/certs","Destination":"/certs","Type":"bind"}]'
    monkeypatch.setattr(certificate_remote, 'command', command)
    assert certificate_remote.certificate_runtime_path(dict(cert_dir='/srv/certs',pem_name='site.pem',
        docker=True,container='haproxy',container_runtime=dict(engine='podman'))) == '/certs/site.pem'
    assert calls[0][0] == 'podman'


def test_remote_runtime_module_has_no_controller_dependency():
    namespace={'__name__':'test_embedded_runtime'}
    exec(containers.embedded(), namespace)
    import roxywi_container_runtime
    assert roxywi_container_runtime.argv(dict(engine='podman'), ['ps']) == ['podman','ps']


def test_inspection_does_not_export_container_environment(monkeypatch):
    def run(args,**kwargs):
        if args[1]=='--version':output='podman version 5.4'
        elif args[1]=='ps':output='proxy-lab\n'
        else:output=json.dumps([dict(Config=dict(Image='example/proxy',Env=['REGISTRY_TOKEN=PRIVATE_VALUE']),
            State=dict(Running=True),HostConfig=dict(NetworkMode='host'),Mounts=[])])
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(containers.subprocess,'run',run)
    monkeypatch.setattr(Path,'glob',lambda *_:[])
    result=containers.inspect_host(dict(engine='podman'))
    assert result['containers'][0]['name']=='proxy-lab'
    assert 'PRIVATE_VALUE' not in json.dumps(result) and 'REGISTRY_TOKEN' not in json.dumps(result)


def test_rootless_staging_uses_stdin_without_exposing_host_file_permissions(monkeypatch,tmp_path):
    import io
    import tarfile
    directory=tmp_path/'private';directory.mkdir(mode=0o700)
    main=directory/'haproxy.cfg';main.write_text('global\n')
    upload=tmp_path/'candidate';upload.write_text('global\n    maxconn 80\n');upload.chmod(0o600)
    spec=dict(service='haproxy',container='proxy-lab',container_runtime=dict(engine='podman',owner='proxy'),
              action='test',main=str(main),target=str(main),sources=[str(main)],candidate=str(upload))
    original=containers.identity
    monkeypatch.setattr(containers,'identity',lambda spec: ['runuser','--user','proxy','--'] if spec['owner']=='proxy' else original(spec))
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        assert args[:5]==['runuser','--user','proxy','--','podman']
        action=args[5]
        output=b''
        if action=='inspect':output=json.dumps([dict(Type='bind',Source=str(directory),Destination='/config',RW=True)]).encode()
        elif action=='cp':
            assert args[6:]==['-','proxy-lab:/']
            with tarfile.open(fileobj=io.BytesIO(kwargs['input'])) as archive:
                member=archive.getmembers()[0]
                assert member.mode==0o600 and member.name.startswith('roxywi-') and '/' not in member.name
                assert archive.extractfile(member).read()==upload.read_bytes()
        elif args[-2:]==['id','-u'] or args[-2:]==['id','-g']:output=b'0\n'
        return SimpleNamespace(returncode=0,stdout=output)
    monkeypatch.setattr(candidate.subprocess,'run',run)
    validator=candidate._HaproxyValidator(spec,main,main)
    validator.inspect()
    assert validator.validate(upload)
    validator.close()
    assert upload.stat().st_mode&0o777==0o600
    assert directory.stat().st_mode&0o777==0o700
    assert any(args[5]=='cp' for args in calls)


@pytest.mark.parametrize('engine',['docker','podman'])
def test_nginx_status_counts_only_the_selected_containers_processes(monkeypatch,engine):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        action=args[1]
        stdout=json.dumps([dict(State=dict(Running=True,StartedAt='2026-10-28T00:00:00Z'))]) if action=='inspect' else 'COMMAND\nnginx\nnginx\n'
        return SimpleNamespace(returncode=0,stdout=stdout,stderr='nginx version: nginx/1.28.0' if action=='exec' else '')
    monkeypatch.setattr(containers.subprocess,'run',run)
    observed=containers.service_status(dict(engine=engine),'proxy-lab','nginx')
    assert observed['Process']=='2' and observed['Version']=='1.28.0'
    assert all(args[0]==engine for args in calls)
    assert all('proxy-lab' in args for args in calls)
    assert '--env' not in str(calls)


@pytest.mark.parametrize('unit_state,exists_code,expected_stopped', [('inactive',1,True),('failed',1,False),('active',1,False),('inactive',125,False)])
def test_absent_quadlet_container_is_stopped_only_with_verified_inactive_unit(monkeypatch,unit_state,exists_code,expected_stopped):
    calls=[]
    monkeypatch.setattr(containers,'verify_unit',lambda spec,name:calls.append(('verify',name)))
    def run(args,**kwargs):
        calls.append(args)
        code=125 if args[1]=='inspect' else exists_code if args[1:3]==['container','exists'] else 0
        return subprocess.CompletedProcess(args,code,stdout=unit_state+'\n',stderr='')
    monkeypatch.setattr(containers.subprocess,'run',run)
    spec=dict(engine='podman',unit='proxy.service')
    if expected_stopped:
        assert containers.service_status(spec,'proxy','nginx')['Process']=='0'
        assert ('verify','proxy') in calls
    else:
        with pytest.raises(subprocess.CalledProcessError):containers.container_state(spec,'proxy')
    assert not any('exec' in row or 'top' in row for row in calls)


def test_missing_unbound_container_does_not_masquerade_as_stopped(monkeypatch):
    monkeypatch.setattr(containers.subprocess,'run',lambda args,**kwargs:subprocess.CompletedProcess(args,125,stdout='',stderr=''))
    with pytest.raises(subprocess.CalledProcessError):containers.container_state(dict(engine='podman'),'missing')


def test_rootless_certificate_runtime_pins_the_verified_network_namespace(monkeypatch):
    ident='a'*64
    calls=[];closed=[]
    monkeypatch.setattr(containers,'identity',lambda _:['runuser','--user','proxy','--'])
    original_read=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda self,*a,**kw:ident if str(self)=='/proc/123/cgroup' else original_read(self,*a,**kw))
    monkeypatch.setattr(certificate_remote.os,'open',lambda path,*_:77 if path=='/proc/123/ns/net' else pytest.fail('Unexpected open'))
    monkeypatch.setattr(certificate_remote.os,'close',lambda fd:closed.append(fd))
    def command(args,stage,**kwargs):
        calls.append((args,kwargs))
        if 'inspect' in args:return json.dumps([dict(Id=ident,State=dict(Pid=123,Running=True))]).encode()
        assert args[:2]==['nsenter','--net=/proc/self/fd/77']
        assert kwargs['pass_fds']==(77,)
        assert b'SYNTHETIC_PRIVATE_PEM' in kwargs['input']
        assert 'SYNTHETIC_PRIVATE_PEM' not in str(args)
        return b'committed'
    monkeypatch.setattr(certificate_remote,'command',command)
    result=certificate_remote.rootless_runtime_request(dict(container='proxy-lab',container_runtime=dict(engine='podman',owner='proxy')),
        dict(server='127.0.0.1',port=1999,command='set ssl cert /certs/site.pem',payload='SYNTHETIC_PRIVATE_PEM'))
    assert result=='committed' and closed==[77]
    assert len(calls)==3


def test_rootless_certificate_runtime_rejects_a_reused_pid_before_sending_material(monkeypatch):
    monkeypatch.setattr(containers,'identity',lambda _:[])
    monkeypatch.setattr(certificate_remote,'command',lambda *_a,**_kw:json.dumps([dict(Id='a'*64,State=dict(Pid=123,Running=True))]).encode())
    monkeypatch.setattr(Path,'read_text',lambda *_a,**_kw:'another-container-id')
    monkeypatch.setattr(certificate_remote.os,'open',lambda *_:pytest.fail('An unrelated namespace must never be opened'))
    with pytest.raises(certificate_remote.CertificateFailure,match='runtime_unavailable'):
        certificate_remote.rootless_runtime_request(dict(container='proxy-lab',container_runtime=dict(engine='podman')),dict(payload='PRIVATE_PEM'))
