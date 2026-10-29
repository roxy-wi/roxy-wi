import json
import hashlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
import requests
from pydantic import ValidationError

from app.modules.connectors import certificates as connectors
from app.modules.db.db_model import CertificateSource, InstallationTasks, PacemakerCluster, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.operations import queue
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.common.time import utc_now
from app.modules.pacemaker import service as clusters
from app.modules.pacemaker.schemas import ClusterCreate
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound, RoxywiValidationError
from app.modules.service import certificate_sources as sources, certificates, certificate_operations as operations
from tests.fixtures.certificate_runtime import make_pem


SETTINGS = dict(url='https://certwarden.example.test', certificate='example.test',
                certificate_api_key='certificate-secret', private_key_api_key='private-secret')


@pytest.mark.parametrize('url', ['http://example.test', 'https://user:pass@example.test',
                                'https://example.test/?token=x', 'https://example.test/#x', 'https://example.test:bad'])
def test_provider_refuses_insecure_or_credential_bearing_urls(url):
    with pytest.raises(ValidationError):
        connectors.validate_settings('certwarden', dict(SETTINGS, url=url))


def test_registry_refuses_unknown_provider():
    with pytest.raises(RoxywiValidationError):
        connectors.provider('arbitrary-module')


@pytest.fixture
def http(monkeypatch):
    response = SimpleNamespace(status_code=200, iter_content=lambda _: [b'PEM'])
    calls = []

    class Response:
        def __enter__(self): return response
        def __exit__(self, *_): pass

    class Session:
        trust_env = True
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, url, **kwargs):
            calls.append((url, kwargs, self.trust_env))
            return Response()

    monkeypatch.setattr(connectors.requests, 'Session', Session)
    return response, calls


def test_certwarden_uses_header_keys_verified_tls_and_no_redirects(http):
    response, calls = http
    assert connectors.CertWarden.fetch(SETTINGS) == 'PEM'
    url, kwargs, trust_env = calls[0]
    assert url.endswith('/certwarden/api/v1/download/privatecertchains/example.test')
    assert 'secret' not in url and not trust_env
    assert kwargs['headers'] == {'X-API-Key': 'certificate-secret.private-secret'}
    assert kwargs['verify'] is True and kwargs['allow_redirects'] is False


@pytest.mark.parametrize('status', [301, 302, 401, 403, 500])
def test_provider_http_failure_does_not_disclose_credentials(http, status):
    response, _calls = http
    response.status_code = status
    with pytest.raises(RoxywiValidationError) as failure:
        connectors.CertWarden.fetch(SETTINGS)
    assert 'secret' not in str(failure.value)


def test_provider_bounds_downloads(http):
    response, _calls = http
    response.iter_content = lambda _: [b'x' * (certificates.MAX_PEM_BYTES + 1)]
    with pytest.raises(RoxywiValidationError, match='limit'):
        connectors.CertWarden.fetch(SETTINGS)


@pytest.fixture
def binding(monkeypatch):
    servers = [Server.create(hostname=f'source-test-{i}', ip=f'192.0.2.{60+i}', group_id=1, haproxy=1) for i in (1, 2, 3)]
    cluster = clusters.register(ClusterCreate(name='source-test', members=[
        dict(server_id=s.server_id, name=s.hostname, address=s.ip, nodeid=i)
        for i, s in enumerate(servers[:2], 1)]), 1)
    from app.modules.service import certificate_cluster
    monkeypatch.setattr(certificate_cluster,'plan',lambda _cluster,settings:{ident:dict(mode='active',cib='fixture') for ident in settings})
    pem = make_pem()
    calls = []
    monkeypatch.setattr(connectors.CertWarden, 'fetch', lambda _settings: pem)
    monkeypatch.setattr(operations, 'authorize', lambda ident, *_args, **_kwargs: Server.get_by_id(ident))
    monkeypatch.setattr(sources.user_sql, 'select_user_services', lambda _: '1 5')
    monkeypatch.setattr(certificates, 'catalog', lambda _: {'certificates': [dict(name='example.pem',
        revision=hashlib.sha256(pem.encode()).hexdigest(), can_update=True, directory='/certs',
        disk_status='matches',runtime_status='used',disk=dict(fingerprint=certificates.certificate_metadata(pem)['fingerprint']),
        fingerprint=certificates.certificate_metadata(pem)['fingerprint'])], 'destinations': []})
    monkeypatch.setattr(certificates, 'deployment_settings', lambda _s, name, **_: dict(
        pem_name=name, cert_dir='/certs', config_path='/haproxy.cfg', docker=False, container='', runtime_port=1999,validation={}))
    monkeypatch.setattr(certificates, 'deploy', lambda server, *_args, **_kwargs: calls.append(server.server_id))
    monkeypatch.setattr(certificates, 'remote', lambda *_args, **_kwargs: {})
    body = sources.SourceRequest(name='Public TLS', settings=SETTINGS, server_id=servers[0].server_id,
        cluster_id=cluster.id, pem_name='example.pem', domains=['example.test'])
    yield SimpleNamespace(servers=servers, cluster=cluster, body=body, calls=calls, pem=pem)
    CertificateSource.delete().where(CertificateSource.name == 'Public TLS').execute()
    InstallationTasks.delete().where(InstallationTasks.operation_type.in_(('certificate-source','certificate'))).execute()
    cluster.delete_instance(recursive=True)
    for server in servers:
        server.delete_instance()


def run(row, *, check=False):
    task = sources.enqueue(row, 1, check=check)
    result = sources.execute(task)
    return sources.get(row.id, 1), task, result


def test_source_encrypts_secrets_and_redacts_api_fields(binding):
    row = sources.save(binding.body, 1, 1)
    assert row.configuration.startswith('fernet:') and 'secret' not in row.configuration
    assert 'certificate_api_key' not in sources.public(row)['settings']
    assert 'private_key_api_key' not in sources.public(row)['settings']
    with pytest.raises(RoxywiResourceNotFound): sources.get(row.id, 2)


def test_source_check_does_not_deploy(binding):
    row, task, result = run(sources.save(binding.body, 1, 1), check=True)
    assert result == 'completed' and row.status == 'checked'
    assert not binding.calls and not row.fingerprint and row.deployment_task_id is None
    assert 'PRIVATE KEY' not in task.operation_payload


def test_sync_deploys_to_all_selected_pacemaker_members_and_skips_unchanged(binding):
    row, _task, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed' and row.status == 'current'
    assert binding.calls == [s.server_id for s in binding.servers[:2]]
    assert row.fingerprint == certificates.certificate_metadata(binding.pem)['fingerprint']
    child = InstallationTasks.get_by_id(row.deployment_task_id)
    assert child.status == 'completed'
    assert deserialize_operation_payload(child.operation_payload)['cluster_id'] == binding.cluster.id
    row, _task, result = run(row)
    assert result == 'completed' and len(binding.calls) == 2


def test_changed_membership_is_refused_before_fetch_or_deploy(binding, monkeypatch):
    row = sources.save(binding.body, 1, 1)
    task = sources.enqueue(row, 1)
    data = json.loads(binding.cluster.servers)
    data.append(dict(server_id=binding.servers[2].server_id, name=binding.servers[2].hostname,
                     address=binding.servers[2].ip, nodeid=3))
    PacemakerCluster.update(servers=json.dumps(data)).where(PacemakerCluster.id == binding.cluster.id).execute()
    monkeypatch.setattr(connectors.CertWarden, 'fetch', lambda _: pytest.fail('Stale targets fetched a key'))
    assert sources.execute(task) == 'failed' and not binding.calls


def test_failed_target_rolls_back_without_accepting_the_new_fingerprint(binding, monkeypatch):
    def deploy(server, *_args, **_kwargs):
        binding.calls.append(server.server_id)
        if len(binding.calls) == 2: raise RuntimeError('sensitive-private-secret')
    monkeypatch.setattr(certificates, 'deploy', deploy)
    row, _task, result = run(sources.save(binding.body, 1, 1))
    assert result == 'failed' and not row.fingerprint
    assert 'secret' not in row.last_error
    child = InstallationTasks.get_by_id(row.deployment_task_id)
    assert child.status == 'failed'
    payload = deserialize_operation_payload(child.operation_payload)
    assert payload['phase'] == 'done'
    assert all(target.get('status') == 'rolled_back' for target in payload['targets'].values())


def test_source_cannot_be_edited_or_duplicated_while_queued(binding):
    row = sources.save(binding.body, 1, 1)
    sources.enqueue(row, 1)
    with pytest.raises(RoxywiConflictError): sources.enqueue(row, 1)
    with pytest.raises(RoxywiConflictError): sources.save(binding.body.model_copy(update={'revision':row.revision}),1,1,row.id)


def test_source_updates_require_current_revision_and_keep_omitted_keys(binding):
    row = sources.save(binding.body, 1, 1)
    with pytest.raises(RoxywiConflictError): sources.save(binding.body,1,1,row.id)
    request = binding.body.model_copy(update={'revision':row.revision,'settings':{'url':SETTINGS['url']}})
    updated = sources.save(request,1,1,row.id)
    assert updated.revision == 2
    assert sources.configuration(updated)['settings']['private_key_api_key'] == 'private-secret'


def test_provider_failure_preserves_working_certificate(binding, monkeypatch):
    monkeypatch.setattr(connectors.CertWarden, 'fetch', lambda _: (_ for _ in ()).throw(requests.RequestException('secret-key')))
    row, _task, result = run(sources.save(binding.body,1,1))
    assert result == 'failed' and not binding.calls and not row.fingerprint
    assert 'secret-key' not in row.last_error


@pytest.mark.parametrize('name', ['.', '..', '../secret', 'name/path', 'name\\path', 'name\tvalue'])
def test_provider_refuses_ambiguous_path_names(name):
    with pytest.raises(ValidationError):
        connectors.validate_settings('certwarden', dict(SETTINGS, certificate=name))


def test_sources_and_letsencrypt_cannot_own_overlapping_destinations(binding):
    from app.modules.db.db_model import LetsEncrypt, LetsEncryptState
    from app.modules.service.le import le_store
    row = sources.save(binding.body, 1, 1)
    with le_store.transaction(), pytest.raises(RoxywiConflictError, match='source'):
        le_store.check_destination(dict(server_id=binding.servers[1].server_id), 'example.pem', 1)
    row.delete_instance()
    legacy = LetsEncrypt.create(server_id=binding.servers[1].server_id, domains='["example.test"]',
        email='admin@example.test', api_key='', api_token='', type='standalone', description='')
    state = LetsEncryptState.create(le_id=legacy.id, pem_name='example.pem', status='current')
    try:
        with pytest.raises(RoxywiConflictError, match="Let's Encrypt"):
            sources.save(binding.body, 1, 1)
        state.status = 'deleted'
        state.save()
        assert sources.save(binding.body, 1, 1)
    finally:
        state.delete_instance()
        legacy.delete_instance()


def test_source_detects_drift_on_a_previously_synchronized_target(binding, monkeypatch):
    row, _, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed'
    original = certificates.catalog
    def catalog(server):
        data = original(server)
        if server.server_id == binding.servers[1].server_id:
            data['certificates'][0]['disk']['fingerprint'] = 'out-of-date'
        return data
    monkeypatch.setattr(certificates, 'catalog', catalog)
    _, _, result = run(row)
    assert result == 'completed' and len(binding.calls) == 4


def test_redelivered_completed_source_job_does_not_write_again(binding):
    row, task, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed'
    assert sources.execute(task) == 'completed' and len(binding.calls) == 2


def test_late_old_delivery_does_not_clear_new_source_job(binding):
    row = sources.save(binding.body, 1, 1)
    old = sources.enqueue(row, 1)
    CertificateSource.update(active_task_id=None).where(CertificateSource.id == row.id).execute()
    new = sources.enqueue(sources.get(row.id, 1), 1)
    assert sources.execute(old) == 'failed'
    assert sources.get(row.id, 1).active_task_id == new.id
    assert not binding.calls


def test_deleted_source_fails_job_without_contacting_the_provider(binding, monkeypatch):
    row = sources.save(binding.body, 1, 1)
    task = sources.enqueue(row, 1)
    row.delete_instance()
    monkeypatch.setattr(connectors.CertWarden, 'fetch', lambda _: pytest.fail('Deleted source contacted provider'))
    assert sources.execute(task) == 'failed'
    assert InstallationTasks.get_by_id(task.id).status == 'failed'


def test_cluster_lease_is_renewed_during_commit_and_rollback(binding, monkeypatch):
    renewed = []
    original = clusters.renew_lock
    monkeypatch.setattr(clusters, 'renew_lock', lambda *args: (renewed.append(args[0].id), original(*args))[1])
    _, _, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed' and len(renewed) == 6


def test_failed_finalization_recovers_under_cluster_lease(binding, monkeypatch):
    remote = certificates.remote
    failed = []
    def fail_once(server, data):
        if data['operation'] == 'commit' and not failed:
            failed.append(True)
            raise RuntimeError('synthetic commit failure')
        return remote(server, data)
    monkeypatch.setattr(certificates, 'remote', fail_once)
    row, _, result = run(sources.save(binding.body, 1, 1))
    assert result == 'failed'
    child = InstallationTasks.get_by_id(row.deployment_task_id)
    with pytest.raises(certificates.CertificateError, match='certificate source'):
        operations.retry(child, 1)
    with pytest.raises(RoxywiConflictError):
        sources.enqueue(row, 1)
    recovery = sources.enqueue(row, 1, recover=True)
    assert sources.execute(recovery) == 'completed'
    row = sources.get(row.id, 1)
    assert row.status == 'current' and row.fingerprint
    assert len(binding.calls) == 2  # Recovery only finalizes; never reapplies.


def test_orphaned_source_child_is_rolled_back_instead_of_reapplied(binding):
    row, _, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed'
    child = InstallationTasks.get_by_id(row.deployment_task_id)
    payload = deserialize_operation_payload(child.operation_payload)
    payload['phase'] = 'apply'
    for target in payload['targets'].values():
        target.pop('finished', None)
    operations.save(child, payload, status='running')
    recovery = sources.enqueue(row, 1, recover=True)
    assert sources.execute(recovery) == 'failed'
    after = deserialize_operation_payload(InstallationTasks.get_by_id(child.id).operation_payload)
    assert after['phase'] == 'done'
    assert all(target['status'] == 'rolled_back' for target in after['targets'].values())
    assert len(binding.calls) == 2
    assert sources.enqueue(sources.get(row.id, 1), 1)


@pytest.mark.parametrize('child_state', ['running', 'created', 'published'])
def test_stale_source_child_cannot_escape_its_parent_cluster_lease(binding, monkeypatch, child_state):
    class WorkerStopped(BaseException):
        pass

    def interrupted(server, *_args, **_kwargs):
        if binding.calls:
            raise WorkerStopped()
        binding.calls.append(server.server_id)

    monkeypatch.setattr(certificates, 'deploy', interrupted)
    row = sources.save(binding.body, 1, 1)
    parent = sources.enqueue(row, 1)
    with pytest.raises(WorkerStopped):
        sources.execute(parent)
    row = sources.get(row.id, 1)
    child = InstallationTasks.get_by_id(row.deployment_task_id)
    assert deserialize_operation_payload(child.operation_payload)['source_task_id'] == parent.id
    assert operations.execute(child, source_task_id=parent.id) == 'owned'  # A parent ID alone is not a lease.
    if child_state == 'published':
        legacy = deserialize_operation_payload(child.operation_payload)
        legacy.pop('source_task_id')
        operations.save(child, legacy)  # Existing journals also remain source-owned after upgrade.
    stale = utc_now() - timedelta(minutes=10)
    InstallationTasks.update(updated_at=stale).where(InstallationTasks.id.in_([parent.id, child.id])).execute()
    assert queue.recover_stale_operations() == 1
    assert InstallationTasks.get_by_id(parent.id).status == 'created'
    assert InstallationTasks.get_by_id(child.id).status == 'running'
    assert sources.public(row)['recovery_required']

    # Also cover already-requeued children from an earlier release and delayed
    # RabbitMQ deliveries. None of the generic entry points may apply them.
    InstallationTasks.update(status=child_state).where(InstallationTasks.id == child.id).execute()
    assert claim_operation(child.operation_id, child.id) == (False, 'owned')
    assert execute_operation(child.operation_id, child.id) == 'owned'
    assert operations.execute(InstallationTasks.get_by_id(child.id)) == 'owned'
    assert binding.calls == [binding.servers[0].server_id]

    assert claim_operation(parent.operation_id, parent.id)[0]
    assert execute_operation(parent.operation_id, parent.id) == 'failed'
    assert queue.publish_pending_operations() == 0  # No RabbitMQ needed for an owned-only outbox.
    assert sources.public(sources.get(row.id, 1))['recovery_required']
    locked_recovery = []
    def recover_remote(_server, data):
        assert clusters.get_cluster(binding.cluster.id, 1).lock_token
        locked_recovery.append(data['operation'])
        return {}
    monkeypatch.setattr(certificates, 'remote', recover_remote)
    recovery = sources.enqueue(sources.get(row.id, 1), 1, recover=True)
    assert sources.execute(recovery) == 'failed'  # Interrupted apply is rolled back, never reapplied.
    assert locked_recovery and set(locked_recovery) == {'rollback'}
    assert binding.calls == [binding.servers[0].server_id]
    assert not sources.public(sources.get(row.id, 1))['recovery_required']


def test_live_source_heartbeat_renews_the_child_without_requeueing(binding, monkeypatch):
    pulses = []
    def deploy(server, *_args, **_kwargs):
        source = CertificateSource.get()
        parent = InstallationTasks.get_by_id(source.active_task_id)
        child = InstallationTasks.get_by_id(source.deployment_task_id)
        stale = utc_now() - timedelta(minutes=10)
        InstallationTasks.update(updated_at=stale).where(InstallationTasks.id.in_([parent.id, child.id])).execute()
        assert queue.renew_operation_lease(parent.operation_id, parent.id) == 1
        assert InstallationTasks.get_by_id(child.id).updated_at > stale
        assert queue.recover_stale_operations() == 0
        assert not sources.public(sources.get(source.id, 1))['recovery_required']
        pulses.append(server.server_id)
    monkeypatch.setattr(certificates, 'deploy', deploy)
    _row, _task, result = run(sources.save(binding.body, 1, 1))
    assert result == 'completed' and pulses == [s.server_id for s in binding.servers[:2]]
