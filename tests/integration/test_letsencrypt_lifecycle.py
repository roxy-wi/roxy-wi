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

from app.modules.db.db_model import LetsEncrypt, LetsEncryptState, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.roxywi.class_models import LetsEncryptRequest
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound
from app.modules.service.le import le_store as store, le_execution as execution, le_certbot as certbot


MODELS = [LetsEncrypt, LetsEncryptState, InstallationTasks, Server]
DATA = dict(server_id=1, domains=['example.com'], email='admin@example.com', type='cloudflare',
            api_key=None, api_token='private-dns-token', description='example certificate')


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    db = SqliteDatabase(tmp_path / 'le.db', pragmas={'journal_mode': 'wal', 'busy_timeout': 10000})
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path / 'lib'))
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
    monkeypatch.setattr(certbot, 'deploy', deploy or (lambda *args: None))


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


def test_failed_ha_target_retries_without_repeating_completed_target(monkeypatch, bundle):
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
    assert json.loads(state.targets)['1']['status'] == 'deployed'
    assert store.dispatch_due(state.retry_at) == 1
    assert run_task(LetsEncryptState.get().active_task_id) == 'completed'
    assert calls == [1, 2, 2]


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
    monkeypatch.setattr(certbot, 'deploy', lambda *args: None)
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
