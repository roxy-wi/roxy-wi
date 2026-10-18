from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import candidate
from app.modules.service import action, nginx


@pytest.mark.parametrize('directive', ['modsecurity off;', 'modsecurity\t"off" ;', "modsecurity\n'off';"])
@pytest.mark.parametrize('enabled', [False, True])
def test_main_switch_preserves_comments_formatting_and_site_overrides(directive, enabled):
    config = ('# modsecurity on;\r\nevents {}\r\nhttp {\r\n'
              ' log_format sample "modsecurity off; # not a directive";\r\n'
              f' {directive} # keep comment\r\n'
              ' server { modsecurity off; location ~ ^/item/[0-9]{2}$ { return 200 "${host}"; } }\r\n}\r\n')
    expected = config.replace(directive + ' # keep', directive.replace('off', 'on' if enabled else 'off') + ' # keep')
    assert nginx.waf_configuration_candidate(config, enabled) == expected
    assert nginx.waf_configuration_candidate(expected, enabled) == expected


def test_switch_preserves_quoted_syntax_characters_in_other_directives():
    config = '''events {}\nhttp {
    log_format punctuation '{' ";" '}';
    modsecurity off;
}\n'''
    assert nginx.waf_configuration_candidate(config, True) == config.replace('modsecurity off;', 'modsecurity on;')


@pytest.mark.parametrize('text', [
    'events {}\nhttp {}', 'http { # modsecurity off;\n}',
    'http { modsecurity off; modsecurity on; }', 'http { modsecurity off; } http { modsecurity on; }',
    'http { server { modsecurity off; } }', 'http { modsecurity invalid; }',
    'http { modsecurity off;', 'http { modsecurity off }', 'http { modsecurity "off; }',
])
def test_missing_or_ambiguous_global_switch_is_rejected(text):
    with pytest.raises(ValueError):
        nginx.waf_configuration_candidate(text, True)


@pytest.fixture
def switching(tmp_path, monkeypatch):
    state = SimpleNamespace(original=b'events {}\nhttp {\n modsecurity off;\n}\n', calls=[], logs=[],
                            main="/srv/custom configs/web's main.conf", runtime={}, response='{"status":"ok"}',
                            protected=False, track=[], failure='')
    settings = {'nginx_dir': '/srv/web', 'tmp_config_path': '/tmp/private uploads'}
    monkeypatch.setattr(action.sql, 'get_setting', lambda key: settings[key])
    monkeypatch.setattr(action.server_sql, 'get_server_by_ip', lambda ip: SimpleNamespace(server_id=12))
    state.runtime = dict(main=state.main, container='', service_unit='nginx-custom')
    monkeypatch.setattr(action.service_common, 'waf_runtime_settings', lambda *args: state.runtime)

    def protect(*args):
        if state.protected:
            raise PermissionError('protected')
    monkeypatch.setattr(action.service_common, 'is_protected', protect)
    monkeypatch.setattr(action, 'get_action_command', lambda *args: 'sudo systemctl reload nginx-custom')
    monkeypatch.setattr(action.roxywi_common, 'logging', lambda *args, **kwargs: state.logs.append(args))
    monkeypatch.setattr(action.waf_state, 'operation_lock', lambda *args: nullcontext())

    @contextmanager
    def track(*args, **kwargs):
        assert kwargs['applying'] is True
        state.track.append('pending')
        yield
        state.track.append('applied')
    monkeypatch.setattr(action.waf_state, 'track_changes', track)

    class Sftp:
        def get_sftp(self, remote, local):
            assert remote == state.main
            Path(local).write_bytes(state.original)

        def put_sftp(self, local, remote):
            assert remote == '/tmp/private uploads/roxywi-nginx-waf-abc123'
            state.upload = Path(local).read_bytes()
            state.local = Path(local)
            if state.failure == 'upload':
                raise OSError('transfer interrupted')

    monkeypatch.setattr(action.mod_ssh, 'ssh_connect', lambda ip: nullcontext(Sftp()))

    def ssh(ip, command, **kwargs):
        assert kwargs['rc'] == 1
        args = shlex.split(command)
        state.calls.append(args)
        if args[0] == 'mktemp':
            return '/tmp/private uploads/roxywi-nginx-waf-abc123\n'
        if 'flock' in args:
            state.spec = json.loads(args[-1])
            assert kwargs['timeout'] == candidate.REMOTE_TIMEOUT
            return state.response
        assert args == ['sudo', 'rm', '-f', '--', '/tmp/private uploads/roxywi-nginx-waf-abc123']
        return ''
    monkeypatch.setattr(action.server_mod, 'ssh_command', ssh)
    return state


@pytest.mark.parametrize('container', ['', 'custom-container'])
@pytest.mark.parametrize('requested', ['start', 'stop'])
def test_switch_uses_transaction_configured_main_checksum_and_cleanup(switching, container, requested):
    state = switching
    state.runtime['container'] = container
    action.action_nginx_waf('192.0.2.12', requested, 'waf_nginx')
    assert state.spec['target'] == state.spec['main'] == state.main
    assert state.spec['container'] == container
    assert state.spec['root'] == '/srv/web/waf'
    assert state.spec['expected_sha256'] == hashlib.sha256(state.original).hexdigest()
    assert state.spec['action'] == 'reload'
    assert state.upload == state.original.replace(b'off', b'on' if requested == 'start' else b'off')
    assert state.track == ['pending', 'applied'] and len(state.logs) == 1
    assert state.calls[-1][1] == 'rm' and not state.local.exists()


@pytest.mark.parametrize('response', ['{"status":"failed","code":"validation_failed"}', '', '{}'])
def test_failed_or_unconfirmed_switch_does_not_mark_applied_or_log_success(switching, response):
    switching.response = response
    with pytest.raises((candidate.CandidateApplyError, RuntimeError, ValueError)):
        action.action_nginx_waf('192.0.2.12', 'start', 'waf_nginx')
    assert switching.track == ['pending'] and not switching.logs
    assert switching.calls[-1][1] == 'rm' and not switching.local.exists()


def test_upload_failure_is_cleaned_up(switching):
    switching.failure = 'upload'
    with pytest.raises(OSError):
        action.action_nginx_waf('192.0.2.12', 'start', 'waf_nginx')
    assert switching.calls[-1][1] == 'rm'
    assert not switching.local.exists() and not switching.logs


def test_protected_server_and_unsupported_actions_fail_before_io(switching):
    switching.protected = True
    with pytest.raises(PermissionError):
        action.action_nginx_waf('192.0.2.12', 'start', 'waf_nginx')
    with pytest.raises(ValueError):
        action.action_nginx_waf('192.0.2.12', 'restart', 'waf_nginx')
    assert not switching.calls and not switching.logs
