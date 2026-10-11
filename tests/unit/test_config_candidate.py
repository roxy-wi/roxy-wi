"""Exercise the common transaction with real files and a simulated process boundary."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.config import candidate


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / 'haproxy with spaces'
    folder = root / 'conf.d'
    folder.mkdir(parents=True)
    main = root / 'haproxy.cfg'
    main.write_bytes(b'global\n')
    target = folder / '20-web.cfg'
    target.write_bytes(b'backend original\n')
    upload = tmp_path / 'upload.cfg'
    upload.write_bytes(b'backend candidate\n')
    spec = dict(service='haproxy', main=str(main), root=str(root), target=str(target), candidate=str(upload),
                sources=[str(main), str(folder)], action='save')
    mkdtemp = candidate.tempfile.mkdtemp
    monkeypatch.setattr(candidate.tempfile, 'mkdtemp', lambda **kw: mkdtemp(dir=tmp_path, **kw))
    return SimpleNamespace(root=root, main=main, folder=folder, target=target, upload=upload, spec=spec)


@pytest.fixture
def runtime(tree, monkeypatch):
    state = SimpleNamespace(calls=[], validations=[], results=[])

    def run(arguments, **kwargs):
        content = tree.target.read_bytes() if tree.target.exists() else None
        state.calls.append((arguments, content))
        assert kwargs['timeout'] > 0 and kwargs['check'] is False
        if arguments[:2] == ['haproxy', '-c']:
            files = [Path(arguments[i + 1]) for i, arg in enumerate(arguments) if arg == '-f']
            state.validations.append([(path, path.read_bytes()) for path in files])
        else:
            assert arguments[:2] == ['sh', '-c']
        result = state.results.pop(0) if state.results else 0
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(returncode=result, stdout=b'secret diagnostic must not be exposed')

    monkeypatch.setattr(candidate.subprocess, 'run', run)
    return state


@pytest.mark.parametrize('action', ['test', 'save', 'reload', 'restart'])
def test_haproxy_checks_separate_candidate_before_replacing_file(tree, runtime, action):
    tree.spec.update(action=action, action_command='systemctl ' + action + ' haproxy')
    response = candidate.execute(tree.spec)
    assert response == {'status': 'ok'}
    assert tree.target.read_bytes() == (b'backend original\n' if action == 'test' else b'backend candidate\n')
    assert all(current == b'backend original\n' for args, current in runtime.calls if args[0] == 'haproxy')
    checked = runtime.validations[-1]
    assert checked[0] == (tree.main, b'global\n')
    assert checked[1][0] != tree.target and checked[1][1] == b'backend candidate\n'
    actions = [(args, content) for args, content in runtime.calls if args[0] == 'sh']
    assert actions == ([(['sh', '-c', tree.spec['action_command']], b'backend candidate\n')]
                       if action in ('reload', 'restart') else [])
    assert not tree.upload.exists()
    assert not list(tree.root.parent.glob('roxywi-candidate-*'))


@pytest.mark.parametrize('new_file', [False, True])
def test_sources_keep_their_order_and_exclude_hidden_and_nested_files(tree, runtime, new_file):
    first = tree.folder / '10-first.cfg'
    last = tree.folder / '30-last.cfg'
    first.write_bytes(b'first')
    last.write_bytes(b'last')
    (tree.folder / '.hidden.cfg').write_bytes(b'hidden')
    (tree.folder / 'nested').mkdir()
    (tree.folder / 'nested/invalid.cfg').write_bytes(b'invalid')
    tree.spec['sources'].reverse()
    if new_file:
        tree.target.unlink()
    assert candidate.execute(tree.spec) == {'status': 'ok'}
    assert [text for _, text in runtime.validations[0]] == [b'first', b'backend candidate\n', b'last', b'global\n']
    assert tree.target.read_bytes() == b'backend candidate\n'


@pytest.mark.parametrize('problem', ['duplicate', 'unselected', 'outside', 'missing_action'])
def test_invalid_context_never_replaces_files_and_removes_upload(tree, runtime, problem):
    if problem == 'duplicate':
        tree.spec['sources'].append(str(tree.target))
    elif problem == 'unselected':
        tree.spec['sources'] = [str(tree.main)]
    elif problem == 'outside':
        tree.spec['target'] = str(tree.root.parent / 'outside.cfg')
        Path(tree.spec['target']).write_bytes(b'outside')
    else:
        tree.spec['action'] = 'reload'
    response = candidate.execute(tree.spec)
    assert response['status'] == 'failed'
    assert tree.target.read_bytes() == b'backend original\n'
    assert not tree.upload.exists()
    assert not runtime.calls


@pytest.mark.parametrize('results,code', [
    ([0, 1], 'validation_failed'),
    ([0, candidate.subprocess.TimeoutExpired('haproxy', 30)], 'validation_failed'),
    ([0, 0, 1, 0, 0], 'apply_failed'),
    ([0, 0, 1, 0, 1], 'recovery_failed'),
    ([1, 0, 1], 'recovery_failed'),
])
def test_failed_validation_or_action_restores_original_without_exposing_output(tree, runtime, results, code):
    runtime.results = results.copy()
    tree.spec.update(action='reload', action_command='systemctl reload haproxy')
    response = candidate.execute(tree.spec)
    assert response['code'] == code and response['status'] == 'failed'
    assert 'secret' not in json.dumps(response)
    assert tree.target.read_bytes() == b'backend original\n'
    assert not tree.upload.exists()
    if code == 'validation_failed':
        assert all(current == b'backend original\n' for _, current in runtime.calls)
        assert all(args[0] == 'haproxy' for args, _ in runtime.calls)
    elif code == 'apply_failed':
        assert [current for args, current in runtime.calls if args[0] == 'sh'] == [b'backend candidate\n', b'backend original\n']
    else:
        assert Path(response['backup']).read_bytes() == b'backend original\n'


def test_failed_apply_of_new_file_removes_it_and_recovers_previous_configuration(tree, runtime):
    tree.target.unlink()
    tree.spec.update(action='reload', action_command='systemctl reload haproxy')
    runtime.results = [0, 0, 1, 0, 0]
    response = candidate.execute(tree.spec)
    assert response['code'] == 'apply_failed' and response['restored']
    assert not tree.target.exists()
    assert [text for _, text in runtime.validations[-1]] == [b'global\n']
    assert not tree.upload.exists()


def test_external_edit_during_validation_is_preserved(tree, runtime, monkeypatch):
    run = candidate.subprocess.run

    def edited(*args, **kwargs):
        result = run(*args, **kwargs)
        tree.target.write_bytes(b'administrator edit')
        return result

    monkeypatch.setattr(candidate.subprocess, 'run', edited)
    response = candidate.execute(tree.spec)
    assert response['code'] == 'recovery_failed'
    assert tree.target.read_bytes() == b'administrator edit'
    assert Path(response['backup']).read_bytes() == b'backend original\n'


@pytest.mark.parametrize('problem', ['', 'single_file', 'read_only', 'cp_failure', 'cleanup_failure'])
def test_docker_staging_uses_writable_alias_and_cleans_up_outside_readonly_tmp(tree, monkeypatch, problem):
    mounts = [{'Type': 'bind', 'Source': str(tree.root), 'Destination': '/tmp', 'RW': False},
              {'Type': 'bind', 'Source': str(tree.root), 'Destination': '/config', 'RW': problem != 'read_only'}]
    if problem == 'single_file':
        mounts.append({'Type': 'bind', 'Source': str(tree.target), 'Destination': '/config/conf.d/20-web.cfg', 'RW': True})
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert args[0] == 'docker'
        output, code = b'', 0
        if args[1] == 'inspect':
            output = json.dumps(mounts).encode()
        elif args[1] == 'cp':
            assert Path(args[2]).read_bytes() == b'backend candidate\n'
            assert args[3].startswith('proxy:/roxywi-')
            code = int(problem == 'cp_failure')
        elif 'id' in args:
            output = b'99\n'
        elif 'chown' in args:
            assert args[-2] == '99:99'
        elif 'haproxy' in args:
            assert args[3:7] == ['haproxy', '-c', '-f', '/config/haproxy.cfg']
            assert args[-1].startswith('/roxywi-')
            assert tree.target.read_bytes() == b'backend original\n'
        else:
            assert args[5:7] == ['rm', '-f']
            assert args[-1] == next(call[3].split(':', 1)[1] for call in calls if call[1] == 'cp')
            code = int(problem == 'cleanup_failure')
        return SimpleNamespace(returncode=code, stdout=output)

    monkeypatch.setattr(candidate.subprocess, 'run', run)
    tree.spec['container'] = 'proxy'
    response = candidate.execute(tree.spec)
    assert response['status'] == ('failed' if problem else 'ok')
    assert tree.target.read_bytes() == (b'backend candidate\n' if problem in ('', 'cleanup_failure') else b'backend original\n')
    assert not tree.upload.exists()
    if problem in ('single_file', 'read_only'):
        assert response['code'] == 'mount_failed' and len(calls) == 1
    else:
        assert 'rm' in calls[-1]
    if problem == 'cleanup_failure':
        assert response['cleanup']


def test_check_uses_current_sources_without_mutation_or_staging(tree, runtime):
    tree.spec.update(action='check', candidate='')
    assert candidate.execute(tree.spec) == {'status': 'ok'}
    assert runtime.validations == [[(tree.main, b'global\n'), (tree.target, b'backend original\n')]]
    assert tree.upload.exists()
    assert not list(tree.root.parent.glob('roxywi-candidate-*'))
