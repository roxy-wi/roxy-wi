import importlib
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, Lock, Thread, get_ident
from types import SimpleNamespace

import pytest
from flask import g
from flask_jwt_extended import create_access_token
from peewee import OperationalError

import app.modules.change.service as change_service
import app.modules.change.access as change_access
import app.modules.config.config as config_module
import app.modules.db.change as change_sql
from app.modules.change.schemas import ConfigChangeCreate, ConfigChangeUpdate
from app.modules.db.db_model import ConfigChange, ConfigChangeTarget, Server, Slack, connect
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiPermissionError,
    RoxywiResourceNotFound,
    RoxywiValidationError,
)


@pytest.fixture(autouse=True)
def active_premium_subscription(monkeypatch):
    monkeypatch.setattr(
        change_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'support'},
    )


@pytest.fixture()
def managed_server():
    server = Server.create(
        hostname='change-center-test',
        ip='192.0.2.240',
        group_id='1',
        enabled=1,
        haproxy=1,
    )
    yield server
    ConfigChange.delete().where(ConfigChange.server_id == server.server_id).execute()
    Server.delete().where(Server.server_id == server.server_id).execute()


@pytest.fixture()
def cluster_servers(managed_server):
    slaves = [
        Server.create(
            hostname=f'change-center-slave-{index}',
            ip=f'192.0.2.{240 + index}',
            group_id='1',
            enabled=1,
            haproxy=1,
            master=managed_server.server_id,
        )
        for index in (1, 2)
    ]
    yield slaves, managed_server
    Server.delete().where(Server.master == managed_server.server_id).execute()


def _db_change(managed_server, tmp_path, **overrides):
    draft = tmp_path / 'draft.cfg'
    before = tmp_path / 'before.cfg'
    draft.write_text('global\n  daemon\n', encoding='utf-8')
    before.write_text('global\n', encoding='utf-8')
    values = {
        'server_id': managed_server.server_id,
        'group_id': 1,
        'user_id': 1,
        'service': 'haproxy',
        'action': 'reload',
        'status': 'draft',
        'title': 'Add daemon mode',
        'description': '',
        'remote_path': '/etc/haproxy/haproxy.cfg',
        'draft_path': str(draft),
        'rollback_path': str(before),
        'diff': '+  daemon\n',
        'requires_approval': 0,
    }
    values.update(overrides)
    return ConfigChange.create(**values)


def _seed_rollout_targets(change, managed_server, tmp_path, *, status='pending'):
    values = []
    for position, (server, role) in enumerate(
        change_service._rollout_servers(managed_server, change.service)
    ):
        if server.server_id == managed_server.server_id:
            rollback_path = Path(change.rollback_path)
        else:
            rollback_path = tmp_path / f'change-{change.id}-{server.server_id}-before.cfg'
            rollback_path.write_text(f'# original {server.ip}\n', encoding='utf-8')
        values.append({
            'server_id': server.server_id,
            'server_ip': server.ip,
            'server_name': server.hostname,
            'role': role,
            'position': position,
            'status': status,
            'rollback_path': str(rollback_path),
        })
    return change_sql.create_targets(change.id, values)


def test_snapshot_paths_stay_short_when_the_source_snapshot_name_is_long(tmp_path):
    source = tmp_path / f'192.0.2.10-{"a" * 180}-before.cfg'

    for purpose in ('before', 'current', 'resume'):
        snapshot = change_service._snapshot_path(source, '2001:db8::10', purpose)

        assert snapshot.parent == source.parent
        assert snapshot.suffix == '.cfg'
        assert purpose in snapshot.name
        assert len(snapshot.name) < 100
        assert source.stem not in snapshot.name


def test_change_repository_supplies_rollout_defaults_without_database_defaults(monkeypatch):
    captured = {}
    marker = object()

    def create(**values):
        captured.update(values)
        return marker

    monkeypatch.setattr(change_sql.ConfigChange, 'create', staticmethod(create))

    result = change_sql.create_change(title='Migration-safe draft')

    assert result is marker
    assert captured['batch_size'] == 0
    assert captured['max_parallel'] == 8
    assert captured['manual_promotion'] == 0
    assert captured['health_check_mode'] == 'full'
    assert captured['health_check_retries'] == 1
    assert captured['health_check_interval'] == 0
    assert captured['pause_requested'] == 0
    assert captured['notification_destinations'] == '[]'


def test_create_change_captures_running_config_and_diff(managed_server, monkeypatch):
    def get_config(_server_ip, destination, **_kwargs):
        Path(destination).write_text('global\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    body = ConfigChangeCreate(
        server_id=managed_server.server_id,
        service='haproxy',
        action='reload',
        execution_mode='parallel',
        config='global\n  daemon\n',
        title='Add daemon mode',
        requires_approval=True,
    )

    change = change_service.create_change(body, user_id=1, group_id=1)

    assert change.status == 'draft'
    assert change.execution_mode == 'parallel'
    assert change.requires_approval == 1
    assert '+  daemon' in change.diff
    assert Path(change.rollback_path).read_text(encoding='utf-8') == 'global\n'
    assert Path(change.draft_path).read_text(encoding='utf-8') == 'global\n  daemon\n'


def test_create_change_accepts_server_ip(managed_server, tmp_path, monkeypatch):
    rollback = tmp_path / 'before.cfg'
    draft = tmp_path / 'draft.cfg'
    monkeypatch.setattr(change_service, '_change_paths', lambda *_args: (draft, rollback))
    monkeypatch.setattr(
        change_service.config_mod,
        'get_config',
        lambda _ip, destination, **_kwargs: Path(destination).write_text('global\n', encoding='utf-8'),
    )
    body = ConfigChangeCreate(
        server_id=managed_server.ip,
        service='haproxy',
        config='global\n  daemon\n',
        title='Create by IP',
    )

    change = change_service.create_change(body, user_id=1, group_id=1)

    assert change.server_id == managed_server.server_id


def test_create_change_rejects_wrong_group_and_disabled_service(managed_server):
    body = ConfigChangeCreate(
        server_id=managed_server.server_id,
        service='haproxy',
        config='global\n',
        title='Rejected change',
    )
    with pytest.raises(RoxywiPermissionError, match='active group'):
        change_service.create_change(body, user_id=1, group_id=2)

    managed_server.haproxy = 0
    managed_server.save()
    with pytest.raises(RoxywiValidationError, match='not enabled'):
        change_service.create_change(body, user_id=1, group_id=1)


def test_create_change_rejects_foreign_notification_recipient_before_ssh(
    managed_server, monkeypatch
):
    receiver = Slack.create(
        token='foreign-secret', chanel_name='Foreign channel', group_id=2
    )
    ssh_called = False

    def unexpected_ssh(*_args, **_kwargs):
        nonlocal ssh_called
        ssh_called = True

    monkeypatch.setattr(change_service.config_mod, 'get_config', unexpected_ssh)
    body = ConfigChangeCreate(
        server_id=managed_server.server_id,
        service='haproxy',
        config='global\n',
        title='Foreign notification',
        notification_destinations=[{
            'channel': 'slack', 'recipient_id': receiver.id,
        }],
    )
    try:
        with pytest.raises(RoxywiValidationError, match='active group'):
            change_service.create_change(body, user_id=1, group_id=1)
        assert not ssh_called
    finally:
        Slack.delete().where(Slack.id == receiver.id).execute()


def test_create_change_removes_private_files_when_snapshot_fails(
    managed_server, tmp_path, monkeypatch
):
    draft = tmp_path / 'draft.cfg'
    rollback = tmp_path / 'before.cfg'
    monkeypatch.setattr(change_service, '_change_paths', lambda *_args: (draft, rollback))

    def failed_snapshot(_ip, destination, **_kwargs):
        Path(destination).write_text('partial snapshot', encoding='utf-8')
        raise RuntimeError('SSH failed')

    monkeypatch.setattr(change_service.config_mod, 'get_config', failed_snapshot)
    body = ConfigChangeCreate(
        server_id=managed_server.server_id,
        service='haproxy',
        config='global\n',
        title='Cleanup failed change',
    )

    with pytest.raises(RuntimeError, match='SSH failed'):
        change_service.create_change(body, user_id=1, group_id=1)

    assert not draft.exists()
    assert not rollback.exists()


def test_change_schemas_reject_incomplete_or_unsafe_input():
    assert ConfigChangeCreate(
        server_id=1, service='haproxy', config='global', title='Default mode'
    ).execution_mode == 'rolling'
    with pytest.raises(ValueError, match='file_path is required'):
        ConfigChangeCreate(server_id=1, service='nginx', config='events {}', title='Nginx')
    with pytest.raises(ValueError, match='config must not be empty'):
        ConfigChangeCreate(server_id=1, service='haproxy', config='  ', title='Empty')
    with pytest.raises(ValueError):
        ConfigChangeCreate(server_id=1, service='haproxy', config='global', title='<script>')
    with pytest.raises(ValueError, match='At least one field'):
        ConfigChangeUpdate()
    with pytest.raises(ValueError, match='title must not be null'):
        ConfigChangeUpdate(title=None)
    with pytest.raises(ValueError, match='action must not be null'):
        ConfigChangeUpdate(action=None)
    with pytest.raises(ValueError, match='execution_mode must not be null'):
        ConfigChangeUpdate(execution_mode=None)
    with pytest.raises(ValueError):
        ConfigChangeCreate(
            server_id=1,
            service='haproxy',
            config='global',
            title='Invalid mode',
            execution_mode='all-at-once',
        )
    with pytest.raises(ValueError, match='notification_destinations must not contain duplicates'):
        ConfigChangeCreate(
            server_id=1,
            service='haproxy',
            config='global',
            title='Duplicate recipients',
            notification_destinations=[
                {'channel': 'email', 'recipient_id': 7},
                {'channel': 'email', 'recipient_id': 7},
            ],
        )


def test_draft_can_be_edited_but_deployed_change_cannot(managed_server, tmp_path):
    change = _db_change(managed_server, tmp_path)

    updated = change_service.update_change(
        change.id,
        ConfigChangeUpdate(
            title='Updated title', action='restart', execution_mode='parallel'
        ),
        group_id=1,
    )

    assert updated.title == 'Updated title'
    assert updated.action == 'restart'
    assert updated.execution_mode == 'parallel'
    assert updated.status == 'draft'
    ConfigChange.update(status='deployed').where(ConfigChange.id == change.id).execute()
    with pytest.raises(RoxywiConflictError, match='Only draft'):
        change_service.update_change(
            change.id,
            ConfigChangeUpdate(title='Too late'),
            group_id=1,
        )


def test_validation_and_distinct_approval_workflow(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, requires_approval=1)
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Configuration file is valid')

    validated = change_service.validate_change(change.id, group_id=1)

    assert validated.status == 'pending_approval'
    with pytest.raises(RoxywiPermissionError, match='author cannot approve'):
        change_service.approve_change(change.id, approver_id=1, group_id=1)

    approved = change_service.approve_change(change.id, approver_id=2, group_id=1)
    assert approved.status == 'approved'
    assert approved.approved_by == 2


def test_validation_failure_can_be_cancelled(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path)
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('invalid configuration')),
    )

    with pytest.raises(RoxywiValidationError, match='invalid configuration'):
        change_service.validate_change(change.id, group_id=1)

    failed = ConfigChange.get_by_id(change.id)
    assert failed.status == 'validation_failed'
    assert failed.validation_output == 'invalid configuration'
    assert change_service.cancel_change(change.id, group_id=1).status == 'cancelled'
    with pytest.raises(RoxywiConflictError):
        change_service.cancel_change(change.id, group_id=1)


def test_approval_is_rejected_when_not_requested(managed_server, tmp_path):
    change = _db_change(managed_server, tmp_path, status='validated', requires_approval=0)

    with pytest.raises(RoxywiConflictError, match='does not require approval'):
        change_service.approve_change(change.id, approver_id=2, group_id=1)


def test_deploy_runs_post_check_and_saves_successful_version(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='validated')
    saved_versions = []
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Uploaded')
    monkeypatch.setattr(change_service, '_post_deploy_check', lambda *_args: 'Service is active')
    monkeypatch.setattr(
        change_service,
        '_save_successful_version',
        lambda *args: saved_versions.append(args),
    )

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'
    assert 'Service is active' in deployed.deployment_output
    assert deployed.deployed_at is not None
    assert len(saved_versions) == 1


def test_deploy_rejects_change_that_is_not_ready(managed_server, tmp_path):
    change = _db_change(managed_server, tmp_path, status='draft')

    with pytest.raises(RoxywiConflictError, match='not ready'):
        change_service.deploy_change(change.id, group_id=1)


def test_candidate_validation_checks_master_and_slave(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path)
    slave = SimpleNamespace(
        ip='192.0.2.241',
        hostname='change-center-slave',
        server_id=managed_server.server_id + 1,
    )
    validated_ips = []
    monkeypatch.setattr(change_service, '_target_servers', lambda _server: [managed_server, slave])
    monkeypatch.setattr(
        change_service.config_mod,
        'validate_candidate_config',
        lambda ip, *_args, **_kwargs: validated_ips.append(ip) or 'Configuration file is valid',
    )

    output = change_service._upload(change, change.draft_path, 'test')

    assert validated_ips == [managed_server.ip, slave.ip]
    assert managed_server.hostname in output
    assert slave.hostname in output


def test_target_server_resolution_uses_server_ip_lookup(managed_server, monkeypatch):
    slave = SimpleNamespace(ip='192.0.2.241', hostname='slave')
    monkeypatch.setattr(
        change_service.server_sql,
        'is_master',
        lambda _ip: [('', 'ignored'), (slave.ip, slave.hostname)],
    )
    monkeypatch.setattr(
        change_service.server_sql,
        'get_server_by_ip',
        lambda ip: slave if ip == slave.ip else None,
    )

    assert change_service._target_servers(managed_server) == [managed_server, slave]


def test_change_creation_captures_cluster_topology_and_per_node_snapshots(
    cluster_servers, monkeypatch
):
    slaves, master = cluster_servers

    def get_config(server_ip, destination, **_kwargs):
        Path(destination).write_text(f'# running on {server_ip}\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    change = change_service.create_change(
        ConfigChangeCreate(
            server_id=master.server_id,
            service='haproxy',
            config='global\n  daemon\n',
            title='Cluster rollout',
        ),
        user_id=1,
        group_id=1,
    )

    targets = change_sql.list_targets(change.id)

    assert [target.server_id for target in targets] == [
        slaves[0].server_id,
        slaves[1].server_id,
        master.server_id,
    ]
    assert [target.role for target in targets] == ['slave', 'slave', 'master']
    assert all(Path(target.rollback_path).is_file() for target in targets)
    assert len({target.rollback_path for target in targets}) == 3
    assert Path(targets[0].rollback_path).read_text(encoding='utf-8') == (
        f'# running on {slaves[0].ip}\n'
    )
    assert change_service.serialize_change(change)['targets'][2]['role'] == 'master'


def test_cluster_validation_records_each_node_and_reports_all_results(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path)
    _seed_rollout_targets(change, master, tmp_path)
    checked_ips = []

    def validate(server_ip, *_args, **_kwargs):
        checked_ips.append(server_ip)
        if server_ip == slaves[0].ip:
            raise RuntimeError('candidate rejected')
        return 'Configuration is valid'

    monkeypatch.setattr(change_service.config_mod, 'validate_candidate_config', validate)

    with pytest.raises(RoxywiValidationError, match='candidate rejected'):
        change_service.validate_change(change.id, group_id=1)

    targets = change_sql.list_targets(change.id)
    assert checked_ips == [slaves[0].ip, slaves[1].ip, master.ip]
    assert [target.status for target in targets] == [
        'validation_failed', 'validated', 'validated'
    ]
    assert ConfigChange.get_by_id(change.id).status == 'validation_failed'


def test_cluster_deploys_slaves_then_master_and_records_per_node_success(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='validated')
    _seed_rollout_targets(change, master, tmp_path)
    applied_ips = []

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(
        change_service.config_mod,
        'upload_and_restart',
        lambda server_ip, *_args, **_kwargs: applied_ips.append(server_ip) or 'Uploaded',
    )

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert applied_ips == [slaves[0].ip, slaves[1].ip, master.ip]
    assert deployed.status == 'deployed'
    assert [target.status for target in change_sql.list_targets(change.id)] == [
        'deployed', 'deployed', 'deployed'
    ]
    assert master.hostname in deployed.deployment_output


def test_parallel_cluster_deploys_all_nodes_concurrently_without_threaded_db_writes(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(
        master, tmp_path, status='validated', execution_mode='parallel'
    )
    targets = _seed_rollout_targets(change, master, tmp_path)
    started = []
    upload_threads = set()
    normalization_calls = []
    worker_normalization_flags = []
    database_write_threads = set()
    lock = Lock()
    barrier = Barrier(len(targets), timeout=3)
    main_thread = get_ident()
    original_update_target = change_sql.update_target

    def upload(server_ip, *_args, **kwargs):
        with lock:
            started.append(server_ip)
            upload_threads.add(get_ident())
            worker_normalization_flags.append(kwargs.get('normalize_config'))
        barrier.wait()
        return 'Uploaded'

    def update_target(*args, **kwargs):
        database_write_threads.add(get_ident())
        return original_update_target(*args, **kwargs)

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(
        change_service.config_mod,
        'normalize_config_file',
        lambda path: normalization_calls.append(path),
    )
    monkeypatch.setattr(change_service.config_mod, 'upload_and_restart', upload)
    monkeypatch.setattr(change_service.change_sql, 'update_target', update_target)

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'
    assert set(started) == {slaves[0].ip, slaves[1].ip, master.ip}
    assert len(upload_threads) == len(targets)
    assert normalization_calls == [change.draft_path]
    assert worker_normalization_flags == [False] * len(targets)
    assert database_write_threads == {main_thread}
    assert all(
        target.status == 'deployed'
        for target in change_sql.list_targets(change.id)
    )


def test_parallel_cluster_failure_rolls_back_every_started_node(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(
        master, tmp_path, status='validated', execution_mode='parallel'
    )
    targets = _seed_rollout_targets(change, master, tmp_path)
    operations = []
    lock = Lock()
    barrier = Barrier(len(targets), timeout=3)

    def upload(server_ip, local_path, *_args, **_kwargs):
        operation = 'deploy' if Path(local_path) == Path(change.draft_path) else 'rollback'
        with lock:
            operations.append((server_ip, operation))
        if operation == 'deploy':
            barrier.wait()
            if server_ip == slaves[1].ip:
                raise RuntimeError('parallel node failed')
        return 'Applied'

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service.config_mod, 'normalize_config_file', lambda *_args: None)
    monkeypatch.setattr(change_service.config_mod, 'upload_and_restart', upload)

    with pytest.raises(RoxywiValidationError, match='restored automatically'):
        change_service.deploy_change(change.id, group_id=1)

    deployed_ips = {
        server_ip for server_ip, operation in operations if operation == 'deploy'
    }
    rollback_ips = [
        server_ip for server_ip, operation in operations if operation == 'rollback'
    ]
    assert deployed_ips == {slaves[0].ip, slaves[1].ip, master.ip}
    assert rollback_ips == [master.ip, slaves[1].ip, slaves[0].ip]
    assert ConfigChange.get_by_id(change.id).status == 'auto_rolled_back'
    assert all(
        target.status == 'rolled_back'
        for target in change_sql.list_targets(change.id)
    )


def test_interrupted_cluster_deployment_resumes_from_each_targets_remote_state(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='deployment_interrupted')
    targets = _seed_rollout_targets(change, master, tmp_path)
    change_sql.update_target(targets[0].id, status='deployed')
    change_sql.update_target(targets[1].id, status='deployment_interrupted')
    candidate = Path(change.draft_path).read_bytes()
    originals = {
        target.server_ip: Path(target.rollback_path).read_bytes()
        for target in targets
    }
    applied_ips = []
    checked_ips = []

    def get_config(server_ip, destination, **_kwargs):
        current = candidate if server_ip in (slaves[0].ip, slaves[1].ip) else originals[server_ip]
        Path(destination).write_bytes(current)

    def check_target(_change, target, _target_count):
        checked_ips.append(target.server_ip)
        return 'Service is active'

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', check_target)
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(
        change_service.config_mod,
        'upload_and_restart',
        lambda server_ip, *_args, **_kwargs: applied_ips.append(server_ip) or 'Uploaded',
    )

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'
    assert applied_ips == [slaves[1].ip, master.ip]
    assert checked_ips == [slaves[0].ip, slaves[1].ip, master.ip]
    assert all(
        target.status == 'deployed'
        for target in change_sql.list_targets(change.id)
    )


def test_parallel_resume_skips_confirmed_node_and_runs_remaining_nodes_together(
    cluster_servers, tmp_path, monkeypatch
):
    _slaves, master = cluster_servers
    change = _db_change(
        master,
        tmp_path,
        status='deployment_interrupted',
        execution_mode='parallel',
    )
    targets = _seed_rollout_targets(change, master, tmp_path)
    change_sql.update_target(targets[0].id, status='deployed')
    candidate = Path(change.draft_path).read_bytes()
    started = []
    lock = Lock()
    barrier = Barrier(len(targets) - 1, timeout=3)

    def get_config(server_ip, destination, **_kwargs):
        target = next(item for item in targets if item.server_ip == server_ip)
        content = candidate if target.id == targets[0].id else Path(target.rollback_path).read_bytes()
        Path(destination).write_bytes(content)

    def upload(server_ip, *_args, **_kwargs):
        with lock:
            started.append(server_ip)
        barrier.wait()
        return 'Uploaded'

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(change_service.config_mod, 'normalize_config_file', lambda *_args: None)
    monkeypatch.setattr(change_service.config_mod, 'upload_and_restart', upload)

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'
    assert set(started) == {targets[1].server_ip, targets[2].server_ip}
    assert targets[0].server_ip not in started
    assert all(
        target.status == 'deployed'
        for target in change_sql.list_targets(change.id)
    )


def test_interrupted_deployment_still_rejects_unrelated_remote_changes(
    cluster_servers, tmp_path, monkeypatch
):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='deployment_interrupted')
    _seed_rollout_targets(change, master, tmp_path)

    def get_config(_server_ip, destination, **_kwargs):
        Path(destination).write_text('global\n  externally-changed\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)

    with pytest.raises(RoxywiConflictError, match='differs from both'):
        change_service.deploy_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'deployment_interrupted'


def test_cluster_failure_stops_rollout_and_rolls_back_only_affected_nodes_in_reverse_order(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='validated')
    targets = _seed_rollout_targets(change, master, tmp_path)
    operations = []

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')

    def upload(server_ip, local_path, *_args, **_kwargs):
        is_candidate = Path(local_path) == Path(change.draft_path)
        operations.append((server_ip, 'deploy' if is_candidate else 'rollback'))
        if is_candidate and server_ip == slaves[1].ip:
            raise RuntimeError('second slave failed')
        return 'Applied'

    monkeypatch.setattr(change_service.config_mod, 'upload_and_restart', upload)

    with pytest.raises(RoxywiValidationError, match='restored automatically'):
        change_service.deploy_change(change.id, group_id=1)

    assert operations == [
        (slaves[0].ip, 'deploy'),
        (slaves[1].ip, 'deploy'),
        (slaves[1].ip, 'rollback'),
        (slaves[0].ip, 'rollback'),
    ]
    assert [target.status for target in change_sql.list_targets(change.id)] == [
        'rolled_back', 'rolled_back', 'skipped'
    ]
    assert ConfigChange.get_by_id(change.id).status == 'auto_rolled_back'
    assert master.ip not in [server_ip for server_ip, _action in operations]
    assert targets[0].rollback_path != targets[1].rollback_path


def test_manual_cluster_rollback_runs_in_reverse_deployment_order(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='deployed')
    targets = _seed_rollout_targets(change, master, tmp_path, status='deployed')
    rolled_back_ips = []

    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(change_service.config_mod, 'diff_config', lambda *_args: 'reverse diff')
    monkeypatch.setattr(
        change_service.config_mod,
        'upload_and_restart',
        lambda server_ip, *_args, **_kwargs: rolled_back_ips.append(server_ip) or 'Restored',
    )

    rolled_back = change_service.rollback_change(change.id, group_id=1)

    assert rolled_back_ips == [master.ip, slaves[1].ip, slaves[0].ip]
    assert rolled_back.status == 'rolled_back'
    assert all(target.status == 'rolled_back' for target in change_sql.list_targets(change.id))
    assert len(targets) == 3


def test_rollout_rejects_topology_changes_before_validation(
    cluster_servers, tmp_path
):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path)
    _seed_rollout_targets(change, master, tmp_path)
    Server.create(
        hostname='late-slave',
        ip='192.0.2.249',
        group_id='1',
        enabled=1,
        haproxy=1,
        master=master.server_id,
    )

    with pytest.raises(RoxywiConflictError, match='topology changed'):
        change_service.validate_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'draft'


def test_keepalived_rollout_does_not_copy_node_specific_config_to_slaves(cluster_servers):
    _slaves, master = cluster_servers

    assert change_service._rollout_servers(master, 'keepalived') == [(master, 'standalone')]


def test_multi_config_service_uses_requested_remote_path(monkeypatch):
    checked_paths = []
    monkeypatch.setattr(
        change_service.config_mod,
        '_replace_config_path_to_correct',
        lambda path: f'/etc/nginx/{path}',
    )
    monkeypatch.setattr(
        change_service.common,
        'check_is_conf',
        lambda path: checked_paths.append(path),
    )

    assert change_service._remote_path('nginx', 'conf.d/app.conf') == '/etc/nginx/conf.d/app.conf'
    assert checked_paths == ['/etc/nginx/conf.d/app.conf']


def test_remote_apply_uses_service_specific_uploader_and_rejects_error_output(
    managed_server, tmp_path, monkeypatch
):
    haproxy_change = _db_change(managed_server, tmp_path, service='haproxy')
    monkeypatch.setattr(
        change_service.config_mod,
        'master_slave_upload_and_restart',
        lambda *_args, **_kwargs: 'server: error: reload failed',
    )
    with pytest.raises(RuntimeError, match='reload failed'):
        change_service._upload(haproxy_change, haproxy_change.draft_path, 'reload')

    keepalived_change = _db_change(
        managed_server,
        tmp_path,
        service='keepalived',
        title='Keepalived change',
    )
    calls = []
    monkeypatch.setattr(
        change_service.config_mod,
        'upload_and_restart',
        lambda *args, **kwargs: calls.append((args, kwargs)) or 'Applied',
    )

    assert change_service._upload(
        keepalived_change, keepalived_change.draft_path, 'restart'
    ) == 'Applied'
    assert calls[0][0][0] == managed_server.ip


@pytest.mark.parametrize(
    ('dockerized', 'ssh_output', 'expected_command_part', 'expected'),
    (
        ('0', '\x1b[32mactive\x1b[0m\n', 'systemctl is-active', True),
        ('0', 'inactive\n', 'systemctl is-active', False),
        ('1', 'true\n', 'docker inspect', True),
    ),
)
def test_service_state_check_supports_systemd_and_docker(
    managed_server, monkeypatch, dockerized, ssh_output, expected_command_part, expected
):
    commands = []
    monkeypatch.setattr(
        change_service.service_sql,
        'select_service_setting',
        lambda *_args: dockerized,
    )
    monkeypatch.setattr(change_service.sql, 'get_setting', lambda *_args: 'haproxy-main')
    monkeypatch.setattr(
        change_service.service_common,
        'get_correct_service_name',
        lambda *_args: 'haproxy.service',
    )
    monkeypatch.setattr(
        change_service.server_mod,
        'ssh_command',
        lambda _ip, command: commands.append(command) or ssh_output,
    )

    assert change_service._is_service_active(managed_server, 'haproxy') is expected
    assert expected_command_part in commands[0]


def test_post_deploy_check_supports_save_and_detects_inactive_service(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(managed_server, tmp_path, action='save')
    checks = []
    monkeypatch.setattr(
        change_service.service_common,
        'check_service_config',
        lambda *args: checks.append(args),
    )

    assert 'configuration is valid' in change_service._post_deploy_check(change)
    assert len(checks) == 1

    change.action = 'reload'
    monkeypatch.setattr(change_service, '_is_service_active', lambda *_args: False)
    with pytest.raises(RuntimeError, match='not active after deployment'):
        change_service._post_deploy_check(change)


def test_restart_action_does_not_require_reload_preflight(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, action='restart')
    monkeypatch.setattr(
        change_service,
        '_is_service_active',
        lambda *_args: (_ for _ in ()).throw(AssertionError('must not be called')),
    )

    change_service._ensure_action_ready(change)


def test_failed_deploy_automatically_restores_snapshot(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='validated')
    uploaded_paths = []
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)

    def upload(_change, local_path, _action):
        uploaded_paths.append(local_path)
        if local_path == change.draft_path:
            raise RuntimeError('reload failed')
        return 'Previous configuration restored'

    monkeypatch.setattr(change_service, '_upload', upload)
    monkeypatch.setattr(change_service, '_post_deploy_check', lambda *_args: 'Service is active')

    with pytest.raises(RoxywiValidationError, match='restored automatically'):
        change_service.deploy_change(change.id, group_id=1)

    restored = ConfigChange.get_by_id(change.id)
    assert restored.status == 'auto_rolled_back'
    assert restored.rollback_output.endswith('Service is active')
    assert uploaded_paths == [change.draft_path, change.rollback_path]


def test_failed_deploy_reports_failed_automatic_rollback_concisely(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='validated')
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('remote operation failed with verbose output')),
    )

    with pytest.raises(RoxywiValidationError) as exception:
        change_service.deploy_change(change.id, group_id=1)

    assert 'Automatic rollback also failed' in str(exception.value)
    assert len(str(exception.value)) < 400
    failed = ConfigChange.get_by_id(change.id)
    assert failed.status == 'auto_rollback_failed'
    assert 'verbose output' in failed.deployment_output
    assert 'verbose output' in failed.rollback_output


@pytest.mark.parametrize('retry_status', ('auto_rolled_back', 'auto_rollback_failed', 'rollback_failed'))
def test_failed_deployment_can_be_retried(
    managed_server, tmp_path, monkeypatch, retry_status
):
    change = _db_change(managed_server, tmp_path, status=retry_status)
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Uploaded')
    monkeypatch.setattr(change_service, '_post_deploy_check', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'


def test_approved_change_can_be_retried_without_second_approval(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(
        managed_server,
        tmp_path,
        status='auto_rolled_back',
        requires_approval=1,
        approved_by=2,
    )
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Uploaded')
    monkeypatch.setattr(change_service, '_post_deploy_check', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)

    deployed = change_service.deploy_change(change.id, group_id=1)

    assert deployed.status == 'deployed'
    assert deployed.approved_by == 2


def test_reload_preflight_does_not_modify_inactive_service(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='validated', action='reload')
    uploaded_paths = []
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_is_service_active', lambda *_args: False)
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda _change, local_path, _action: uploaded_paths.append(local_path),
    )

    with pytest.raises(RoxywiConflictError, match='not active'):
        change_service.deploy_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'validated'
    assert uploaded_paths == []


def test_reload_preflight_reports_state_check_error_without_modifying_service(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(managed_server, tmp_path, status='validated', action='reload')
    uploaded_paths = []
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(
        change_service,
        '_is_service_active',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('\x1b[31mSSH connection failed\x1b[0m')),
    )
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda _change, local_path, _action: uploaded_paths.append(local_path),
    )

    with pytest.raises(RoxywiValidationError, match='SSH connection failed'):
        change_service.deploy_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'validated'
    assert uploaded_paths == []


def test_deploy_rejects_configuration_drift_without_upload(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='validated')
    uploaded_paths = []

    def get_config(_server_ip, destination, **_kwargs):
        Path(destination).write_text('global\n  changed-outside-roxy-wi\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda _change, local_path, _action: uploaded_paths.append(local_path),
    )

    with pytest.raises(Exception, match='changed after this draft was created'):
        change_service.deploy_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'validated'
    assert uploaded_paths == []


def test_deploy_rejects_missing_original_snapshot(managed_server, tmp_path):
    change = _db_change(managed_server, tmp_path, status='validated')
    Path(change.rollback_path).unlink()

    with pytest.raises(RoxywiConflictError, match='snapshot is no longer available'):
        change_service.deploy_change(change.id, group_id=1)


def test_manual_rollback_restores_snapshot_and_records_version(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(managed_server, tmp_path, status='deployed')
    saved_versions = []
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Snapshot uploaded')
    monkeypatch.setattr(change_service, '_post_deploy_check', lambda *_args: 'Service is active')
    monkeypatch.setattr(change_service.config_mod, 'diff_config', lambda *_args: 'reverse diff')
    monkeypatch.setattr(
        change_service,
        '_save_successful_version',
        lambda *args: saved_versions.append(args),
    )

    rolled_back = change_service.rollback_change(change.id, group_id=1)

    assert rolled_back.status == 'rolled_back'
    assert rolled_back.rollback_output == 'Snapshot uploaded\nService is active'
    assert saved_versions[0][2] == 'reverse diff'


def test_manual_rollback_failure_is_retryable(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path, status='deployed')
    monkeypatch.setattr(
        change_service,
        '_upload',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('restore failed')),
    )

    with pytest.raises(RoxywiValidationError, match='restore failed'):
        change_service.rollback_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'rollback_failed'


def test_successful_version_is_copied_and_recorded(managed_server, tmp_path, monkeypatch):
    change = _db_change(managed_server, tmp_path)
    version_path = tmp_path / 'versions' / 'haproxy.cfg'
    inserted = []
    monkeypatch.setattr(
        change_service.config_common,
        'generate_config_path',
        lambda *_args: str(version_path),
    )
    monkeypatch.setattr(
        change_service.config_sql,
        'insert_config_version',
        lambda *args, **kwargs: inserted.append((args, kwargs)),
    )

    change_service._save_successful_version(
        change,
        change.draft_path,
        change.diff,
        'Recorded change',
    )

    saved_path = Path(inserted[0][0][3])
    assert saved_path.read_text(encoding='utf-8') == Path(change.draft_path).read_text(encoding='utf-8')
    assert inserted[0][1]['message'] == 'Recorded change'


def test_change_serialization_tolerates_deleted_server_and_user(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(managed_server, tmp_path, approved_by=999)
    monkeypatch.setattr(
        change_service.server_sql,
        'get_server',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('server removed')),
    )
    monkeypatch.setattr(
        change_service.user_sql,
        'get_user_id',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('user removed')),
    )

    serialized = change_service.serialize_change(change)

    assert serialized['server_name'] is None
    assert serialized['server_ip'] is None
    assert serialized['created_by'] is None
    assert serialized['approved_by_name'] is None


@pytest.mark.parametrize(
    ('operation_status', 'recovered_status', 'output_field'),
    (
        ('validating', 'validation_failed', 'validation_output'),
        ('deploying', 'deployment_interrupted', 'deployment_output'),
        ('rolling_back', 'rollback_failed', 'rollback_output'),
    ),
)
def test_stale_change_operation_can_be_recovered_without_remote_action(
    managed_server,
    tmp_path,
    operation_status,
    recovered_status,
    output_field,
):
    change = _db_change(
        managed_server,
        tmp_path,
        status=operation_status,
        updated_at=datetime.now() - timedelta(minutes=6),
        **{output_field: 'Output recorded before interruption'},
    )

    assert change_service.serialize_change(change)['recoverable'] is True

    recovered = change_service.recover_change(change.id, group_id=1)

    assert recovered.status == recovered_status
    output = getattr(recovered, output_field)
    assert 'Output recorded before interruption' in output
    assert 'interrupted and unlocked' in output


def test_stale_recovery_marks_only_the_in_progress_rollout_target(
    managed_server, tmp_path
):
    change = _db_change(
        managed_server,
        tmp_path,
        status='deploying',
        updated_at=datetime.now() - timedelta(minutes=6),
    )
    targets = _seed_rollout_targets(change, managed_server, tmp_path)
    change_sql.update_target(targets[0].id, status='deploying')
    ConfigChange.update(
        updated_at=datetime.now() - timedelta(minutes=6)
    ).where(ConfigChange.id == change.id).execute()

    change_service.recover_change(change.id, group_id=1)

    recovered_target = change_sql.get_target(targets[0].id)
    assert recovered_target.status == 'deployment_interrupted'
    assert 'interrupted and unlocked' in recovered_target.deployment_output


def test_active_change_operation_cannot_be_recovered_before_timeout(
    managed_server, tmp_path
):
    change = _db_change(
        managed_server,
        tmp_path,
        status='rolling_back',
        updated_at=datetime.now(),
    )

    assert change_service.serialize_change(change)['recoverable'] is False
    with pytest.raises(RoxywiConflictError, match='five-minute recovery timeout'):
        change_service.recover_change(change.id, group_id=1)

    assert ConfigChange.get_by_id(change.id).status == 'rolling_back'


def test_sqlite_waits_briefly_for_concurrent_writes():
    database = connect()

    if database.__class__.__name__ == 'SqliteExtDatabase':
        assert dict(database._pragmas)['busy_timeout'] == 5000


def test_change_writes_retry_transient_sqlite_lock(monkeypatch):
    attempts = []
    delays = []

    def operation():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise OperationalError('database is locked')
        return 'written'

    monkeypatch.setattr(change_sql, 'sleep', lambda delay: delays.append(delay))

    assert change_sql._execute_write(operation) == 'written'
    assert attempts == [1, 2, 3]
    assert delays == list(change_sql._LOCK_RETRY_DELAYS[:2])


def test_change_writes_are_serialized_within_the_process():
    first_entered = Event()
    release_first = Event()
    second_started = Event()
    second_entered = Event()

    def first_operation():
        first_entered.set()
        assert release_first.wait(timeout=2)

    def second_operation():
        second_entered.set()

    first_thread = Thread(target=lambda: change_sql._execute_write(first_operation))
    second_thread = Thread(
        target=lambda: (
            second_started.set(),
            change_sql._execute_write(second_operation),
        )
    )
    first_thread.start()
    assert first_entered.wait(timeout=2)
    second_thread.start()
    assert second_started.wait(timeout=2)
    assert not second_entered.wait(timeout=0.1)

    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_entered.is_set()


def test_change_write_returns_clear_conflict_after_lock_retries_are_exhausted(monkeypatch):
    attempts = []
    monkeypatch.setattr(change_sql, 'sleep', lambda _delay: None)

    def locked_operation():
        attempts.append(1)
        raise OperationalError('database is locked')

    with pytest.raises(RoxywiConflictError, match='database is busy'):
        change_sql._execute_write(locked_operation)

    assert len(attempts) == len(change_sql._LOCK_RETRY_DELAYS) + 1


def test_target_status_and_parent_heartbeat_are_updated_together(
    managed_server, tmp_path
):
    old_heartbeat = datetime.now() - timedelta(days=1)
    change = _db_change(managed_server, tmp_path, updated_at=old_heartbeat)
    target = _seed_rollout_targets(change, managed_server, tmp_path)[0]

    updated_target = change_sql.update_target(target.id, status='deploying')
    updated_change = change_sql.get_change(change.id)

    assert updated_target.status == 'deploying'
    assert updated_change.updated_at > old_heartbeat
    assert updated_change.updated_at == updated_target.updated_at


def test_change_repository_filters_and_rejects_stale_transition(managed_server, tmp_path):
    draft = _db_change(managed_server, tmp_path, title='Draft', status='draft')
    _db_change(managed_server, tmp_path, title='Validated', status='validated')

    listed = list(change_sql.list_changes(1, service='haproxy', status='draft'))

    assert [change.id for change in listed] == [draft.id]
    assert change_sql.get_change(draft.id).title == 'Draft'
    with pytest.raises(RoxywiResourceNotFound):
        change_sql.get_change(999999)
    with pytest.raises(ValueError, match='Unsupported change fields'):
        change_sql.update_change(draft.id, server_id=999)
    with pytest.raises(ValueError, match='Unsupported change fields'):
        change_sql.transition_change(draft.id, ('draft',), 'validated', server_id=999)
    with pytest.raises(RoxywiConflictError, match='no longer in a state'):
        change_sql.transition_change(draft.id, ('approved',), 'deploying')


def test_change_center_migration_creates_and_drops_workflow_table(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260823000000_add_config_changes'
    )
    calls = []
    connection = SimpleNamespace(
        create_tables=lambda models, **kwargs: calls.append(('up', models, kwargs)),
        drop_tables=lambda models, **kwargs: calls.append(('down', models, kwargs)),
    )
    monkeypatch.setattr(migration, 'connect', lambda: connection)

    migration.up()
    migration.down()

    assert calls == [
        ('up', [ConfigChange], {'safe': True}),
        ('down', [ConfigChange], {'safe': True}),
    ]


def test_cluster_rollout_migration_creates_and_drops_target_table(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260824000000_add_config_change_targets'
    )
    calls = []
    connection = SimpleNamespace(
        create_tables=lambda models, **kwargs: calls.append(('up', models, kwargs)),
        drop_tables=lambda models, **kwargs: calls.append(('down', models, kwargs)),
    )
    monkeypatch.setattr(migration, 'connect', lambda: connection)

    migration.up()
    migration.down()

    assert calls == [
        ('up', [ConfigChangeTarget], {'safe': True}),
        ('down', [ConfigChangeTarget], {'safe': True}),
    ]


def test_execution_mode_migration_adds_and_removes_column(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260824010000_add_change_execution_mode'
    )
    operations = []
    migrator = SimpleNamespace(
        add_column=lambda table, column, field: ('add', table, column, field),
        drop_column=lambda table, column: ('drop', table, column),
    )
    monkeypatch.setattr(migration, '_has_column', lambda: len(operations) == 1)
    monkeypatch.setattr(migration, 'connect', lambda **_kwargs: migrator)
    monkeypatch.setattr(migration, 'migrate', lambda operation: operations.append(operation))

    migration.up()
    migration.down()

    assert operations[0][0:3] == ('add', 'config_changes', 'execution_mode')
    assert operations[1] == ('drop', 'config_changes', 'execution_mode')


def test_advanced_rollout_migration_adds_and_removes_all_columns(monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260829000000_add_advanced_change_rollout'
    )
    operations = []
    migrator = SimpleNamespace(
        add_column=lambda table, column, field: ('add', table, column, field),
        drop_column=lambda table, column: ('drop', table, column),
    )
    monkeypatch.setattr(migration, 'connect', lambda **_kwargs: migrator)
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
    removed = operations[len(added):]

    assert len(added) == len(migration.CHANGE_COLUMNS) + len(migration.TARGET_COLUMNS)
    assert len(removed) == len(added)
    assert all(operation[0] == 'add' for operation in added)
    assert all(operation[0] == 'drop' for operation in removed)


def test_change_is_isolated_to_active_group(managed_server, tmp_path):
    change = _db_change(managed_server, tmp_path)
    with pytest.raises(RoxywiPermissionError, match='active group'):
        change_service.validate_change(change.id, group_id=2)


def test_config_version_is_written_only_after_successful_apply(app, managed_server, tmp_path, monkeypatch):
    config_path = tmp_path / 'candidate.cfg'
    config_path.write_text('global\n', encoding='utf-8')
    versions = []
    monkeypatch.setattr(config_module, 'upload', lambda *_args: None)
    monkeypatch.setattr(config_module.subprocess, 'run', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(config_module, '_generate_command', lambda *_args: 'validate-and-apply')
    monkeypatch.setattr(config_module, '_prepare_config_version_diff', lambda *_args: 'diff')
    monkeypatch.setattr(config_module, '_create_config_version', lambda *args, **kwargs: versions.append((args, kwargs)))
    monkeypatch.setattr(config_module.server_mod, 'ssh_command', lambda *_args, **_kwargs: '{"status":"ok"}')

    with app.test_request_context('/'):
        g.user_params = {'user_id': 1}
        config_module.upload_and_restart(
            managed_server.ip, str(config_path), 'test', 'haproxy'
        )
        assert versions == []

        config_module.upload_and_restart(
            managed_server.ip, str(config_path), 'reload', 'haproxy'
        )

    assert len(versions) == 1


def test_failed_remote_apply_does_not_create_config_version(app, managed_server, tmp_path, monkeypatch):
    config_path = tmp_path / 'invalid.cfg'
    config_path.write_text('invalid\n', encoding='utf-8')
    versions = []
    monkeypatch.setattr(config_module, 'upload', lambda *_args: None)
    monkeypatch.setattr(config_module.subprocess, 'run', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(config_module, '_generate_command', lambda *_args: 'validate-and-apply')
    monkeypatch.setattr(config_module, '_prepare_config_version_diff', lambda *_args: 'diff')
    monkeypatch.setattr(config_module, '_create_config_version', lambda *args, **kwargs: versions.append((args, kwargs)))
    monkeypatch.setattr(
        config_module.server_mod,
        'ssh_command',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('validation failed')),
    )

    with app.test_request_context('/'):
        g.user_params = {'user_id': 1}
        with pytest.raises(Exception, match='Cannot reload haproxy'):
            config_module.upload_and_restart(
                managed_server.ip, str(config_path), 'reload', 'haproxy'
            )

    assert versions == []


def test_upload_without_version_history_does_not_require_request_context(
    managed_server, tmp_path, monkeypatch
):
    config_path = tmp_path / 'background.cfg'
    config_path.write_text('global\n', encoding='utf-8')
    monkeypatch.setattr(config_module, 'upload', lambda *_args: None)
    monkeypatch.setattr(config_module, '_generate_command', lambda *_args: 'apply')
    monkeypatch.setattr(config_module.server_mod, 'ssh_command', lambda *_args, **_kwargs: '{"status":"ok"}')
    monkeypatch.setattr(config_module.roxywi_common, 'logging', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        config_module,
        '_create_config_version',
        lambda *_args, **_kwargs: pytest.fail('version history must remain disabled'),
    )

    result = config_module.upload_and_restart(
        managed_server.ip,
        str(config_path),
        'reload',
        'haproxy',
        record_version=False,
        normalize_config=False,
        user_id=1,
    )

    assert result == 'Haproxy'


def test_nginx_candidate_validation_restores_original_file(managed_server, tmp_path, monkeypatch):
    candidate = tmp_path / 'nginx.conf'
    candidate.write_text('events {}\n', encoding='utf-8')
    commands = []
    monkeypatch.setattr(config_module, 'upload', lambda *_args: None)
    monkeypatch.setattr(config_module.subprocess, 'run', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        config_module.service_sql,
        'select_service_setting',
        lambda *_args: '0',
    )
    monkeypatch.setattr(
        config_module.server_mod,
        'ssh_command',
        lambda _ip, command, **_kwargs: commands.append(command) or '',
    )

    result = config_module.validate_candidate_config(
        managed_server.ip,
        str(candidate),
        'nginx',
        config_file_name='/etc/nginx/nginx.conf',
    )

    assert result == 'Nginx configuration is valid'
    assert 'sudo cp -p /etc/nginx/nginx.conf' in commands[0]
    assert 'sudo nginx -t' in commands[0]
    assert commands[0].count('/etc/nginx/nginx.conf') == 3
    assert 'exit $validation_rc' in commands[0]


def test_change_center_page_is_available_to_authenticated_editor(app, client, monkeypatch):
    monkeypatch.setattr(
        change_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'support'},
    )
    monkeypatch.setattr(
        'app.routes.change.routes.render_template',
        lambda template, **_kwargs: template,
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})

    response = client.get('/changes', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'change_center.html'


@pytest.mark.parametrize(
    ('subscription', 'expected'),
    (
        ({'user_status': 1, 'user_plan': 'support'}, True),
        ({'user_status': 1, 'user_plan': 'company'}, False),
        ({'user_status': 1, 'user_plan': 'cloud'}, False),
        ({'user_status': 1, 'user_plan': 'user'}, False),
        ({'user_status': 1, 'user_plan': 'Trial'}, False),
        ({'user_status': 0, 'user_plan': 'support'}, False),
    ),
)
def test_change_center_requires_exact_active_premium_plan(subscription, expected):
    assert change_access.is_change_center_available(subscription) is expected


def test_change_center_menu_remains_visible_below_premium():
    menu = Path('app/templates/include/main_menu.html').read_text(encoding='utf-8')

    assert "url_for('change.index')" in menu
    assert "g.user_params['role'] <= 3 and change_center_available" not in menu


def test_change_center_template_has_premium_upgrade_state():
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')

    assert '{% if not change_center_available %}' in template
    assert 'lang.change_center.premium_required' in template
    assert 'https://roxy-wi.org/pricing' in template
    assert 'rel="noopener noreferrer"' in template


def test_change_center_templates_compile(app):
    assert app.jinja_env.get_template('change_center.html')
    for language in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'):
        assert app.jinja_env.get_template(f'languages/{language}.html')


def test_change_center_translation_catalogs_include_cluster_rollout_keys(app):
    with app.app_context():
        catalogs = [
            app.jinja_env.get_template(f'languages/{language}.html').module.change_center
            for language in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')
        ]

    expected_keys = set(catalogs[0])
    expected_statuses = set(catalogs[0]['statuses'])
    for catalog in catalogs:
        assert set(catalog) == expected_keys
        assert set(catalog['statuses']) == expected_statuses
        assert set(catalog['roles']) == {'master', 'slave', 'standalone'}
        assert set(catalog['execution_modes']) == {'rolling', 'parallel'}
        assert all(catalog[key] for key in ('rollout', 'node', 'role', 'result'))


def test_change_editor_exposes_rollout_execution_mode():
    template = Path('app/templates/config.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-editor.js').read_text(encoding='utf-8')
    details_template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    details_script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')

    assert 'id="change-execution-mode"' in template
    assert 'value="rolling" selected' in template
    assert 'value="parallel"' in template
    assert "execution_mode: $('#change-execution-mode').val()" in script
    assert 'data-execution-mode-rolling=' in details_template
    assert 'data-execution-mode-parallel=' in details_template
    assert 'change.execution_mode' in details_script


def test_change_center_uses_application_confirmation_dialog():
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')
    stylesheet = Path('app/static/css/change-center.css').read_text(encoding='utf-8')

    assert 'id="change-confirm-dialog"' in template
    assert "$('#change-confirm-dialog')" in script
    assert 'window.confirm' not in script
    for action in ('deploy', 'rollback', 'cancel', 'recover'):
        assert f'change-confirm-{action}' in stylesheet
        assert f'change-action-{action}' in stylesheet
    assert template.index('id="change-center-table"') < template.index('class="alert alert-info change-center-intro"')


def test_change_center_refreshes_icons_added_after_fontawesome_initialization():
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')

    assert 'function refreshActionIcons()' in script
    assert 'window.FontAwesome.dom.i2svg({node: tableBody.get(0)})' in script
    assert 'refreshActionIcons();' in script


def test_change_details_show_live_per_node_rollout_progress():
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')

    assert 'id="change-details-rollout"' in template
    assert 'change.targets' in script
    assert 'window.setInterval(loadChanges, 1500)' in script
    assert 'target.validation_output' in script
    assert 'target.deployment_output' in script
    assert 'target.rollback_output' in script


def test_every_change_status_has_an_explicit_background():
    stylesheet = Path('app/static/css/change-center.css').read_text(encoding='utf-8')
    statuses = (
        'draft',
        'validating',
        'validated',
        'validation_failed',
        'pending_approval',
        'approved',
        'deploying',
        'pause_requested',
        'paused',
        'awaiting_promotion',
        'deployment_interrupted',
        'deployed',
        'failed',
        'auto_rolled_back',
        'auto_rollback_failed',
        'rolling_back',
        'rolled_back',
        'rollback_failed',
        'cancelled',
        'pending',
        'skipped',
        'excluded',
        'deployment_failed',
    )

    for status in statuses:
        selector = f'.change-status-{status}'
        declaration = stylesheet.split(selector, maxsplit=1)[1].split('}', maxsplit=1)[0]
        assert 'background:' in declaration


def test_change_center_api_requires_authentication(client):
    response = client.get('/changes/api', headers={'Accept': 'application/json'})
    assert response.status_code == 401


def test_advanced_rollout_schema_validates_limits_and_target_sets():
    body = ConfigChangeCreate(
        server_id=1, service='haproxy', config='global\n', title='Advanced rollout',
        batch_size=3, max_parallel=4, manual_promotion=True,
        health_check_mode='service', health_check_retries=3, health_check_interval=2,
        canary_server_ids=[2], excluded_server_ids=[3],
    )
    assert (body.batch_size, body.max_parallel, body.manual_promotion) == (3, 4, True)

    with pytest.raises(ValueError, match='both canary and excluded'):
        ConfigChangeCreate(
            server_id=1, service='haproxy', config='global\n', title='Invalid rollout',
            canary_server_ids=[2], excluded_server_ids=[2],
        )
    with pytest.raises(ValueError):
        ConfigChangeCreate(
            server_id=1, service='haproxy', config='global\n',
            title='Too much concurrency', max_parallel=9,
        )


def test_rollout_plan_places_canaries_first_and_excluded_nodes_outside_batches(
    cluster_servers, tmp_path
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, execution_mode='rolling', batch_size=1)
    targets = _seed_rollout_targets(change, master, tmp_path)
    plan = change_service._prepare_rollout_plan(
        targets, execution_mode='rolling', batch_size=1,
        canary_server_ids=[slaves[1].server_id],
        excluded_server_ids=[slaves[0].server_id],
    )
    by_server = {target['server_id']: target for target in plan}

    assert by_server[slaves[1].server_id]['is_canary'] == 1
    assert by_server[slaves[1].server_id]['batch'] == 0
    assert by_server[slaves[0].server_id]['excluded'] == 1
    assert by_server[slaves[0].server_id]['batch'] == -1
    assert by_server[master.server_id]['batch'] == 1


def test_rollout_plan_rejects_master_canary_and_exclusion(cluster_servers, tmp_path):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path)
    targets = _seed_rollout_targets(change, master, tmp_path)

    with pytest.raises(RoxywiValidationError, match='Only slave nodes'):
        change_service._prepare_rollout_plan(
            targets, execution_mode='rolling', batch_size=1,
            canary_server_ids=[master.server_id],
        )
    with pytest.raises(RoxywiValidationError, match='cannot be excluded'):
        change_service._prepare_rollout_plan(
            targets, execution_mode='rolling', batch_size=1,
            excluded_server_ids=[master.server_id],
        )


def test_create_change_persists_advanced_rollout_settings(cluster_servers, monkeypatch):
    slaves, master = cluster_servers

    def get_config(server_ip, destination, **_kwargs):
        Path(destination).write_text(f'# {server_ip}\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    change = change_service.create_change(
        ConfigChangeCreate(
            server_id=master.server_id, service='haproxy', config='global\n  daemon\n',
            title='Canary rollout', batch_size=2, max_parallel=2,
            manual_promotion=True, health_check_mode='full',
            health_check_retries=3, health_check_interval=1,
            canary_server_ids=[slaves[1].server_id],
            excluded_server_ids=[slaves[0].server_id],
        ),
        user_id=1, group_id=1,
    )
    serialized = change_service.serialize_change(change)
    targets = {target['server_id']: target for target in serialized['targets']}

    assert serialized['batch_size'] == 2
    assert serialized['max_parallel'] == 2
    assert serialized['manual_promotion'] is True
    assert serialized['health_check_retries'] == 3
    assert change.pause_requested == 0
    assert targets[slaves[1].server_id]['is_canary'] is True
    assert targets[slaves[0].server_id]['excluded'] is True
    assert targets[master.server_id]['batch'] == 1


def test_create_change_does_not_contact_pre_excluded_unavailable_slave(
    cluster_servers, monkeypatch
):
    slaves, master = cluster_servers
    contacted = []

    def get_config(server_ip, destination, **_kwargs):
        contacted.append(server_ip)
        if server_ip == slaves[0].ip:
            raise RuntimeError('unavailable node was contacted')
        Path(destination).write_text(f'# {server_ip}\n', encoding='utf-8')

    monkeypatch.setattr(change_service.config_mod, 'get_config', get_config)
    change = change_service.create_change(
        ConfigChangeCreate(
            server_id=master.server_id,
            service='haproxy',
            config='global\n',
            title='Exclude offline slave',
            excluded_server_ids=[slaves[0].server_id],
        ),
        user_id=1,
        group_id=1,
    )
    excluded = next(
        target for target in change_sql.list_targets(change.id)
        if target.server_id == slaves[0].server_id
    )

    assert slaves[0].ip not in contacted
    assert excluded.excluded == 1
    assert not Path(excluded.rollback_path).exists()


def test_manual_canary_rollout_waits_for_each_promotion(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(
        master, tmp_path, status='validated', batch_size=1,
        max_parallel=1, manual_promotion=1,
    )
    targets = _seed_rollout_targets(change, master, tmp_path)
    change_sql.update_target(targets[1].id, is_canary=1)
    deployed_to = []

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(
        change_service, '_reconcile_interrupted_rollout',
        lambda item: change_sql.list_targets(item.id),
    )
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Healthy')
    monkeypatch.setattr(
        change_service.config_mod, 'upload_and_restart',
        lambda server_ip, *_args, **_kwargs: deployed_to.append(server_ip) or 'Uploaded',
    )

    first = change_service.deploy_change(change.id, group_id=1)
    assert first.status == 'awaiting_promotion'
    assert deployed_to == [slaves[1].ip]
    second = change_service.promote_change(change.id, group_id=1)
    assert second.status == 'awaiting_promotion'
    assert deployed_to == [slaves[1].ip, slaves[0].ip]
    completed = change_service.promote_change(change.id, group_id=1)
    assert completed.status == 'deployed'
    assert deployed_to == [slaves[1].ip, slaves[0].ip, master.ip]


def test_pause_request_stops_rollout_after_active_batch(
    cluster_servers, tmp_path, monkeypatch
):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='validated', batch_size=1, max_parallel=1)
    _seed_rollout_targets(change, master, tmp_path)
    original_batch = change_service._deploy_batch
    batch_calls = []

    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)
    monkeypatch.setattr(change_service, '_check_target', lambda *_args: 'Healthy')
    monkeypatch.setattr(change_service.config_mod, 'upload_and_restart', lambda *_args, **_kwargs: 'Uploaded')

    def deploy_one_batch(active_change, targets, all_targets):
        original_batch(active_change, targets, all_targets)
        batch_calls.append([target.id for target in targets])
        change_sql.update_change(active_change.id, status='pause_requested', pause_requested=1)

    monkeypatch.setattr(change_service, '_deploy_batch', deploy_one_batch)
    paused = change_service.deploy_change(change.id, group_id=1)

    assert paused.status == 'paused'
    assert len(batch_calls) == 1
    assert sum(target.status == 'deployed' for target in change_sql.list_targets(change.id)) == 1


def test_pause_and_promotion_transitions_are_guarded(managed_server, tmp_path):
    deploying = _db_change(managed_server, tmp_path, status='deploying')
    paused = change_service.pause_change(deploying.id, group_id=1)
    assert paused.status == 'pause_requested'
    assert paused.pause_requested == 1

    resumed = change_service.resume_change(deploying.id, group_id=1)
    assert resumed.status == 'deploying'
    assert resumed.pause_requested == 0

    ConfigChange.update(status='awaiting_promotion', pause_requested=0).where(
        ConfigChange.id == deploying.id
    ).execute()
    paused = change_service.pause_change(deploying.id, group_id=1)
    assert paused.status == 'paused'
    with pytest.raises(RoxywiConflictError):
        change_service.promote_change(deploying.id, group_id=1)


def test_health_checks_retry_and_can_be_disabled(managed_server, tmp_path, monkeypatch):
    change = _db_change(
        managed_server, tmp_path, health_check_retries=3, health_check_interval=2,
    )
    target = _seed_rollout_targets(change, managed_server, tmp_path)[0]
    attempts = []
    delays = []
    original_health_check = change_service._check_target

    def health_check(*_args):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError('not ready')
        return 'Healthy'

    monkeypatch.setattr(change_service, '_check_target', health_check)
    monkeypatch.setattr(change_service, 'sleep', lambda seconds: delays.append(seconds))

    assert 'attempt 3/3' in change_service._run_target_health_check(change, target, 1)
    assert len(attempts) == 3
    assert delays == [2, 2]
    change.health_check_mode = 'none'
    assert original_health_check(change, target, 1) == 'Post-deployment health checks are disabled'


def test_health_check_failure_is_persisted_on_target(
    managed_server, tmp_path, monkeypatch
):
    change = _db_change(
        managed_server, tmp_path, status='validated', health_check_retries=2,
    )
    target = _seed_rollout_targets(change, managed_server, tmp_path)[0]
    monkeypatch.setattr(change_service, '_ensure_base_unchanged', lambda *_args: None)
    monkeypatch.setattr(change_service, '_ensure_action_ready', lambda *_args: None)
    monkeypatch.setattr(change_service, '_upload', lambda *_args: 'Uploaded')
    monkeypatch.setattr(
        change_service, '_check_target',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('unhealthy')),
    )
    original_apply = change_service._apply_target
    monkeypatch.setattr(
        change_service,
        '_apply_target',
        lambda active_change, target_item, local_path, count, **kwargs: (
            'Rolled back' if local_path == active_change.rollback_path
            else original_apply(active_change, target_item, local_path, count, **kwargs)
        ),
    )

    with pytest.raises(RoxywiValidationError, match='Health check failed'):
        change_service.deploy_change(change.id, group_id=1)

    failed_target = change_sql.get_target(target.id)
    assert 'Attempt 2/2: unhealthy' in failed_target.health_output


def test_exclude_and_include_slave_replans_rollout(
    cluster_servers, tmp_path, monkeypatch
):
    slaves, master = cluster_servers
    change = _db_change(master, tmp_path, batch_size=1)
    targets = _seed_rollout_targets(change, master, tmp_path)
    by_server = {target.server_id: target for target in targets}

    excluded = change_service.exclude_target(
        change.id, by_server[slaves[0].server_id].id,
        group_id=1, reason='maintenance',
    )
    excluded_target = change_sql.get_target(by_server[slaves[0].server_id].id)
    assert excluded.id == change.id
    assert excluded_target.excluded == 1
    assert excluded_target.status == 'excluded'
    assert excluded_target.batch == -1

    with pytest.raises(RoxywiConflictError, match='cannot be excluded'):
        change_service.exclude_target(
            change.id, by_server[master.server_id].id, group_id=1,
        )

    monkeypatch.setattr(
        change_service.config_mod, 'validate_candidate_config',
        lambda *_args, **_kwargs: 'Configuration is valid',
    )
    change_service.include_target(
        change.id, by_server[slaves[0].server_id].id, group_id=1,
    )
    included_target = change_sql.get_target(by_server[slaves[0].server_id].id)
    assert included_target.excluded == 0
    assert included_target.status == 'pending'
    assert included_target.batch >= 0


def test_per_node_retry_leaves_partial_rollout_paused(
    cluster_servers, tmp_path, monkeypatch
):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='auto_rolled_back')
    targets = _seed_rollout_targets(change, master, tmp_path, status='rolled_back')
    monkeypatch.setattr(
        change_service, '_reconcile_interrupted_rollout',
        lambda item: change_sql.list_targets(item.id),
    )
    monkeypatch.setattr(change_service, '_ensure_target_reload_ready', lambda *_args: None)
    monkeypatch.setattr(
        change_service, '_apply_target_result',
        lambda *_args, **_kwargs: ('Uploaded', 'Healthy'),
    )
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)

    retried = change_service.retry_target(change.id, targets[0].id, group_id=1)

    assert retried.status == 'paused'
    assert change_sql.get_target(targets[0].id).status == 'deployed'
    assert sum(target.status == 'deployed' for target in change_sql.list_targets(change.id)) == 1


def test_per_node_rollback_keeps_remaining_nodes_deployed(
    cluster_servers, tmp_path, monkeypatch
):
    _slaves, master = cluster_servers
    change = _db_change(master, tmp_path, status='deployed')
    targets = _seed_rollout_targets(change, master, tmp_path, status='deployed')
    monkeypatch.setattr(change_service, '_apply_target', lambda *_args, **_kwargs: 'Restored')
    monkeypatch.setattr(change_service, '_save_successful_version', lambda *_args: None)

    rolled_back = change_service.rollback_target(change.id, targets[0].id, group_id=1)

    assert rolled_back.status == 'paused'
    assert change_sql.get_target(targets[0].id).status == 'rolled_back'
    assert sum(target.status == 'deployed' for target in change_sql.list_targets(change.id)) == 2


def test_target_action_rejects_target_from_another_change(managed_server, tmp_path):
    first = _db_change(managed_server, tmp_path, status='paused')
    first_target = _seed_rollout_targets(first, managed_server, tmp_path)[0]
    second = _db_change(managed_server, tmp_path, status='paused', title='Other change')

    with pytest.raises(RoxywiResourceNotFound):
        change_service.retry_target(second.id, first_target.id, group_id=1)


def test_change_center_stage_three_assets_expose_all_rollout_controls():
    template = Path('app/templates/change_center.html').read_text(encoding='utf-8')
    editor_template = Path('app/templates/config.html').read_text(encoding='utf-8')
    script = Path('app/static/js/change-center.js').read_text(encoding='utf-8')
    editor_script = Path('app/static/js/change-editor.js').read_text(encoding='utf-8')

    for action in ('pause', 'resume', 'promote'):
        assert f"'{action}'" in script
    for action in ('retry', 'rollback', 'exclude', 'include'):
        assert action in script
    assert "'/targets/' + targetId + '/' + action" in script
    assert 'change-details-rollout' in template
    assert 'change-batch-size' in editor_template
    assert 'change-manual-promotion' in editor_template
    assert '/changes/api/rollout-preview' in editor_script


def test_change_center_translations_cover_every_stage_three_key(app):
    languages = ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh')
    with app.app_context():
        catalogs = {
            language: app.jinja_env.get_template(
                f'languages/{language}.html'
            ).module.change_center
            for language in languages
        }

    expected_keys = set(catalogs['en'])
    expected_statuses = set(catalogs['en']['statuses'])
    expected_health_modes = set(catalogs['en']['health_check_modes'])
    for catalog in catalogs.values():
        assert set(catalog) == expected_keys
        assert set(catalog['statuses']) == expected_statuses
        assert set(catalog['health_check_modes']) == expected_health_modes
