"""Keepalived observations must never turn transport errors into service DOWN."""
import json
import io
from contextlib import redirect_stdout
import os
import struct
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from peewee import OperationalError

from app.modules.connectors import keepalived as probe
from app.modules.integrations.keepalived_contract import KeepalivedSnapshot
from app.modules.service import keepalived as service


DUMP = '''------< VRRP Topology >------
 VRRP Instance = VI_PUBLIC
   VRRP Version = 2
   State = MASTER
   Wantstate = MASTER
   Authentication Password = DoNotReturnThis
 VRRP Instance = VI_PRIVATE
   State = BACKUP
   Wantstate = BACKUP
'''


def test_every_instance_is_read_without_configuration_secrets():
    instances = probe.parse_instances(DUMP)
    assert instances == [dict(name='VI_PUBLIC', state='MASTER'), dict(name='VI_PRIVATE', state='BACKUP')]
    assert 'DoNotReturnThis' not in json.dumps(instances)


@pytest.mark.parametrize('dump', ['', 'State = MASTER', DUMP + ' VRRP Instance = unfinished\n',
                                DUMP.replace('State = BACKUP', 'State = UNKNOWN')])
def test_incomplete_or_unknown_dump_is_not_a_partial_success(dump):
    with pytest.raises(ValueError):
        probe.parse_instances(dump)


@pytest.mark.parametrize('payload', [
    dict(service='UP', instances=[]),
    dict(service='DOWN', instances=[dict(name='one', state='MASTER')]),
    dict(service='UP', instances=[dict(name='one', state='MASTER'), dict(name='one', state='BACKUP')]),
    dict(service='UP', instances=[dict(name='one', state='UNKNOWN')]),
    dict(service='UP', instances=[dict(name='one', state='MASTER', auth_pass='secret')]),
])
def test_snapshot_rejects_invalid_or_sensitive_fields(payload):
    with pytest.raises(ValidationError):
        KeepalivedSnapshot.model_validate(payload)


@pytest.mark.parametrize('state,pid,expected', [('active', 12, (True, 12)), ('inactive', 0, (False, 0)),
                                            ('failed', 0, (False, 0))])
def test_native_process_status(monkeypatch, state, pid, expected):
    monkeypatch.setattr(probe.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        stdout=f'LoadState=loaded\nActiveState={state}\nMainPID={pid}\n'))
    assert probe.native_state() == expected


@pytest.mark.parametrize('output', ['LoadState=not-found\nActiveState=inactive\nMainPID=0',
                                  'LoadState=loaded\nActiveState=activating\nMainPID=12',
                                  'LoadState=loaded\nActiveState=active\nMainPID=0', ''])
def test_unavailable_systemd_or_transition_is_unknown(monkeypatch, output):
    monkeypatch.setattr(probe.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=output))
    with pytest.raises(ValueError):
        probe.native_state()


def test_native_restart_during_probe_rejects_result(monkeypatch):
    states = iter([(True, 12), (True, 13)])
    monkeypatch.setattr(probe, 'native_state', lambda: next(states))
    monkeypatch.setattr(probe, 'fresh_dump', lambda pid: probe.parse_instances(DUMP))
    with pytest.raises(ValueError, match='restarted'):
        probe.collect()


def test_stopped_process_does_not_read_stale_dump(monkeypatch):
    monkeypatch.setattr(probe, 'native_state', lambda: (False, 0))
    monkeypatch.setattr(probe, 'fresh_dump', lambda pid: pytest.fail('Read a stale dump'))
    assert probe.collect() == dict(service='DOWN', instances=[])


def test_container_uses_verified_host_pid(monkeypatch):
    calls = []
    monkeypatch.setattr(probe, 'fresh_dump', lambda pid: calls.append(pid) or probe.parse_instances(DUMP))
    record = dict(State=dict(Running=True, Pid=123), HostConfig=dict(NetworkMode='host'))
    assert len(probe.collect(record)['instances']) == 2
    assert calls == [123]
    record['HostConfig']['NetworkMode'] = 'bridge'
    with pytest.raises(ValueError):
        probe.collect(record)
    record['State']['Running'] = False
    assert probe.collect(record)['service'] == 'DOWN'


@pytest.mark.parametrize('states,expected', [(['BACKUP'], 'BACKUP'), (['MASTER', 'BACKUP'], 'MASTER'),
                                           (['MASTER', 'FAULT'], 'FAULT'), (['INIT', 'BACKUP'], 'INIT')])
def test_aggregate_label_does_not_hide_an_instance_failure(states, expected):
    snapshot = KeepalivedSnapshot(service='UP', instances=[dict(name=str(i), state=s) for i, s in enumerate(states)])
    assert service.summary(snapshot) == expected


@pytest.mark.parametrize('dockerized', [False, True])
def test_shared_collector_sends_fixed_source_and_settings(monkeypatch, dockerized):
    monkeypatch.setattr(service.service_sql, 'select_service_setting', lambda *a: '1' if dockerized else '0')
    monkeypatch.setattr(service.container_settings, 'runtime', lambda *a: dict(engine='podman', owner='root', unit=''))
    monkeypatch.setattr(service.container_settings, 'name', lambda *a: 'keepalived')
    calls = []
    def run(argv, **kw):
        compile(argv[2], 'remote-probe', 'exec')
        calls.append((argv, kw))
        return json.dumps(dict(service='UP', instances=probe.parse_instances(DUMP)))
    monkeypatch.setattr(service, 'Remote', lambda server: SimpleNamespace(run=run))
    assert len(service.collect(SimpleNamespace(server_id=42)).instances) == 2
    data = json.loads(calls[0][1]['data'])
    assert bool(data) == dockerized
    assert calls[0][0][:2] == ['python3', '-c']
    assert calls[0][1]['timeout'] == 45


def test_database_failure_cannot_switch_a_container_probe_to_the_host(monkeypatch):
    def fail(*args):
        raise OperationalError('database is unavailable')
    monkeypatch.setattr(service.service_sql.ServiceSetting, 'get', fail)
    monkeypatch.setattr(service, 'Remote', lambda server: pytest.fail('Incorrect host fallback'))
    with pytest.raises(OperationalError):
        service.collect(SimpleNamespace(server_id=42))


def test_missing_setting_preserves_native_default(monkeypatch):
    def missing(*args):
        raise service.service_sql.ServiceSetting.DoesNotExist()
    monkeypatch.setattr(service.service_sql.ServiceSetting, 'get', missing)
    assert service.service_sql.select_service_setting(42, 'keepalived', 'dockerized') == '0'


def test_binding_change_during_probe_discards_old_host_result(monkeypatch):
    bindings = iter([{}, dict(runtime=dict(engine='docker', owner='root'), name='keepalived')])
    monkeypatch.setattr(service, 'probe_settings', lambda server: next(bindings))
    monkeypatch.setattr(service, 'Remote', lambda server: SimpleNamespace(
        run=lambda *a, **kw: '{"service":"DOWN","instances":[]}'))
    with pytest.raises(ValueError, match='binding changed'):
        service.collect(SimpleNamespace(server_id=42))


@pytest.mark.parametrize('changed', ['health', 'pid', 'stopped'])
def test_container_identity_ignores_healthcheck_counters_but_rejects_restarts(monkeypatch, tmp_path, changed):
    source = tmp_path / 'probe.py'
    source.write_text("def collect(record): return {'service': 'UP', 'instances': [{'name': 'one', 'state': 'BACKUP'}]}\n")
    monkeypatch.setattr(probe, '__file__', str(source))
    monkeypatch.setattr(service.service_sql, 'select_service_setting', lambda *a: '1')
    monkeypatch.setattr(service.container_settings, 'runtime', lambda *a: dict(engine='docker', owner='root', unit=''))
    monkeypatch.setattr(service.container_settings, 'name', lambda *a: 'keepalived')
    before = dict(Id='a'*64, State=dict(Running=True, Pid=55, Health=dict(FailingStreak=0)))
    after = dict(Id='a'*64, State=dict(Running=changed != 'stopped', Pid=66 if changed == 'pid' else 55,
                                     Health=dict(FailingStreak=1)))
    embedded = ('from types import SimpleNamespace\nrecords=' + repr([before, after]) + '\n'
                'module=SimpleNamespace(container_state=lambda *a: records.pop(0))\n')
    monkeypatch.setattr(service.containers, 'embedded', lambda: embedded)
    def run(argv, **kw):
        monkeypatch.setattr(sys, 'stdin', io.StringIO(kw['data']))
        output = io.StringIO()
        with redirect_stdout(output):
            exec(compile(argv[2], 'probe', 'exec'), {})
        return output.getvalue()
    monkeypatch.setattr(service, 'Remote', lambda server: SimpleNamespace(run=run))
    if changed == 'health':
        assert service.collect(SimpleNamespace(server_id=42)).service == 'UP'
    else:
        with pytest.raises(ValueError, match='Container changed'):
            service.collect(SimpleNamespace(server_id=42))


@pytest.mark.parametrize('mode', ['fresh', 'stale', 'partial', 'restart', 'busy'])
def test_dump_freshness_completion_locking_and_cleanup(monkeypatch, tmp_path, mode):
    """Drive Linux syscalls explicitly so these failure paths also run on Windows."""
    path = tmp_path / 'keepalived.data'
    path.write_text(' VRRP Instance = old\n   State = FAULT\n')
    clock = iter(range(100))
    monkeypatch.setattr(probe.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(probe.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(probe, 'Path', lambda *args: path)
    identities = iter(['before', 'before', 'changed' if mode == 'restart' else 'before'])
    monkeypatch.setattr(probe, 'process_identity', lambda pid: next(identities))
    def flock(*args):
        if mode == 'busy':
            raise BlockingIOError()
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(flock=flock, LOCK_EX=1, LOCK_NB=2))
    monkeypatch.setattr(probe.ctypes, 'CDLL', lambda *a, **kw: SimpleNamespace(
        inotify_init1=lambda flags: 12345, inotify_add_watch=lambda *a: 1))
    signalled = []
    def kill(pid, sig):
        signalled.append(pid)
        if mode != 'stale':
            path.write_text(DUMP + (' VRRP Instance = incomplete\n' if mode == 'partial' else ''))
    def open_file(name, flags, *args):
        if str(name).startswith('/run/'):
            name = tmp_path / 'probe.lock'
        return os.open(name, flags, *args)
    calls = []
    fake_os = SimpleNamespace(**{name: getattr(os, name) for name in (
        'O_CREAT', 'O_RDWR', 'O_RDONLY', 'fdopen', 'fstat', 'fsencode', 'readlink')})
    fake_os.O_NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)
    fake_os.O_NONBLOCK = getattr(os, 'O_NONBLOCK', 0)
    fake_os.O_CLOEXEC = getattr(os, 'O_CLOEXEC', 0)
    fake_os.open, fake_os.kill = open_file, kill
    filename = b'keepalived.data\0'
    fake_os.read = lambda *a: struct.pack('iIII', 1, 0x8, 0, len(filename)) + filename
    fake_os.close = calls.append
    monkeypatch.setattr(probe, 'os', fake_os)
    monkeypatch.setattr(probe.signal, 'SIGUSR1', 10, raising=False)
    monkeypatch.setattr(probe.select, 'select', lambda *a: ([] if mode == 'stale' else [12345], [], []))
    if mode == 'fresh':
        assert probe.fresh_dump(77) == probe.parse_instances(DUMP)
    else:
        with pytest.raises((TimeoutError, ValueError)):
            probe.fresh_dump(77)
    assert signalled == ([] if mode == 'busy' else [77])
    assert path.exists() == (mode in ('busy', 'stale'))
    assert calls == ([] if mode == 'busy' else [12345])


@pytest.mark.parametrize('changed', [False, True])
def test_pidfd_prevents_signalling_a_reused_pid(monkeypatch, changed):
    calls = []
    monkeypatch.setattr(probe, 'os', SimpleNamespace(pidfd_open=lambda pid: 99, close=calls.append))
    monkeypatch.setattr(probe.signal, 'SIGUSR1', 10, raising=False)
    monkeypatch.setattr(probe.signal, 'pidfd_send_signal', lambda *a: calls.append(a), raising=False)
    monkeypatch.setattr(probe, 'process_identity', lambda pid: 'new' if changed else 'old')
    if changed:
        with pytest.raises(ValueError):
            probe.signal_dump(77, 'old')
        assert calls == [99]
    else:
        probe.signal_dump(77, 'old')
        assert calls == [(99, 10), 99]
