import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
import threading
from uuid import uuid4

import pytest
from peewee import OperationalError, SqliteDatabase

from app.modules.db.db_model import Backup, S3Backup, BackupSchedule, InstallationTasks, Server
from app.modules.operations.queue import deserialize_operation_payload, recover_stale_operations
from app.modules.operations.worker import claim_operation, execute_operation
from app.modules.service import backup, backup_scheduler as scheduling, backup_execution as execution
from app.modules.service import backup_migration as cutover
from app.modules.roxywi.class_models import BackupRequest, S3BackupRequest
from app.modules.roxywi.exception import RoxywiConflictError


MODELS = [Backup, S3Backup, BackupSchedule, InstallationTasks, Server]
NOW = datetime(2026, 9, 16, 10, 30)


@pytest.fixture(autouse=True)
def backup_database(tmp_path, monkeypatch):
    database = SqliteDatabase(tmp_path / 'backups.db', pragmas={'journal_mode': 'wal', 'busy_timeout': 10000})
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path / 'lib'))
    monkeypatch.setenv('ROXYWI_BACKUP_TIMEZONE', 'UTC')
    monkeypatch.delenv('ROXYWI_BACKUP_HISTORY_RETENTION_DAYS', raising=False)
    with database.bind_ctx(MODELS, bind_refs=False, bind_backrefs=False):
        database.create_tables(MODELS)
        Server.create(server_id=1, hostname='source', ip='192.0.2.1', group_id='1')
        yield database
        database.close()


def config(kind='fs', **kwargs):
    if kind == 'fs':
        row = Backup.create(server_id='1', rserver='backup.test', rpath='/srv/backups',
                            type='backup', time='hourly', cred_id=1)
    else:
        row = S3Backup.create(server_id='1', s3_server='https://s3.test', bucket='configs',
                              access_key='private-access', secret_key='private-secret', time='hourly')
    schedule = BackupSchedule.create(kind=kind, backup_id=row.id, timezone='UTC',
                                     next_run_at=NOW - timedelta(days=5), **kwargs)
    return row, schedule


def test_missed_runs_coalesce_and_payload_contains_no_secrets():
    _, schedule = config('s3')
    assert scheduling.dispatch_due_backups(NOW) == 1
    assert scheduling.dispatch_due_backups(NOW) == 0
    schedule = BackupSchedule.get_by_id(schedule.id)
    task = InstallationTasks.get_by_id(schedule.active_task_id)
    assert task.operation_type == 'backup'
    assert schedule.next_run_at == datetime(2026, 9, 16, 11)
    assert set(deserialize_operation_payload(task.operation_payload)) == {'schedule_id', 'run_key'}
    assert 'private-' not in task.operation_payload


def test_parallel_schedulers_create_only_one_operation(backup_database):
    config()
    def dispatch(_):
        try:
            return scheduling.dispatch_due_backups(NOW)
        finally:
            backup_database.close()
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(dispatch, range(5))) == 1
    assert InstallationTasks.select().count() == 1


def test_busy_schedule_does_not_starve_other_due_backups():
    config()
    scheduling.dispatch_due_backups(NOW)
    other, _ = config('s3')
    assert scheduling.dispatch_due_backups(NOW, limit=1) == 1
    assert InstallationTasks.select().count() == 2


def test_failed_runs_retry_with_backoff_and_same_run_identity_then_resume_schedule():
    _, schedule = config()
    scheduling.dispatch_due_backups(NOW)
    clock = NOW
    run_keys = set()
    for failure in range(1, 4):
        schedule = BackupSchedule.get_by_id(schedule.id)
        task = InstallationTasks.get_by_id(schedule.active_task_id)
        run_keys.add(deserialize_operation_payload(task.operation_payload)['run_key'])
        InstallationTasks.update(status='failed').where(InstallationTasks.id == task.id).execute()
        assert scheduling.dispatch_due_backups(clock) == 0
        schedule = BackupSchedule.get_by_id(schedule.id)
        assert schedule.failures == failure
        if failure < 3:
            assert schedule.retry_at == clock + timedelta(seconds=60 * 2 ** (failure - 1))
            assert scheduling.dispatch_due_backups(schedule.retry_at - timedelta(seconds=1)) == 0
            clock = schedule.retry_at
            assert scheduling.dispatch_due_backups(clock) == 1
        else:
            assert schedule.retry_at is None
            assert scheduling.dispatch_due_backups(schedule.next_run_at) == 1
    assert len(run_keys) == 1


def test_native_worker_executes_once_and_history_is_completed(monkeypatch):
    config()
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    calls = []
    monkeypatch.setattr(execution, 'transfer_backup', lambda *args: calls.append(args))
    assert claim_operation(task.operation_id, task.id) == (True, 'running')
    assert execute_operation(task.operation_id, task.id) == 'completed'
    assert execute_operation(task.operation_id, task.id) == 'completed'
    assert len(calls) == 1
    scheduling.dispatch_due_backups(NOW)
    assert BackupSchedule.get().active_task_id is None


def test_worker_errors_are_recorded_without_secret_exception_text(monkeypatch):
    config('s3')
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    def fail(*_args):
        raise RuntimeError('credential=private-secret&access_key=private-access')
    monkeypatch.setattr(execution, 'transfer_backup', fail)
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'failed'
    assert 'private-' not in InstallationTasks.get().error
    assert 'RuntimeError' in InstallationTasks.get().error


@pytest.mark.parametrize('fail', [False, True])
def test_recovered_delivery_waits_for_running_transfer_and_does_not_repeat(backup_database, monkeypatch, fail):
    config()
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    started, release = threading.Event(), threading.Event()
    calls = []
    def transfer(*args):
        calls.append(args)
        started.set()
        assert release.wait(10)
        if fail:
            raise OSError('Transfer failed')
    monkeypatch.setattr(execution, 'transfer_backup', transfer)
    def execute():
        try:
            return execute_operation(task.operation_id, task.id)
        finally:
            backup_database.close()
    claim_operation(task.operation_id, task.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute)
        assert started.wait(10)
        InstallationTasks.update(updated_at=datetime(2000, 1, 1)).where(InstallationTasks.id == task.id).execute()
        assert recover_stale_operations() == 1
        assert claim_operation(task.operation_id, task.id) == (True, 'running')
        second = pool.submit(execute)
        release.set()
        assert first.result(10) == second.result(10) == ('failed' if fail else 'completed')
    assert len(calls) == 1


def test_config_and_receipt_are_atomic_and_api_contract_is_preserved(monkeypatch):
    monkeypatch.setattr(backup.ssh_mod, 'return_ssh_keys_path', lambda *_args: {})
    monkeypatch.setattr(backup.roxywi_common, 'get_jwt_token_claims', lambda: {})
    monkeypatch.setattr(backup.roxywi_common, 'logging', lambda *_args, **_kwargs: None)
    data = BackupRequest(server_id=1, cred_id=1, rserver='192.0.2.2', rpath='/backups', type='backup', time='daily')
    response, status = backup.create_backup(data, True)
    assert status == 202
    assert InstallationTasks.get_by_id(response['tasks_ids'][0]).status == 'completed'
    row = Backup.get_by_id(response['id'])
    assert BackupSchedule.get().legacy_pending is False
    assert BackupSchedule.get().next_run_at > scheduling.utc_now()
    backup.update_backup(data.model_copy(update={'time': 'weekly'}), row.id)
    assert Backup.get_by_id(row.id).time == 'weekly'
    backup.delete_backup(data, row.id)
    assert BackupSchedule.select().count() == Backup.select().count() == 0
    monkeypatch.setattr(backup, '_schedule_receipt', lambda *_args: (_ for _ in ()).throw(RuntimeError('DB failure')))
    with pytest.raises(RuntimeError):
        backup.create_backup(data, True)
    assert Backup.select().count() == BackupSchedule.select().count() == 0


@pytest.mark.parametrize('kind', ['fs', 's3'])
def test_queued_run_or_pending_migration_blocks_edit_and_delete(kind):
    row, schedule = config(kind, legacy_pending=True)
    with scheduling.transaction(), pytest.raises(RoxywiConflictError):
        scheduling.ensure_editable(kind, row.id)
    assert scheduling.dispatch_due_backups(NOW) == 0
    BackupSchedule.update(legacy_pending=False).execute()
    scheduling.dispatch_due_backups(NOW)
    with scheduling.transaction(), pytest.raises(RoxywiConflictError):
        scheduling.ensure_editable(kind, row.id)


def test_migration_is_repeatable_and_never_reactivates_a_migrated_schedule():
    row, schedule = config()
    schedule.delete_instance()
    migration = importlib.import_module('app.modules.db.migrations.20260916000000_backup_schedules')
    migration.up()
    assert BackupSchedule.get().legacy_pending
    BackupSchedule.update(legacy_pending=False).execute()
    migration.up()
    assert BackupSchedule.select().count() == 1
    assert BackupSchedule.get().legacy_pending is False


def test_cutover_preserves_user_cron_and_is_repeatable(monkeypatch):
    config(legacy_pending=True)
    user_jobs = 'MAILTO=ops@example.test\n0 1 * * * /usr/local/bin/user-backup\n'
    crontab = [user_jobs + '#Ansible: Roxy-WI Backup configs for server 192.0.2.1 hap_config\n@daily rsync configs\n']
    monkeypatch.setattr(cutover, '_require_original_host', lambda _config: None)
    monkeypatch.setattr(cutover.psutil, 'process_iter', lambda *_args: [])
    monkeypatch.setattr(cutover, '_read_crontab', lambda: crontab[0])
    def write(*_args, input=None):
        crontab[0] = input
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cutover, '_crontab', write)
    assert cutover.migrate_legacy_cron() == (1, 1)
    assert crontab[0] == user_jobs
    assert cutover.migrate_legacy_cron() == (0, 0)


def test_cutover_failure_does_not_enable_schedules(monkeypatch):
    config(legacy_pending=True)
    monkeypatch.setattr(cutover, '_require_original_host', lambda _config: None)
    monkeypatch.setattr(cutover.psutil, 'process_iter', lambda *_args: [])
    monkeypatch.setattr(cutover, '_read_crontab', lambda: '#Ansible: Roxy-WI S3 Backup configs for server x b hap_config\n@daily s3cmd\n')
    monkeypatch.setattr(cutover, '_crontab', lambda *_args, **_kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match='remain paused'):
        cutover.migrate_legacy_cron()
    assert BackupSchedule.get().legacy_pending


def test_concurrent_s3_creation_cannot_duplicate_schedule(backup_database, monkeypatch):
    monkeypatch.setattr(backup.roxywi_common, 'get_jwt_token_claims', lambda: {})
    monkeypatch.setattr(backup.roxywi_common, 'logging', lambda *_args, **_kwargs: None)
    data = S3BackupRequest(server_id=1, s3_server='https://s3.test', bucket='configs',
                           access_key='test-key', secret_key='test-secret', time='daily')
    def create(_):
        try:
            return backup.create_s3_backup(data, True)[1]
        except RoxywiConflictError:
            return 409
        finally:
            backup_database.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(create, range(4))) == [202, 409, 409, 409]
    assert S3Backup.select().count() == BackupSchedule.select().count() == 1
    row = S3Backup.get()
    backup.update_s3_backup(data.model_copy(update={'bucket': 'new-configs'}), row.id)
    assert S3Backup.get().bucket == 'new-configs'
    backup.delete_s3_backup(data, row.id)
    assert S3Backup.select().count() == BackupSchedule.select().count() == 0


def test_missing_server_does_not_block_other_schedules(monkeypatch):
    config()
    Server.delete().execute()
    config('s3')
    assert scheduling.dispatch_due_backups(NOW) == 2
    task = InstallationTasks.select().first()
    claim_operation(task.operation_id, task.id)
    assert execute_operation(task.operation_id, task.id) == 'failed'


def test_source_selection_and_snapshot_use_configured_directories(tmp_path, monkeypatch):
    from app.modules.service import backup_transfer
    folder = tmp_path / 'configs'
    folder.mkdir()
    monkeypatch.setenv('ROXYWI_HAPROXY_SAVE_CONFIGS_DIR', str(folder))
    monkeypatch.setenv('ROXYWI_NGINX_SAVE_CONFIGS_DIR', str(tmp_path / 'missing-nginx'))
    monkeypatch.setenv('ROXYWI_APACHE_SAVE_CONFIGS_DIR', str(tmp_path / 'missing-apache'))
    monkeypatch.setenv('ROXYWI_KEEPALIVED_SAVE_CONFIGS_DIR', str(tmp_path / 'missing-keepalived'))
    server = Server.get_by_id(1)
    with pytest.raises(ValueError, match='No saved configurations'):
        backup_transfer.source_files(server)
    selected = folder / '192.0.2.1-2026.cfg'
    selected.write_text('config')
    (folder / '192.0.2.10-2026.cfg').write_text('other server')
    seen = []
    def upload(_config, _server, files):
        paths = files['hap_config']
        assert len(paths) == 1
        assert paths[0] != selected
        seen.append(paths[0])
        selected.write_text('changed during transfer')
        assert paths[0].read_text() == 'config'
    monkeypatch.setattr(backup_transfer, 'upload_s3', upload)
    row, _ = config('s3')
    backup_transfer.transfer_backup('s3', row, 'run-key')
    assert not seen[0].exists()


def history_task(**kwargs):
    values = dict(service_name='Backup history', operation_type='backup',
                  operation_id=str(uuid4()), status='completed',
                  start_date=NOW - timedelta(days=60), finish_date=NOW - timedelta(days=31))
    values.update(kwargs)
    return InstallationTasks.create(**values)


def test_history_cleanup_preserves_active_latest_and_other_operations():
    _, schedule = config()
    active = history_task(status='failed')
    latest = history_task()
    BackupSchedule.update(active_task_id=active.id, last_task_id=latest.id).where(
        BackupSchedule.id == schedule.id
    ).execute()
    config('s3')  # NULL references must not exclude every row from the cleanup.
    protected = [active, latest]
    protected += [history_task(status=status) for status in ('created', 'published', 'running')]
    protected += [history_task(operation_type=kind) for kind in ('ansible', None)]
    protected += [history_task(finish_date=NOW - timedelta(days=30)),
                  history_task(finish_date=NOW - timedelta(days=1))]
    history_task()
    history_task(status='failed')
    assert scheduling.cleanup_backup_history(NOW) == 2
    assert set(row.id for row in InstallationTasks.select()) == {row.id for row in protected}
    assert scheduling.cleanup_backup_history(NOW) == 0
    assert scheduling.schedule_state('fs', schedule.backup_id)['last_status'] == 'completed'


def test_history_cleanup_keeps_pending_retry_and_releases_deleted_schedule_history():
    _, schedule = config()
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    InstallationTasks.update(status='failed', finish_date=NOW - timedelta(days=31)).execute()
    assert scheduling.cleanup_backup_history(NOW) == 0
    scheduling.dispatch_due_backups(NOW)
    schedule = BackupSchedule.get_by_id(schedule.id)
    assert schedule.active_task_id is None
    assert schedule.failures == 1
    assert schedule.retry_at == NOW + timedelta(seconds=60)
    assert scheduling.cleanup_backup_history(NOW) == 0
    assert scheduling.dispatch_due_backups(schedule.retry_at) == 1
    retry = InstallationTasks.select().where(InstallationTasks.id != task.id).get()
    assert deserialize_operation_payload(retry.operation_payload) == deserialize_operation_payload(task.operation_payload)
    assert scheduling.cleanup_backup_history(NOW) == 1
    # A removed schedule no longer pins its last result; its running task is
    # still protected by status even if the schedule disappeared independently.
    BackupSchedule.delete().execute()
    assert scheduling.cleanup_backup_history(NOW) == 0
    InstallationTasks.update(status='completed', finish_date=NOW - timedelta(days=31)).execute()
    assert scheduling.cleanup_backup_history(NOW) == 1


@pytest.mark.parametrize('setting, deleted', [(None, 1), ('1', 1), ('90', 0), ('0', 0)])
def test_history_retention_configuration(monkeypatch, setting, deleted):
    if setting is not None:
        monkeypatch.setenv('ROXYWI_BACKUP_HISTORY_RETENTION_DAYS', setting)
    history_task()
    assert scheduling.cleanup_backup_history(NOW) == deleted


@pytest.mark.parametrize('setting', ['-1', 'invalid'])
def test_invalid_history_retention_does_not_delete_records(monkeypatch, setting):
    monkeypatch.setenv('ROXYWI_BACKUP_HISTORY_RETENTION_DAYS', setting)
    history_task()
    with pytest.raises(ValueError):
        scheduling.cleanup_backup_history(NOW)
    assert InstallationTasks.select().count() == 1


def test_history_cleanup_is_bounded_and_resumable():
    for _ in range(5):
        history_task()
    assert scheduling.cleanup_backup_history(NOW, batch_size=2, max_batches=2) == 4
    assert InstallationTasks.select().count() == 1
    assert scheduling.cleanup_backup_history(NOW, batch_size=2, max_batches=2) == 1
    assert scheduling.cleanup_backup_history(NOW) == 0


def test_history_cleanup_rechecks_schedule_references_before_delete(monkeypatch):
    _, schedule = config()
    task = history_task()
    delete = InstallationTasks.delete
    def protect_then_delete():
        BackupSchedule.update(last_task_id=task.id).where(BackupSchedule.id == schedule.id).execute()
        return delete()
    monkeypatch.setattr(InstallationTasks, 'delete', protect_then_delete)
    assert scheduling.cleanup_backup_history(NOW) == 0
    assert InstallationTasks.get_by_id(task.id).status == 'completed'


def test_parallel_cleanup_and_dispatch_preserve_the_retry(backup_database):
    config()
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    InstallationTasks.update(status='failed', finish_date=NOW - timedelta(days=31)).execute()
    for _ in range(20):
        history_task()
    def run(cleanup):
        try:
            if cleanup:
                return scheduling.cleanup_backup_history(NOW, batch_size=3)
            scheduling.dispatch_due_backups(NOW)
            return 0
        finally:
            backup_database.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(run, [True, False, True, False])) == 20
    assert InstallationTasks.get().id == task.id
    assert BackupSchedule.get().failures == 1
    assert BackupSchedule.get().retry_at == NOW + timedelta(seconds=60)


def test_completed_schedule_receipts_are_included_in_retention(monkeypatch):
    monkeypatch.setattr(backup.roxywi_common, 'get_jwt_token_claims', lambda: {})
    task_id = backup._schedule_receipt('s3', 1, 'deleted')
    task = InstallationTasks.get_by_id(task_id)
    assert task.operation_id is None  # A receipt must never enter the outbox.
    assert scheduling.cleanup_backup_history(task.finish_date + timedelta(days=31)) == 1


def test_removed_operation_delivery_is_acknowledged_without_execution(monkeypatch):
    from app.modules.operations import worker as operations
    from app.modules.operations.queue import OperationQueueSettings
    task = history_task()
    assert scheduling.cleanup_backup_history(NOW) == 1
    assert claim_operation(task.operation_id, task.id) == (False, 'missing')
    assert execute_operation(task.operation_id, task.id) == 'missing'
    worker = operations.OperationWorker(OperationQueueSettings('broker', 5672, '/', 'test', 'test'))
    acks = []
    def basic_get(**_kwargs):
        worker._stop_event.set()
        return SimpleNamespace(delivery_tag=1), None, json.dumps({
            'operation_id': task.operation_id, 'task_id': task.id,
        }).encode()
    channel = SimpleNamespace(basic_get=basic_get, basic_ack=acks.append)
    connection = SimpleNamespace(is_open=True, channel=lambda: channel, close=lambda: None)
    monkeypatch.setattr(operations.pika, 'BlockingConnection', lambda _: connection)
    monkeypatch.setattr(operations, 'declare_operation_topology', lambda *_: None)
    monkeypatch.setattr(operations, 'set_process_heartbeat_status', lambda *_: None)
    monkeypatch.setattr(operations, 'execute_operation', lambda *_: pytest.fail('Removed task was executed'))
    worker.consume_once()
    assert acks == [1]


def test_claim_database_errors_still_propagate(monkeypatch):
    def unavailable(*_args):
        raise OperationalError('Database unavailable')
    monkeypatch.setattr(InstallationTasks, 'get_or_none', unavailable)
    with pytest.raises(OperationalError, match='Database unavailable'):
        claim_operation('removed-task', 1)


@pytest.mark.parametrize('reuse_id', [False, True])
def test_recovered_backup_waiter_does_not_execute_a_removed_or_replaced_task(monkeypatch, reuse_id):
    config()
    scheduling.dispatch_due_backups(NOW)
    task = InstallationTasks.get()
    @contextmanager
    def wait_for_lock(_schedule_id):
        InstallationTasks.update(status='completed', finish_date=NOW - timedelta(days=31)).execute()
        BackupSchedule.update(active_task_id=None, last_task_id=None).execute()
        assert scheduling.cleanup_backup_history(NOW) == 1
        if reuse_id:
            history_task(id=task.id, status='running')
        yield
    monkeypatch.setattr(execution, 'backup_lock', wait_for_lock)
    monkeypatch.setattr(execution, 'transfer_backup', lambda *_: pytest.fail('Stale worker transferred files'))
    assert execution.execute_backup(task) == 'missing'
    if reuse_id:
        replacement = InstallationTasks.get_by_id(task.id)
        assert replacement.operation_id != task.operation_id
        assert replacement.status == 'running'
        assert claim_operation(task.operation_id, task.id) == (False, 'missing')


def test_history_cleanup_scheduler_job_runs_and_closes_connection(monkeypatch):
    jobs = importlib.import_module('app.jobs')
    job = jobs.scheduler.get_job('backup_history_retention')
    assert job.trigger.interval == timedelta(hours=1)
    closed = []
    monkeypatch.setattr(jobs, 'close_database_connection', lambda: closed.append(True))
    monkeypatch.setattr(scheduling, 'utc_now', lambda: NOW)
    history_task()
    assert jobs.run_backup_history_retention() == 1
    assert closed == [True]
    def unavailable():
        raise OperationalError('Database unavailable')
    monkeypatch.setattr(scheduling, 'cleanup_backup_history', unavailable)
    with pytest.raises(OperationalError):
        jobs.run_backup_history_retention()
    assert closed == [True, True]
