import json

import pytest

from app.modules.service import certificates
from app.scripts import certificate_remote as remote
from tests.fixtures.certificate_runtime import Runtime, make_pem


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    state = Runtime(tmp_path, monkeypatch)
    state.old, state.new = make_pem(1), make_pem(2)
    state.data = dict(state.add('primary', state.old), pem=state.new, transaction='first')
    return state


def test_pem_validation_and_metadata_do_not_return_private_material():
    pem = make_pem()
    bundle, metadata = certificates.inspect_pem(pem)
    assert metadata['domains'] == ['example.test']
    assert len(metadata['fingerprint']) == 64
    assert 'PRIVATE KEY' not in json.dumps(metadata)
    _, second = certificates.inspect_pem(bundle['fullchain'] + bundle['key'])
    assert second == metadata
    with pytest.raises(certificates.CertificateError, match='do not match'):
        certificates.inspect_pem(bundle['fullchain'] + certificates.inspect_pem(make_pem(2))[0]['key'])


def test_pem_validation_checks_requested_domains_in_the_same_pass():
    pem = make_pem(domains=('example.test', 'www.example.test'))
    _bundle, metadata = certificates.inspect_pem(pem, domains=['www.example.test', 'example.test'])
    assert set(metadata['domains']) == {'example.test', 'www.example.test'}
    with pytest.raises(certificates.CertificateError, match='domains do not match'):
        certificates.inspect_pem(pem, domains=['other.test'])


@pytest.mark.parametrize('pem', ['', 'invalid', 'x' * (1024 * 1024 + 1)], ids=['empty', 'invalid', 'oversize'])
def test_invalid_uploads(pem):
    with pytest.raises(certificates.CertificateError):
        certificates.inspect_pem(pem)


def test_update_uses_runtime_and_is_repeatable_after_lost_commit(runtime):
    runtime.lose_commit = True
    assert remote.deploy(runtime.data)['verification'] == 'runtime'
    assert runtime.files['primary'].read_text() == runtime.new
    assert runtime.active[str(runtime.files['primary'])] == runtime.new
    commits = len([c for c in runtime.calls if c.startswith('commit ssl cert')])
    remote.deploy(runtime.data)
    assert len([c for c in runtime.calls if c.startswith('commit ssl cert')]) == commits
    assert list(runtime.root.rglob('previous.pem'))
    remote.finish_deployment(dict(runtime.data, operation='commit'))
    assert not list(runtime.root.rglob('pending.json'))
    assert not list(runtime.root.rglob('previous.pem'))


def test_failed_validation_restores_file_and_runtime(runtime):
    runtime.fail_validation = True
    with pytest.raises(remote.CertificateFailure, match='validation_failed'):
        remote.deploy(runtime.data)
    assert runtime.files['primary'].read_text() == runtime.old
    assert runtime.active[str(runtime.files['primary'])] == runtime.old
    assert not runtime.staged
    assert not list(runtime.root.rglob('pending.json'))


def test_partial_cluster_update_can_be_rolled_back(runtime):
    remote.deploy(runtime.data)
    remote.finish_deployment(dict(runtime.data, operation='rollback'))
    assert runtime.active[str(runtime.files['primary'])] == runtime.old
    assert runtime.files['primary'].read_text() == runtime.old
    remote.finish_deployment(dict(runtime.data, operation='rollback'))


def test_unrelated_runtime_transaction_is_never_aborted(runtime):
    runtime.staged['/other.pem'] = runtime.new
    with pytest.raises(remote.CertificateFailure, match='transaction_busy'):
        remote.deploy(runtime.data)
    assert not any(c.startswith(('set ', 'abort ', 'commit ')) for c in runtime.calls)
    assert runtime.files['primary'].read_text() == runtime.old


@pytest.mark.parametrize('failure', ['disk', 'revision', 'not_loaded', 'operator'])
def test_preflight_rejects_unsafe_baselines(runtime, failure):
    if failure == 'disk':
        runtime.files['primary'].write_text(runtime.new)
    elif failure == 'revision':
        runtime.data['expected_revision'] = '0' * 64
    elif failure == 'not_loaded':
        runtime.active.clear()
    else:
        runtime.level = 'operator'
    original = runtime.files['primary'].read_bytes()
    with pytest.raises(remote.CertificateFailure):
        remote.deploy(runtime.data)
    assert runtime.files['primary'].read_bytes() == original
    assert not list(runtime.root.rglob('pending.json'))


def test_chain_update_with_unchanged_leaf_is_committed(runtime):
    extra = certificates.inspect_pem(runtime.new)[0]['fullchain']
    runtime.data['pem'] = runtime.old + extra
    remote.deploy(runtime.data)
    assert runtime.active[str(runtime.files['primary'])] == runtime.data['pem']
    remote.finish_deployment(dict(runtime.data, operation='rollback'))
    assert runtime.active[str(runtime.files['primary'])] == runtime.old


def test_chain_update_does_not_accept_a_rejected_commit(runtime, monkeypatch):
    runtime.data['pem'] = runtime.old + certificates.inspect_pem(runtime.new)[0]['fullchain']
    request = runtime.request
    rejected = []

    def reject_once(data, command):
        if command.startswith('commit ssl cert ') and not rejected:
            rejected.append(True)
            return 'Failed to commit the transaction'
        return request(data, command)

    monkeypatch.setattr(remote, 'runtime_request', reject_once)
    with pytest.raises(remote.CertificateFailure, match='verification_failed'):
        remote.deploy(runtime.data)
    assert runtime.files['primary'].read_text() == runtime.old
    assert runtime.active[str(runtime.files['primary'])] == runtime.old
    assert not runtime.staged


def test_automatic_renewal_uses_runtime_for_loaded_certificate(runtime):
    runtime.data['apply_mode'] = 'auto'
    assert remote.deploy(runtime.data)['verification'] == 'runtime'
    assert runtime.active[str(runtime.files['primary'])] == runtime.new


def test_catalog_keeps_key_private_and_reports_drift(runtime):
    result = remote.catalog(runtime.data)
    assert 'PRIVATE KEY' not in json.dumps(result)
    item = result['certificates'][0]
    assert item['runtime_status'] == 'used' and item['disk_status'] == 'matches' and item['can_update']
    runtime.files['primary'].write_text(runtime.new)
    item = remote.catalog(runtime.data)['certificates'][0]
    assert item['disk_status'] == 'differs' and not item['can_update']
    runtime.unreachable = True
    result = remote.catalog(runtime.data)
    assert result['runtime_error'] == 'runtime_unavailable'
    assert result['certificates'][0]['runtime_status'] == 'unknown'


def test_catalog_reports_runtime_metadata_when_file_is_missing(runtime):
    runtime.files['primary'].unlink()
    item = remote.catalog(runtime.data)['certificates'][0]
    assert item['disk_status'] == 'missing' and not item['can_update']
    assert item['runtime']['domains'] == ['example.test']
    assert item['runtime']['not_after']
    assert item['runtime']['fingerprint'] == remote.pem_fingerprint(runtime.old)


@pytest.mark.parametrize('disk_state', ['matches', 'differs', 'missing'])
def test_catalog_checks_crt_list_certificates_outside_managed_directories(runtime, disk_state):
    path = runtime.files['primary'].parent / 'nested' / 'external.pem'
    path.parent.mkdir()
    if disk_state != 'missing':
        path.write_text(runtime.new if disk_state == 'differs' else runtime.old)
    runtime.active[str(path)] = runtime.old
    listing = str(runtime.files['primary'].parent / 'certificates.list')
    runtime.sources[listing].append(str(path))

    item = next(item for item in remote.catalog(runtime.data)['certificates'] if item['path'] == str(path))

    assert item['runtime_status'] == 'used'
    assert item['disk_status'] == disk_state
    assert item['can_update'] == (disk_state == 'matches')
    assert item['can_view'] == (disk_state != 'missing')
    if disk_state != 'missing':
        assert item['directory'] == str(path.parent)
    assert 'PRIVATE KEY' not in json.dumps(item)


def test_catalog_reports_unmapped_runtime_file_as_unknown(runtime, monkeypatch):
    path = str(runtime.root / 'container-only' / 'external.pem')
    runtime.active[path] = runtime.old
    resolve = remote.host_path

    def unmapped(data, value):
        if value == path:
            raise RuntimeError('No persistent mount')
        return resolve(data, value)

    monkeypatch.setattr(remote, 'host_path', unmapped)
    item = next(item for item in remote.catalog(runtime.data)['certificates'] if item['path'] == path)

    assert item['disk_status'] == 'unknown' and item['runtime_status'] == 'used'
    assert not item['can_update'] and not item['can_view']
    assert item['runtime']['fingerprint'] == remote.pem_fingerprint(runtime.old)


def test_lost_worker_resumes_owned_transaction(runtime, monkeypatch):
    validate = remote.validate_configuration
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise SystemExit()
    monkeypatch.setattr(remote, 'validate_configuration', interrupted)
    with pytest.raises(SystemExit):
        remote.deploy(runtime.data)
    assert runtime.files['primary'].read_text() == runtime.new
    assert runtime.staged
    monkeypatch.setattr(remote, 'validate_configuration', validate)
    remote.deploy(runtime.data)
    assert runtime.active[str(runtime.files['primary'])] == runtime.new


def test_shared_validation_receives_all_configuration_sources(monkeypatch):
    spec = dict(service='haproxy', sources=['/etc/haproxy/haproxy.cfg', '/etc/haproxy/conf.d'])
    received = []
    monkeypatch.setattr(remote.config_candidate, 'execute', lambda data: received.append(data) or {'status': 'ok'})
    remote.validate_configuration({'validation': spec})
    assert received == [spec]


@pytest.mark.parametrize('suffix', ['pem', 'crt', 'key'])
def test_uploaded_file_uses_atomic_private_storage(runtime, suffix):
    data = dict(runtime.data, pem_name='uploaded.' + suffix, pem=runtime.new)
    result = remote.store_file(data)
    target = runtime.files['primary'].parent / data['pem_name']
    assert result == {'stored': True}
    assert target.read_text() == runtime.new
    assert not runtime.calls


def test_upload_does_not_replace_a_pending_runtime_transaction(runtime):
    target, journal = remote.deployment_journal(runtime.data)
    (journal / 'pending.json').write_text('{}')
    with pytest.raises(remote.CertificateFailure, match='transaction_busy'):
        remote.store_file(dict(runtime.data, pem=runtime.new))
    assert target.read_text() == runtime.old


def test_crt_list_file_outside_upload_directory_can_be_viewed_and_updated(runtime):
    path = runtime.root / 'external' / 'site.pem'
    path.parent.mkdir()
    path.write_text(runtime.old)
    runtime.active[str(path)] = runtime.old
    item = next(item for item in remote.catalog(runtime.data)['certificates'] if item['path'] == str(path))
    assert item['can_view'] and item['can_update'] and not item['can_delete']
    result = remote.read_file(dict(runtime.data, path=str(path)))
    assert 'BEGIN CERTIFICATE' in result['content'] and 'PRIVATE KEY' not in result['content']
    update = dict(runtime.data, update_directory=str(path.parent), expected_revision=item['revision'])
    remote.deploy(update)
    remote.finish_deployment(dict(update, operation='commit'))
    assert path.read_text() == runtime.new
    assert runtime.active[str(path)] == runtime.new
    assert runtime.files['primary'].read_text() == runtime.old


def test_file_operations_reject_unknown_paths_and_loaded_deletion(runtime):
    secret = runtime.root / 'unlisted.pem'
    secret.write_text(runtime.old)
    with pytest.raises(remote.CertificateFailure, match='invalid_path'):
        remote.read_file(dict(runtime.data, path=str(secret)))
    target = runtime.files['primary']
    with pytest.raises(remote.CertificateFailure, match='certificate_in_use'):
        remote.remove_file(dict(runtime.data, path=str(target), revision=runtime.revision('primary')))
    assert target.read_text() == runtime.old


def test_file_deletion_checks_revision_and_restores_failed_validation(runtime):
    target = runtime.files['primary'].parent / 'uploaded.crt'
    target.write_text(runtime.old)
    item = next(item for item in remote.catalog(runtime.data)['certificates'] if item['path'] == str(target))
    data = dict(runtime.data, path=str(target), revision=item['revision'])
    with pytest.raises(remote.CertificateFailure, match='concurrent_change'):
        remote.remove_file(dict(data, revision='0' * 64))
    runtime.fail_validation = True
    with pytest.raises(remote.CertificateFailure, match='validation_failed'):
        remote.remove_file(data)
    assert target.read_text() == runtime.old
    runtime.fail_validation = False
    assert remote.remove_file(data)['deleted']
    assert not target.exists()
