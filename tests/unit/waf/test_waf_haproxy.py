import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from app.modules.config import candidate


@pytest.fixture
def agent(tmp_path, monkeypatch):
    root = tmp_path / 'haproxy custom/waf'
    (root / 'rules').mkdir(parents=True)
    target = root / 'rules/test.conf'
    target.write_bytes(b'# original\n')
    upload = tmp_path / 'upload.conf'
    upload.write_bytes(b'# candidate\n')
    main = root / 'modsecurity.conf'
    main.write_text('Include rules/test.conf\n')
    proc = tmp_path / 'proc'
    state = SimpleNamespace(pid=100, outcomes=[], calls=[], probes=[], probe_results=[], clock=0, container='',
                            port=23456, wrong_path=False, foreign_socket=False, loaded=True, reject_candidate=False,
                            mounts=[{'Type': 'bind', 'Source': str(root), 'Destination': '/etc/waf', 'RW': False}])

    def process(pid):
        directory = proc / str(pid)
        (directory / 'fd').mkdir(parents=True, exist_ok=True)
        (directory / 'net').mkdir(exist_ok=True)
        runtime_main = '/etc/waf/modsecurity.conf' if state.container else str(main)
        args = ['modsecurity', '-n', '4', '-f', '/wrong.conf' if state.wrong_path else runtime_main, '-p', str(state.port)]
        (directory / 'cmdline').write_bytes(b'\0'.join(os.fsencode(arg) for arg in args) + b'\0')
        (directory / 'fd/4').touch()
        inode = 999 if state.foreign_socket else pid
        (directory / 'net/tcp').write_text(f'header\n0: 00000000:{state.port:04X} 00000000:0000 0A 0:0 0:0 0 0 0 {inode}\n')

    def run(args, **kwargs):
        state.calls.append((args, target.read_bytes()))
        assert kwargs['timeout'] > 0 and kwargs['check'] is False
        status, output = 0, b''
        if args[:2] == ['systemctl', 'show']:
            assert args[2] == 'custom-waf.service'
            if '--property=LoadState' in args:
                output = b'loaded' if state.loaded else b'not-found'
            else:
                output = f'MainPID={state.pid}\nActiveState=active\nSubState=running\n'.encode()
                if state.pid:
                    process(state.pid)
        elif args[:2] == ['docker', 'inspect']:
            assert args[-1] == state.container
            if args[3] == '{{json .Mounts}}':
                output = json.dumps(state.mounts).encode()
            else:
                output = json.dumps({'Pid': state.pid, 'Running': bool(state.pid), 'Restarting': False}).encode()
                if state.pid:
                    process(state.pid)
        elif args[0] == 'sh':
            outcome = state.outcomes.pop(0) if state.outcomes else 'ok'
            if outcome == 'external_edit':
                target.write_bytes(b'# external edit\n')
                status = 1
            elif outcome == 'command_failed':
                status = 1
            elif outcome == 'timeout':
                raise subprocess.TimeoutExpired(args, 30)
            elif outcome == 'stopped':
                state.pid = 0
            elif outcome != 'unchanged':
                state.pid += 1
        elif candidate.SPOA_HEALTHCHECK in args:
            state.probes.append(args)
            assert args[-1] == str(state.port)
            assert ('nsenter' in args) == bool(state.container)
            status = state.probe_results.pop(0) if state.probe_results else 0
            if state.reject_candidate and target.read_bytes() == b'# candidate\n':
                status = 1
            if isinstance(status, Exception):
                raise status
        else:
            pytest.fail(f'Unexpected command: {args}')
        return SimpleNamespace(returncode=status, stdout=output)

    def tick(seconds):
        state.clock += seconds

    readlink = os.readlink
    monkeypatch.setattr(candidate, 'Path', lambda path: proc if str(path) == '/proc' else Path(path))
    monkeypatch.setattr(candidate.os, 'readlink', lambda path, **kw: f'socket:[{Path(path).parent.parent.name}]'
                        if proc in Path(path).parents else readlink(path, **kw))
    monkeypatch.setattr(candidate.subprocess, 'run', run)
    monkeypatch.setattr(candidate.shutil, 'which', lambda executable: '/usr/bin/' + executable)
    monkeypatch.setattr(candidate, 'time', SimpleNamespace(monotonic=lambda: state.clock, sleep=tick))
    mkdtemp = candidate.tempfile.mkdtemp
    monkeypatch.setattr(candidate.tempfile, 'mkdtemp', lambda **kw: mkdtemp(dir=tmp_path, **kw))

    def apply(action='restart'):
        command = 'sudo docker restart custom-waf' if state.container else 'sudo systemctl restart custom-waf.service'
        return candidate.execute(dict(service='haproxy_waf', target=str(target), candidate=str(upload), main=str(main),
                                      action=action, service_unit='custom-waf.service', container=state.container,
                                      action_command=command if action == 'restart' else ''))

    return SimpleNamespace(state=state, target=target, upload=upload, main=main, apply=apply, root=tmp_path)


@pytest.mark.parametrize('container', ['', 'custom-waf'])
def test_save_does_not_pretend_to_validate_or_restart(agent, container):
    agent.state.container = container
    agent.upload.write_text('syntactically invalid rule')
    assert agent.apply('save') == {'status': 'ok'}
    assert agent.target.read_text() == 'syntactically invalid rule'
    assert not agent.state.probes
    assert all(args[:2] == ['docker', 'inspect'] for args, _ in agent.state.calls)
    assert not agent.upload.exists()
    assert not list(agent.root.glob('roxywi-candidate-*'))


@pytest.mark.parametrize('container', ['', 'custom-waf'])
@pytest.mark.parametrize('condition,check,error', [('ready', 'ready', ''), ('stopped', 'not_checked', ''),
                                                 ('foreign_socket', 'unready', ''), ('no_response', 'unready', ''),
                                                 ('wrong_path', 'not_checked', 'check_unavailable')])
def test_status_reuses_agent_readiness_without_restart(agent, container, condition, check, error):
    agent.state.container = container
    if condition == 'stopped':
        agent.state.pid = 0
    elif condition == 'no_response':
        agent.state.probe_results = [1]
    elif condition in ('foreign_socket', 'wrong_path'):
        setattr(agent.state, condition, True)
    result = candidate.execute(dict(service='haproxy_waf', action='status', target=str(agent.main), main=str(agent.main),
                                    candidate='', container=container, service_unit='custom-waf.service'))
    assert result['check'] == check and result['error'] == error
    assert result['process'] == ('stopped' if condition == 'stopped' else 'running')
    assert agent.target.read_bytes() == b'# original\n' and agent.upload.exists()
    assert not any(args[0] == 'sh' for args, _ in agent.state.calls)


@pytest.mark.parametrize('container', ['', 'custom-waf'])
def test_restart_requires_new_agent_and_checks_its_own_socket(agent, container):
    agent.state.container = container
    assert agent.apply() == {'status': 'ok'}
    assert agent.state.pid == 101 and len(agent.state.probes) == 1
    assert agent.target.read_bytes() == b'# candidate\n'
    assert [content for args, content in agent.state.calls if args[0] == 'sh'] == [b'# candidate\n']
    assert not agent.upload.exists()


@pytest.mark.parametrize('failure', ['command_failed', 'timeout', 'stopped', 'unchanged'])
@pytest.mark.parametrize('container', ['', 'custom-waf'])
def test_failed_restart_restores_file_and_verifies_recovery(agent, failure, container):
    agent.state.container = container
    agent.state.outcomes = [failure, 'ok']
    result = agent.apply()
    assert result['code'] == 'apply_failed' and result['restored'] is True
    assert agent.target.read_bytes() == b'# original\n'
    assert [content for args, content in agent.state.calls if args[0] == 'sh'] == [b'# candidate\n', b'# original\n']
    assert len(agent.state.probes) == 1
    assert not agent.upload.exists()
    assert not list(agent.root.glob('roxywi-candidate-*'))


@pytest.mark.parametrize('failure', ['command_failed', 'stopped', 'foreign_socket', 'external_edit'])
def test_failed_recovery_retains_backup_and_external_edits(agent, failure):
    agent.state.foreign_socket = failure == 'foreign_socket'
    agent.state.outcomes = ['ok', 'ok'] if failure == 'foreign_socket' else [failure, failure]
    result = agent.apply()
    assert result['code'] == 'recovery_failed'
    assert Path(result['backup']).read_bytes() == b'# original\n'
    assert agent.target.read_bytes() == (b'# external edit\n' if failure == 'external_edit' else b'# original\n')
    assert not agent.state.probes
    assert not agent.upload.exists()


@pytest.mark.parametrize('failure', ['startup_path', 'unit_missing', 'nsenter_missing', 'single_file_mount'])
def test_preflight_failure_leaves_original_untouched(agent, monkeypatch, failure):
    if failure == 'startup_path':
        agent.state.wrong_path = True
    elif failure == 'unit_missing':
        agent.state.loaded = False
    else:
        agent.state.container = 'custom-waf'
        if failure == 'nsenter_missing':
            monkeypatch.setattr(candidate.shutil, 'which', lambda _: None)
        else:
            agent.state.mounts.append({'Type': 'bind', 'Source': str(agent.target), 'Destination': '/etc/waf/rules/test.conf'})
    result = agent.apply()
    assert result['code'] == 'mount_failed'
    assert agent.target.read_bytes() == b'# original\n'
    assert not any(args[0] == 'sh' for args, _ in agent.state.calls)
    assert not agent.upload.exists()


def test_stopped_agent_can_be_repaired(agent):
    agent.state.pid = 0
    assert agent.apply() == {'status': 'ok'}
    assert agent.state.probes


@pytest.mark.parametrize('failure', [1, subprocess.TimeoutExpired('probe', 3)])
def test_starting_agent_can_become_ready_before_deadline(agent, failure):
    # The first probe fails; another attempt can succeed within the readiness window.
    agent.state.probe_results = [failure, 0]
    assert agent.apply() == {'status': 'ok'}
    assert len(agent.state.probes) == 2


def test_failed_protocol_handshake_triggers_recovery(agent):
    agent.state.reject_candidate = True
    result = agent.apply()
    assert result['code'] == 'apply_failed' and result['restored']
    assert agent.target.read_bytes() == b'# original\n'


@pytest.mark.skipif(os.name != 'posix', reason='Unix file ownership and mode')
@pytest.mark.parametrize('failure', [False, True])
def test_rule_metadata_survives_save_or_recovery(agent, failure):
    agent.target.chmod(0o640)
    before = agent.target.stat()
    agent.state.outcomes = ['command_failed', 'ok'] if failure else []
    agent.apply()
    after = agent.target.stat()
    assert (before.st_mode, before.st_uid, before.st_gid) == (after.st_mode, after.st_uid, after.st_gid)


def test_command_shares_rule_operation_lock_and_carries_waf_unit():
    root = '/srv/haproxy custom/waf'
    command = shlex.split(candidate.candidate_command('haproxy_waf', root + '/rules/test.conf', '/tmp/upload',
        'restart', main=root + '/modsecurity.conf', service_unit='waf', action_command='sudo systemctl restart waf'))
    assert command[:8] == ['sudo', '-n', 'flock', '-w', '30',
                          '/var/lock/roxywi-waf-' + hashlib.sha256(root.encode()).hexdigest() + '.lock', 'python3', '-c']
    assert json.loads(command[-1])['service_unit'] == 'waf'


@pytest.mark.parametrize('action', ['test', 'check', 'reload'])
def test_haproxy_waf_rejects_unsupported_actions(action):
    with pytest.raises(ValueError, match='save and restart only'):
        candidate.candidate_command('haproxy_waf', '/waf/rules/test.conf', '/tmp/upload', action, main='/waf/modsecurity.conf')


@pytest.mark.parametrize('startup', ['/etc/haproxy//waf/modsecurity.conf', '/etc/haproxy/./waf/modsecurity.conf'])
def test_legacy_unit_path_spelling_identifies_the_same_configuration(tmp_path, monkeypatch, startup):
    process = tmp_path / '42'
    process.mkdir()
    (process / 'cmdline').write_bytes(b'modsecurity\0-f\0' + startup.encode() + b'\0-p\0' + b'23456\0')
    validator = candidate._HaproxyWafValidator({}, Path('/etc/haproxy/waf/rules/test.conf'),
                                              Path('/etc/haproxy/waf/modsecurity.conf'))
    validator.runtime_main = '/etc/haproxy/waf/modsecurity.conf'
    monkeypatch.setattr(candidate, 'Path', lambda _: tmp_path)
    assert validator.listener_port(42) == 23456


@pytest.mark.parametrize('container', ['', 'custom-waf'])
@pytest.mark.parametrize('failure', ['', 'command_failed', 'unchanged', 'stopped'])
def test_apply_saved_requires_readiness_and_preserves_saved_files(agent, container, failure):
    agent.state.container = container
    agent.state.outcomes = [failure] if failure else []
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (agent.main, agent.target, agent.upload)}
    response = candidate.execute(dict(service='haproxy_waf', target=str(agent.main), main=str(agent.main),
                                      candidate='', apply_only=True, action='restart', service_unit='custom-waf.service',
                                      container=container, action_command='restart saved WAF'))
    assert response['code'] == 'apply_failed' if failure else response == {'status': 'ok'}
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before
    assert len([args for args, _ in agent.state.calls if args[0] == 'sh']) == 1
    if not failure:
        assert agent.state.pid == 101 and len(agent.state.probes) == 1
    assert not list(agent.root.glob('roxywi-candidate-*'))
