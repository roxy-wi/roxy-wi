import hashlib
import hmac
import importlib
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.modules.change.automation as automation
import app.modules.change.service as change_service
import app.modules.db.change as change_sql
from app.modules.change.schemas import (
    ConfigChangeSchedule,
    ConfigChangeWebhookCreate,
    ConfigChangeWebhookUpdate,
)
from app.modules.db.db_model import (
    ConfigChange,
    ConfigChangeDelivery,
    ConfigChangeEvent,
    ConfigChangeTarget,
    ConfigChangeWebhook,
    Slack,
    Server,
    Telegram,
    User,
    UserGroups,
)
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiPermissionError,
    RoxywiValidationError,
)
from app.modules.server.ssh import decrypt_password


GROUP_ID = 917


@pytest.fixture(autouse=True)
def stage_four_feature(monkeypatch):
    monkeypatch.setattr(automation, 'require_feature', lambda *_args, **_kwargs: None)


@pytest.fixture()
def managed_server(tmp_path):
    server = Server.create(
        hostname='change-automation-test',
        ip='192.0.2.117',
        group_id=str(GROUP_ID),
        enabled=1,
        haproxy=1,
    )
    yield server
    change_ids = [
        row.id for row in ConfigChange.select(ConfigChange.id).where(
            ConfigChange.group_id == GROUP_ID
        )
    ]
    if change_ids:
        ConfigChangeDelivery.delete().where(
            ConfigChangeDelivery.change.in_(change_ids)
        ).execute()
        ConfigChangeEvent.delete().where(ConfigChangeEvent.change.in_(change_ids)).execute()
        ConfigChangeTarget.delete().where(ConfigChangeTarget.change.in_(change_ids)).execute()
        ConfigChange.delete().where(ConfigChange.id.in_(change_ids)).execute()
    ConfigChangeDelivery.delete().where(ConfigChangeDelivery.change.is_null(True)).execute()
    ConfigChangeWebhook.delete().where(ConfigChangeWebhook.group_id == GROUP_ID).execute()
    Server.delete().where(Server.server_id == server.server_id).execute()


def _change(managed_server, tmp_path, **overrides):
    draft = tmp_path / f'draft-{len(list(tmp_path.iterdir()))}.cfg'
    rollback = tmp_path / f'rollback-{len(list(tmp_path.iterdir()))}.cfg'
    draft.write_text('global\n  daemon\n', encoding='utf-8')
    rollback.write_text('global\n', encoding='utf-8')
    values = {
        'server_id': managed_server.server_id,
        'group_id': GROUP_ID,
        'user_id': 1,
        'service': 'haproxy',
        'action': 'reload',
        'execution_mode': 'rolling',
        'status': 'validated',
        'title': 'Automated change',
        'description': '',
        'remote_path': '/etc/haproxy/haproxy.cfg',
        'draft_path': str(draft),
        'rollback_path': str(rollback),
        'diff': '+  daemon\n',
        'requires_approval': 0,
    }
    values.update(overrides)
    return change_sql.create_change(**values)


def _target(change, managed_server, tmp_path, **overrides):
    rollback = tmp_path / f'target-{change.id}-before.cfg'
    rollback.write_text('global\n', encoding='utf-8')
    values = {
        'server_id': managed_server.server_id,
        'server_ip': managed_server.ip,
        'server_name': managed_server.hostname,
        'role': 'standalone',
        'position': 0,
        'status': 'deployed',
        'rollback_path': str(rollback),
    }
    values.update(overrides)
    return change_sql.create_targets(change.id, [values])[0]


def test_schedule_and_cancel_restore_the_ready_state(managed_server, tmp_path):
    change = _change(managed_server, tmp_path)
    scheduled_at = automation.utc_now() + timedelta(hours=1)
    window_end = scheduled_at + timedelta(hours=2)

    scheduled = automation.schedule_change(
        change.id,
        ConfigChangeSchedule(
            scheduled_at=scheduled_at,
            maintenance_window_end=window_end,
        ),
        GROUP_ID,
        actor_id=8,
    )

    assert scheduled.status == 'scheduled'
    assert scheduled.schedule_base_status == 'validated'
    assert scheduled.maintenance_window_end == window_end
    event = ConfigChangeEvent.get(ConfigChangeEvent.change == change.id)
    assert event.event_type == 'change.scheduled'
    assert event.actor_id == 8

    restored = automation.cancel_schedule(change.id, GROUP_ID, actor_id=8)

    assert restored.status == 'validated'
    assert restored.scheduled_at is None
    assert [event.event_type for event in change_sql.list_events(
        GROUP_ID, change_id=change.id
    )] == ['change.schedule_cancelled', 'change.scheduled']


def test_schedule_rejects_wrong_group_past_time_and_unready_change(
    managed_server, tmp_path
):
    change = _change(managed_server, tmp_path)
    future = ConfigChangeSchedule(scheduled_at=automation.utc_now() + timedelta(hours=1))

    with pytest.raises(RoxywiPermissionError):
        automation.schedule_change(change.id, future, GROUP_ID + 1)
    with pytest.raises(RoxywiValidationError):
        automation.schedule_change(
            change.id,
            ConfigChangeSchedule(scheduled_at=automation.utc_now() - timedelta(hours=1)),
            GROUP_ID,
        )
    change_sql.update_change(change.id, status='draft')
    with pytest.raises(RoxywiConflictError):
        automation.schedule_change(change.id, future, GROUP_ID)


def test_due_scheduler_runs_once_and_marks_expired_windows(
    managed_server, tmp_path, monkeypatch
):
    due = _change(
        managed_server,
        tmp_path,
        title='Due',
        status='scheduled',
        scheduled_at=automation.utc_now() - timedelta(minutes=1),
        schedule_base_status='validated',
    )
    expired = _change(
        managed_server,
        tmp_path,
        title='Expired',
        status='scheduled',
        scheduled_at=automation.utc_now() - timedelta(hours=2),
        maintenance_window_end=automation.utc_now() - timedelta(hours=1),
        schedule_base_status='validated',
    )
    calls = []

    def deploy(change_id, group_id, actor_id=None):
        calls.append((change_id, group_id, actor_id))
        return change_sql.update_change(
            change_id,
            status='deployed',
            finished_at=automation.utc_now(),
            deployed_at=automation.utc_now(),
        )

    monkeypatch.setattr(change_service, 'deploy_change', deploy)

    result = automation.run_due_scheduled_changes()

    assert result == {'executed': 1, 'missed': 1, 'failed': 0}
    assert calls == [(due.id, GROUP_ID, None)]
    assert change_sql.get_change(expired.id).status == 'schedule_missed'


def test_record_event_creates_timeline_and_notification_outbox(
    managed_server, tmp_path
):
    change = _change(
        managed_server,
        tmp_path,
        notification_channels=json.dumps(['email']),
    )
    webhook = automation.create_webhook(
        ConfigChangeWebhookCreate(
            name='Automation',
            url='https://hooks.example.test/roxy-wi',
            events=['deployment.succeeded'],
        ),
        user_id=1,
        group_id=GROUP_ID,
    )

    event = automation.record_event(
        change.id,
        'deployment.succeeded',
        'Deployment completed',
        actor_id=2,
    )

    deliveries = change_sql.list_change_deliveries(change.id)
    assert event.event_type == 'deployment.succeeded'
    assert {(item.destination_type, item.destination_id) for item in deliveries} == {
        ('email', None), ('webhook', webhook.id)
    }


def test_notification_destinations_are_group_scoped_and_hide_secrets():
    user = User.create(
        username='change-recipient',
        email='change-recipient@example.test',
        password='unused',
        role_id='user',
        group_id=str(GROUP_ID),
        enabled=1,
    )
    disabled = User.create(
        username='change-disabled-recipient',
        email='change-disabled@example.test',
        password='unused',
        role_id='user',
        group_id=str(GROUP_ID),
        enabled=0,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=GROUP_ID, user_role_id=3)
    UserGroups.create(user_id=disabled.user_id, user_group_id=GROUP_ID, user_role_id=3)
    telegram = Telegram.create(
        token='secret-telegram-token', chanel_name='Operations', group_id=GROUP_ID
    )
    foreign = Slack.create(
        token='secret-slack-token', chanel_name='Foreign', group_id=GROUP_ID + 1
    )
    try:
        destinations = automation.list_notification_destinations(GROUP_ID)

        assert {
            (item['channel'], item['recipient_id']) for item in destinations
        } == {('email', user.user_id), ('telegram', telegram.id)}
        assert all('token' not in item for item in destinations)
        assert 'secret-telegram-token' not in json.dumps(destinations)
        with pytest.raises(RoxywiValidationError, match='active group'):
            automation.validate_notification_destinations(
                [{'channel': 'slack', 'recipient_id': foreign.id}], GROUP_ID
            )
    finally:
        Telegram.delete().where(Telegram.id == telegram.id).execute()
        Slack.delete().where(Slack.id == foreign.id).execute()
        UserGroups.delete().where(UserGroups.user_id.in_([user.user_id, disabled.user_id])).execute()
        User.delete().where(User.user_id.in_([user.user_id, disabled.user_id])).execute()


def test_record_event_queues_only_explicit_notification_recipients(
    managed_server, tmp_path
):
    user = User.create(
        username='selected-change-recipient',
        email='selected-change-recipient@example.test',
        password='unused',
        role_id='user',
        group_id=str(GROUP_ID),
        enabled=1,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=GROUP_ID, user_role_id=3)
    selected = Telegram.create(
        token='selected-token', chanel_name='Selected', group_id=GROUP_ID
    )
    unselected = Telegram.create(
        token='unselected-token', chanel_name='Unselected', group_id=GROUP_ID
    )
    try:
        change = _change(
            managed_server,
            tmp_path,
            notification_channels=json.dumps(['email', 'telegram']),
            notification_destinations=json.dumps([
                {'channel': 'email', 'recipient_id': user.user_id},
                {'channel': 'telegram', 'recipient_id': selected.id},
            ]),
        )

        automation.record_event(
            change.id, 'deployment.succeeded', 'Deployment completed'
        )

        deliveries = change_sql.list_change_deliveries(change.id)
        assert {(item.destination_type, item.destination_id) for item in deliveries} == {
            ('email', user.user_id), ('telegram', selected.id)
        }
        assert all(item.destination_id != unselected.id for item in deliveries)
    finally:
        Telegram.delete().where(Telegram.id.in_([selected.id, unselected.id])).execute()
        UserGroups.delete().where(UserGroups.user_id == user.user_id).execute()
        User.delete().where(User.user_id == user.user_id).execute()


def test_selected_email_delivery_targets_one_current_group_member(monkeypatch):
    user = User.create(
        username='delivery-change-recipient',
        email='delivery-change-recipient@example.test',
        password='unused',
        role_id='user',
        group_id=str(GROUP_ID),
        enabled=1,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=GROUP_ID, user_role_id=3)
    sent = []
    monkeypatch.setattr(automation.alerting, 'send_email', lambda *args: sent.append(args))
    delivery = SimpleNamespace(destination_type='email', destination_id=user.user_id)
    payload = {
        'subject': 'Change deployed', 'message': 'Completed', 'level': 'info',
        'group_id': GROUP_ID,
    }
    try:
        automation._send_notification(delivery, payload)
        assert sent == [(
            'delivery-change-recipient@example.test',
            'Change deployed',
            'info: Completed',
        )]

        UserGroups.delete().where(UserGroups.user_id == user.user_id).execute()
        with pytest.raises(Exception, match='active group'):
            automation._send_notification(delivery, payload)
    finally:
        UserGroups.delete().where(UserGroups.user_id == user.user_id).execute()
        User.delete().where(User.user_id == user.user_id).execute()


def test_webhook_secret_is_encrypted_hidden_and_preserved_on_update(
    managed_server
):
    webhook = automation.create_webhook(
        ConfigChangeWebhookCreate(
            name='Signed',
            url='https://hooks.example.test/change',
            secret='top-secret',
        ),
        user_id=1,
        group_id=GROUP_ID,
    )

    assert webhook.secret_encrypted != 'top-secret'
    assert decrypt_password(webhook.secret_encrypted) == 'top-secret'
    assert 'secret' not in automation.serialize_webhook(webhook)

    updated = automation.update_webhook(
        webhook.id,
        ConfigChangeWebhookUpdate(enabled=False),
        GROUP_ID,
    )
    assert decrypt_password(updated.secret_encrypted) == 'top-secret'
    assert not automation.serialize_webhook(updated)['enabled']


def test_webhook_delivery_uses_hmac_and_disables_redirects(
    managed_server, monkeypatch
):
    webhook = automation.create_webhook(
        ConfigChangeWebhookCreate(
            name='Signed delivery',
            url='https://hooks.example.test/change',
            secret='delivery-secret',
        ),
        user_id=1,
        group_id=GROUP_ID,
    )
    captured = {}

    class Response:
        status_code = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(automation, '_validate_webhook_destination', lambda _url: None)
    monkeypatch.setattr(automation.requests, 'post', post)
    payload = {'type': 'deployment.succeeded', 'message': 'ok'}
    delivery = SimpleNamespace(id=71, destination_id=webhook.id)

    assert automation._send_webhook(delivery, payload) == 204
    expected = hmac.new(
        b'delivery-secret', captured['data'], hashlib.sha256
    ).hexdigest()
    assert captured['headers']['X-Roxy-WI-Signature'] == f'sha256={expected}'
    assert captured['allow_redirects'] is False
    assert captured['timeout'] == 5


@pytest.mark.parametrize(
    'address', ('127.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1')
)
def test_webhook_destination_rejects_special_addresses(monkeypatch, address):
    monkeypatch.setattr(
        automation.socket,
        'getaddrinfo',
        lambda *_args: [(None, None, None, None, (address, 443))],
    )

    with pytest.raises(RoxywiPermissionError):
        automation._validate_webhook_destination('https://metadata.example.test/hook')


def test_delivery_failure_is_retried_without_changing_workflow(
    managed_server, tmp_path, monkeypatch
):
    change = _change(managed_server, tmp_path, status='deployed')
    webhook = automation.create_webhook(
        ConfigChangeWebhookCreate(
            name='Retry', url='https://hooks.example.test/retry'
        ),
        user_id=1,
        group_id=GROUP_ID,
    )
    change_sql.create_deliveries([{
        'change': change.id,
        'event': None,
        'destination_type': 'webhook',
        'destination_id': webhook.id,
        'payload': '{}',
    }])
    monkeypatch.setattr(
        automation, '_send_webhook', lambda *_args: (_ for _ in ()).throw(RuntimeError('offline'))
    )

    result = automation.process_pending_deliveries()
    delivery = change_sql.list_change_deliveries(change.id)[0]

    assert result == {'processed': 1, 'delivered': 0, 'failed': 1}
    assert delivery.status == 'failed'
    assert delivery.attempts == 1
    assert delivery.next_attempt_at > automation.utc_now()
    assert change_sql.get_change(change.id).status == 'deployed'


def test_delivery_batch_uses_two_writes_for_multiple_messages(
    managed_server, tmp_path, monkeypatch
):
    change = _change(managed_server, tmp_path, status='deployed')
    change_sql.create_deliveries([
        {
            'change': change.id,
            'event': None,
            'destination_type': 'webhook',
            'destination_id': 101,
            'payload': '{}',
        },
        {
            'change': change.id,
            'event': None,
            'destination_type': 'webhook',
            'destination_id': 102,
            'payload': '{}',
        },
    ])
    monkeypatch.setattr(automation, '_send_webhook', lambda *_args: 204)
    original_execute_write = change_sql._execute_write
    write_operations = []

    def counted_write(operation):
        write_operations.append(operation)
        return original_execute_write(operation)

    monkeypatch.setattr(change_sql, '_execute_write', counted_write)

    result = automation.process_pending_deliveries()
    deliveries = change_sql.list_change_deliveries(change.id)

    assert result == {'processed': 2, 'delivered': 2, 'failed': 0}
    assert len(write_operations) == 2
    assert {delivery.status for delivery in deliveries} == {'delivered'}
    assert {delivery.attempts for delivery in deliveries} == {1}


def test_webhook_test_does_not_require_an_existing_change(managed_server):
    webhook = automation.create_webhook(
        ConfigChangeWebhookCreate(
            name='Test only', url='https://hooks.example.test/test'
        ),
        user_id=1,
        group_id=GROUP_ID,
    )

    automation.queue_webhook_test(webhook.id, GROUP_ID, user_id=1)

    delivery = ConfigChangeDelivery.select().where(
        (ConfigChangeDelivery.change.is_null(True)) &
        (ConfigChangeDelivery.destination_id == webhook.id)
    ).get()
    assert json.loads(delivery.payload)['type'] == 'webhook.test'


def test_drift_detection_updates_each_node_and_records_transitions(
    managed_server, tmp_path, monkeypatch
):
    change = _change(managed_server, tmp_path, status='deployed')
    target = _target(change, managed_server, tmp_path)
    monkeypatch.setattr(
        automation,
        '_drift_target',
        lambda *_args: {'status': 'drifted', 'diff': '-old\n+new'},
    )

    drifted = automation.check_change_drift(change.id, GROUP_ID, actor_id=9)

    assert drifted.drift_status == 'drifted'
    assert change_sql.get_target(target.id).drift_status == 'drifted'
    assert change_sql.list_events(GROUP_ID, change_id=change.id)[0].event_type == 'drift.detected'

    monkeypatch.setattr(
        automation,
        '_drift_target',
        lambda *_args: {'status': 'in_sync', 'diff': ''},
    )
    resolved = automation.check_change_drift(change.id, GROUP_ID, actor_id=9)
    assert resolved.drift_status == 'in_sync'
    assert change_sql.list_events(GROUP_ID, change_id=change.id)[0].event_type == 'drift.resolved'


def test_drift_results_are_persisted_with_one_repository_write(
    managed_server, tmp_path, monkeypatch
):
    change = _change(managed_server, tmp_path, status='deployed')
    target = _target(change, managed_server, tmp_path)
    monkeypatch.setattr(
        automation,
        '_drift_target',
        lambda *_args: {'status': 'drifted', 'diff': '-old\n+new'},
    )
    original_update = change_sql.update_drift_results
    updates = []

    def counted_update(*args, **kwargs):
        updates.append((args, kwargs))
        return original_update(*args, **kwargs)

    monkeypatch.setattr(change_sql, 'update_drift_results', counted_update)
    monkeypatch.setattr(
        change_sql,
        'update_target',
        lambda *_args, **_kwargs: pytest.fail('drift must not update targets one by one'),
    )

    automation.check_change_drift(change.id, GROUP_ID)

    assert len(updates) == 1
    assert change_sql.get_target(target.id).drift_status == 'drifted'


def test_drift_worker_always_closes_its_database_connection(
    managed_server, tmp_path, monkeypatch
):
    change = _change(managed_server, tmp_path, status='deployed')
    target = _target(change, managed_server, tmp_path)
    closed = []
    monkeypatch.setattr(
        automation.config_mod,
        'get_config',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('offline')),
    )
    monkeypatch.setattr(automation, 'close_database_connection', lambda: closed.append(True))

    result = automation._drift_target(change, target)

    assert result['status'] == 'check_failed'
    assert closed == [True]


def test_audit_search_statistics_and_reports_include_per_node_results(
    managed_server, tmp_path
):
    started = automation.utc_now() - timedelta(seconds=12)
    change = _change(
        managed_server,
        tmp_path,
        title='Searchable release',
        status='deployed',
        started_at=started,
        finished_at=started + timedelta(seconds=12),
        deployed_at=started + timedelta(seconds=12),
        drift_status='drifted',
    )
    _target(
        change,
        managed_server,
        tmp_path,
        deployment_output='Uploaded',
        health_output='Healthy',
        drift_status='drifted',
        drift_diff='-old\n+new',
    )
    automation.record_event(change.id, 'deployment.succeeded', 'Search marker')

    events = change_sql.list_events(GROUP_ID, search='Search marker')
    statistics = automation.deployment_statistics(GROUP_ID, days=30)
    report = automation.build_change_report(change)
    csv_report = automation.build_change_report(change, as_csv=True)

    assert [event.change_id for event in events] == [change.id]
    assert statistics['deployments'] == 1
    assert statistics['successful'] == 1
    assert statistics['success_rate'] == 100.0
    assert statistics['average_duration_seconds'] == 12.0
    assert statistics['drifted_targets'] == 1
    assert report['targets'][0]['health_output'] == 'Healthy'
    assert report['timeline'][0]['event_type'] == 'deployment.succeeded'
    assert 'change_id,title,service' in csv_report
    assert 'Searchable release' in csv_report


def test_stage_four_migration_adds_columns_tables_and_removes_them(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260829010000_add_change_automation_visibility'
    )
    operations = []
    table_calls = []
    migrator = SimpleNamespace(
        add_column=lambda table, column, field: ('add', table, column, field),
        drop_column=lambda table, column: ('drop', table, column),
    )
    connection = SimpleNamespace(
        create_tables=lambda models, **kwargs: table_calls.append(('create', models, kwargs)),
        drop_tables=lambda models, **kwargs: table_calls.append(('drop', models, kwargs)),
    )

    def connect(get_migrator=0):
        return migrator if get_migrator else connection

    monkeypatch.setattr(migration, 'connect', connect)
    monkeypatch.setattr(migration, '_columns', lambda _table: set())
    monkeypatch.setattr(migration, 'migrate', lambda *items: operations.extend(items))

    migration.up()
    added = list(operations)
    monkeypatch.setattr(
        migration,
        '_columns',
        lambda table: {
            name for name, _field in (
                migration.CHANGE_COLUMNS if table == 'config_changes'
                else migration.TARGET_COLUMNS
            )
        },
    )
    migration.down()

    assert len([item for item in added if item[0] == 'add']) == (
        len(migration.CHANGE_COLUMNS) + len(migration.TARGET_COLUMNS)
    )
    assert table_calls[0][0] == 'create'
    assert table_calls[0][1] == [ConfigChangeEvent, ConfigChangeWebhook, ConfigChangeDelivery]
    assert table_calls[1][0] == 'drop'
    assert len([item for item in operations if item[0] == 'drop']) == (
        len(migration.CHANGE_COLUMNS) + len(migration.TARGET_COLUMNS)
    )


def test_notification_destination_migration_is_safe_to_apply_and_remove(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260829020000_add_change_notification_destinations'
    )
    operations = []
    migrator = SimpleNamespace(
        add_column=lambda table, column, field: ('add', table, column, field),
        drop_column=lambda table, column: ('drop', table, column),
    )
    monkeypatch.setattr(migration, 'connect', lambda **_kwargs: migrator)
    monkeypatch.setattr(migration, 'migrate', lambda *items: operations.extend(items))
    monkeypatch.setattr(migration, '_columns', lambda: set())

    migration.up()
    monkeypatch.setattr(migration, '_columns', lambda: {migration.COLUMN_NAME})
    migration.down()

    assert operations[0][0:3] == (
        'add', 'config_changes', 'notification_destinations'
    )
    assert operations[1] == (
        'drop', 'config_changes', 'notification_destinations'
    )


def test_stage_four_scheduler_jobs_are_registered():
    jobs = importlib.import_module('app.jobs')
    registered = {job.id for job in jobs.scheduler.get_jobs()}

    assert {
        'change_center_scheduled_deployments',
        'change_center_deliveries',
        'change_center_drift_detection',
        'service_command_outbox',
        'service_assignment_reconciliation',
        'delete_old_service_metrics',
    } <= registered


def test_scheduler_database_job_closes_connection(monkeypatch):
    jobs = importlib.import_module('app.jobs')
    closed = []
    executed = []
    monkeypatch.setattr(jobs, 'close_database_connection', lambda: closed.append(True))

    assert jobs._run_database_job(lambda: executed.append('normal') or 'done') == 'done'
    assert closed == [True]
    assert executed == ['normal']


def test_dedicated_scheduler_forces_enabled_mode_and_starts_after_job_registration():
    runner = Path('scheduler_runner.py').read_text(encoding='utf-8')
    application = Path('app/__init__.py').read_text(encoding='utf-8')

    assert "os.environ['ROXYWI_SCHEDULER_ENABLED'] = '1'" in runner
    assert "setdefault('ROXYWI_SCHEDULER_ENABLED'" not in runner
    jobs_import = application.index('from app import jobs')
    scheduler_start = application.index('scheduler.start()', jobs_import)
    assert jobs_import < scheduler_start


def test_stage_four_ui_and_all_translations_cover_automation_features(app):
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')
    editor = Path('app/templates/config.html').read_text(encoding='utf-8')
    expected_keys = {
        'statistics', 'audit_history', 'webhooks', 'timeline', 'schedule_deployment',
        'cancel_schedule', 'check_drift', 'export_report', 'notifications',
        'drift_statuses', 'drift_help', 'drift_not_applicable',
        'webhook_delivery', 'webhook_status_help',
    }

    assert 'change-center-stats' in template
    assert 'change-details-timeline' in template
    assert 'change-webhooks-dialog' in template
    assert '/changes/api/statistics' in script
    assert '/schedule' in script
    assert '/events' in script
    assert '/report?format=csv' in script
    assert 'change-notification-destinations' in editor
    assert '/changes/api/notification-destinations' in Path(
        'app/static/js/change-editor.js'
    ).read_text(encoding='utf-8')

    for language in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'):
        catalog = app.jinja_env.get_template(
            f'languages/{language}.html'
        ).module.change_center
        assert expected_keys <= set(catalog)
        assert {'scheduled', 'schedule_missed'} <= set(catalog['statuses'])
        assert {'unknown', 'in_sync', 'drifted', 'check_failed'} <= set(
            catalog['drift_statuses']
        )


def test_stage_four_interface_has_persistent_filters_and_non_blocking_states(app):
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')
    stylesheet = Path('app/static/css/change-center.css').read_text(encoding='utf-8')
    ui_script = Path('app/static/js/ui-components.js').read_text(encoding='utf-8')
    ui_stylesheet = Path('app/static/css/ui-components.css').read_text(encoding='utf-8')

    for element_id in (
        'change-list-search', 'change-list-service', 'change-list-status',
        'change-list-drift', 'change-list-clear', 'change-center-list-state',
        'change-list-retry', 'change-center-no-results',
    ):
        assert f'id="{element_id}"' in template
    assert 'aria-busy="true"' in template
    assert '<th data-sortable="false">{{lang.words.action|title()}}</th>' in template
    assert 'roxywi-change-center-filters:v1' in script
    assert 'window.localStorage.setItem(filterStorageKey' in script
    assert "on('change selectmenuchange', applyFilters)" in script
    assert "select.selectmenu('refresh')" in script
    assert "on('change selectmenuchange', loadAudit)" in script
    assert "webhookEvents.select2({" in script
    assert ".trigger('change.select2')" in script
    assert "window.location.assign('/changes')" in Path(
        'app/static/js/change-editor.js'
    ).read_text(encoding='utf-8')
    assert "setListState('error')" in script
    assert 'change-actions-menu' in script
    assert "rw-status-badge change-status change-status-" in script
    assert "['pause_requested', 'paused', 'deployment_interrupted'].includes(change.status)" in script
    assert "actionButton('fa-play', i18n.resume, 'resume', change.id, false, true)" in script
    assert 'aria-haspopup' in script
    assert "confirmAction('deleteWebhook'" in script
    assert 'window.confirm' not in script
    assert 'Intl.RelativeTimeFormat' in script
    assert '.change-list-toolbar' in stylesheet
    assert '#change-center #change-list-search' in stylesheet
    assert '#change-center #change-list-clear' in stylesheet
    assert 'height: 34px !important' in stylesheet
    assert '#change-center .change-action-resume .fa-play' in stylesheet
    assert '#change-center .change-action-resume .svg-inline--fa' in stylesheet
    assert '#change-center .change-action-resume.change-action-labeled' in stylesheet
    assert '.change-actions-menu' in stylesheet
    assert '.change-live-indicator' in stylesheet
    assert "attr('data-sortable') === 'false'" in ui_script
    assert 'thead th[role="button"]::after' in ui_stylesheet
    assert 'th[aria-sort="ascending"]::after' in ui_stylesheet
    assert 'th[aria-sort="descending"]::after' in ui_stylesheet

    with app.app_context():
        catalogs = [
            app.jinja_env.get_template(f'languages/{language}.html').module.change_center
            for language in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')
        ]
    expected = {
        'filters', 'search_placeholder', 'clear_filters', 'loading',
        'load_failed', 'no_matching_changes', 'showing_changes',
        'more_actions', 'live', 'local_timezone', 'invalid_schedule',
        'confirm_delete_webhook', 'drift_help', 'drift_not_applicable',
        'webhook_delivery', 'webhook_status_help',
    }
    assert all(expected <= set(catalog) for catalog in catalogs)
