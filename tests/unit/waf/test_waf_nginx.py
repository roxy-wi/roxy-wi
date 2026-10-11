import hashlib
import json
import os
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from app.modules.config import candidate as remote


def apply_candidate(target, candidate, main, container='', action_command=''):
    return remote.execute(dict(service='nginx_waf', target=str(target), candidate=str(candidate), main=str(main),
                               action='reload' if action_command else 'save', container=container, action_command=action_command))


@pytest.fixture
def files(tmp_path):
    root = tmp_path / 'nginx with spaces'
    (root / 'waf/rules').mkdir(parents=True)
    target = root / 'waf/rules/test.conf'
    target.write_bytes(b'# original\n')
    candidate = tmp_path / 'upload.conf'
    candidate.write_bytes(b'# candidate\n')
    main = root / 'nginx.conf'
    main.write_text('# main configuration\n')
    return target, candidate, main


@pytest.fixture
def runtime(files, monkeypatch):
    target, _, main = files
    state = SimpleNamespace(calls=[], results=[], mounts=[{
        'Type': 'bind', 'Source': str(main.parent), 'Destination': '/etc/custom nginx', 'RW': False,
    }])

    def run(arguments, **kwargs):
        state.calls.append((arguments, target.read_bytes()))
        assert kwargs['timeout'] > 0 and kwargs['check'] is False
        if arguments[:2] == ['docker', 'inspect']:
            return SimpleNamespace(returncode=0, stdout=json.dumps(state.mounts).encode())
        result = state.results.pop(0) if state.results else 0
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(returncode=result, stdout=b'Synthetic secret rule text; must not be returned')

    monkeypatch.setattr(remote.subprocess, 'run', run)
    return state


@pytest.mark.parametrize('container', ['', 'custom-nginx'])
@pytest.mark.parametrize('action', ['', 'systemctl reload nginx', 'systemctl restart nginx'])
def test_validation_precedes_action_and_keeps_candidate_on_success(files, runtime, container, action):
    target, candidate, main = files
    assert apply_candidate(*files, container, action) == {'status': 'ok'}
    assert target.read_bytes() == b'# candidate\n'
    calls = runtime.calls[1:] if container else runtime.calls
    check = (['docker', 'exec', container] if container else []) + ['nginx', '-t', '-c',
              '/etc/custom nginx/nginx.conf' if container else str(main)]
    assert calls == [(check, b'# original\n'), (check, b'# candidate\n')] + (
        [(['sh', '-c', action], b'# candidate\n')] if action else [])
    assert not candidate.exists()
    assert sorted(path.name for path in target.parent.iterdir()) == ['test.conf']


@pytest.mark.parametrize('results,code,states', [
    ([1, 1], 'validation_failed', [b'# original\n', b'# candidate\n']),
    ([0, 1], 'validation_failed', [b'# original\n', b'# candidate\n']),
    ([0, remote.subprocess.TimeoutExpired('nginx', 30)], 'validation_failed', [b'# original\n', b'# candidate\n']),
    ([0, InterruptedError()], 'validation_failed', [b'# original\n', b'# candidate\n']),
    ([0, 0, 1, 0, 0], 'apply_failed', [b'# original\n', b'# candidate\n', b'# candidate\n', b'# original\n', b'# original\n']),
    ([0, 0, 1, 0, 1], 'recovery_failed', [b'# original\n', b'# candidate\n', b'# candidate\n', b'# original\n', b'# original\n']),
    ([1, 0, 1], 'recovery_failed', [b'# original\n', b'# candidate\n', b'# candidate\n']),
    ([0, 0, 1, 1], 'recovery_failed', [b'# original\n', b'# candidate\n', b'# candidate\n', b'# original\n']),
])
def test_failures_restore_the_file_and_never_signal_invalid_candidate(files, runtime, results, code, states):
    runtime.results = results.copy()
    response = apply_candidate(*files, action_command='systemctl reload nginx')
    assert response['code'] == code and response['status'] == 'failed'
    assert 'secret' not in json.dumps(response)
    assert files[0].read_bytes() == b'# original\n'
    assert [content for _, content in runtime.calls] == states
    assert not files[1].exists()
    if code == 'recovery_failed':
        assert Path(response['backup']).read_bytes() == b'# original\n'
    else:
        assert sorted(path.name for path in files[0].parent.iterdir()) == ['test.conf']


@pytest.mark.parametrize('failure_at', [1, 2])
def test_replace_failure_preserves_original_or_retains_a_recoverable_backup(files, runtime, monkeypatch, failure_at):
    replace = remote.os.replace
    calls = []

    def fail(source, target):
        calls.append(target)
        if len(calls) == failure_at:
            raise OSError('synthetic disk failure')
        replace(source, target)

    monkeypatch.setattr(remote.os, 'replace', fail)
    runtime.results = [0, 1]
    response = apply_candidate(*files)
    assert response['status'] == 'failed'
    if failure_at == 1:
        assert response['code'] == 'save_failed'
        assert files[0].read_bytes() == b'# original\n'
    else:
        assert response['code'] == 'recovery_failed'
        assert Path(response['backup']).read_bytes() == b'# original\n'
        assert files[0].read_bytes() == b'# candidate\n'


@pytest.mark.parametrize('check_result', [0, 1])
def test_concurrent_external_edit_is_not_overwritten_during_recovery(files, runtime, monkeypatch, check_result):
    run = remote.subprocess.run

    def edited(arguments, **kwargs):
        if len(runtime.calls) == 1:
            files[0].write_bytes(b'# administrator edit\n')
        return run(arguments, **kwargs)

    monkeypatch.setattr(remote.subprocess, 'run', edited)
    runtime.results = [0, check_result]
    response = apply_candidate(*files)
    assert response['code'] == 'recovery_failed'
    assert files[0].read_bytes() == b'# administrator edit\n'
    assert Path(response['backup']).read_bytes() == b'# original\n'


def test_a_valid_candidate_can_repair_an_already_invalid_configuration(files, runtime):
    runtime.results = [1, 0]
    assert apply_candidate(*files) == {'status': 'ok'}
    assert files[0].read_bytes() == b'# candidate\n'


@pytest.mark.parametrize('problem', ['missing', 'single_file', 'shadowed', 'ambiguous'])
def test_unsupported_container_mounts_fail_before_mutation(files, runtime, problem, tmp_path):
    target, _, main = files
    if problem == 'missing':
        runtime.mounts = []
    elif problem == 'single_file':
        runtime.mounts.append({'Type': 'bind', 'Source': str(target), 'Destination': '/etc/custom nginx/waf/rules/test.conf'})
    elif problem == 'ambiguous':
        runtime.mounts.append({'Type': 'bind', 'Source': str(main.parent), 'Destination': '/alias'})
    else:
        hidden = tmp_path / 'other-rules'
        hidden.mkdir()
        runtime.mounts.append({'Type': 'bind', 'Source': str(hidden), 'Destination': '/etc/custom nginx/waf/rules'})
    response = apply_candidate(*files, container='custom-nginx')
    assert response['code'] == 'mount_failed'
    assert target.read_bytes() == b'# original\n'
    assert len(runtime.calls) == 1


@pytest.mark.parametrize('candidate_index', [0, 2])
def test_invalid_candidate_path_never_deletes_rule_or_main_file(files, runtime, candidate_index):
    original = {path: path.read_bytes() for path in files}
    response = apply_candidate(files[0], files[candidate_index], files[2])
    assert response['status'] == 'failed'
    assert {path: path.read_bytes() for path in files} == original
    assert not runtime.calls


@pytest.mark.skipif(os.name != 'posix', reason='Unix ownership and mode')
@pytest.mark.parametrize('failed', [False, True])
def test_rule_mode_and_ownership_survive_save_and_rollback(files, runtime, failed):
    files[0].chmod(0o640)
    before = files[0].stat()
    runtime.results = [0, 1 if failed else 0]
    apply_candidate(*files)
    after = files[0].stat()
    assert (after.st_mode, after.st_uid, after.st_gid) == (before.st_mode, before.st_uid, before.st_gid)


def test_command_uses_the_rule_operation_lock_and_quotes_all_arguments():
    root = '/srv/nginx with spaces/waf'
    args = [root + '/rules/test.conf', '/tmp/unique.conf', '/srv/main nginx.conf', 'custom-container', 'sudo systemctl reload nginx']
    command = shlex.split(remote.candidate_command('nginx_waf', args[0], args[1], 'reload',
                                                   main=args[2], container=args[3], action_command=args[4]))
    lock = hashlib.sha256(root.encode()).hexdigest()
    assert command[:8] == ['sudo', '-n', 'flock', '-w', '30', f'/var/lock/roxywi-waf-{lock}.lock', 'python3', '-c']
    spec = json.loads(command[-1])
    assert [spec[key] for key in ('target', 'candidate', 'main', 'container', 'action_command')] == args


@pytest.mark.parametrize('output', ['', 'null', '{"status":"failed"}', '{"status":"unknown"}'])
def test_unconfirmed_remote_response_is_not_success(output):
    with pytest.raises((ValueError, RuntimeError)):
        remote.check_result(output)
