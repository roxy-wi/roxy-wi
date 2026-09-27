"""User actions across HTTP requests, durable state and operation execution."""
import importlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.db.db_model import (
    Backup, BackupSchedule, Cred, GitSetting, InstallationTasks, LetsEncrypt, LetsEncryptState,
    S3Backup, Server, UserGroups,
)
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.service import backup_scheduler


def s3_config(server_id=11):
    return dict(server_id=server_id, s3_server='https://s3.example.test', bucket='product-backups',
                access_key='synthetic-access', secret_key='synthetic-secret', time='weekly',
                description='Team backup')


def le_config():
    return dict(server_id=11, domains=['example.com'], type='cloudflare', email='admin@example.com',
                api_token='synthetic-dns-token', description='Product certificate', draft=True)


@pytest.mark.parametrize('kind', ['fs', 's3', 'git', 'le'])
def test_server_deletion_explains_dependencies_and_preserves_them(product_client, product, kind):
    if kind == 'fs':
        row = Backup.create(server_id='11', rserver='192.0.2.30', rpath='/backup', type='backup', time='weekly', cred_id=11)
    elif kind == 's3':
        row = S3Backup.create(**s3_config())
    elif kind == 'git':
        row = GitSetting.create(server_id=11, service_id=1, repo='git@example.test:configs', branch='main', time='daily', cred_id=11)
    else:
        result = product_client.post('/service/letsencrypt', json=le_config())
        assert result.status_code == 201, result.get_data(as_text=True)
        row = LetsEncrypt.get_by_id(result.json['id'])
    response = product_client.delete('/server/11')
    assert response.status_code == 409, response.get_data(as_text=True)
    assert 'first' in response.json['error'].lower()
    assert Server.get_by_id(11).hostname == 'Product HAProxy'
    assert type(row).get_by_id(row.get_id())


@pytest.mark.parametrize('reference', ['server', 'backup', 'git'])
def test_credentials_in_use_cannot_be_deleted(product_client, product, reference):
    if reference != 'server':
        Server.update(cred_id=0).execute()
    if reference == 'backup':
        Backup.create(server_id='11', rserver='192.0.2.30', rpath='/backup', type='backup', time='weekly', cred_id=11)
    if reference == 'git':
        GitSetting.create(server_id=11, service_id=1, repo='git@example.test:configs', branch='main', time='daily', cred_id=11)
    response = product_client.delete('/server/cred/11')
    assert response.status_code == 409, response.get_data(as_text=True)
    assert Cred.get_by_id(11).username == 'operator'
    assert 'synthetic' not in response.get_data(as_text=True).lower()


def test_duplicate_backup_and_schedule_edit_keep_one_configuration(product_client, product, monkeypatch):
    # A Wednesday keeps the hourly and weekly dates distinct even when CI runs
    # just before a real weekly boundary.
    monkeypatch.setattr(backup_scheduler, 'utc_now', lambda: datetime(2026, 9, 23, 12, 15))
    response = product_client.post('/api/server/backup/s3', json=s3_config())
    assert response.status_code == 202, response.get_data(as_text=True)
    backup_id = response.json['id']
    duplicate = product_client.post('/api/server/backup/s3', json=s3_config())
    assert duplicate.status_code == 409, duplicate.get_data(as_text=True)
    assert S3Backup.select().count() == BackupSchedule.select().count() == 1
    old_due = BackupSchedule.get().next_run_at
    updated = product_client.put(f'/api/server/backup/s3/{backup_id}', json=s3_config() | {'time': 'hourly'})
    assert updated.status_code == 202, updated.get_data(as_text=True)
    schedule = product_client.get(f'/api/server/backup/s3/{backup_id}').json['schedule']
    assert schedule['next_run_at'] and BackupSchedule.get().next_run_at < old_due
    assert BackupSchedule.select().count() == 1


def test_backup_transfer_failure_is_visible_and_config_remains_editable(product_client, product, monkeypatch):
    from app.modules.service import backup_execution
    response = product_client.post('/api/server/backup/s3', json=s3_config())
    assert response.status_code == 202, response.get_data(as_text=True)
    schedule = BackupSchedule.get()
    assert backup_scheduler.dispatch_due_backups(schedule.next_run_at) == 1
    task = InstallationTasks.get_by_id(BackupSchedule.get().active_task_id)

    def unavailable(*args, **kwargs):
        raise OSError('synthetic-secret: destination unavailable')

    monkeypatch.setattr(backup_execution, 'transfer_backup', unavailable)
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'failed'
    backup_scheduler.dispatch_due_backups(schedule.next_run_at)
    response = product_client.get(f'/api/server/backup/s3/{response.json["id"]}')
    assert response.status_code == 200
    assert response.json['schedule']['retry_at']
    assert S3Backup.select().count() == 1
    assert 'synthetic-secret' not in json.dumps(response.json['schedule'])
    edited = product_client.put(f'/api/server/backup/s3/{response.json["id"]}', json=s3_config() | {'time': 'daily'})
    assert edited.status_code == 202, edited.get_data(as_text=True)
    assert S3Backup.get().time == 'daily'


def test_old_backup_requires_cutover_and_is_not_duplicated(product_client, product):
    row = S3Backup.create(**s3_config())
    migration = importlib.import_module('app.modules.db.migrations.20260916000000_backup_schedules')
    migration.up()
    migration.up()
    state = product_client.get(f'/api/server/backup/s3/{row.id}').json['schedule']
    assert state['migration_required'] is True
    assert BackupSchedule.select().count() == 1
    response = product_client.put(f'/api/server/backup/s3/{row.id}', json=s3_config() | {'time': 'daily'})
    assert response.status_code == 409
    assert S3Backup.get_by_id(row.id).time == 'weekly'


def test_old_certificate_remains_visible_after_repeat_migration(product_client, product):
    row = LetsEncrypt.create(server_id=11, domains="['example.test']", email='admin@example.test',
                             type='cloudflare', api_key='', api_token='legacy-private-token', description='Old certificate')
    migration = importlib.import_module('app.modules.db.migrations.20260919000000_letsencrypt_state')
    migration.up()
    migration.up()
    response = product_client.get(f'/service/letsencrypt/{row.id}?recurse=True')
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.json['domains'] == ['example.test']
    assert response.json['state']['legacy_pending'] is True
    assert 'legacy-private-token' not in response.get_data(as_text=True)
    assert LetsEncryptState.select().count() == 1


def test_role_change_applies_to_an_already_open_session(product_client, product):
    assert product_client.get('/server/11').status_code == 200
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    response = product_client.delete('/server/11')
    assert response.status_code == 403, response.get_data(as_text=True)
    assert Server.get_by_id(11)


def test_group_admin_cannot_read_or_modify_another_teams_backup(product_client, product):
    UserGroups.update(user_role_id=2).where(UserGroups.user_id == product.admin.user_id).execute()
    other = S3Backup.create(**s3_config(22))
    for method in ('get', 'put', 'delete'):
        response = getattr(product_client, method)(f'/api/server/backup/s3/{other.id}', json=s3_config(11))
        assert response.status_code == 403, response.get_data(as_text=True)
        assert 'synthetic-secret' not in response.get_data(as_text=True)
    assert S3Backup.get_by_id(other.id).server_id == '22'


def test_unused_credentials_can_be_deleted(product_client, product):
    Server.update(cred_id=0).execute()
    assert product_client.delete('/server/cred/11').status_code == 204
    assert Cred.get_or_none(Cred.id == 11) is None
    assert product_client.delete('/server/cred/11').status_code == 404


def test_certificate_cleanup_unblocks_server_deletion_and_preserves_history(product_client, product, monkeypatch):
    from app.modules.server import server as server_module
    monkeypatch.setattr(server_module, 'subprocess', SimpleNamespace(run=lambda *args, **kwargs: None))
    created = product_client.post('/service/letsencrypt', json=le_config())
    assert created.status_code == 201
    le_id = created.json['id']
    deletion = product_client.delete(f'/service/letsencrypt/{le_id}')
    assert deletion.status_code == 202
    task = InstallationTasks.get_by_id(deletion.json['tasks_ids'][0])
    assert product_client.delete('/server/11').status_code == 409
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'completed'
    assert product_client.get(f'/service/letsencrypt/{le_id}').status_code == 404
    response = product_client.delete('/server/11')
    assert response.status_code == 204, response.get_data(as_text=True)
    assert InstallationTasks.get_by_id(task.id).status == 'completed'
    assert Server.get_or_none(Server.server_id == 11) is None


def test_partial_certificate_deployment_can_be_retried_without_duplicate_operations(product_client, product, monkeypatch):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from app.modules.service.le import le_certbot as certbot

    Server.create(server_id=33, hostname='Secondary', ip='192.0.2.33', group_id='1', master=11)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'example.com')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(days=80)).add_extension(
                       x509.SubjectAlternativeName([x509.DNSName('example.com')]), critical=False)
                   .sign(key, hashes.SHA256()))
    bundle = {'fullchain': certificate.public_bytes(serialization.Encoding.PEM).decode(),
              'key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()).decode()}
    calls = []

    def deploy(server, *_args, **_kwargs):
        calls.append(server.server_id)
        if server.server_id == 33 and calls.count(33) == 1:
            raise OSError('synthetic-dns-token: reload failed')

    monkeypatch.setattr(certbot, 'obtain', lambda *args, **kwargs: bundle)
    monkeypatch.setattr(certbot, 'deploy', deploy)
    monkeypatch.setattr(certbot, 'deployment_settings', lambda _server, name: {'pem_name': name})
    monkeypatch.setattr(certbot, 'remote', lambda _server, _data: {'finished': True})
    data = le_config() | {'draft': False}
    created = product_client.post('/service/letsencrypt', json=data)
    assert created.status_code == 202, created.get_data(as_text=True)
    assert product_client.post('/service/letsencrypt', json=data).status_code == 409
    assert InstallationTasks.select().count() == 1
    le_id = created.json['id']
    assert product_client.delete('/server/33').status_code == 409
    task = InstallationTasks.get_by_id(created.json['tasks_ids'][0])
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'failed'
    state = product_client.get(f'/service/letsencrypt/{le_id}').json['state']
    assert state['status'] == 'failed' and state['can_retry']
    assert state['targets']['11']['status'] == 'rolled_back'
    assert state['history'][0]['status'] == 'failed'
    assert 'synthetic-dns-token' not in json.dumps(state)
    retry = product_client.patch(f'/service/letsencrypt/{le_id}', json={'action': 'retry'})
    assert retry.status_code == 202, retry.get_data(as_text=True)
    assert product_client.patch(f'/service/letsencrypt/{le_id}', json={'action': 'retry'}).status_code == 409
    task = InstallationTasks.get_by_id(retry.json['tasks_ids'][0])
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'completed'
    state = product_client.get(f'/service/letsencrypt/{le_id}').json['state']
    assert state['status'] == 'active' and state['next_run_at']
    assert len(state['history']) == 2 and calls == [11, 33, 11, 33]
    assert LetsEncrypt.select().count() == 1
