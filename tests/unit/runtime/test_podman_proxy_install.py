import importlib.util
import json
import os
from pathlib import Path
import pwd
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from app.modules.roxywi.class_models import HAClusterService, ServiceInstall
from app.modules.service import installation


@pytest.fixture
def recipe():
    source = Path(__file__).resolve().parents[3] / 'app/scripts/ansible/roles/podman_proxy/files/proxy.py'
    spec = importlib.util.spec_from_file_location('podman_proxy_recipe', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def options(tmp_path):
    return dict(service='haproxy', name='haproxy', image='docker.io/haproxytech/haproxy-alpine:3.3.1',
                directory=str(tmp_path / 'proxy'), config=str(tmp_path / 'proxy/haproxy.cfg'),
                certificates='/var/lib/roxy-wi/certificates/haproxy', user=pwd.getpwuid(os.geteuid()).pw_name,
                stats_port='8085', runtime_port='1999', stats_user='stats', stats_password='testing-password',
                stats_page='stats', syn_flood=False)


@pytest.mark.parametrize('old,explicit,expected', [(False,None,'native'),(True,None,'docker'),
    (True,'native','native'),(False,'podman','podman'),(True,'podman','podman')])
def test_explicit_engine_and_legacy_boolean_have_unambiguous_meaning(old,explicit,expected):
    parsed = HAClusterService(docker=old, container_engine=explicit)
    assert installation.installation_engine(parsed.model_dump()) == expected


@pytest.mark.parametrize('key,value', [('name','--privileged'), ('image','other/image:latest'),
    ('directory','/etc'), ('config','/etc/shadow'), ('directory','/tmp/x\n[Service]'),
    ('stats_password','password\nlisten admin'),('certificates','/etc/ssl/certs')])
def test_recipe_rejects_unmanaged_paths_images_and_configuration_injection(recipe,options,key,value):
    options[key] = value
    with pytest.raises(ValueError): recipe.validate(options)


def test_recipe_refuses_foreign_container_before_pulling_or_replacing_files(recipe,options,tmp_path,monkeypatch):
    generator = tmp_path / 'generator'; generator.touch()
    monkeypatch.setattr(recipe,'GENERATOR',generator)
    monkeypatch.setattr(recipe,'STATE',tmp_path / 'state')
    monkeypatch.setattr(recipe,'UNITS',tmp_path / 'units')
    monkeypatch.setattr(recipe.os,'geteuid',lambda:0)
    # The private state created by this unprivileged test belongs to this account.
    original_stat = recipe.Path.stat
    def stat(path,*args,**kwargs):
        result = original_stat(path,*args,**kwargs)
        if str(path).startswith(str(tmp_path / 'state')):
            return SimpleNamespace(st_uid=0, st_mode=result.st_mode)
        return result
    monkeypatch.setattr(recipe.Path,'stat',stat)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args == ['podman','--version']: return 'podman version 4.9.3'
        if args[:2] == ['podman','inspect']: return json.dumps([{'Config':{'Labels':{}}}])
        pytest.fail('Unexpected mutation: '+repr(args))
    monkeypatch.setattr(recipe,'run',run)
    monkeypatch.setattr(recipe.subprocess,'run',lambda args,**kw:SimpleNamespace(returncode=0,
        stdout='LoadState=not-found\nSourcePath=\n' if args[0]=='systemctl' else ''))
    with pytest.raises(ValueError,match='Adopt the existing container'):
        recipe.install(options)
    assert not Path(options['directory']).exists()
    assert not (tmp_path/'units').exists()


def test_proxy_quadlet_uses_pinned_image_and_dedicated_certificate_mount(recipe,options):
    unit = recipe.render_unit(options,'sha256:'+'a'*64)
    assert 'Image=sha256:'+'a'*64 in unit
    assert '/var/lib/roxy-wi/certificates/haproxy:/var/lib/roxy-wi/certificates/haproxy:rw,Z' in unit
    assert '/etc/ssl/certs:' not in unit
    assert 'SecurityLabelDisable' not in unit
    assert 'WantedBy=multi-user.target' in unit


@pytest.mark.parametrize('service', ['haproxy', 'nginx', 'apache'])
def test_actual_quadlet_generator_preserves_mount_arguments(recipe, options, tmp_path, service):
    if not recipe.GENERATOR.is_file():
        pytest.skip('Podman Quadlet generator required')
    options['service'] = service
    options['log_directory'] = str(tmp_path / 'logs')
    units = tmp_path / 'units'; units.mkdir()
    (units / 'proxy.container').write_text(recipe.render_unit(options, 'sha256:' + 'a' * 64))
    result = subprocess.run([str(recipe.GENERATOR), '--dryrun'],
        env={**os.environ, 'QUADLET_UNIT_DIRS': str(units)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and 'failed to' not in result.stderr.lower()
    command = next(shlex.split(line.removeprefix('ExecStart=')) for line in result.stdout.splitlines() if line.startswith('ExecStart='))
    mounts = [command[index + 1] for index, argument in enumerate(command[:-1]) if argument in ('-v', '--volume')]
    assert options['directory'] + ':' + options['directory'] + ':rw,Z' in mounts
    assert options['certificates'] + ':' + options['certificates'] + ':rw,Z' in mounts
    if service != 'haproxy':
        assert options['log_directory'] + ':' + options['log_directory'] + ':rw,Z' in mounts
    if service == 'apache':
        assert options['directory'] + ':/usr/local/apache2/conf:rw,Z' in mounts


def test_podman_installer_uses_durable_queue_and_does_not_run_the_docker_role(app,monkeypatch):
    monkeypatch.setattr(installation,'_authorize_installation_servers',lambda *_:None)
    monkeypatch.setattr(installation,'generate_haproxy_inv',lambda *_:({'server':{'hosts':{'192.0.2.10':{
        'CONT_NAME':'haproxy','HAP_DIR':'/etc/haproxy','HAPVER':'3.3.1-1'}}}},['192.0.2.10']))
    monkeypatch.setattr(installation.sql,'get_setting',lambda *_:'/etc/haproxy/haproxy.cfg')
    saved=[]
    monkeypatch.setattr(installation,'run_ansible_thread',lambda *args,**kw:saved.append((args,kw)) or 81)
    body=ServiceInstall(servers=[{'id':11}],services={'haproxy':{'enabled':True,'container_engine':'podman'}},syn_flood=True)
    assert installation.install_service('haproxy',body)==81
    args,kw=saved[0]
    assert args[2]=='podman_proxy'
    host=args[0]['server']['hosts']['192.0.2.10']
    assert host['CONTAINER_ENGINE']=='podman' and host['SYN_FLOOD'] is True
    assert host['IMAGE']=='docker.io/haproxytech/haproxy-alpine:3.3.1'
    assert kw['success_action']['request']['services']['haproxy']['docker'] is True


def test_failed_preparation_does_not_leave_partial_production_configuration(recipe,options,tmp_path,monkeypatch):
    state=tmp_path/'state';state.mkdir();manifest=state/'manifest.json'
    directory=Path(options['directory']);binding={'service':'haproxy'}
    def interrupted(data,image,destination):
        (destination/'haproxy.cfg').write_text('partial preparation')
        raise ValueError('Image configuration could not be prepared')
    monkeypatch.setattr(recipe,'configure',interrupted)
    with pytest.raises(ValueError,match='prepared'):
        recipe.prepare_configuration(options,'pinned-image',directory,state,manifest,binding,None)
    assert not list(directory.iterdir())
    assert json.loads(manifest.read_text())['phase']=='preparing'
    monkeypatch.setattr(recipe,'configure',lambda data,image,destination:(destination/'haproxy.cfg').write_text('complete configuration'))
    recipe.prepare_configuration(options,'pinned-image',directory,state,manifest,binding,json.loads(manifest.read_text()))
    assert (directory/'haproxy.cfg').read_text()=='complete configuration'
    assert json.loads(manifest.read_text())['phase']=='configured'


def test_resume_after_lost_rename_reply_preserves_the_installed_tree(recipe,options,tmp_path,monkeypatch):
    state=tmp_path/'state';state.mkdir();manifest=state/'manifest.json'
    directory=Path(options['directory']);binding={'service':'haproxy'}
    monkeypatch.setattr(recipe,'configure',lambda data,image,destination:(destination/'haproxy.cfg').write_text('verified configuration'))
    replace=recipe.os.replace
    def disconnected(source,target):
        replace(source,target)
        if Path(source).name=='tree':raise OSError('Reply lost after atomic installation')
    monkeypatch.setattr(recipe.os,'replace',disconnected)
    with pytest.raises(OSError):recipe.prepare_configuration(options,'image',directory,state,manifest,binding,None)
    saved=json.loads(manifest.read_text())
    assert saved['phase']=='configuration-staged'
    monkeypatch.setattr(recipe,'configure',lambda *_:pytest.fail('An installed tree was overwritten'))
    recipe.prepare_configuration(options,'image',directory,state,manifest,binding,saved)
    assert (directory/'haproxy.cfg').read_text()=='verified configuration'


def test_nginx_configuration_keeps_image_mime_types_inside_its_dedicated_mount(recipe,options,tmp_path,monkeypatch):
    options.update(service='nginx',directory=str(tmp_path/'runtime'),config=str(tmp_path/'runtime/nginx.conf'),
        certificates=str(tmp_path/'certs'),log_directory=str(tmp_path/'logs'))
    staged=tmp_path/'staged';staged.mkdir()
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        assert argv[:2] in (['podman','create'],['podman','cp'])
        if argv[1]=='create':
            assert argv[-3:]==['--network','none','sha256:'+'a'*64]
        else:
            assert argv[2].endswith(':/etc/nginx/mime.types')
            Path(argv[3]).write_text('types { text/plain txt; }\n')
        return ''
    monkeypatch.setattr(recipe,'run',run)
    monkeypatch.setattr(recipe.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='fixture-password-hash'))
    recipe.configure(options,'sha256:'+'a'*64,staged)
    assert (staged/'mime.types').read_text()=='types { text/plain txt; }\n'
    assert 'include '+options['directory']+'/mime.types;' in (staged/'nginx.conf').read_text()
    assert not any(argv[1]=='run' for argv in calls)


def test_nginx_mime_retry_preserves_existing_operator_file(recipe,options,tmp_path,monkeypatch):
    path=tmp_path/'mime.types';path.write_text('types { application/x-operator custom; }\n')
    monkeypatch.setattr(recipe,'run',lambda *_:pytest.fail('Existing MIME configuration must not be replaced from an image'))
    recipe.nginx_mime_types(options,'new-image',tmp_path)
    assert path.read_text()=='types { application/x-operator custom; }\n'


def test_failed_nginx_image_copy_cleans_only_its_disposable_seed(recipe,options,tmp_path,monkeypatch):
    seed=[];removed=[]
    def run(argv,**kwargs):
        if argv[1]=='create':seed.append(argv[3]);return ''
        raise RuntimeError('Image copy failed')
    monkeypatch.setattr(recipe,'run',run)
    monkeypatch.setattr(recipe.subprocess,'run',lambda argv,**kwargs:removed.append(argv) or SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError,match='Image copy failed'):
        recipe.nginx_mime_types(options,'pinned-image',tmp_path)
    assert removed==[['podman','rm','-f',seed[0]]]
    assert not (tmp_path/'mime.types').exists()
