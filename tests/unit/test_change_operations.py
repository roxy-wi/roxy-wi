import importlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest
from flask import g, has_request_context
from peewee import SqliteDatabase

from app.modules.change import operations, service, automation
from app.modules.common.execution_context import group_id, group_settings
from app.modules.common.time import utc_now
from app.modules.db import change as change_sql, sql
from app.modules.db.db_model import (
    ConfigChange, ConfigChangeTarget, ConfigChangeEvent, ConfigChangeDelivery,
    InstallationTasks, Server, User, Groups, UserGroups, close_database_connection,
)
from app.modules.operations import queue, worker
from app.modules.roxywi.exception import RoxywiConflictError


@pytest.fixture
def change(tmp_path, monkeypatch):
    for module in (operations, service, automation):
        monkeypatch.setattr(module, 'require_feature', lambda *_a: None)
    monkeypatch.setenv('ROXYWI_LIB_PATH', str(tmp_path))
    server = Server.create(hostname='queued-change', ip='192.0.2.246', group_id='1', haproxy=1)
    draft = tmp_path / 'draft.cfg'
    before = tmp_path / 'before.cfg'
    draft.write_text('global\n  daemon\n', encoding='utf-8')
    before.write_text('global\n', encoding='utf-8')
    change = ConfigChange.create(
        server_id=server.server_id, group_id=1, user_id=1, service='haproxy',
        action='reload', status='validated', title='Queued change', remote_path='/etc/haproxy/haproxy.cfg',
        draft_path=str(draft), rollback_path=str(before),
    )
    ConfigChangeTarget.create(
        change=change, server_id=server.server_id, server_ip=server.ip,
        server_name=server.hostname, role='standalone', position=0,
        status='validated', rollback_path=str(before),
    )
    yield change
    ConfigChangeDelivery.delete().where(ConfigChangeDelivery.change == change.id).execute()
    ConfigChangeEvent.delete().where(ConfigChangeEvent.change == change.id).execute()
    ConfigChangeTarget.delete().where(ConfigChangeTarget.change == change.id).execute()
    ConfigChange.delete().where(ConfigChange.id == change.id).execute()
    InstallationTasks.delete().where(InstallationTasks.service_name.startswith(f'Change #{change.id}:')).execute()
    Server.delete().where(Server.server_id == server.server_id).execute()


def queued_task(change, action='deploy', **kwargs):
    result = operations.enqueue(change.id, action, change.group_id, 1, **kwargs)
    return InstallationTasks.get_by_id(result.active_task_id)


def run(task):
    assert worker.claim_operation(task.operation_id, task.id) == (True, 'running')
    return worker.execute_operation(task.operation_id, task.id)


@pytest.fixture
def workflow_group(change):
    group = Groups.create(name='queued-workflow-group')
    UserGroups.create(user_id=1, user_group_id=group.group_id, user_role_id=1)
    ConfigChange.update(group_id=group.group_id).where(ConfigChange.id == change.id).execute()
    Server.update(group_id=str(group.group_id)).where(Server.server_id == change.server_id).execute()
    change.group_id = group.group_id
    yield group.group_id
    UserGroups.delete().where(UserGroups.user_group_id == group.group_id).execute()
    Groups.delete_by_id(group.group_id)


def test_queue_is_atomic_and_blocks_duplicate_and_metadata_writes(change):
    task = queued_task(change)
    assert task.operation_payload.startswith('fernet:')
    assert change_sql.get_change(change.id).status == 'validated'
    with pytest.raises(RoxywiConflictError):
        queued_task(change)
    with pytest.raises(RoxywiConflictError):
        with operations.locked_change(change.id, 1):
            pytest.fail('Cannot edit a queued change')
    assert InstallationTasks.select().where(InstallationTasks.id == task.id).count() == 1


def test_two_requests_queue_only_one_command(change):
    barrier = Barrier(2)

    def enqueue():
        try:
            barrier.wait()
            return operations.enqueue(change.id, 'deploy', 1, 1).active_task_id
        except RoxywiConflictError:
            return None
        finally:
            close_database_connection()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: enqueue(), range(2)))
    assert len([item for item in results if item]) == 1


def test_failed_task_creation_rolls_back_schedule_claim(change, monkeypatch):
    change_sql.update_change(change.id, status='scheduled', scheduled_at=utc_now() - timedelta(minutes=1))
    monkeypatch.setattr(operations, 'serialize_operation_payload', lambda *_: (_ for _ in ()).throw(RuntimeError('DB unavailable')))
    with pytest.raises(RuntimeError):
        operations.enqueue(change.id, 'deploy', 1, 1, scheduled=True)
    current = change_sql.get_change(change.id)
    assert current.status == 'scheduled' and current.active_task_id is None


def test_worker_runs_without_http_and_acknowledges_redelivery(change, monkeypatch):
    calls = []

    def deploy(change_id, active_group, actor_id):
        assert not has_request_context()
        assert group_id.get() == active_group == 1
        calls.append((change_id, actor_id))
        return change_sql.update_change(change_id, status='deployed')

    monkeypatch.setattr(service, 'deploy_change', deploy)
    task = queued_task(change)
    assert run(task) == 'completed'
    assert operations.execute(task) == 'completed'
    assert calls == [(change.id, 1)]
    assert group_id.get() is None
    current = change_sql.get_change(change.id)
    assert current.active_task_id is None and current.last_task_id == task.id
    assert service.serialize_change(current)['operation']['active'] is False


@pytest.mark.parametrize('started', [False, True])
def test_expired_worker_lease_never_replays_started_remote_work(change, monkeypatch, started):
    calls = []
    monkeypatch.setattr(service, 'deploy_change', lambda *args: calls.append(args))
    task = queued_task(change)
    payload = queue.deserialize_operation_payload(task.operation_payload)
    payload['started'] = started
    InstallationTasks.update(
        status='running', updated_at=utc_now() - timedelta(hours=1),
        operation_payload=queue.serialize_operation_payload(payload),
    ).where(InstallationTasks.id == task.id).execute()
    if started:
        change_sql.update_change(change.id, status='deploying')
        ConfigChangeTarget.update(status='deploying').where(ConfigChangeTarget.change == change.id).execute()
    assert queue.recover_stale_operations() >= 1
    assert run(task) == ('failed' if started else 'completed')
    assert len(calls) == (0 if started else 1)
    current = change_sql.get_change(change.id)
    assert current.active_task_id is None
    if started:
        assert current.status == 'deployment_interrupted'
        assert change_sql.list_targets(change.id)[0].status == 'deployment_interrupted'


def test_running_task_is_not_manually_recoverable_after_five_minutes(change):
    queued_task(change)
    ConfigChange.update(status='deploying', updated_at=utc_now() - timedelta(hours=1)).where(ConfigChange.id == change.id).execute()
    assert not service.is_recoverable(change_sql.get_change(change.id))
    with pytest.raises(RoxywiConflictError):
        service.recover_change(change.id, 1)


def test_worker_rechecks_maintenance_window_after_waiting_in_queue(change, monkeypatch):
    change_sql.update_change(
        change.id, status='scheduled', scheduled_at=utc_now() - timedelta(minutes=1),
        maintenance_window_end=utc_now() - timedelta(seconds=1),
    )
    monkeypatch.setattr(service, 'deploy_change', lambda *_: pytest.fail('Window has closed'))
    task = queued_task(change, scheduled=True)
    assert run(task) == 'failed'
    assert change_sql.get_change(change.id).status == 'schedule_missed'
    assert change_sql.get_change(change.id).active_task_id is None


def test_scheduled_deployment_uses_the_user_who_scheduled_it(change, monkeypatch):
    from app.modules.change.schemas import ConfigChangeSchedule
    # A permitted administrator can schedule a change whose author has left.
    ConfigChange.update(user_id=999999).where(ConfigChange.id == change.id).execute()
    automation.schedule_change(
        change.id, ConfigChangeSchedule(scheduled_at=utc_now() + timedelta(minutes=1)),
        change.group_id, actor_id=1,
    )
    change_sql.update_change(change.id, scheduled_at=utc_now() - timedelta(seconds=1))
    assert automation.run_due_scheduled_changes() == {'queued': 1, 'missed': 0, 'failed': 0}
    current = change_sql.get_change(change.id)
    task = InstallationTasks.get_by_id(current.active_task_id)
    calls = []
    monkeypatch.setattr(service, 'deploy_change', lambda *args: calls.append(args))
    assert run(task) == 'completed'
    assert calls == [(change.id, change.group_id, 1)]


@pytest.mark.parametrize('revoke', ['user', 'service', 'group', 'address'])
def test_access_and_server_identity_are_rechecked_before_ssh(change, monkeypatch, revoke):
    task = queued_task(change)
    actor = User.get_by_id(1)
    try:
        if revoke == 'user':
            User.update(enabled=0).where(User.user_id == 1).execute()
        elif revoke == 'service':
            User.update(user_services='2 3').where(User.user_id == 1).execute()
        elif revoke == 'group':
            Server.update(group_id='999').where(Server.server_id == change.server_id).execute()
        else:
            Server.update(ip='192.0.2.247').where(Server.server_id == change.server_id).execute()
        monkeypatch.setattr(service, 'deploy_change', lambda *_: pytest.fail('Access was revoked'))
        assert run(task) == 'failed'
        assert change_sql.get_change(change.id).active_task_id is None
    finally:
        User.update(enabled=actor.enabled, user_services=actor.user_services).where(User.user_id == 1).execute()


def test_failure_recovers_domain_state_and_does_not_log_sensitive_output(change, monkeypatch):
    def deploy(*_):
        change_sql.update_change(change.id, status='deploying')
        raise RuntimeError('password=do-not-log-me')

    monkeypatch.setattr(service, 'deploy_change', deploy)
    messages = []
    monkeypatch.setattr(operations.logger, 'error', messages.append)
    task = queued_task(change)
    assert run(task) == 'failed'
    assert change_sql.get_change(change.id).status == 'deployment_interrupted'
    assert 'do-not-log-me' not in str(messages) + InstallationTasks.get_by_id(task.id).error


def test_api_returns_202_and_task_id_without_running_deploy(change, app, monkeypatch):
    from app.routes.change import routes
    monkeypatch.setattr(routes.roxywi_auth, 'is_access_permit_to_service', lambda *_: True)
    monkeypatch.setattr(service, 'deploy_change', lambda *_: pytest.fail('Web must not deploy'))
    with app.test_request_context('/changes/api/1/deploy', method='POST'):
        g.user_params = {'user_id': 1, 'group_id': 1, 'role': 1}
        response, status = routes.deploy_change.__wrapped__(change.id)
    assert status == 202
    data = response.get_json()
    assert data['status'] == 'accepted'
    assert data['tasks_ids'] == [data['data']['operation']['id']]
    assert data['data']['operation']['active'] is True


def test_explicit_background_group_settings_are_isolated(app, monkeypatch):
    from app.modules.db.db_model import Setting
    calls = []

    class Query:
        def where(self, expression):
            calls.append(expression.rhs.rhs)
            return self

        def execute(self):
            return []

    monkeypatch.setattr(Setting, 'select', lambda: Query())
    with app.app_context():
        g.user_params = {'group_id': 2}
        with group_settings(7):
            sql.get_setting('haproxy_config_path')
            sql.get_setting('haproxy_config_path', group_id=8)
        sql.get_setting('haproxy_config_path')
    assert calls == [7, 8, 2]
    assert group_id.get() is None


def test_change_operations_migration_is_repeatable(tmp_path):
    database = SqliteDatabase(tmp_path / 'migration.db')
    with database.bind_ctx([ConfigChange], bind_refs=False, bind_backrefs=False):
        database.execute_sql('CREATE TABLE config_changes (id INTEGER PRIMARY KEY, status TEXT)')
        database.execute_sql("INSERT INTO config_changes VALUES (1, 'deployed')")
        migration = importlib.import_module('app.modules.db.migrations.20260922000000_change_operations')
        migration.up()
        migration.up()
        assert database.execute_sql('SELECT status, active_task_id, last_task_id, scheduled_by FROM config_changes').fetchone() == ('deployed', None, None, None)
    database.close()


@pytest.mark.parametrize('mode', ['rolling', 'parallel', 'promotion'])
def test_real_workflow_through_worker_validate_deploy_drift_and_rollback(change, workflow_group, monkeypatch, mode):
    """Only remote IO and version storage are faked; domain transitions are real."""
    ConfigChange.update(
        status='draft', execution_mode='parallel' if mode == 'parallel' else 'rolling',
        health_check_mode='none', batch_size=3 if mode == 'parallel' else 1,
        manual_promotion=int(mode == 'promotion'),
    ).where(ConfigChange.id == change.id).execute()
    ConfigChangeTarget.update(role='master', position=2).where(ConfigChangeTarget.change == change.id).execute()
    slaves = []
    remote = {'192.0.2.246': 'global\n'}
    for index in (1, 2):
        server = Server.create(
            hostname=f'operation-slave-{index}', ip=f'192.0.2.{247 + index}',
            group_id=str(workflow_group), haproxy=1, master=change.server_id,
        )
        slaves.append(server)
        remote[server.ip] = 'global\n'
        ConfigChangeTarget.create(
            change=change, server_id=server.server_id, server_ip=server.ip,
            server_name=server.hostname, role='slave', position=index - 1,
            rollback_path=change.rollback_path,
        )

    def assert_context():
        assert not has_request_context()
        assert group_id.get() == workflow_group != 1

    def get_config(ip, path, **_kwargs):
        assert_context()
        Path(path).write_text(remote[ip], encoding='utf-8')

    def upload(ip, path, *_args, **_kwargs):
        assert_context()
        remote[ip] = Path(path).read_text(encoding='utf-8')
        return 'haproxy'

    def validate(*_args, **_kwargs):
        assert_context()
        return 'Configuration is valid'

    monkeypatch.setattr(service.config_mod, 'get_config', get_config)
    monkeypatch.setattr(service.config_mod, 'upload_and_restart', upload)
    monkeypatch.setattr(service.config_mod, 'validate_candidate_config', validate)
    monkeypatch.setattr(service.config_mod, 'normalize_config_file', lambda *_: None)
    monkeypatch.setattr(service, '_is_service_active', lambda *_: True)
    monkeypatch.setattr(service, '_save_successful_version', lambda *_: None)
    try:
        assert run(queued_task(change, 'validate')) == 'completed'
        assert change_sql.get_change(change.id).status == 'validated'
        assert run(queued_task(change)) == 'completed'
        if mode == 'promotion':
            for _ in range(2):
                assert change_sql.get_change(change.id).status == 'awaiting_promotion'
                assert run(queued_task(change, 'promote')) == 'completed'
        assert change_sql.get_change(change.id).status == 'deployed'
        assert all(value == 'global\n  daemon\n' for value in remote.values())
        assert run(queued_task(change, 'drift')) == 'completed'
        assert change_sql.get_change(change.id).drift_status == 'in_sync'
        assert run(queued_task(change, 'rollback')) == 'completed'
        assert change_sql.get_change(change.id).status == 'rolled_back'
        assert all(value == 'global\n' for value in remote.values())
    finally:
        Server.delete().where(Server.server_id.in_([server.server_id for server in slaves])).execute()


def test_corrupt_payload_finishes_and_releases_change(change):
    task = queued_task(change)
    InstallationTasks.update(operation_payload='invalid-payload').where(InstallationTasks.id == task.id).execute()
    assert run(task) == 'failed'
    assert change_sql.get_change(change.id).active_task_id is None


def test_metadata_api_rejects_change_while_queued(change, app, monkeypatch):
    from app.routes.change import routes
    queued_task(change)
    monkeypatch.setattr(routes.roxywi_auth, 'is_access_permit_to_service', lambda *_: True)
    with app.test_request_context('/changes/api/1/cancel', method='POST'):
        g.user_params = {'user_id': 1, 'group_id': 1, 'role': 1}
        _response, status = routes.cancel_change.__wrapped__(change.id)
    assert status == 409
    assert change_sql.get_change(change.id).status == 'validated'


def test_pause_and_cancel_pending_pause_do_not_launch_another_worker(change, app, monkeypatch):
    from app.routes.change import routes
    task = queued_task(change)
    change_sql.update_change(change.id, status='deploying')
    monkeypatch.setattr(routes.roxywi_auth, 'is_access_permit_to_service', lambda *_: True)
    monkeypatch.setattr(service, 'resume_change', lambda *_: pytest.fail('Web must not resume remote rollout'))
    with app.test_request_context('/changes/api/1/pause', method='POST'):
        g.user_params = {'user_id': 1, 'group_id': 1, 'role': 1}
        response = routes.pause_change.__wrapped__(change.id)
        assert response.get_json()['data']['status'] == 'pause_requested'
        response = routes.resume_change.__wrapped__(change.id)
        assert response.get_json()['data']['status'] == 'deploying'
    assert change_sql.get_change(change.id).active_task_id == task.id


def test_scheduler_enqueues_drift_without_ssh_and_deduplicates(change, monkeypatch):
    change_sql.update_change(change.id, status='deployed')
    monkeypatch.setattr(automation.change_sql, 'list_latest_deployed_changes', lambda **_: [change_sql.get_change(change.id)])
    monkeypatch.setattr(automation, 'check_change_drift', lambda *_: pytest.fail('Scheduler must not use SSH'))
    assert automation.run_continuous_drift_scan() == {'queued': 1, 'failed': 0}
    assert automation.run_continuous_drift_scan() == {'queued': 0, 'failed': 0}


def test_history_retention_preserves_active_latest_and_other_operation_types(change, monkeypatch):
    monkeypatch.setattr(service, 'deploy_change', lambda *_: None)
    old = queued_task(change)
    assert run(old) == 'completed'
    latest = queued_task(change)
    assert run(latest) == 'completed'
    active = queued_task(change)
    old_finish = utc_now() - timedelta(days=31)
    InstallationTasks.update(finish_date=old_finish).where(InstallationTasks.id.in_([old.id, latest.id, active.id])).execute()
    # Preserve the last completed task as well as a currently active one.
    ConfigChange.update(last_task_id=latest.id).where(ConfigChange.id == change.id).execute()
    other = InstallationTasks.create(service_name=f'Change #{change.id}: other', operation_type='backup', status='completed', finish_date=old_finish)
    assert operations.cleanup_history(retention_days=0) == 0
    assert operations.cleanup_history(batch_size=1, max_batches=1) == 1
    assert InstallationTasks.get_or_none(InstallationTasks.id == old.id) is None
    assert all(InstallationTasks.get_by_id(task.id) for task in (latest, active, other))
    assert operations.cleanup_history() == 0


def test_expired_lease_cannot_overlap_a_worker_that_is_still_alive(change, monkeypatch):
    started, finish, duplicate_lock_attempt = Event(), Event(), Event()
    calls = []
    real_lock = operations.file_lock
    lock_attempts = []

    @contextmanager
    def file_lock(path):
        lock_attempts.append(path)
        if len(lock_attempts) == 2:
            duplicate_lock_attempt.set()
        with real_lock(path):
            yield

    def deploy(*args):
        calls.append(args)
        started.set()
        assert finish.wait(10)
        return change_sql.update_change(change.id, status='deployed')

    monkeypatch.setattr(operations, 'file_lock', file_lock)
    monkeypatch.setattr(service, 'deploy_change', deploy)
    task = queued_task(change)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, task)
        try:
            assert started.wait(10)
            InstallationTasks.update(updated_at=utc_now() - timedelta(hours=1)).where(InstallationTasks.id == task.id).execute()
            assert queue.recover_stale_operations() >= 1
            duplicate = pool.submit(run, task)
            assert duplicate_lock_attempt.wait(10)
        finally:
            finish.set()
        assert first.result(timeout=10) == duplicate.result(timeout=10) == 'completed'
    assert len(calls) == 1
    assert change_sql.get_change(change.id).active_task_id is None


def test_failed_completion_write_keeps_reservation_until_safe_recovery(change, monkeypatch):
    monkeypatch.setattr(service, 'deploy_change', lambda *_: change_sql.update_change(change.id, status='deployed'))
    task = queued_task(change)
    with monkeypatch.context() as patch:
        patch.setattr(operations, '_finish', lambda *_, **_kw: (_ for _ in ()).throw(RuntimeError('Database unavailable')))
        with pytest.raises(RuntimeError):
            run(task)
    assert InstallationTasks.get_by_id(task.id).status == 'running'
    assert change_sql.get_change(change.id).active_task_id == task.id
    InstallationTasks.update(updated_at=utc_now() - timedelta(hours=1)).where(InstallationTasks.id == task.id).execute()
    queue.recover_stale_operations()
    monkeypatch.setattr(service, 'deploy_change', lambda *_: pytest.fail('Do not repeat a completed remote action'))
    assert run(task) == 'failed'
    assert change_sql.get_change(change.id).active_task_id is None
    assert change_sql.get_change(change.id).status == 'deployed'


def test_routine_drift_check_keeps_task_history_without_flooding_audit(change, monkeypatch):
    change_sql.update_change(change.id, status='deployed')
    monkeypatch.setattr(automation, 'check_change_drift', lambda *_: change_sql.get_change(change.id))
    current = operations.enqueue(change.id, 'drift', change.group_id, None)
    task = InstallationTasks.get_by_id(current.active_task_id)
    assert run(task) == 'completed'
    assert ConfigChangeEvent.select().where(ConfigChangeEvent.change == change.id).count() == 0
    assert run(queued_task(change, 'drift')) == 'completed'
    assert ConfigChangeEvent.select().where(ConfigChangeEvent.change == change.id).count() == 2
