import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.modules.pacemaker import operations, qdevice
from app.modules.pacemaker.schemas import WitnessInstall
from app.modules.pacemaker.witness_docker import RUNTIME, RECIPE


def runtime(tmp_path, monkeypatch):
    values = {}
    root = tmp_path / 'witness'
    exec(RUNTIME.replace("ROOT = pathlib.Path('/var/lib/roxy-wi/qnetd')", f'ROOT = pathlib.Path({str(root)!r})'), values)
    values.update(ROOT=root, DATA=root / 'data', CERT=root / 'data/nssdb/qnetd-cacert.crt',
                  platform_profile=lambda: {'manager': 'apt-get'},
                  install_packages=lambda *_: pytest.fail('Docker is already installed'))
    monkeypatch.setattr(values['shutil'], 'which', lambda _: '/usr/bin/docker')
    original_exists = values['pathlib'].Path.exists
    monkeypatch.setattr(values['pathlib'].Path, 'exists', lambda p: False if str(p) == '/etc/corosync/qnetd/nssdb' else original_exists(p))
    return values


def managed():
    return {'State': {'Running': True}, 'Image': 'sha256:reviewed-image',
            'Config': {'Labels': {'org.roxy-wi.recipe': RECIPE, 'org.roxy-wi.role': 'qnetd'}},
            'Mounts': [{'Type': 'bind', 'Source': '/var/lib/roxy-wi/qnetd/data', 'Destination': '/etc/corosync/qnetd'}]}


def test_docker_mode_is_strict_and_survives_durable_worker_dispatch(monkeypatch):
    with pytest.raises(ValidationError): WitnessInstall(server_id=1, docker='false')
    assert WitnessInstall(server_id=1).docker is False
    calls = []
    monkeypatch.setattr(qdevice, 'witness_server', lambda *_: SimpleNamespace(ip='192.0.2.1', port=22, cred_id=7, server_id=1))
    monkeypatch.setattr(qdevice, 'install_witness', lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(operations.User, 'get_or_none', lambda *_: SimpleNamespace(user_id=1, enabled=True))
    monkeypatch.setattr(operations.user_sql, 'select_user_services', lambda _: '5')
    monkeypatch.setattr(operations.user_sql, 'get_user_role_in_group', lambda *_: 1)
    task = SimpleNamespace(id=987, user_id_id=1, group_id_id=1)
    monkeypatch.setattr(operations.InstallationTasks, 'update', lambda **_: SimpleNamespace(where=lambda *_: SimpleNamespace(execute=lambda: None)))
    payload = {'server_id': 1, 'docker': True, 'identity': {'ip': '192.0.2.1', 'port': 22, 'cred_id': 7}}
    assert operations.execute_witness(task, payload) == 'completed'
    assert calls == [((1, 1), {'docker': True})]


@pytest.mark.parametrize('bad', ['label', 'mount', 'daemon'])
def test_container_discovery_never_adopts_an_unmanaged_container(tmp_path, monkeypatch, bad):
    code = runtime(tmp_path, monkeypatch)
    state = managed()
    if bad == 'label': state['Config']['Labels'] = {}
    if bad == 'mount': state['Mounts'] = []
    def command(args, **_):
        if args[1] == 'info' and bad == 'daemon': raise RuntimeError('unreachable Docker daemon')
        return 'roxywi-qnetd' if args[1] == 'ps' else json.dumps([state])
    code['command'] = command
    with pytest.raises((SystemExit, RuntimeError)): code['container_state']()


def test_repeated_docker_install_preserves_ca_and_container(tmp_path, monkeypatch):
    code = runtime(tmp_path, monkeypatch)
    code['CERT'].parent.mkdir(parents=True)
    code['CERT'].write_bytes(b'original-ca')
    code['container_state'] = managed
    code['docker_status'] = lambda _: {'active': True}
    calls = []
    code['command'] = lambda args, **_: calls.append(args)
    code['prepare_docker']()
    assert calls == [['docker', 'start', 'roxywi-qnetd']]
    assert code['CERT'].read_bytes() == b'original-ca'


def test_new_docker_witness_uses_persistent_tls_and_restricted_runtime(tmp_path, monkeypatch):
    code = runtime(tmp_path, monkeypatch)
    states = iter([None, managed()])
    code['container_state'] = lambda: next(states)
    code['docker_status'] = lambda _: {'active': True}
    monkeypatch.setattr(code['socket'], 'socket', MagicMock())
    monkeypatch.setattr(code['os'], 'chown', lambda *_: None)
    monkeypatch.setattr(code['subprocess'], 'run', lambda args, **_kwargs: SimpleNamespace(returncode=3 if 'is-active' in args else 0))
    original_exists = code['pathlib'].Path.exists
    monkeypatch.setattr(code['pathlib'].Path, 'exists', lambda p: False if str(p) == '/etc/corosync/qnetd/nssdb' else original_exists(p))
    calls = []
    def command(args, **_):
        calls.append(args)
        if args[1:3] == ['image', 'inspect']: return json.dumps([{'Id': 'sha256:reviewed-image'}])
        if args[1] == 'run':
            code['CERT'].parent.mkdir()
            code['CERT'].write_bytes(b'new-ca')
        return ''
    code['command'] = command
    code['prepare_docker']()
    run = next(args for args in calls if args[1] == 'run')
    assert run[-1] == 'sha256:reviewed-image'
    for value in ['--read-only', '--cap-drop', 'ALL', 'no-new-privileges', '65532:65532', 'unless-stopped', 'host']:
        assert value in run
    assert str(code['DATA']) + ':/etc/corosync/qnetd:rw,Z' in run
    assert '--privileged' not in run and '/var/run/docker.sock' not in ' '.join(run)


def test_orphaned_certificate_storage_is_not_overwritten(tmp_path, monkeypatch):
    code = runtime(tmp_path, monkeypatch)
    code['CERT'].parent.mkdir(parents=True)
    code['CERT'].write_bytes(b'preserve-me')
    code['container_state'] = lambda: None
    original_exists = code['pathlib'].Path.exists
    monkeypatch.setattr(code['pathlib'].Path, 'exists', lambda p: False if str(p) == '/etc/corosync/qnetd/nssdb' else original_exists(p))
    monkeypatch.setattr(code['socket'], 'socket', MagicMock())
    monkeypatch.setattr(code['subprocess'], 'run', lambda *_args, **_kwargs: SimpleNamespace(returncode=3))
    with pytest.raises(SystemExit, match='recover it explicitly'): code['prepare_docker']()
    assert code['CERT'].read_bytes() == b'preserve-me'


def test_existing_native_ca_prevents_docker_changes(tmp_path, monkeypatch):
    code = runtime(tmp_path, monkeypatch)
    original_exists = code['pathlib'].Path.exists
    monkeypatch.setattr(code['pathlib'].Path, 'exists', lambda p: True if str(p) == '/etc/corosync/qnetd/nssdb' else original_exists(p))
    code['container_state'] = lambda: pytest.fail('A native witness must be rejected before Docker changes')
    with pytest.raises(SystemExit, match='explicit migration'): code['prepare_docker']()


def test_container_disappearing_during_recovery_is_a_transient_native_state(tmp_path,monkeypatch):
    code=runtime(tmp_path,monkeypatch)
    scans=iter(['roxywi-qnetd',''])
    def command(args,**_):
        if args[1]=='ps':return next(scans)
        if args[1]=='inspect':raise code['subprocess'].CalledProcessError(1,args)
        return '26.0'
    code['command']=command
    assert code['container_state']() is None
