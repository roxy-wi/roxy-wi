import importlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from peewee import SqliteDatabase

from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, LetsEncryptDnsProfile, ServiceNotification, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.roxywi.class_models import LetsEncryptRequest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound
from app.modules.service.le import le_store as store, le_execution as execution, le_certbot as certbot


MODELS = [LetsEncrypt, LetsEncryptState, LetsEncryptDnsProfile, ServiceNotification, InstallationTasks, Server]
DATA = dict(server_id=1, domains=['example.com'], email='admin@example.com', type='cloudflare',
            api_key=None, api_token='private-dns-token', description='example certificate')


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    db = SqliteDatabase(tmp_path / 'le.db', pragmas={'journal_mode': 'wal', 'busy_timeout': 10000})
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path / 'lib'))
    monkeypatch.setattr(certbot, 'deployment_settings', lambda server, name: {'pem_name': name})
    def finish(server, data):
        assert data['operation'] in ('commit', 'rollback')
        return {'finished': True}
    monkeypatch.setattr(certbot, 'remote', finish)
    with db.bind_ctx(MODELS, bind_refs=False, bind_backrefs=False):
        db.create_tables(MODELS)
        Server.create(server_id=1, ip='192.0.2.1', hostname='primary', group_id='1')
        Server.create(server_id=2, ip='192.0.2.2', hostname='secondary', group_id='1', master=1)
        Server.create(server_id=3, ip='192.0.2.3', hostname='other tenant', group_id='2')
        yield db
        db.close()


@pytest.fixture
def bundle():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'example.com')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(days=80)).add_extension(
                       x509.SubjectAlternativeName([x509.DNSName('example.com')]), critical=False)
                   .sign(key, hashes.SHA256()))
    return {'fullchain': certificate.public_bytes(serialization.Encoding.PEM).decode(),
            'key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()}


def run_task(task_id):
    task = InstallationTasks.get_by_id(task_id)
    claim_operation(task.operation_id, task.id)
    return execute_operation(task.operation_id, task.id)


def fake_issuer(monkeypatch, bundle, deploy=None):
    monkeypatch.setattr(certbot, 'obtain', lambda *args, **kwargs: bundle)
    monkeypatch.setattr(certbot, 'deploy', lambda *args, **kwargs: deploy(*args) if deploy else None)


def test_configuration_is_encrypted_and_api_is_sanitized():
    le_id, task_id = store.create(DATA, '1', 7)
    row, state = LetsEncrypt.get_by_id(le_id), LetsEncryptState.get()
    assert row.api_key == row.api_token == ''
    assert DATA['api_token'] not in state.credentials
    assert DATA['api_token'] not in state.pending_config
    assert deserialize_operation_payload(state.credentials)['api_token'] == DATA['api_token']
    response = store.public_config(row, recurse=True)
    assert response['api_key'] is None and response['api_token'] is None
    assert response['has_api_token'] is True
    assert response['server_id']['hostname'] == 'primary'
    assert DATA['api_token'] not in json.dumps(response)
    task = InstallationTasks.get_by_id(task_id)
    assert task.server_ids == [1, 2]
    assert deserialize_operation_payload(task.operation_payload) == {'le_id': le_id, 'revision': 1, 'action': 'issue'}


def test_tenant_checks_cover_server_and_existing_certificate():
    with pytest.raises(RoxywiResourceNotFound):
        store.create(DATA | {'server_id': 3}, '1')
    le_id, _ = store.create(DATA, '1')
    with pytest.raises(RoxywiResourceNotFound):
        store.get_owned(le_id, '2')
    assert LetsEncrypt.select().count() == 1


def test_busy_and_overlapping_ha_destinations_are_rejected():
    le_id, _ = store.create(DATA, '1')
    with pytest.raises(RoxywiConflictError):
        store.update(le_id, DATA, '1')
    with pytest.raises(RoxywiConflictError):
        store.create(DATA | {'server_id': 2}, '1')


def test_full_lifecycle_is_idempotent_and_scheduled(monkeypatch, bundle):
    calls = []
    fake_issuer(monkeypatch, bundle, lambda server, *_: calls.append(server.server_id))
    le_id, task_id = store.create(DATA, '1')
    assert run_task(task_id) == 'completed'
    assert run_task(task_id) == 'completed'
    assert calls == [1, 2]
    state = LetsEncryptState.get()
    assert state.status == 'active' and state.applied_revision == 1
    assert state.fingerprint and state.not_after and state.next_run_at
    assert not state.pending_config and not state.active_task_id
    assert store.dispatch_due(state.next_run_at) == 1
    assert store.dispatch_due(state.next_run_at) == 0
    assert LetsEncryptState.get().last_task_id != task_id


def test_failed_ha_target_rolls_back_before_retrying(monkeypatch, bundle):
    calls = []
    def deploy(server, *_):
        calls.append(server.server_id)
        if server.server_id == 2 and calls.count(2) == 1:
            raise OSError('private-dns-token should never be logged')
    fake_issuer(monkeypatch, bundle, deploy)
    le_id, task_id = store.create(DATA, '1')
    assert run_task(task_id) == 'failed'
    state = LetsEncryptState.get()
    assert state.status == 'failed' and state.retry_at
    assert 'private-dns-token' not in state.last_error
    assert json.loads(state.targets)['1']['status'] == 'rolled_back'
    assert store.dispatch_due(state.retry_at) == 1
    assert run_task(LetsEncryptState.get().active_task_id) == 'completed'
    assert calls == [1, 2, 1, 2]


def test_failed_update_keeps_working_config_and_credentials(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    task_id = store.update(le_id, DATA | {'description': 'replacement', 'api_token': 'replacement-token'}, '1')
    def fail(*args, **kwargs):
        raise certbot.CertificateError('ACME challenge failed')
    monkeypatch.setattr(certbot, 'obtain', fail)
    assert run_task(task_id) == 'failed'
    row, state = LetsEncrypt.get(), LetsEncryptState.get()
    assert row.description == DATA['description']
    assert store.config_for(row, state)['api_token'] == DATA['api_token']
    fake_issuer(monkeypatch, bundle)
    retry = store.action(le_id, 'retry', '1')
    assert run_task(retry) == 'completed'
    assert LetsEncrypt.get().description == 'replacement'


def test_delete_waits_for_cleanup_and_keeps_failed_record(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    deletion = store.action(le_id, 'delete', '1')
    assert store.get_owned(le_id, '1')
    def fail(*args):
        raise OSError('cleanup failed')
    monkeypatch.setattr(execution, 'delete_material', fail)
    assert run_task(deletion) == 'failed'
    assert store.get_owned(le_id, '1')
    monkeypatch.setattr(execution, 'delete_material', lambda *args: None)
    assert run_task(store.action(le_id, 'retry', '1')) == 'completed'
    with pytest.raises(RoxywiResourceNotFound):
        store.get_owned(le_id, '1')
    assert LetsEncryptState.get().credentials == ''
    assert LetsEncryptState.get().next_run_at is None


def test_failed_staging_test_does_not_block_production_renewal(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    def fail(*args, **kwargs):
        raise certbot.CertificateError('Staging unavailable')
    monkeypatch.setattr(certbot, 'obtain', fail)
    assert run_task(store.action(le_id, 'test', '1')) == 'failed'
    state = LetsEncryptState.get()
    assert state.pending_config is None
    assert store.dispatch_due(state.next_run_at) == 1
    task = InstallationTasks.get_by_id(LetsEncryptState.get().active_task_id)
    assert deserialize_operation_payload(task.operation_payload)['action'] == 'renew'


def test_parallel_schedulers_enqueue_once(database, monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    _, task_id = store.create(DATA, '1')
    run_task(task_id)
    due = LetsEncryptState.get().next_run_at
    def dispatch(_):
        try:
            return store.dispatch_due(due)
        finally:
            database.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(dispatch, range(4))) == 1


def test_migration_encrypts_legacy_credentials_and_pauses_scheduling():
    row = LetsEncrypt.create(server_id=1, domains="['example.com']", email='admin@example.com',
                             type='cloudflare', api_key='', api_token='legacy-token', description='')
    migration = importlib.import_module('app.modules.db.migrations.20260919000000_letsencrypt_state')
    migration.up()
    migration.up()
    state = LetsEncryptState.get()
    assert state.legacy_pending
    assert state.status == 'migration_required'
    assert LetsEncrypt.get_by_id(row.id).api_token == ''
    assert store.config_for(LetsEncrypt.get(), state)['api_token'] == 'legacy-token'
    assert store.dispatch_due(datetime.now()) == 0
    with pytest.raises(RoxywiConflictError):
        store.action(row.id, 'renew', '1')


@pytest.mark.parametrize('changes', [
    {'domains': []}, {'domains': ['bad.*.example.com']},
    {'type': 'standalone', 'email': None}, {'type': 'standalone', 'domains': ['*.example.com']},
    {'api_token': 'token\ninjected=value'},
])
def test_invalid_requests_are_rejected(changes):
    with pytest.raises(ValueError):
        LetsEncryptRequest(**(DATA | changes))


def test_domains_are_normalized_and_deduplicated():
    model = LetsEncryptRequest(**(DATA | {'domains': [' Example.COM. ', 'example.com', 'тест.рф']}))
    assert model.domains == ['example.com', 'xn--e1aybc.xn--p1ai']


@pytest.mark.parametrize('fail', [False, True])
def test_recovered_delivery_waits_without_executing_twice(database, monkeypatch, bundle, fail):
    started, release = threading.Event(), threading.Event()
    calls = []
    def obtain(*args, **kwargs):
        calls.append(1)
        started.set()
        assert release.wait(10)
        if fail:
            raise certbot.CertificateError('ACME failed')
        return bundle
    monkeypatch.setattr(certbot, 'obtain', obtain)
    monkeypatch.setattr(certbot, 'deploy', lambda *args, **kwargs: None)
    _, task_id = store.create(DATA, '1')
    task = InstallationTasks.get_by_id(task_id)
    claim_operation(task.operation_id, task_id)
    def execute():
        return execute_operation(task.operation_id, task_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute)
        assert started.wait(10)
        second = pool.submit(execute)
        release.set()
        expected = 'failed' if fail else 'completed'
        assert first.result(10) == second.result(10) == expected
    assert calls == [1]


def test_exhausted_replacement_retries_resume_applied_revision(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    task_id = store.update(le_id, DATA | {'domains': ['new.example.com']}, '1')
    def fail(*args, **kwargs):
        raise certbot.CertificateError('New domain challenge failed')
    monkeypatch.setattr(certbot, 'obtain', fail)
    for attempt in range(3):
        assert run_task(task_id) == 'failed'
        state = LetsEncryptState.get()
        if attempt < 2:
            assert store.dispatch_due(state.retry_at) == 1
            task_id = LetsEncryptState.get().active_task_id
    assert state.pending_config is None and state.pending_action == 'renew'
    assert state.applied_revision == 1 and state.revision == 2
    assert store.dispatch_due(state.next_run_at) == 1
    calls = []
    def previous_config(data, runtime, *args, **kwargs):
        calls.append((data['domains'], runtime.revision))
        return bundle
    monkeypatch.setattr(certbot, 'obtain', previous_config)
    assert run_task(LetsEncryptState.get().active_task_id) == 'completed'
    assert calls == [(['example.com'], 1)]


def test_cleanup_preserves_last_active_and_non_le_operations(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, first = store.create(DATA, '1')
    run_task(first)
    second = store.action(le_id, 'renew', '1')
    run_task(second)
    old = datetime.now() - timedelta(days=60)
    InstallationTasks.update(finish_date=old).execute()
    other = InstallationTasks.create(service_name='Unrelated', server_ids=[1], operation_type='ansible',
                                      status='completed', finish_date=old)
    assert store.cleanup_history() == 1
    assert InstallationTasks.get_or_none(InstallationTasks.id == first) is None
    assert InstallationTasks.get_by_id(second) and InstallationTasks.get_by_id(other.id)
    assert store.cleanup_history(retention_days=0) == 0


def test_migration_cutover_is_resumable_and_does_not_issue(monkeypatch, bundle, tmp_path):
    from app.modules.service.le import le_migration as migration
    row = LetsEncrypt.create(server_id=1, domains="['example.com']", email='admin@example.com',
                             type='cloudflare', api_key='', api_token='legacy-token', description='')
    importlib.import_module('app.modules.db.migrations.20260919000000_letsencrypt_state').up()
    monkeypatch.setattr(migration, '_require_original_host', lambda *args: None)
    monkeypatch.setattr(migration.os, 'chown', lambda *args: None, raising=False)
    monkeypatch.setattr(migration.legacy, 'legacy_export', lambda *_: {'bundles': [dict(bundle, name='example.com')]})
    calls = []
    def disable(data):
        calls.append(data)
        if len(calls) == 1:
            raise RuntimeError('Crontab changed')
    monkeypatch.setattr(migration.legacy, 'legacy_disable', disable)
    with pytest.raises(RuntimeError, match='Crontab changed'):
        migration.migrate_legacy()
    assert LetsEncryptState.get().legacy_pending
    assert InstallationTasks.select().count() == 0
    assert migration.migrate_legacy() == 1
    assert migration.migrate_legacy() == 0
    assert not LetsEncryptState.get().legacy_pending
    assert calls[-1]['names'] == ['example.com']
    assert (certbot.revision_root(row.id, 1) / 'bundle.json').exists()


def test_http_contract_and_recurse_do_not_return_credentials(monkeypatch):
    from flask import Flask
    from app.views.service import lets_encrypt_views as views
    # Exercise the real request validation/serialization. Authorization boundary
    # is tested separately through get_owned/targets_for and existing RBAC tests.
    api = Flask('le-contract')
    monkeypatch.setattr(views, 'identity', lambda query: ('1', 7))
    monkeypatch.setattr(views, 'protect', lambda *args: None)
    api.add_url_rule('/le', view_func=views.LetsEncryptView().post, methods=['POST'])
    api.add_url_rule('/le/<int:le_id>', view_func=views.LetsEncryptView().get, methods=['GET'])
    api.add_url_rule('/les', endpoint='list_certificates', view_func=views.LetsEncryptsView().get)
    client = api.test_client()
    response = client.post('/le', json=DATA)
    assert response.status_code == 202
    le_id = response.json['id']
    assert response.json['tasks_ids']
    response = client.get(f'/le/{le_id}?recurse=True')
    assert response.status_code == 200
    assert response.json['server_id']['hostname'] == 'primary'
    assert response.json['api_token'] is None
    assert client.get('/les?recurse=True').json[0]['id'] == le_id
    assert client.post('/le', json=DATA | {'domains': []}).status_code == 400


def test_rotation_preserves_applied_and_pending_dns_credentials(database, monkeypatch):
    from cryptography.fernet import Fernet
    from app.modules.db.db_model import Cred, OidcProvider
    from rotate_credential_secret import rotate_credentials
    import os
    old = os.environ['ROXYWI_SECRET_PHRASE']
    new = Fernet.generate_key().decode()
    with database.bind_ctx([Cred, OidcProvider], bind_refs=False, bind_backrefs=False):
        database.create_tables([Cred, OidcProvider])
        store.create(DATA, '1')
        monkeypatch.setenv('ROXYWI_OLD_SECRET_PHRASE', old)
        monkeypatch.setenv('ROXYWI_SECRET_PHRASE', new)
        assert rotate_credentials() == 2
        state = LetsEncryptState.get()
        assert deserialize_operation_payload(state.credentials)['api_token'] == DATA['api_token']
        assert deserialize_operation_payload(state.pending_config)['api_token'] == DATA['api_token']
        assert rotate_credentials() == 0


def test_failed_database_commit_preserves_applied_revision(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    replacement = store.update(le_id, DATA | {'type': 'route53', 'api_key': 'access', 'api_token': 'new-token'}, '1')
    original_write = store.write_config
    def failed_write(*args):
        original_write(*args)
        raise RuntimeError('Database commit failed')
    monkeypatch.setattr(store, 'write_config', failed_write)
    assert run_task(replacement) == 'failed'
    row, state = LetsEncrypt.get(), LetsEncryptState.get()
    assert row.type == 'cloudflare'
    assert state.applied_revision == 1
    assert store.config_for(row, state)['api_token'] == DATA['api_token']


def test_scheduler_recovers_failure_outside_certificate_handler(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    _, task_id = store.create(DATA, '1')
    InstallationTasks.update(status='failed', error='Worker transport failure').where(InstallationTasks.id == task_id).execute()
    assert store.dispatch_due() == 0
    state = LetsEncryptState.get()
    assert state.status == 'failed' and state.active_task_id is None
    assert state.retry_at and state.last_error == 'Worker transport failure'
    assert store.dispatch_due(state.retry_at) == 1
    assert run_task(LetsEncryptState.get().active_task_id) == 'completed'


def test_partial_replacement_is_rolled_back_immediately_and_recovery_blocks_edits(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    run_task(task_id)
    rollback = []
    def remote(server, request):
        if request['operation'] == 'rollback':
            rollback.append(server.server_id)
            if server.server_id == 2:
                raise OSError('SSH unavailable')
    monkeypatch.setattr(certbot, 'remote', remote)
    def fail_second(server, *_):
        if server.server_id == 2:
            raise OSError('SSH unavailable')
    fake_issuer(monkeypatch, bundle, fail_second)
    replacement = store.update(le_id, DATA | {'description': 'new'}, '1')
    assert run_task(replacement) == 'failed'
    assert rollback == [1, 2]
    state = LetsEncryptState.get()
    assert json.loads(state.targets)['1']['status'] == 'rolled_back'
    assert json.loads(state.targets)['2']['status'] == 'rollback_failed'
    assert json.loads(state.deployment)['phase'] == 'rollback'
    assert state.retry_at < store.utc_now() + timedelta(minutes=6)
    assert LetsEncrypt.get().description == DATA['description']
    with pytest.raises(RoxywiConflictError, match='recovery'):
        store.update(le_id, DATA, '1')
    monkeypatch.setattr(certbot, 'remote', lambda *args: None)
    store.dispatch_due(state.retry_at)
    assert run_task(LetsEncryptState.get().active_task_id) == 'failed'
    assert LetsEncryptState.get().deployment == '{}'
    assert all(item['status'] == 'rolled_back' for item in json.loads(LetsEncryptState.get().targets).values())


def test_failed_finalize_retries_without_issuing_or_rolling_back_applied_certificate(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    calls = []
    def remote(server, request):
        calls.append((server.server_id, request['operation']))
        if server.server_id == 2:
            raise OSError('Lost response')
    monkeypatch.setattr(certbot, 'remote', remote)
    _, task_id = store.create(DATA, '1')
    assert run_task(task_id) == 'failed'
    state = LetsEncryptState.get()
    assert state.applied_revision == 1 and json.loads(state.deployment)['phase'] == 'commit'
    monkeypatch.setattr(certbot, 'obtain', lambda *args, **kwargs: pytest.fail('Must not issue during finalization'))
    monkeypatch.setattr(certbot, 'remote', lambda server, request: calls.append((server.server_id, request['operation'])))
    store.dispatch_due(state.retry_at)
    assert run_task(LetsEncryptState.get().active_task_id) == 'completed'
    assert calls == [(1, 'commit'), (2, 'commit'), (2, 'commit')]


def test_dns_profiles_are_tenant_scoped_and_rotation_is_used_at_execution(monkeypatch, bundle):
    from app.modules.service.le import le_profiles
    profile = le_profiles.save(dict(name='Production', provider='cloudflare', api_token='first-secret', propagation_seconds=120), '1')
    assert 'first-secret' not in json.dumps(profile)
    with pytest.raises(RoxywiResourceNotFound):
        store.create(DATA | {'dns_profile_id': profile['id']}, '2')
    le_id, task_id = store.create(DATA | {'dns_profile_id': profile['id']}, '1')
    le_profiles.save(dict(name='Production', provider='cloudflare', api_token='rotated-secret', propagation_seconds=180), '1', profile['id'])
    used = []
    monkeypatch.setattr(certbot, 'obtain', lambda data, *args, **kwargs: used.append((data['api_token'], data['propagation_seconds'])) or bundle)
    monkeypatch.setattr(certbot, 'deploy', lambda *args, **kwargs: None)
    assert run_task(task_id) == 'completed'
    assert used == [('rotated-secret', 180)]
    state = LetsEncryptState.get()
    assert deserialize_operation_payload(state.credentials)['api_token'] is None
    assert store.public_config(LetsEncrypt.get())['dns_profile'] == 'Production'
    with pytest.raises(RoxywiConflictError, match='used'):
        le_profiles.delete(profile['id'], '1')


def test_draft_requires_current_staging_check_before_production(monkeypatch, bundle):
    from app.modules.service.le import le_preflight, le_profiles
    profile = le_profiles.save(dict(name='DNS', provider='cloudflare', api_token='secret', propagation_seconds=60), '1')
    le_id, task_id = store.create(DATA | {'draft': True, 'dns_profile_id': profile['id']}, '1')
    assert task_id is None and store.dispatch_due(datetime.now() + timedelta(days=1)) == 0
    with pytest.raises(RoxywiConflictError, match='setup check'):
        store.action(le_id, 'issue', '1')
    monkeypatch.setattr(le_preflight, 'check_dns', lambda *args: 'DNS checked')
    monkeypatch.setattr(certbot, 'remote', lambda *args: {'checked': True})
    calls = []
    monkeypatch.setattr(certbot, 'obtain', lambda *args, **kwargs: calls.append(kwargs.get('test', False)) or (None if kwargs.get('test') else bundle))
    monkeypatch.setattr(certbot, 'deploy', lambda *args, **kwargs: None)
    assert run_task(store.action(le_id, 'preflight', '1')) == 'completed'
    assert calls == [True] and LetsEncryptState.get().draft
    assert LetsEncryptState.get().next_run_at is None
    assert store.public_config(LetsEncrypt.get())['state']['can_issue']
    production = store.action(le_id, 'issue', '1')
    le_profiles.save(dict(name='DNS', provider='cloudflare', api_token='rotated', propagation_seconds=60), '1', profile['id'])
    assert not store.public_config(LetsEncrypt.get())['state']['can_issue']
    assert run_task(production) == 'failed'  # queued check became stale
    assert calls == [True]
    assert run_task(store.action(le_id, 'preflight', '1')) == 'completed'
    assert run_task(store.action(le_id, 'issue', '1')) == 'completed'
    assert calls == [True, True, False]
    assert not LetsEncryptState.get().draft and LetsEncryptState.get().next_run_at


def test_rate_limit_defers_automatic_and_manual_retries(monkeypatch):
    retry = store.utc_now() + timedelta(days=2)
    def limited(*args, **kwargs):
        raise certbot.CertificateError('ACME rate limit reached', 'rate_limited', retry.isoformat() + '+00:00')
    monkeypatch.setattr(certbot, 'obtain', limited)
    le_id, task_id = store.create(DATA, '1')
    assert run_task(task_id) == 'failed'
    assert LetsEncryptState.get().retry_at == retry
    assert store.dispatch_due(retry - timedelta(seconds=1)) == 0
    with pytest.raises(RoxywiConflictError, match='retry time'):
        store.action(le_id, 'retry', '1')
    with pytest.raises(RoxywiConflictError, match='retry time'):
        store.update(le_id, DATA | {'description': 'edit while rate limited'}, '1')
    assert LetsEncryptState.get().retry_at == retry
    monkeypatch.setattr(store, 'utc_now', lambda: retry)
    assert store.dispatch_due(retry) == 1


def test_expiry_failure_and_recovery_notifications_are_deduplicated(monkeypatch, bundle):
    from app.modules.service.le.le_notifications import check_notifications
    fake_issuer(monkeypatch, bundle)
    _, task_id = store.create(DATA, '1')
    run_task(task_id)
    now = store.utc_now()
    LetsEncryptState.update(not_after=now + timedelta(days=6), failures=3, status='failed', last_error='ACME unavailable').execute()
    assert check_notifications(now) == 2
    assert check_notifications(now) == 0
    assert ServiceNotification.select().count() == 2
    LetsEncryptState.update(status='active', failures=0).execute()
    assert check_notifications(now) == 1
    assert check_notifications(now) == 0


def test_dns_profile_and_draft_http_contract(monkeypatch):
    from flask import Flask
    from app.views.service import lets_encrypt_views as views, le_profile_views as profiles
    from app.modules.roxywi.error_handler import register_error_handlers
    api = Flask('le-release-contract')
    api.config['FLASK_PYDANTIC_VALIDATION_ERROR_RAISE'] = True
    register_error_handlers(api)
    group = ['1']
    monkeypatch.setattr(views, 'identity', lambda query: (group[0], 7))
    monkeypatch.setattr(profiles, 'identity', lambda query: (group[0], 7))
    monkeypatch.setattr(views, 'protect', lambda *args: None)
    api.add_url_rule('/profiles', endpoint='list_profiles', view_func=profiles.LetsEncryptDnsProfilesView().get)
    api.add_url_rule('/profiles', endpoint='add_profile', view_func=profiles.LetsEncryptDnsProfilesView().post, methods=['POST'])
    api.add_url_rule('/profiles/<int:profile_id>', endpoint='edit_profile', view_func=profiles.LetsEncryptDnsProfileView().put, methods=['PUT'])
    api.add_url_rule('/profiles/<int:profile_id>', endpoint='delete_profile', view_func=profiles.LetsEncryptDnsProfileView().delete, methods=['DELETE'])
    api.add_url_rule('/le', view_func=views.LetsEncryptView().post, methods=['POST'])
    client = api.test_client()
    data = dict(name='DNS account', provider='cloudflare', api_token='profile-secret', propagation_seconds=90)
    profile = client.post('/profiles', json=data)
    assert profile.status_code == 201
    profile_id = profile.json['id']
    assert profile.json['has_api_token'] and 'profile-secret' not in profile.text
    assert 'api_token' not in client.get('/profiles').json[0]
    assert client.post('/profiles', json=data | {'name': 'Other', 'api_token': 'token\ninvalid'}).status_code == 400
    draft = client.post('/le', json=DATA | {'dns_profile_id': profile_id, 'draft': True, 'api_token': None})
    assert draft.status_code == 201 and draft.json['tasks_ids'] == []
    assert InstallationTasks.select().count() == 0
    response = client.put(f'/profiles/{profile_id}', json=data | {'api_token': None, 'propagation_seconds': 120})
    assert response.status_code == 200 and response.json['revision'] == 2
    assert response.json['has_api_token']
    deletion = client.delete(f'/profiles/{profile_id}')
    assert deletion.status_code == 409 and 'used by a certificate' in deletion.json['error']
    group[0] = '2'
    assert client.get('/profiles').json == []
    assert client.put(f'/profiles/{profile_id}', json=data).status_code == 404
    assert client.delete(f'/profiles/{profile_id}').status_code == 404


def test_recovery_rejects_changed_target_address_before_reusing_progress(monkeypatch, bundle):
    fake_issuer(monkeypatch, bundle)
    le_id, task_id = store.create(DATA, '1')
    state = LetsEncryptState.get()
    _, fingerprint = certbot.inspect_bundle(bundle, DATA['domains'])
    state.deployment = json.dumps({'id': 'interrupted', 'phase': 'apply', 'targets': {
        '1': {'address': '192.0.2.1', 'settings': {}}, '2': {'address': '192.0.2.2', 'settings': {}}}})
    state.targets = json.dumps({'1': {'status': 'deployed', 'fingerprint': fingerprint, 'address': '192.0.2.1'}})
    state.save()
    Server.update(ip='192.0.2.99').where(Server.server_id == 1).execute()
    recovered = []
    monkeypatch.setattr(certbot, 'remote', lambda server, data: recovered.append(server.server_id))
    monkeypatch.setattr(certbot, 'obtain', lambda *args, **kwargs: pytest.fail('Recovery must precede new issuance'))
    assert run_task(task_id) == 'failed'
    state = LetsEncryptState.get()
    assert json.loads(state.deployment)['phase'] == 'rollback'
    assert json.loads(state.targets)['1']['status'] == 'rollback_failed'
    assert recovered == [2]  # Never write the old certificate to the changed address.


def test_imported_renewal_falls_back_safely_with_corrupt_cache(tmp_path, bundle, monkeypatch):
    from app.modules.service.le import le_legacy_renewal
    warnings = []
    monkeypatch.setattr(le_legacy_renewal.logger, 'warning', warnings.append)
    (tmp_path / 'imported-ari.json').write_text('{invalid json')
    now = datetime.now(timezone.utc)
    assert not le_legacy_renewal.due(bundle, tmp_path, now=now)
    assert le_legacy_renewal.due(bundle, tmp_path, now=now + timedelta(days=70))
    assert any('cache is invalid' in message for message in warnings)


def test_imported_renewal_uses_ari_window_and_retry_after(tmp_path, monkeypatch):
    from app.modules.service.le import le_legacy_renewal
    now = datetime.now(timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'example.com')])
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(128).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=89))
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256()))
    bundle = {'fullchain': certificate.public_bytes(serialization.Encoding.PEM).decode()}
    calls = []
    class Response:
        headers = {'Retry-After': '3600'}
        def __init__(self, url):
            self.url = url
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def raise_for_status(self):
            return None
        def json(self):
            if self.url.endswith('/directory'):
                return {'renewalInfo': 'https://acme.example.test/renewal-info'}
            return {'suggestedWindow': {'start': (now - timedelta(hours=2)).isoformat(),
                                         'end': (now - timedelta(hours=1)).isoformat()}}
    monkeypatch.setattr(le_legacy_renewal.requests, 'get', lambda url, **kwargs: calls.append(url) or Response(url))
    assert le_legacy_renewal.due(bundle, tmp_path, now=now)  # ARI can renew long before lifetime fallback.
    assert len(calls) == 2 and calls[-1].startswith('https://acme.example.test/renewal-info/')
    assert calls[-1].endswith('.AIA')  # Positive DER INTEGER 00:80, without base64 padding.
    assert le_legacy_renewal.due(bundle, tmp_path, now=now + timedelta(minutes=30))
    assert len(calls) == 2
    assert le_legacy_renewal.due(bundle, tmp_path, now=now + timedelta(hours=1))
    assert len(calls) == 4
    assert le_legacy_renewal.due(bundle, tmp_path, now=now + timedelta(days=90))
    assert len(calls) == 4  # Never query ARI for expired certificates.
