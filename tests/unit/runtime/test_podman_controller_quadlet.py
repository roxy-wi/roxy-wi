import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@pytest.fixture
def deploy(monkeypatch):
    path=Path(__file__).resolve().parents[3]/'podman/deploy.py'
    spec=importlib.util.spec_from_file_location('roxywi_quadlet_deploy',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    records={};calls=[]
    def run(args,**kwargs):
        assert args[:2]==['podman','secret']
        calls.append((args,kwargs))
        name=args[-2] if args[2]=='create' else args[-1]
        if args[2]=='exists':return SimpleNamespace(returncode=0 if name in records else 1)
        if args[2]=='create':
            assert name not in records and '--driver=pass' in args and args[-1]=='-'
            options=dict(item.removeprefix('--driver-opts=').split('=',1) for item in args if item.startswith('--driver-opts='))
            labels=dict(item.removeprefix('--label=').split('=',1) for item in args if item.startswith('--label='))
            records[name]={'Spec':{'Name':name,'Driver':{'Name':'pass','Options':options},'Labels':labels},'SecretData':kwargs['input']}
            return SimpleNamespace(returncode=0,stdout='synthetic-id')
        if args[2]=='inspect':
            record=dict(records[name])
            if '--showsecret' not in args:record.pop('SecretData')
            return SimpleNamespace(returncode=0,stdout=json.dumps([record]))
        pytest.fail('Unexpected Podman secret operation')
    module.secret_records=records;module.secret_calls=calls
    monkeypatch.setattr(module.subprocess,'run',run)
    return module


@pytest.mark.parametrize('existing', [False, True])
def test_resource_ownership_checks_decrypt_shared_secrets_once(deploy, tmp_path, monkeypatch, existing):
    (tmp_path / 'secrets.json').write_text('{}')
    label = {'org.roxy-wi.deployment': deploy.deployment_id(tmp_path)}
    inspected = []
    decrypted = []

    def run(arguments, **kwargs):
        if arguments[2] == 'exists':
            return SimpleNamespace(returncode=0 if existing else 1)
        assert arguments[2] == 'inspect'
        inspected.append((arguments[1], arguments[3]))
        return SimpleNamespace(returncode=0, stdout=json.dumps([
            {'Labels': label, 'Config': {'Labels': label}}]))

    monkeypatch.setattr(deploy.subprocess, 'run', run)
    monkeypatch.setattr(deploy, 'controller_secrets', lambda directory: decrypted.append(directory))
    deploy.verify_resources(tmp_path)
    assert len(inspected) == (12 if existing else 0)
    assert decrypted == ([tmp_path] if existing else [])


def test_all_controller_roles_share_private_data_and_migration_order(deploy,tmp_path):
    units=deploy.units(tmp_path)
    assert len(units)==12
    for role in deploy.ROLES:
        text=units['roxywi-'+role+'.container']
        assert 'Requires=roxywi-migrate.service roxywi-broker.service' in text
        assert 'After=roxywi-migrate.service roxywi-broker.service' in text
        assert 'Volume=roxywi-app.volume:/var/lib/roxy-wi:U,z' in text
        assert 'RunInit=true' in text and 'ROXYWI_DEPLOYMENT_MODE=quadlet' in text
        assert 'WantedBy=' in text
        assert 'PublishPort=' not in text and 'docker.sock' not in text and '/run/podman' not in text
    assert 'Type=oneshot\nRemainAfterExit=yes' in units['roxywi-migrate.container']
    assert 'TimeoutStopSec=1860' in units['roxywi-operations.container']
    assert 'PublishPort=127.0.0.1:8443:443' in units['roxywi-tls.container']
    assert 'app.env' not in units['roxywi-broker.container']
    assert 'docker-entrypoint.sh rabbitmq-diagnostics -q ping' in units['roxywi-broker.container']


def test_prepare_retains_secrets_and_does_not_share_them_with_broker(deploy,tmp_path):
    root=tmp_path/'state';units=tmp_path/'units'
    deploy.prepare(root,units,gpg_fingerprint="A"*40)
    metadata=(root/'secrets.json').read_bytes()
    records=json.dumps(deploy.secret_records,sort_keys=True)
    deploy.prepare(root,units,gpg_fingerprint="A"*40)
    assert (root/'secrets.json').read_bytes()==metadata
    assert json.dumps(deploy.secret_records,sort_keys=True)==records
    assert (root/'secrets.json').stat().st_mode&0o777==0o600
    assert root.stat().st_mode&0o777==0o700
    assert (root/'roxy-wi.cfg').stat().st_mode&0o777==0o644
    assert json.loads(metadata)=={'format':1,'key':'A'*40,'complete':True}
    for record in deploy.secret_records.values():
        value=record['SecretData']
        assert all(value not in path.read_text() for path in root.iterdir() if path.is_file())
        assert all(value not in arg for args,_kwargs in deploy.secret_calls for arg in args)
    assert not (root/'app.env').exists() and not (root/'broker.env').exists()
    broker=(units/'roxywi-broker.container').read_text()
    assert 'roxywi-broker-password,type=env,target=RABBITMQ_DEFAULT_PASS' in broker
    assert 'roxywi-secret-key' not in broker and 'roxywi-secret-phrase' not in broker


def test_prepare_refuses_unmanaged_units_and_secret_symlinks(deploy,tmp_path):
    root=tmp_path/'state';units=tmp_path/'units';units.mkdir()
    target=units/'roxywi-web.container';target.write_text('[Container]\nImage=other\n')
    with pytest.raises(ValueError,match='unmanaged'):
        deploy.prepare(root,units,gpg_fingerprint="A"*40)
    assert target.read_text()=='[Container]\nImage=other\n'
    target.unlink()
    secret=root/'secrets.json';secret.symlink_to(tmp_path/'missing-secret')
    with pytest.raises(ValueError,match='symlink'):
        deploy.prepare(root,units,gpg_fingerprint="A"*40)


@pytest.mark.parametrize('url',['http://example.test','https://user:secret@example.test','https://example.test/?token=x','https://example.test/path','https://example.test/\n[Service]'])
def test_quadlet_origin_cannot_inject_configuration(deploy,url,tmp_path):
    with pytest.raises(ValueError):deploy.units(tmp_path,public_url=url)


def test_unit_path_percent_and_spaces_are_escaped(deploy,tmp_path):
    assert deploy.unit_value('/private/state 50%')=='/private/state 50%%'
    with pytest.raises(ValueError):deploy.unit_value('/tmp/abc\n[Service]')
    with pytest.raises(ValueError):deploy.units(tmp_path,image='example;touch /tmp/marker')


def test_rootless_units_use_the_user_boot_target(deploy,tmp_path,monkeypatch):
    monkeypatch.setattr(deploy.os,'geteuid',lambda:1000)
    result=deploy.units(tmp_path)
    assert 'WantedBy=default.target' in result['roxywi-tls.container']
    assert all('WantedBy=default.target' in result['roxywi-'+role+'.container'] for role in deploy.ROLES)


def test_readiness_requires_stable_success_and_keeps_failure_visible(deploy,monkeypatch):
    clock=[0];reads=[]
    monkeypatch.setattr(deploy.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(deploy.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def run(args,**kwargs):
        reads.append(args)
        return SimpleNamespace(returncode=1 if len(reads)<=4 else 0)
    monkeypatch.setattr(deploy.subprocess,'run',run)
    deploy.wait_ready(timeout=15)
    assert len(reads)==16
    reads.clear()
    monkeypatch.setattr(deploy.subprocess,'run',lambda *_a,**_kw:SimpleNamespace(returncode=1))
    with pytest.raises(ValueError,match='retained'):deploy.wait_ready(timeout=4)


def test_existing_data_with_missing_encryption_key_is_never_reinitialized(deploy,tmp_path,monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args[2]=='exists':return SimpleNamespace(returncode=0)
        return SimpleNamespace(stdout=json.dumps([dict(Labels={'org.roxy-wi.deployment':deploy.deployment_id(tmp_path)})]))
    monkeypatch.setattr(deploy.subprocess,'run',run)
    with pytest.raises(ValueError,match='original deployment secrets'):
        deploy.verify_resources(tmp_path)
    assert not (tmp_path/'secrets.json').exists()
    assert all(args[1] in ('network','volume','container') for args in calls)


def test_foreign_volume_is_not_attached_to_new_controller(deploy,tmp_path,monkeypatch):
    monkeypatch.setattr(deploy.subprocess,'run',lambda args,**kwargs:SimpleNamespace(returncode=0,stdout='[{"Labels":{"org.roxy-wi.deployment":"foreign"}}]'))
    with pytest.raises(ValueError,match='another or unmanaged'):
        deploy.verify_resources(tmp_path)


def test_unmanaged_systemd_unit_cannot_be_started_or_stopped(deploy,tmp_path,monkeypatch):
    monkeypatch.setattr(deploy.subprocess,'run',lambda *_a,**_kw:SimpleNamespace(returncode=0,stdout='LoadState=loaded\nSourcePath=/etc/systemd/system/unrelated.service\n'))
    with pytest.raises(ValueError,match='unmanaged systemd'):
        deploy.verify_manager(['systemctl'],tmp_path)
    monkeypatch.setattr(deploy.subprocess,'run',lambda *_a,**_kw:SimpleNamespace(returncode=1,stdout='LoadState=not-found\n'))
    deploy.verify_manager(['systemctl'],tmp_path)


def test_ipv6_bind_is_explicit_and_remains_loopback_scoped(deploy,tmp_path):
    result=deploy.units(tmp_path,bind='[::1]:8443',public_url='https://[::1]:8443')
    assert 'PublishPort=[::1]:8443:443' in result['roxywi-tls.container']
    with pytest.raises(ValueError):deploy.units(tmp_path,bind='arbitrary-host:8443')


def test_preparing_units_preserves_an_operators_existing_configuration(deploy,tmp_path):
    state=tmp_path/'private';units=tmp_path/'units'
    deploy.prepare(state,units,gpg_fingerprint="A"*40)
    (state/'roxy-wi.cfg').write_text('[main]\nlog_console=1\n')
    (state/'Caddyfile').write_text('# operator configuration\n')
    deploy.prepare(state,units,gpg_fingerprint="A"*40)
    assert (state/'roxy-wi.cfg').read_text()=='[main]\nlog_console=1\n'
    assert (state/'Caddyfile').read_text()=='# operator configuration\n'


def test_healthy_workers_without_a_working_https_endpoint_do_not_report_ready(deploy,monkeypatch):
    clock=[0]
    monkeypatch.setattr(deploy.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(deploy.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    monkeypatch.setattr(deploy.subprocess,'run',lambda *_a,**_kw:SimpleNamespace(returncode=0))
    monkeypatch.setattr(deploy,'probe_https',lambda _url:False)
    with pytest.raises(ValueError,match='retained'):
        deploy.wait_ready(timeout=5,public_url='https://localhost:8443')


def test_real_https_probe_uses_public_ca_and_actual_readiness_route(deploy, tmp_path, monkeypatch):
    now = datetime.now(timezone.utc); ca_key = ec.generate_private_key(ec.SECP256R1())
    key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Disposable readiness CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(1).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_pem = ca.public_bytes(serialization.Encoding.PEM).decode()
    certificate = tmp_path/'server.pem'; certificate.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    private = tmp_path/'key.pem'
    with os.fdopen(os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
        output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    paths = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(200 if self.path == '/health/ready' else 302)
            if self.path != '/health/ready': self.send_header('Location', '/login')
            self.end_headers(); self.wfile.write(b'{"ready":true}')
        def log_message(self, *_args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def command(argv, **_kwargs):
        assert argv == ['podman', 'exec', 'roxywi-tls', 'cat', '/data/caddy/pki/authorities/local/root.crt']
        return SimpleNamespace(stdout=ca_pem)
    monkeypatch.setattr(deploy, 'command', command)
    try: assert deploy.probe_https(f'https://localhost:{server.server_port}')
    finally: server.shutdown(); server.server_close(); thread.join(timeout=3)
    assert paths == ['/health/ready']


@pytest.mark.parametrize('failure', ['', 'missing-init', 'timeout'])
def test_runtime_init_preflight_reports_missing_helper_and_cleans_its_own_probe(deploy, monkeypatch, failure):
    calls = []
    def run(argv, **_kwargs):
        calls.append(argv)
        if argv[1] == 'run':
            if failure == 'timeout': raise deploy.subprocess.TimeoutExpired(argv, 30)
            return SimpleNamespace(returncode=125 if failure else 0, stderr='lookup init binary: catatonit not found')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(deploy.subprocess, 'run', run)
    if failure:
        with pytest.raises(ValueError, match='catatonit' if failure == 'missing-init' else 'timed out'):
            deploy.verify_init_runtime('sha256:' + 'a' * 64)
    else: deploy.verify_init_runtime('sha256:' + 'a' * 64)
    name = calls[0][calls[0].index('--name') + 1]
    assert name.startswith('roxywi-init-probe-') and '--network=none' in calls[0]
    assert calls[1] == ['podman', 'rm', '--force', '--ignore', name]


def test_quadlet_tools_show_the_owner_and_disable_host_lifecycle(monkeypatch):
    from app.modules.tools import common
    monkeypatch.setattr(common.roxywi_mod,'deployment_mode',lambda:'quadlet')
    for role in ('web','scheduler','service-events','operations'):
        metadata=common._management_metadata('roxy-wi-'+role,'active',{'active':1})
        assert metadata['management']=='Podman Quadlet'
        assert metadata['can_lifecycle'] is False
        assert metadata['instances']==1


@pytest.mark.parametrize('failure',['missing','driver','owner','key','decrypt'])
def test_existing_encryption_secrets_are_never_replaced(deploy,tmp_path,failure):
    state=tmp_path/'state';units=tmp_path/'units'
    deploy.prepare(state,units,gpg_fingerprint='A'*40)
    name=deploy.SECRET_NAMES['secret_phrase']
    if failure=='missing':deploy.secret_records.pop(name)
    elif failure=='driver':deploy.secret_records[name]['Spec']['Driver']['Name']='file'
    elif failure=='owner':deploy.secret_records[name]['Spec']['Labels']={}
    elif failure=='key':deploy.secret_records[name]['Spec']['Driver']['Options']['key']='B'*40
    elif failure=='decrypt':deploy.secret_records[name]['SecretData']='invalid'
    before=json.dumps(deploy.secret_records,sort_keys=True)
    deploy.secret_calls.clear()
    with pytest.raises(ValueError):deploy.prepare(state,units)
    assert json.dumps(deploy.secret_records,sort_keys=True)==before
    assert not any(args[2]=='create' for args,_ in deploy.secret_calls)


def test_legacy_plaintext_installation_is_refused_without_replacing_its_keys(deploy,tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    old=state/'secrets.json';old.write_text('{"secret_key":"legacy-key"}')
    with pytest.raises(ValueError,match='reviewed migration'):
        deploy.prepare(state,tmp_path/'units',gpg_fingerprint='A'*40)
    assert old.read_text()=='{"secret_key":"legacy-key"}'
    assert not deploy.secret_records


def test_first_prepare_requires_an_explicit_gpg_key(deploy,tmp_path):
    with pytest.raises(ValueError,match='--gpg-fingerprint'):
        deploy.prepare(tmp_path/'state',tmp_path/'units')
    assert not deploy.secret_records


def test_interrupted_initial_prepare_resumes_without_rotating_created_secrets(deploy,tmp_path,monkeypatch):
    state=tmp_path/'state';units=tmp_path/'units'
    original=deploy.command
    def fail_second(args,**kwargs):
        if args[2]=='create' and args[-2]=='roxywi-secret-phrase':
            raise OSError('Synthetic interrupted initialization')
        return original(args,**kwargs)
    monkeypatch.setattr(deploy,'command',fail_second)
    with pytest.raises(OSError):deploy.prepare(state,units,gpg_fingerprint='A'*40)
    first=deploy.secret_records['roxywi-secret-key']['SecretData']
    assert json.loads((state/'secrets.json').read_text())['complete'] is False
    monkeypatch.setattr(deploy,'command',original)
    deploy.prepare(state,units)
    assert deploy.secret_records['roxywi-secret-key']['SecretData']==first
    assert len(deploy.secret_records)==3
    assert json.loads((state/'secrets.json').read_text())['complete'] is True


@pytest.fixture
def controller_cli(deploy, tmp_path, monkeypatch):
    """Simulate mutable tags and systemd's persistent completed oneshot state."""
    state = SimpleNamespace(tag='sha256:'+'a'*64, active=False, migrated=False,
                            migrations=[], starts=[], calls=[], root=tmp_path/'state', units=tmp_path/'units')
    original_run = deploy.subprocess.run
    original_is_file = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda path: True if str(path)=='/sys/fs/cgroup/cgroup.controllers' else original_is_file(path))
    monkeypatch.setattr(deploy, 'verify_resources', lambda *_: None)
    monkeypatch.setattr(deploy, 'verify_manager', lambda *_: None)
    monkeypatch.setattr(deploy, 'verify_init_runtime', lambda *_: None)
    monkeypatch.setattr(deploy, 'wait_ready', lambda **_: None)
    def image(role):
        return next(line[6:] for line in (state.units/f'roxywi-{role}.container').read_text().splitlines() if line.startswith('Image='))
    def run(argv, **kwargs):
        state.calls.append(argv)
        if argv[:2]==['podman', 'secret']: return original_run(argv, **kwargs)
        if argv==['podman', '--version']: return SimpleNamespace(stdout='podman version 5.4.2', returncode=0)
        if argv[:3]==['podman', 'image', 'inspect']: return SimpleNamespace(stdout=state.tag, returncode=0)
        if argv[0]=='systemctl':
            args=argv[1:]
            if args[0]=='--user': args=args[1:]
            if args[0]=='is-active': return SimpleNamespace(returncode=0 if state.active else 3)
            if args[0]=='stop':
                if 'roxywi-migrate.service' in args: state.migrated=False
                if 'roxywi-web.service' in args: state.active=False
            if args[0]=='start':
                if args[1:]==['roxywi-migrate.service']:
                    if not state.migrated: state.migrations.append(image('migrate')); state.migrated=True
                else: state.starts.append(image('web')); state.active=True
            return SimpleNamespace(returncode=0)
        pytest.fail('Unexpected controller command: '+repr(argv))
    monkeypatch.setattr(deploy.subprocess, 'run', run)
    def invoke(action, *options):
        monkeypatch.setattr(deploy.sys, 'argv', ['deploy.py', action, '--directory', str(state.root),
            '--unit-directory', str(state.units), '--gpg-fingerprint', 'A'*40, *options])
        deploy.main()
    state.invoke=invoke
    return state


def test_start_uses_prepared_image_even_when_all_roles_are_stopped_and_tag_moved(controller_cli):
    state=controller_cli
    state.invoke('prepare')
    prepared=state.tag
    assert json.loads((state.root/'settings.json').read_text())['image_id']==prepared
    state.tag='sha256:'+'b'*64
    state.calls.clear()
    state.invoke('start')
    assert state.starts==[prepared] and state.migrations==[prepared]
    assert not any(args[:3]==['podman','image','inspect'] for args in state.calls)


def test_still_active_migration_is_reset_and_upgrade_uses_matching_image(controller_cli):
    state=controller_cli
    state.invoke('prepare'); first=state.tag
    state.invoke('start')
    state.active=False  # App roles stopped independently; migration remains active.
    assert state.migrated
    state.tag='sha256:'+'b'*64
    state.invoke('start')
    assert state.migrations==[first,first] and state.starts==[first,first]
    state.invoke('upgrade')
    assert state.migrations==[first,first,state.tag] and state.starts[-1]==state.tag
    assert json.loads((state.root/'settings.json').read_text())['image_id']==state.tag
    stops=[i for i,args in enumerate(state.calls) if 'stop' in args and 'roxywi-migrate.service' in args]
    reloads=[i for i,args in enumerate(state.calls) if 'daemon-reload' in args]
    assert stops[-1]<reloads[-1]


@pytest.mark.parametrize('action', ['prepare','start'])
@pytest.mark.parametrize('options', [('--image','new:tag'),('--build',),('--public-url','https://localhost:9443')])
def test_prepared_deployment_changes_require_upgrade_even_if_inactive(controller_cli, action, options):
    state=controller_cli
    state.invoke('prepare')
    saved=(state.root/'settings.json').read_bytes()
    with pytest.raises(SystemExit) as error: state.invoke(action,*options)
    assert error.value.code==1
    assert (state.root/'settings.json').read_bytes()==saved
    assert not state.starts


def test_active_start_resumes_missing_roles_without_stopping_migration(controller_cli):
    state=controller_cli
    state.invoke('prepare'); state.invoke('start')
    state.tag='sha256:'+'b'*64
    state.calls.clear(); state.invoke('start')
    assert state.migrations==['sha256:'+'a'*64]
    assert state.starts==['sha256:'+'a'*64]*2
    assert not any('stop' in args for args in state.calls)


def test_legacy_settings_without_pin_refuse_ordinary_start(controller_cli):
    state=controller_cli
    state.invoke('prepare')
    path=state.root/'settings.json'; settings=json.loads(path.read_text()); del settings['image_id']; path.write_text(json.dumps(settings))
    with pytest.raises(SystemExit): state.invoke('start')
    assert not state.starts
    state.invoke('upgrade')
    assert state.migrations==[state.tag]


@pytest.mark.parametrize('role,seconds', [('operations',1800),('web',300),('scheduler',300),
    ('service-events',300),('migrate',300),('broker',120),('tls',30)])
def test_container_and_systemd_shutdown_budgets_allow_real_drain(deploy,tmp_path,role,seconds):
    text=deploy.units(tmp_path)[f'roxywi-{role}.container']
    assert f'StopTimeout={seconds}\n' in text
    timeout=int(next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('TimeoutStopSec=')))
    assert timeout>=seconds+60
