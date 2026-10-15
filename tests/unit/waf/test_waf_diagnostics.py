import json
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from app.modules.config import candidate


@pytest.fixture
def nginx(tmp_path, monkeypatch):
    root = tmp_path / 'nginx custom/waf'
    root.mkdir(parents=True)
    target = root / 'modsecurity.conf'
    target.write_text('SecRuleEngine On\n')
    main = root.parent / 'nginx.conf'
    main.write_text('events {}\nhttp { modsecurity on; }\n')
    state = SimpleNamespace(pid=42, active='active', loaded=b'loaded', calls=[], valid=True,
                            dump='# configuration file /etc/nginx/nginx.conf:\n' + main.read_text(),
                            failure=None, changed=False, container='', paused=False)
    spec = dict(service='nginx_waf', action='status', target=str(target), main=str(main),
                candidate='', action_command='', service_unit='nginx', container='')

    def run(args, **kwargs):
        state.calls.append(args)
        if state.failure:
            raise state.failure
        if args[:2] == ['systemctl', 'show']:
            if '--property=LoadState' in args:
                return SimpleNamespace(returncode=0, stdout=state.loaded)
            output = f'MainPID={state.pid}\nActiveState={state.active}\nSubState=running\n'.encode()
        elif args[:2] == ['docker', 'inspect']:
            if args[3] == '{{json .State}}':
                output = json.dumps(dict(Pid=state.pid, Running=bool(state.pid), Restarting=False, Paused=state.paused)).encode()
            else:
                output = json.dumps([dict(Type='bind', Source=str(root.parent), Destination='/etc/nginx', RW=False)]).encode()
        else:
            expected = ['docker', 'exec', state.container] if state.container else []
            expected += ['nginx', '-T', '-c', '/etc/nginx/nginx.conf' if state.container else str(main)]
            assert args == expected  # No shell command, reload, staging or file writes.
            assert kwargs['separate_errors'] is True
            if state.changed:
                state.pid += 1
            return SimpleNamespace(returncode=0 if state.valid else 1, stdout=state.dump.encode())
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(candidate, '_run', run)
    return SimpleNamespace(state=state, spec=spec, target=target, main=main)


@pytest.mark.parametrize('container', ['', 'custom-nginx'])
@pytest.mark.parametrize('text,expected', [
    ('http { modsecurity on; }', 'enabled'),
    ('http {modsecurity\n off ;}', 'disabled'),
    ('http { modsecurity on; server { modsecurity off; } }', 'mixed'),
    ('http { # modsecurity on;\n set $x "modsecurity on;"; }', 'not_configured'),
    ('http { modsecurity_rules "SecRuleEngine On"; }', 'not_configured'),
])
def test_nginx_inspects_only_dumped_directives_and_never_changes_files(nginx, container, text, expected):
    nginx.spec['container'] = nginx.state.container = container
    nginx.state.dump = '# configuration file /etc/nginx/nginx.conf:\n' + text
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (nginx.target, nginx.main)}
    result = candidate.execute(nginx.spec)
    assert result == dict(status='ok', process='running', check='valid', module=expected, error='')
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before


def test_nginx_rejected_config_does_not_leak_output(nginx):
    nginx.state.valid = False
    nginx.state.dump = 'secret rule and credential from nginx output'
    result = candidate.execute(nginx.spec)
    assert result['check'] == 'invalid' and result['module'] == 'unknown'
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('dump', ['', 'not a configuration dump', '# configuration file /etc/nginx/nginx.conf:\n"unterminated'])
def test_missing_or_unparseable_dump_is_not_a_successful_check(nginx, dump):
    nginx.state.dump = dump
    result = candidate.execute(nginx.spec)
    assert result['error'] == 'check_unavailable' and result['check'] == 'not_checked'


@pytest.mark.parametrize('failure', [OSError('sensitive output'), subprocess.TimeoutExpired(['secret'], 30)])
def test_transport_and_tool_failures_are_unknown_not_stopped(nginx, failure):
    nginx.state.failure = failure
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'unknown' and result['error'] == 'process_unavailable'
    assert 'secret' not in json.dumps(result) and 'sensitive' not in json.dumps(result)


def test_missing_systemd_service_is_distinct_from_unknown(nginx):
    nginx.state.loaded = b'not-found'
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'missing' and result['check'] == 'not_checked'
    assert len(nginx.state.calls) == 1


@pytest.mark.parametrize('container', ['', 'custom-nginx'])
def test_stopped_service_cannot_report_running_protection(nginx, container):
    nginx.spec['container'] = nginx.state.container = container
    nginx.state.pid = 0
    nginx.state.active = 'inactive'
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'stopped'
    assert result['check'] == ('not_checked' if container else 'valid')


def test_paused_container_is_not_reported_as_running(nginx):
    nginx.spec['container'] = nginx.state.container = 'custom-nginx'
    nginx.state.paused = True
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'stopped' and result['check'] == 'not_checked'


def test_process_change_invalidates_snapshot(nginx):
    nginx.state.changed = True
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'unknown' and result['error'] == 'process_changed'


def test_missing_config_keeps_observed_process_state(nginx):
    nginx.target.unlink()
    result = candidate.execute(nginx.spec)
    assert result['process'] == 'running' and result['error'] == 'config_unavailable'
    assert result['check'] == 'not_checked'


@pytest.mark.parametrize('field,value', [('candidate', '/tmp/keep.conf'), ('action_command', 'must not run'),
                                        ('apply_only', True), ('service', 'haproxy')])
def test_status_rejects_transaction_fields_before_io(nginx, field, value):
    nginx.spec[field] = value
    assert candidate.execute(nginx.spec)['error']
    assert not nginx.state.calls


def test_status_command_uses_same_waf_lock_and_no_candidate():
    args = dict(service='nginx_waf', target='/etc/nginx/waf/modsecurity.conf', candidate='', action='status',
                main='/etc/nginx/nginx.conf', service_unit='nginx')
    command = shlex.split(candidate.candidate_command(**args))
    apply = shlex.split(candidate.candidate_command(**{**args, 'action': 'reload'}, apply_only=True, action_command='reload'))
    assert command[:8] == apply[:8]
    assert json.loads(command[-1])['action'] == 'status'
    with pytest.raises(ValueError):
        candidate.candidate_command(**{**args, 'candidate': '/tmp/rule.conf'})


def test_dump_keeps_stderr_separate(monkeypatch):
    observed = {}
    def run(args, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b'# configuration file /etc/nginx/nginx.conf:\nmodsecurity on;')
    monkeypatch.setattr(candidate.subprocess, 'run', run)
    validator = candidate._NginxWafValidator({}, Path('/etc/nginx/waf/modsecurity.conf'), Path('/etc/nginx/nginx.conf'))
    validator.inspect()
    assert validator.module_state() == ('valid', 'enabled')
    assert observed['stderr'] == subprocess.PIPE
