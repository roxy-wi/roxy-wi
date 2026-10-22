import json

import pytest

from app.scripts import certificate_remote as remote
from tests.fixtures.certificate_runtime import Runtime, make_pem


@pytest.fixture(params=['directory', 'crt_list'])
def creation(tmp_path, monkeypatch, request):
    state = Runtime(tmp_path, monkeypatch)
    state.old, state.new = make_pem(), make_pem(2, ('new.example.test',))
    state.data = dict(state.add('primary', state.old), pem_name='new.pem', pem=state.new, transaction='create')
    state.destination = next(d for d in remote.certificate_destinations(state.data) if d['kind'] == request.param)
    state.data['destination'] = state.destination
    state.target = state.files['primary'].parent / 'new.pem'
    state.listing = state.files['primary'].parent / 'certificates.list'
    state.original_list = state.listing.read_bytes()
    return state


def assert_restored(state):
    assert not state.target.exists()
    assert str(state.target) not in state.active
    assert not state.staged
    assert state.listing.read_bytes() == state.original_list
    assert state.files['primary'].read_text() == state.old
    assert not list(state.root.rglob('pending.json'))


def test_create_persists_attaches_and_recovers_lost_commit(creation):
    state = creation
    state.lose_commit = True
    pid = remote.runtime_pid(state.data)
    assert remote.deploy(state.data)['verification'] == 'runtime'
    assert state.target.read_text() == state.new
    assert state.active[str(state.target)] == state.new
    assert str(state.target) in state.sources[state.destination['path']]
    assert remote.runtime_certificate(state.data)['used']
    assert remote.runtime_pid(state.data) == pid
    calls = list(state.calls)
    remote.deploy(state.data)
    assert state.calls.count('new ssl cert ' + remote.runtime_path(state.data)) == 1
    assert state.calls.count('commit ssl cert ' + remote.runtime_path(state.data)) == calls.count('commit ssl cert ' + remote.runtime_path(state.data))
    if state.destination['kind'] == 'crt_list':
        assert len(state.listing.read_text().splitlines()) == 2
    remote.finish_deployment(dict(state.data, operation='commit'))
    assert not list(state.root.rglob('pending.json'))
    assert not list(state.root.rglob('previous.crt-list'))


def test_creation_can_roll_back_without_touching_existing_certificates(creation):
    remote.deploy(creation.data)
    remote.finish_deployment(dict(creation.data, operation='rollback'))
    remote.finish_deployment(dict(creation.data, operation='rollback'))
    assert_restored(creation)


@pytest.mark.parametrize('failure', ['existing_file', 'existing_runtime', 'unknown_destination', 'transaction'])
def test_creation_preflight_leaves_baseline_unchanged(creation, failure):
    state = creation
    if failure == 'existing_file':
        state.target.write_text(state.new)
    elif failure == 'existing_runtime':
        state.active[str(state.target)] = state.new
    elif failure == 'unknown_destination':
        del state.sources[state.destination['path']]
    else:
        state.staged['other.pem'] = state.old
    active, staged = dict(state.active), dict(state.staged)
    with pytest.raises(remote.CertificateFailure):
        remote.deploy(state.data)
    assert state.active == active and state.staged == staged
    assert state.listing.read_bytes() == state.original_list
    assert state.target.exists() == (failure == 'existing_file')
    assert not list(state.root.rglob('pending.json'))


@pytest.mark.parametrize('command', ['new ssl cert', 'set ssl cert', 'commit ssl cert', 'add ssl crt-list'])
def test_failed_creation_rolls_back_all_owned_state(creation, monkeypatch, command):
    state = creation
    request = state.request

    def reject(data, value):
        if value.startswith(command):
            return 'Rejected'
        return request(data, value)

    monkeypatch.setattr(remote, 'runtime_request', reject)
    with pytest.raises(remote.CertificateFailure):
        remote.deploy(state.data)
    assert_restored(state)


def test_invalid_candidate_is_removed_before_runtime_changes(creation, monkeypatch):
    def validate(data, *args, **kwargs):
        if creation.target.exists() and not kwargs.get('rollback'):
            raise remote.CertificateFailure('validation_failed')

    monkeypatch.setattr(remote, 'validate_configuration', validate)
    with pytest.raises(remote.CertificateFailure, match='validation_failed'):
        remote.deploy(creation.data)
    assert_restored(creation)


@pytest.mark.parametrize('command', ['new ssl cert', 'commit ssl cert', 'add ssl crt-list'])
def test_worker_restart_resumes_owned_creation(creation, monkeypatch, command):
    state = creation
    request = state.request

    def interrupt(data, value):
        result = request(data, value)
        if value.startswith(command):
            raise SystemExit()
        return result

    monkeypatch.setattr(remote, 'runtime_request', interrupt)
    with pytest.raises(SystemExit):
        remote.deploy(state.data)
    monkeypatch.setattr(remote, 'runtime_request', request)
    remote.deploy(state.data)
    remote.finish_deployment(dict(state.data, operation='commit'))
    assert state.target.read_text() == state.new
    assert state.active[str(state.target)] == state.new
    assert not list(state.root.rglob('pending.json'))


def test_recovery_preserves_external_changes(creation):
    remote.deploy(creation.data)
    creation.target.write_text(creation.old)
    with pytest.raises(remote.CertificateFailure, match='concurrent_change'):
        remote.finish_deployment(dict(creation.data, operation='rollback'))
    assert creation.target.read_text() == creation.old
    assert creation.active[str(creation.target)] == creation.new
    assert list(creation.root.rglob('pending.json'))


def test_catalog_lists_only_loaded_destinations(creation):
    (creation.root / 'not-loaded').mkdir()
    result = remote.catalog(creation.data)
    assert result['can_create']
    assert {d['kind'] for d in result['destinations']} == {'crt_list', 'directory'}
    assert all(d['path'] in creation.sources for d in result['destinations'])
    assert 'PRIVATE KEY' not in json.dumps(result)


def test_new_certificate_in_another_loaded_directory_can_be_updated(creation):
    state = creation
    directory = state.root / 'another loaded directory'
    directory.mkdir()
    state.sources[str(directory)] = []
    data = dict(state.data, destination=dict(path=str(directory), kind='directory'))
    remote.deploy(data)
    remote.finish_deployment(dict(data, operation='commit'))
    item = next(item for item in remote.catalog(state.data)['certificates'] if item['name'] == 'new.pem')
    assert item['can_update'] and item['disk_status'] == 'matches'
    assert item['directory'] == str(directory)
    update = dict(state.data, pem=state.old, transaction='replace', update_directory=item['directory'],
                  expected_revision=item['revision'])
    update.pop('destination')
    remote.deploy(update)
    remote.finish_deployment(dict(update, operation='commit'))
    assert (directory / 'new.pem').read_text() == state.old
    assert state.active[str(directory / 'new.pem')] == state.old


def test_crt_list_rejects_paths_its_file_parser_cannot_read(creation):
    if creation.destination['kind'] != 'crt_list':
        return
    data = dict(creation.data, cert_dir=str(creation.root / 'with spaces'))
    with pytest.raises(remote.CertificateFailure, match='crt_list_path_unsupported'):
        remote.deploy(data)
    assert creation.listing.read_bytes() == creation.original_list
    assert not any(c.startswith(('new ', 'set ', 'add ')) for c in creation.calls)


def test_recovery_does_not_overwrite_an_edited_crt_list(creation):
    if creation.destination['kind'] != 'crt_list':
        return
    remote.deploy(creation.data)
    changed = creation.listing.read_bytes() + b'# changed by operator\n'
    creation.listing.write_bytes(changed)
    with pytest.raises(remote.CertificateFailure, match='concurrent_change'):
        remote.finish_deployment(dict(creation.data, operation='rollback'))
    assert creation.listing.read_bytes() == changed
    assert creation.active[str(creation.target)] == creation.new


def test_pinned_docker_file_mount_cannot_be_replaced_via_parent_mount(creation, monkeypatch):
    source = creation.files['primary'].parent
    destination = creation.root / 'container-tls'
    mounts = [{'Source': str(source), 'Destination': str(destination)},
              {'Source': str(creation.listing), 'Destination': str(destination / 'certificates.list')}]
    monkeypatch.setattr(remote, 'command', lambda *args: json.dumps(mounts).encode())
    with pytest.raises(remote.CertificateFailure, match='destination_unavailable'):
        remote.host_path(dict(docker=True, container='haproxy'), str(destination / 'certificates.list'))
