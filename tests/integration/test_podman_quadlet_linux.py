"""Validate actual systemd units produced by the installed Quadlet generator.

Generation is read-only. The opt-in drain test starts only a disposable container
in an isolated storage root; it never starts or changes the host's services.
"""
import importlib.util
import os
import json
import shutil
import shlex
import re
import time
from uuid import uuid4
from pathlib import Path
import subprocess
import tempfile

import pytest


GENERATOR=Path('/usr/lib/systemd/system-generators/podman-system-generator')
pytestmark=pytest.mark.skipif(not GENERATOR.is_file(),reason='Install Podman with Quadlet for real generator validation')


@pytest.fixture
def encrypted_backend(tmp_path,monkeypatch):
    if not shutil.which('gpg') or not shutil.which('podman'):
        pytest.skip('GnuPG and Podman are required for encrypted secret validation')
    home=tmp_path/'gnupg';home.mkdir(mode=0o700)
    monkeypatch.setenv('GNUPGHOME',str(home))
    run=subprocess.run
    run(['gpg','--batch','--pinentry-mode','loopback','--passphrase','','--quick-generate-key',
         'Synthetic Roxy-WI test <roxywi-test@example.invalid>','rsa2048','encr','1d'],
         check=True,capture_output=True,timeout=60)
    result=run(['gpg','--batch','--with-colons','--list-secret-keys'],check=True,capture_output=True,text=True,timeout=10)
    fingerprint=next(line.split(':')[9] for line in result.stdout.splitlines() if line.startswith('fpr:'))
    podman=shutil.which('podman')
    runtime=tempfile.TemporaryDirectory(prefix='rw-',dir='/tmp')
    def isolated(args,**kwargs):
        if args[0]=='podman':
            args=[podman,'--root',str(tmp_path/'engine'),'--runroot',runtime.name,
                  '--storage-driver=vfs','--events-backend=file',*args[1:]]
        result=run(args,**kwargs)
        if 'exists' in args:
            assert result.returncode in (0,1),result.stderr
        return result
    monkeypatch.setattr(subprocess,'run',isolated)
    try:
        yield fingerprint
    finally:
        run(['gpgconf','--homedir',str(home),'--kill','all'],capture_output=True,timeout=10)
        runtime.cleanup()


def test_controller_quadlets_generate_all_service_and_storage_units(tmp_path,encrypted_backend):
    path=Path(__file__).resolve().parents[2]/'podman/deploy.py'
    spec=importlib.util.spec_from_file_location('quadlet_generator_validation',path)
    deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)
    state=tmp_path/'private state';units=tmp_path/'units'
    deploy.prepare(state,units,gpg_fingerprint=encrypted_backend,image='sha256:'+'a'*64)
    metadata=(state/'secrets.json').read_bytes()
    deploy.prepare(state,units)
    assert (state/'secrets.json').read_bytes()==metadata
    assert not (state/'app.env').exists() and not (state/'broker.env').exists()
    for name in deploy.SECRET_NAMES.values():
        record=deploy.secret_record(name,show=True)
        assert record['Spec']['Driver']['Name']=='pass'
        secret=record['SecretData'].encode()
        assert all(secret not in path.read_bytes() for path in (tmp_path/'engine').rglob('*') if path.is_file())
        assert all(secret not in path.read_bytes() for path in state.rglob('*') if path.is_file())
    result=subprocess.run([str(GENERATOR),'--dryrun'],env={**os.environ,'QUADLET_UNIT_DIRS':str(units)},
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    for name in ('web','scheduler','service-events','operations','migrate','broker','tls'):
        assert 'roxywi-'+name+'.service' in result.stdout,result.stdout+'\n'+result.stderr
    assert '--init' in result.stdout
    assert 'roxywi-app-data:/var/lib/roxy-wi:U,z' in result.stdout
    assert '--publish 127.0.0.1:8443:443' in result.stdout
    assert '--secret roxywi-secret-key,type=env,target=ROXYWI_SECRET_KEY' in result.stdout
    assert '--env-file' not in result.stdout
    commands=[shlex.split(line.removeprefix('ExecStart=')) for line in result.stdout.splitlines() if line.startswith('ExecStart=')]
    # Newer generators encode the space in this fixture as systemd's \x20.
    # shlex preserves that C escape; normalize it before comparing argv paths.
    mounts=[command[index+1].replace(r'\x20',' ') for command in commands for index,argument in enumerate(command[:-1]) if argument in ('-v','--volume')]
    assert str(state/'roxy-wi.cfg')+':/etc/roxy-wi/roxy-wi.cfg:ro,z' in mounts
    assert str(state/'Caddyfile')+':/etc/caddy/Caddyfile:ro,Z' in mounts
    assert 'roxywi-migrate.service' in result.stdout
    assert 'unknown key' not in result.stderr.lower()
    assert 'failed to' not in result.stderr.lower(),result.stderr


STOP_LIMITS = {
    'web': (300, 360), 'scheduler': (300, 360), 'service-events': (300, 360),
    'operations': (1800, 1860), 'migrate': (300, 360),
    'broker': (120, 180), 'tls': (30, 90),
}


def _option(arguments, name):
    for index, argument in enumerate(arguments):
        if argument == name:
            return arguments[index + 1]
        if argument.startswith(name + '='):
            return argument[len(name) + 1:]
    raise AssertionError(f'Generated container command has no {name}')


def _generated_service(output, name):
    # Quadlet --dryrun concatenates generated unit files. Each service has its
    # own [Unit] section, independently of the generator's filename banners.
    for block in re.split(r'(?m)^\[Unit\]\s*$', output):
        for line in block.splitlines():
            if not line.startswith('ExecStart='):
                continue
            arguments = shlex.split(line.removeprefix('ExecStart='))
            if '--name' not in arguments and not any(a.startswith('--name=') for a in arguments):
                continue
            if _option(arguments, '--name') == name:
                return block, arguments
    raise AssertionError(f'No generated service for container {name}')


def _render_without_starting(tmp_path, image):
    path = Path(__file__).resolve().parents[2] / 'podman/deploy.py'
    spec = importlib.util.spec_from_file_location('quadlet_stop_validation', path)
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    directory = tmp_path / 'units'
    directory.mkdir()
    for name, content in deploy.units(tmp_path / 'state', image=image).items():
        (directory / name).write_text(content)
    generated = subprocess.run([str(GENERATOR), '--dryrun'],
        env={**os.environ, 'QUADLET_UNIT_DIRS': str(directory)},
        capture_output=True, text=True, timeout=30)
    assert generated.returncode == 0, generated.stderr
    assert 'failed to' not in generated.stderr.lower(), generated.stderr
    return generated.stdout


def test_generated_controller_services_preserve_container_and_systemd_drain_windows(tmp_path):
    generated = _render_without_starting(tmp_path, 'sha256:' + 'a' * 64)
    for role, (container_seconds, systemd_seconds) in STOP_LIMITS.items():
        block, arguments = _generated_service(generated, 'roxywi-' + role)
        assert int(_option(arguments, '--stop-timeout')) == container_seconds
        assert re.search(rf'(?m)^TimeoutStopSec={systemd_seconds}(?:s)?$', block), block


@pytest.mark.skipif(os.environ.get('ROXYWI_TEST_PODMAN_DRAIN') != '1',
                    reason='Enable ROXYWI_TEST_PODMAN_DRAIN=1 on an isolated Linux engine host')
def test_operations_container_can_finish_a_drain_longer_than_podmans_default(tmp_path):
    """Exercise SIGTERM + init forwarding and the generated engine stop timeout.

    Uses an independent vfs image/container store. The 12-second TERM handler
    exceeds Podman's usual ten-second default. Do not override podman stop's
    timeout: it must use the timeout stored when the container was created.
    """
    podman = shutil.which('podman')
    if not podman:
        pytest.skip('Podman is required for the actual signal/drain qualification')
    image = os.environ.get('ROXYWI_TEST_PODMAN_DRAIN_IMAGE', 'docker.io/library/alpine:3.21')
    generated = _render_without_starting(tmp_path, image)
    _block, arguments = _generated_service(generated, 'roxywi-operations')
    assert '--init' in arguments
    stop_timeout = _option(arguments, '--stop-timeout')
    assert int(stop_timeout) == 1800
    state = tmp_path / 'drain'
    state.mkdir()
    name = 'roxywi-drain-test-' + uuid4().hex
    with tempfile.TemporaryDirectory(prefix='rw-drain-', dir='/tmp') as runroot:
        engine = [podman, '--root', str(tmp_path / 'engine'), '--runroot', runroot,
                  '--storage-driver=vfs', '--events-backend=file']
        def run(*command, timeout=30, check=True):
            return subprocess.run([*engine, *command], capture_output=True,
                                  text=True, check=check, timeout=timeout)
        try:
            run('pull', image, timeout=180)
            script = ("trap 'echo draining > /state/status; sleep 12; "
                      "echo complete > /state/status; exit 0' TERM; "
                      "echo ready > /state/status; while :; do sleep 1 & wait $!; done")
            run('run', '--detach', '--name', name, '--network=none', '--init',
                '--stop-timeout', stop_timeout, '--volume', str(state) + ':/state:rw,Z',
                '--entrypoint', '/bin/sh', image, '-c', script)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if (state / 'status').is_file() and (state / 'status').read_text().strip() == 'ready':
                    break
                time.sleep(0.1)
            else:
                pytest.fail('Disposable drain container did not become ready: ' + run('logs', name).stdout)
            started = time.monotonic()
            run('stop', name, timeout=40)
            elapsed = time.monotonic() - started
            assert elapsed >= 11, f'Drain ended too early after {elapsed:.2f}s'
            assert (state / 'status').read_text().strip() == 'complete'
            status = json.loads(run('inspect', '--format', '{{json .State}}', name).stdout)
            assert status['ExitCode'] == 0 and not status.get('OOMKilled', False), status
        finally:
            run('rm', '--force', name, timeout=30, check=False)
