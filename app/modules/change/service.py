import os
import re
import shutil
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timedelta
from pathlib import Path
from shlex import quote
from time import sleep
from uuid import uuid4

import app.modules.common.common as common
import app.modules.change.automation as change_automation
import app.modules.config.common as config_common
import app.modules.config.config as config_mod
import app.modules.config.deployment_policy as deployment_policy
import app.modules.db.change as change_sql
import app.modules.db.config as config_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
from app.modules.db.db_model import close_database_connection
from app.modules.subscription.access import CHANGE_CENTER, require_feature
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiPermissionError,
    RoxywiValidationError,
)


EDITABLE_STATUSES = ('draft', 'validation_failed')
VALIDATABLE_STATUSES = ('draft', 'validation_failed')
CANCELLABLE_STATUSES = ('draft', 'validation_failed', 'validated', 'pending_approval', 'approved')
RETRYABLE_DEPLOY_STATUSES = (
    'auto_rolled_back', 'auto_rollback_failed', 'rollback_failed', 'deployment_interrupted',
    'schedule_missed',
)
IN_PROGRESS_STATUSES = ('validating', 'deploying', 'pause_requested', 'rolling_back')
RESUMABLE_STATUSES = ('paused', 'awaiting_promotion', 'deployment_interrupted')
TARGET_ACTION_STATUSES = (
    'paused', 'awaiting_promotion', 'deployment_interrupted', 'auto_rolled_back',
    'auto_rollback_failed', 'rollback_failed',
)
STALE_OPERATION_TIMEOUT = timedelta(minutes=5)
ERROR_PATTERN = re.compile(r'(^|[\n>])\s*(?:[^\n:]+:\s*)?error:', re.IGNORECASE)
ANSI_PATTERN = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


class _RolloutFailure(RuntimeError):
    def __init__(self, message: str, affected_target_ids: list[int]):
        super().__init__(message)
        self.affected_target_ids = affected_target_ids


class _HealthCheckFailure(RuntimeError):
    def __init__(self, output: str):
        super().__init__(f'Health check failed: {output.splitlines()[-1]}')
        self.output = output


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[^A-Za-z0-9_.-]+', '-', value).strip('-')
    return value or fallback


def _change_paths(service: str, server_ip: str) -> tuple[Path, Path]:
    changes_dir = Path(config_common.get_config_dir(service)).resolve() / 'changes'
    changes_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    extension = config_common.get_file_format(service)
    server_name = _safe_name(server_ip, 'server')
    return (
        changes_dir / f'{server_name}-{token}-draft.{extension}',
        changes_dir / f'{server_name}-{token}-before.{extension}',
    )


def _write_private_file(path: Path, content: str) -> None:
    path.write_text(content, encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _remote_path(service: str, requested_path: str | None) -> str:
    if service in ('haproxy', 'keepalived'):
        path = sql.get_setting(f'{service}_config_path')
    else:
        path = config_mod._replace_config_path_to_correct(requested_path)
    common.check_is_conf(path)
    return path


def _require_server_service(server, service: str) -> None:
    if not int(getattr(server, service, 0)):
        raise RoxywiValidationError(f'{service.title()} is not enabled for this server')


def _require_change_group(change, group_id: int) -> None:
    if int(change.group_id) != int(group_id):
        raise RoxywiPermissionError('Change does not belong to the active group')


def _has_error(output: str | None) -> bool:
    return bool(output and ERROR_PATTERN.search(output))


def _upload(change, local_path: str, action: str) -> str:
    server = server_sql.get_server(change.server_id)
    if action == 'test':
        validation_results = []
        for target in _target_servers(server):
            output = config_mod.validate_candidate_config(
                target.ip,
                local_path,
                change.service,
                config_file_name=change.remote_path,
            )
            validation_results.append(f'{target.hostname}: {output}')
        return '\n'.join(validation_results)
    kwargs = {
        'config_file_name': change.remote_path,
        'oldcfg': change.rollback_path,
        'record_version': False,
        'deployment_policy_bypass': True,
    }
    if change.service == 'keepalived':
        output = config_mod.upload_and_restart(server.ip, local_path, action, change.service, **kwargs)
    else:
        output = config_mod.master_slave_upload_and_restart(
            server.ip, local_path, action, change.service, **kwargs
        )
    output = str(output or '')
    if _has_error(output):
        raise RuntimeError(output)
    return output


def _target_servers(server) -> list:
    targets = [server]
    for slave_ip, _slave_hostname in server_sql.is_master(server.ip):
        if slave_ip:
            targets.append(server_sql.get_server_by_ip(slave_ip))
    return targets


def _rollout_servers(server, service: str) -> list[tuple[object, str]]:
    """Return the existing propagation topology in safe apply order."""
    if service == 'keepalived':
        return [(server, 'standalone')]

    slaves = []
    for slave_ip, _slave_hostname in server_sql.is_master(server.ip):
        if slave_ip:
            slaves.append(server_sql.get_server_by_ip(slave_ip))
    slaves.sort(key=lambda item: (int(item.pos or 0), int(item.server_id)))
    primary_role = 'master' if slaves else 'standalone'
    return [*((slave, 'slave') for slave in slaves), (server, primary_role)]


def rollout_preview(server_id: int | str, service: str, group_id: int) -> list[dict]:
    """Return the immutable topology that a new change would capture."""
    require_feature(CHANGE_CENTER)
    if isinstance(server_id, int) or str(server_id).isdigit():
        server = server_sql.get_server(int(server_id))
    else:
        server = server_sql.get_server_by_ip(common.is_ip_or_dns(str(server_id)))
    if int(server.group_id) != int(group_id):
        raise RoxywiPermissionError('Server does not belong to the active group')
    _require_server_service(server, service)
    return [
        {
            'server_id': target.server_id,
            'server_ip': target.ip,
            'server_name': target.hostname,
            'role': role,
            'position': position,
            'can_exclude': role == 'slave',
            'canary_eligible': role == 'slave',
        }
        for position, (target, role) in enumerate(_rollout_servers(server, service))
    ]


def _effective_batch_size(change, active_count: int) -> int:
    configured = int(getattr(change, 'batch_size', 0) or 0)
    if configured:
        return configured
    return 1 if change.execution_mode == 'rolling' else max(1, active_count)


def _prepare_rollout_plan(
    targets: list,
    *,
    execution_mode: str,
    batch_size: int,
    canary_server_ids: list[int] | set[int] | None = None,
    excluded_server_ids: list[int] | set[int] | None = None,
) -> list[dict]:
    """Validate rollout selections and assign deterministic canary/main batches."""
    canary_ids = {int(server_id) for server_id in (canary_server_ids or [])}
    excluded_ids = {int(server_id) for server_id in (excluded_server_ids or [])}
    known_ids = {
        int(target['server_id'] if isinstance(target, dict) else target.server_id)
        for target in targets
    }
    unknown_ids = (canary_ids | excluded_ids) - known_ids
    if unknown_ids:
        raise RoxywiValidationError(
            f'Rollout target does not belong to this cluster: {min(unknown_ids)}'
        )
    if canary_ids & excluded_ids:
        raise RoxywiValidationError('A rollout target cannot be both canary and excluded')

    normalized = []
    for target in targets:
        values = dict(target) if isinstance(target, dict) else {
            'id': target.id,
            'server_id': target.server_id,
            'role': target.role,
            'position': target.position,
        }
        server_id = int(values['server_id'])
        role = values['role']
        if role != 'slave' and server_id in canary_ids:
            raise RoxywiValidationError('Only slave nodes can be selected as canaries')
        if role != 'slave' and server_id in excluded_ids:
            raise RoxywiValidationError('The master or standalone node cannot be excluded')
        values['is_canary'] = int(server_id in canary_ids)
        values['excluded'] = int(server_id in excluded_ids)
        values['excluded_reason'] = values.get('excluded_reason')
        normalized.append(values)

    active = [target for target in normalized if not target['excluded']]
    effective_size = batch_size or (1 if execution_mode == 'rolling' else max(1, len(active)))
    canaries = [target for target in active if target['is_canary']]
    regular = [target for target in active if not target['is_canary']]
    next_batch = 0
    if canaries:
        for target in canaries:
            target['batch'] = 0
        next_batch = 1
    for index, target in enumerate(regular):
        target['batch'] = next_batch + index // effective_size
    for target in normalized:
        if target['excluded']:
            target['batch'] = -1
            target['status'] = 'excluded'
    return normalized


def _snapshot_path(
    rollback_path: str | Path,
    server_ip: str,
    purpose: str,
) -> Path:
    base_path = Path(rollback_path)
    return base_path.with_name(
        f'{_safe_name(server_ip, "server")}-{purpose}-{uuid4().hex}{base_path.suffix}'
    )


def _target_snapshot_path(rollback_path: str | Path, server_ip: str) -> Path:
    return _snapshot_path(rollback_path, server_ip, 'before')


def _capture_rollout_targets(
    server,
    service: str,
    remote_path: str,
    rollback_path: Path,
    excluded_server_ids: list[int] | set[int] | None = None,
) -> tuple[list[dict], list[Path]]:
    """Capture an independent pre-change snapshot for every rollout target."""
    topology = _rollout_servers(server, service)
    excluded_ids = {int(server_id) for server_id in (excluded_server_ids or [])}
    captured_paths = [rollback_path]
    try:
        config_mod.get_config(
            server.ip,
            str(rollback_path),
            service=service,
            config_file_name=remote_path,
        )
        try:
            os.chmod(rollback_path, 0o600)
        except OSError:
            pass

        targets = []
        for position, (target_server, role) in enumerate(topology):
            if int(target_server.server_id) == int(server.server_id):
                target_rollback_path = rollback_path
            else:
                target_rollback_path = _target_snapshot_path(rollback_path, target_server.ip)
                if int(target_server.server_id) not in excluded_ids:
                    captured_paths.append(target_rollback_path)
                    config_mod.get_config(
                        target_server.ip,
                        str(target_rollback_path),
                        service=service,
                        config_file_name=remote_path,
                    )
                    try:
                        os.chmod(target_rollback_path, 0o600)
                    except OSError:
                        pass
            targets.append({
                'server_id': target_server.server_id,
                'server_ip': target_server.ip,
                'server_name': target_server.hostname,
                'role': role,
                'position': position,
                'status': 'pending',
                'rollback_path': str(target_rollback_path),
            })
        return targets, captured_paths
    except Exception:
        for captured_path in captured_paths:
            try:
                captured_path.unlink()
            except FileNotFoundError:
                pass
        raise


def _ensure_rollout_targets(change) -> list:
    """Load rollout targets and lazily upgrade changes created before phase two."""
    targets = change_sql.list_targets(change.id)
    server = server_sql.get_server(change.server_id)
    expected_topology = _rollout_servers(server, change.service)

    if not targets:
        captured_paths = []
        values = []
        for position, (target_server, role) in enumerate(expected_topology):
            if int(target_server.server_id) == int(change.server_id):
                snapshot_path = Path(change.rollback_path)
            else:
                snapshot_path = _target_snapshot_path(change.rollback_path, target_server.ip)
                config_mod.get_config(
                    target_server.ip,
                    str(snapshot_path),
                    service=change.service,
                    config_file_name=change.remote_path,
                )
                captured_paths.append(snapshot_path)
                try:
                    os.chmod(snapshot_path, 0o600)
                except OSError:
                    pass
            values.append({
                'server_id': target_server.server_id,
                'server_ip': target_server.ip,
                'server_name': target_server.hostname,
                'role': role,
                'position': position,
                'status': 'pending',
                'rollback_path': str(snapshot_path),
            })
        try:
            targets = change_sql.create_targets(change.id, values)
        except Exception:
            for snapshot_path in captured_paths:
                try:
                    snapshot_path.unlink()
                except FileNotFoundError:
                    pass
            raise

    expected_ids = [int(item.server_id) for item, _role in expected_topology]
    stored_ids = [int(target.server_id) for target in targets]
    if stored_ids != expected_ids:
        raise RoxywiConflictError(
            'The master/slave topology changed after this draft was created; create a new change'
        )
    for target, (target_server, expected_role) in zip(targets, expected_topology):
        if target.server_ip != target_server.ip or target.role != expected_role:
            raise RoxywiConflictError(
                'The master/slave topology changed after this draft was created; create a new change'
            )
    return _refresh_rollout_batches(change, targets)


def _target_server(target):
    server = server_sql.get_server(target.server_id)
    if server.ip != target.server_ip:
        raise RoxywiConflictError(
            f'The address of rollout target {target.server_name} changed; create a new change'
        )
    return server


def _post_deploy_check(change) -> str:
    server = server_sql.get_server(change.server_id)
    results = []
    for target in _target_servers(server):
        service_common.check_service_config(target.ip, target.server_id, change.service)
        result = f'{target.hostname}: configuration is valid'
        if change.action in ('reload', 'restart'):
            if not _is_service_active(target, change.service):
                raise RuntimeError(f'{target.hostname}: {change.service} is not active after deployment')
            result += ', service is active'
        results.append(result)
    return '\n'.join(results)


def _is_service_active(target, service: str) -> bool:
    is_dockerized = service_sql.select_service_setting(target.server_id, service, 'dockerized')
    if is_dockerized == '1':
        container_name = sql.get_setting(f'{service}_container_name')
        command = f"sudo docker inspect -f '{{{{.State.Running}}}}' {quote(str(container_name))}"
        expected_state = 'true'
    else:
        service_name = service_common.get_correct_service_name(service, target.server_id)
        command = f'systemctl is-active {quote(service_name)}'
        expected_state = 'active'
    state = server_mod.ssh_command(target.ip, command)
    return ANSI_PATTERN.sub('', str(state or '')).strip().lower() == expected_state


def _ensure_action_ready(change) -> None:
    """Do not replace a configuration when reload cannot activate the service."""
    if change.action != 'reload':
        return
    targets = [target for target in _ensure_rollout_targets(change) if not target.excluded]
    inactive_servers = []
    try:
        inactive_servers = [
            target.server_name for target in targets
            if not _is_service_active(_target_server(target), change.service)
        ]
    except Exception as exc:
        raise RoxywiValidationError(
            f'Cannot verify {change.service.title()} state before deployment: '
            f'{_short_operation_error(exc)}'
        ) from exc
    if inactive_servers:
        raise RoxywiConflictError(
            f'Cannot deploy with reload because {change.service.title()} is not active on '
            f'{", ".join(inactive_servers)}. Start the service or create the change with restart.'
        )


def _ensure_base_unchanged(change) -> None:
    """Refuse to overwrite a configuration changed after the draft snapshot."""
    targets = _ensure_rollout_targets(change)
    for target in targets:
        if target.excluded:
            continue
        rollback_path = Path(target.rollback_path)
        if not rollback_path.is_file():
            raise RoxywiConflictError(
                f'The original configuration snapshot is no longer available for {target.server_name}'
            )
        current_path = _snapshot_path(rollback_path, target.server_ip, 'current')
        try:
            config_mod.get_config(
                target.server_ip,
                str(current_path),
                service=change.service,
                config_file_name=change.remote_path,
            )
            if current_path.read_bytes() != rollback_path.read_bytes():
                raise RoxywiConflictError(
                    f'Configuration on {target.server_name} changed after this draft was created; create a new change'
                )
        finally:
            try:
                current_path.unlink()
            except FileNotFoundError:
                pass


def _reconcile_interrupted_rollout(change) -> list:
    """Resolve each target to original or candidate state before resuming."""
    targets = _ensure_rollout_targets(change)
    candidate_path = Path(change.draft_path)
    if not candidate_path.is_file():
        raise RoxywiConflictError('The candidate configuration is no longer available')
    candidate = candidate_path.read_bytes()

    for target in targets:
        if target.excluded:
            continue
        rollback_path = Path(target.rollback_path)
        if not rollback_path.is_file():
            raise RoxywiConflictError(
                f'The original configuration snapshot is no longer available for {target.server_name}'
            )
        current_path = _snapshot_path(rollback_path, target.server_ip, 'resume')
        try:
            config_mod.get_config(
                target.server_ip,
                str(current_path),
                service=change.service,
                config_file_name=change.remote_path,
            )
            current = current_path.read_bytes()
        finally:
            try:
                current_path.unlink()
            except FileNotFoundError:
                pass

        if current == candidate and target.status == 'deployed':
            _check_target(change, target, len(targets))
            continue
        if current == candidate:
            change_sql.update_target(
                target.id,
                status='pending',
                deployment_output=(
                    'Candidate configuration found after the interrupted deployment; '
                    'the service action will be retried.'
                ),
                rollback_output=None,
                deployed_at=None,
            )
            continue
        if current == rollback_path.read_bytes():
            change_sql.update_target(
                target.id,
                status='pending',
                deployment_output=None,
                rollback_output=None,
                deployed_at=None,
            )
            continue
        raise RoxywiConflictError(
            f'Configuration on {target.server_name} differs from both the original and '
            'candidate versions; create a new change'
        )
    return change_sql.list_targets(change.id)


def _version_path(change) -> Path:
    generated = Path(config_common.generate_config_path(
        change.service, server_sql.get_server(change.server_id).ip
    ))
    return generated.with_name(f'{generated.stem}-change-{change.id}{generated.suffix}')


def _save_successful_version(change, source_path: str, diff: str, message: str) -> None:
    version_path = _version_path(change)
    version_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, version_path)
    try:
        os.chmod(version_path, 0o600)
    except OSError:
        pass
    config_sql.insert_config_version(
        change.server_id,
        change.user_id,
        change.service,
        str(version_path),
        change.remote_path,
        diff,
        message=message,
    )


def _name_for_user(user_id: int | None) -> str | None:
    if not user_id:
        return None
    try:
        return user_sql.get_user_id(user_id).username
    except Exception:
        return None


def _stored_list(value: str | None) -> list:
    try:
        loaded = json.loads(value or '[]')
    except (TypeError, ValueError):
        return []
    return loaded if isinstance(loaded, list) else []


def is_recoverable(change, now: datetime | None = None) -> bool:
    if getattr(change, 'active_task_id', None):
        return False
    if change.status not in IN_PROGRESS_STATUSES:
        return False
    if not change.updated_at:
        return True
    if now is None:
        now = datetime.now(change.updated_at.tzinfo) if change.updated_at.tzinfo else datetime.now()
    return now - change.updated_at >= STALE_OPERATION_TIMEOUT


def _serialize_target(target) -> dict:
    return {
        'id': target.id,
        'server_id': target.server_id,
        'server_ip': target.server_ip,
        'server_name': target.server_name,
        'role': target.role,
        'position': target.position,
        'batch': target.batch,
        'is_canary': bool(target.is_canary),
        'excluded': bool(target.excluded),
        'excluded_reason': target.excluded_reason or '',
        'status': target.status,
        'validation_output': target.validation_output or '',
        'deployment_output': target.deployment_output or '',
        'health_output': target.health_output or '',
        'rollback_output': target.rollback_output or '',
        'drift_status': target.drift_status or 'unknown',
        'drift_checked_at': change_automation.utc_iso(target.drift_checked_at),
        'drift_diff': target.drift_diff or '',
        'updated_at': target.updated_at.isoformat() if target.updated_at else None,
        'deployed_at': target.deployed_at.isoformat() if target.deployed_at else None,
    }


def serialize_change(change) -> dict:
    from app.modules.change.operations import serialize_operation
    try:
        server = server_sql.get_server(change.server_id)
        server_name = server.hostname
        server_ip = server.ip
    except Exception:
        server_name = None
        server_ip = None
    return {
        'id': change.id,
        'operation': serialize_operation(change),
        'server_id': change.server_id,
        'server_name': server_name,
        'server_ip': server_ip,
        'group_id': change.group_id,
        'user_id': change.user_id,
        'created_by': _name_for_user(change.user_id),
        'approved_by': change.approved_by,
        'approved_by_name': _name_for_user(change.approved_by),
        'service': change.service,
        'action': change.action,
        'execution_mode': change.execution_mode,
        'batch_size': int(change.batch_size or 0) or None,
        'effective_batch_size': _effective_batch_size(
            change,
            len([target for target in change_sql.list_targets(change.id) if not target.excluded]),
        ),
        'max_parallel': int(change.max_parallel or 1),
        'manual_promotion': bool(change.manual_promotion),
        'health_check_mode': change.health_check_mode,
        'health_check_retries': int(change.health_check_retries or 1),
        'health_check_interval': int(change.health_check_interval or 0),
        'notification_channels': _stored_list(change.notification_channels),
        'notification_destinations': _stored_list(
            getattr(change, 'notification_destinations', '[]')
        ),
        'scheduled_at': change_automation.utc_iso(change.scheduled_at),
        'maintenance_window_end': (
            change_automation.utc_iso(change.maintenance_window_end)
        ),
        'drift_status': change.drift_status or 'unknown',
        'drift_checked_at': change_automation.utc_iso(change.drift_checked_at),
        'drift_diff': change.drift_diff or '',
        'started_at': change_automation.utc_iso(change.started_at),
        'finished_at': change_automation.utc_iso(change.finished_at),
        'duration_seconds': (
            max(0.0, (change.finished_at - change.started_at).total_seconds())
            if change.started_at and change.finished_at else None
        ),
        'status': change.status,
        'title': change.title,
        'description': change.description or '',
        'remote_path': change.remote_path,
        'diff': change.diff or '',
        'validation_output': change.validation_output or '',
        'deployment_output': change.deployment_output or '',
        'rollback_output': change.rollback_output or '',
        'targets': [_serialize_target(target) for target in change_sql.list_targets(change.id)],
        'requires_approval': bool(change.requires_approval),
        'recoverable': is_recoverable(change),
        'created_at': change.created_at.isoformat() if change.created_at else None,
        'updated_at': change.updated_at.isoformat() if change.updated_at else None,
        'deployed_at': change.deployed_at.isoformat() if change.deployed_at else None,
    }


def create_change(body, user_id: int, group_id: int):
    require_feature(CHANGE_CENTER)
    notification_destinations = change_automation.validate_notification_destinations(
        body.notification_destinations, group_id
    )
    notification_channels = (
        list(dict.fromkeys(item['channel'] for item in notification_destinations))
        if notification_destinations else list(body.notification_channels)
    )
    if isinstance(body.server_id, int) or str(body.server_id).isdigit():
        server = server_sql.get_server(int(body.server_id))
    else:
        server = server_sql.get_server_by_ip(common.is_ip_or_dns(str(body.server_id)))
    if int(server.group_id) != int(group_id):
        raise RoxywiPermissionError('Server does not belong to the active group')
    _require_server_service(server, body.service)
    deployment_policy.require_change_center_creation(group_id, body.service)
    remote_path = _remote_path(body.service, body.file_path)
    draft_path, rollback_path = _change_paths(body.service, server.ip)
    captured_paths = []
    change = None
    try:
        target_values, captured_paths = _capture_rollout_targets(
            server,
            body.service,
            remote_path,
            rollback_path,
            body.excluded_server_ids,
        )
        target_values = _prepare_rollout_plan(
            target_values,
            execution_mode=body.execution_mode,
            batch_size=body.batch_size or 0,
            canary_server_ids=body.canary_server_ids,
            excluded_server_ids=body.excluded_server_ids,
        )
        _write_private_file(draft_path, body.config)
        diff = config_mod.diff_config(str(rollback_path), str(draft_path))
        change = change_sql.create_change(
            server_id=server.server_id,
            group_id=group_id,
            user_id=user_id,
            service=body.service,
            action=body.action,
            execution_mode=body.execution_mode,
            batch_size=body.batch_size or 0,
            max_parallel=body.max_parallel,
            manual_promotion=int(body.manual_promotion),
            health_check_mode=body.health_check_mode,
            health_check_retries=body.health_check_retries,
            health_check_interval=body.health_check_interval,
            pause_requested=0,
            notification_channels=json.dumps(notification_channels),
            notification_destinations=json.dumps(notification_destinations),
            drift_status='unknown',
            status='draft',
            title=body.title,
            description=body.description,
            remote_path=remote_path,
            draft_path=str(draft_path),
            rollback_path=str(rollback_path),
            diff=diff,
            requires_approval=int(body.requires_approval),
        )
        change_sql.create_targets(change.id, target_values)
        change_automation.record_event(
            change.id,
            'change.created',
            'Configuration change draft was created',
            actor_id=user_id,
        )
        return change
    except Exception:
        if change is not None:
            try:
                change.delete_instance()
            except Exception:
                pass
        for path in (draft_path, *captured_paths):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def update_change(change_id: int, body, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    if change.status not in EDITABLE_STATUSES:
        raise RoxywiConflictError('Only draft or failed validation changes can be edited')
    values = body.model_dump(exclude_unset=True)
    canary_server_ids = values.pop('canary_server_ids', None)
    excluded_server_ids = values.pop('excluded_server_ids', None)
    rollout_fields = {
        'execution_mode', 'batch_size', 'max_parallel', 'manual_promotion',
        'health_check_mode', 'health_check_retries', 'health_check_interval',
    }
    replan = bool(rollout_fields & set(values)) or canary_server_ids is not None or excluded_server_ids is not None
    if 'batch_size' in values and values['batch_size'] is None:
        values['batch_size'] = 0
    for boolean_field in ('manual_promotion',):
        if boolean_field in values:
            values[boolean_field] = int(values[boolean_field])
    if 'notification_destinations' in values:
        notification_destinations = change_automation.validate_notification_destinations(
            values.pop('notification_destinations'), group_id
        )
        values['notification_destinations'] = json.dumps(notification_destinations)
        values['notification_channels'] = json.dumps(list(dict.fromkeys(
            item['channel'] for item in notification_destinations
        )))
    elif 'notification_channels' in values:
        values['notification_channels'] = json.dumps(values['notification_channels'])
        values['notification_destinations'] = '[]'
    values.update(validation_output=None, approved_by=None, status='draft')
    change = change_sql.update_change(change_id, **values)
    if replan:
        targets = change_sql.list_targets(change.id)
        if canary_server_ids is None:
            canary_server_ids = [target.server_id for target in targets if target.is_canary]
        if excluded_server_ids is None:
            excluded_server_ids = [target.server_id for target in targets if target.excluded]
        planned = _prepare_rollout_plan(
            targets,
            execution_mode=change.execution_mode,
            batch_size=int(change.batch_size or 0),
            canary_server_ids=canary_server_ids,
            excluded_server_ids=excluded_server_ids,
        )
        for target, plan in zip(targets, planned):
            change_sql.update_target(
                target.id,
                batch=plan['batch'],
                is_canary=plan['is_canary'],
                excluded=plan['excluded'],
                excluded_reason=None,
                status='excluded' if plan['excluded'] else 'pending',
                validation_output=None,
                deployment_output=None,
                health_output=None,
                rollback_output=None,
                drift_status='unknown',
                drift_checked_at=None,
                drift_diff=None,
                deployed_at=None,
            )
    change = change_sql.get_change(change_id)
    change_automation.record_event(
        change.id,
        'change.updated',
        'Configuration change draft was updated',
        actor_id=actor_id,
    )
    return change


def _upload_target(
    change, target, local_path: str, action: str, target_count: int, *, normalize_config: bool = True
) -> str:
    """Apply one configuration without implicitly touching any other server."""
    if target_count == 1 and change.service != 'keepalived':
        return _upload(change, local_path, action)
    output = config_mod.upload_and_restart(
        target.server_ip,
        local_path,
        action,
        change.service,
        config_file_name=change.remote_path,
        oldcfg=target.rollback_path,
        record_version=False,
        slave=target.role == 'slave',
        normalize_config=normalize_config,
        user_id=change.user_id,
        deployment_policy_bypass=True,
    )
    output = str(output or change.service.title())
    if _has_error(output):
        raise RuntimeError(output)
    return output


def _check_target(change, target, target_count: int) -> str:
    mode = getattr(change, 'health_check_mode', 'full') or 'full'
    if mode == 'none':
        return 'Post-deployment health checks are disabled'
    target_server = _target_server(target)
    results = []
    if mode == 'full' and target_count == 1 and change.service != 'keepalived':
        return _post_deploy_check(change)
    if mode in ('full', 'config'):
        service_common.check_service_config(target.server_ip, target.server_id, change.service)
        results.append('Configuration is valid')
    if mode in ('full', 'service') and change.action in ('reload', 'restart'):
        if not _is_service_active(target_server, change.service):
            raise RuntimeError(f'{change.service} is not active after deployment')
        results.append('Service is active')
    return ', '.join(results) or 'No runtime health check is required for save-only changes'


def _run_target_health_check(change, target, target_count: int) -> str:
    retries = max(1, min(10, int(getattr(change, 'health_check_retries', 1) or 1)))
    interval = max(0, min(60, int(getattr(change, 'health_check_interval', 0) or 0)))
    errors = []
    for attempt in range(1, retries + 1):
        try:
            output = _check_target(change, target, target_count)
            if attempt > 1:
                output = f'{output} (passed on attempt {attempt}/{retries})'
            return output
        except Exception as exc:
            errors.append(f'Attempt {attempt}/{retries}: {_short_operation_error(exc)}')
            if attempt < retries and interval:
                sleep(interval)
    output = '\n'.join(errors)
    raise _HealthCheckFailure(output)


def _target_operation_output(targets: list, field: str) -> str:
    if len(targets) == 1:
        return getattr(targets[0], field) or ''
    sections = []
    for target in targets:
        output = getattr(target, field) or ''
        sections.append(
            f'{target.server_name} ({target.role}) [{target.status}]' + (f'\n{output}' if output else '')
        )
    return '\n\n'.join(sections)


def validate_change(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    targets = _ensure_rollout_targets(change)
    change_sql.transition_change(change_id, VALIDATABLE_STATUSES, 'validating')
    change_automation.record_event(
        change.id,
        'change.validation_started',
        'Configuration validation started',
        actor_id=actor_id,
    )
    failures = []
    for target in targets:
        if target.excluded:
            change_sql.update_target(
                target.id,
                status='excluded',
                validation_output=target.excluded_reason or 'Temporarily excluded from rollout',
            )
            continue
        change_sql.update_target(target.id, status='validating', validation_output=None)
        try:
            if len(targets) == 1 and change.service != 'keepalived':
                output = _upload(change, change.draft_path, 'test')
            else:
                output = config_mod.validate_candidate_config(
                    target.server_ip,
                    change.draft_path,
                    change.service,
                    config_file_name=change.remote_path,
                )
            change_sql.update_target(
                target.id,
                status='validated',
                validation_output=str(output or 'Configuration is valid'),
            )
            change_automation.record_event(
                change.id,
                'target.validated',
                f'Configuration is valid on {target.server_name}',
                target_id=target.id,
                actor_id=actor_id,
            )
        except Exception as exc:
            failures.append(f'{target.server_name}: {exc}')
            change_sql.update_target(
                target.id,
                status='validation_failed',
                validation_output=str(exc),
            )
            change_automation.record_event(
                change.id,
                'target.validation_failed',
                f'Configuration validation failed on {target.server_name}',
                target_id=target.id,
                actor_id=actor_id,
                details={'error': _short_operation_error(exc)},
            )
    targets = change_sql.list_targets(change.id)
    output = _target_operation_output(targets, 'validation_output')
    if failures:
        change_sql.update_change(change_id, status='validation_failed', validation_output=output)
        change_automation.record_event(
            change.id,
            'change.validation_failed',
            'Configuration validation failed',
            status='validation_failed',
            actor_id=actor_id,
            details={'error': _short_operation_error(failures[0])},
        )
        raise RoxywiValidationError(
            f'Configuration validation failed: {_short_operation_error(failures[0])}'
        )
    status = 'pending_approval' if change.requires_approval else 'validated'
    change = change_sql.update_change(
        change_id, status=status, validation_output=output or 'Configuration is valid'
    )
    change_automation.record_event(
        change.id,
        'change.validated',
        'Configuration validation completed successfully',
        status=status,
        actor_id=actor_id,
    )
    return change


def approve_change(change_id: int, approver_id: int, group_id: int):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    if not change.requires_approval:
        raise RoxywiConflictError('This change does not require approval')
    if int(change.user_id) == int(approver_id):
        raise RoxywiPermissionError('The author cannot approve their own change')
    change = change_sql.transition_change(
        change_id, ('pending_approval',), 'approved', approved_by=approver_id
    )
    change_automation.record_event(
        change.id,
        'change.approved',
        'Configuration change was approved',
        actor_id=approver_id,
    )
    return change


def _apply_target(
    change, target, local_path: str, target_count: int, *, normalize_config: bool = True
) -> str:
    output, _health_output = _apply_target_result(
        change,
        target,
        local_path,
        target_count,
        normalize_config=normalize_config,
    )
    return output


def _apply_target_result(
    change, target, local_path: str, target_count: int, *, normalize_config: bool = True
) -> tuple[str, str]:
    upload_output = _upload_target(
        change,
        target,
        local_path,
        change.action,
        target_count,
        normalize_config=normalize_config,
    )
    health_output = _run_target_health_check(change, target, target_count)
    return '\n'.join(filter(None, (upload_output, health_output))), health_output


def _apply_target_result_worker(*args, **kwargs) -> tuple[str, str]:
    """Run a rollout target without retaining a worker-thread DB connection."""
    try:
        return _apply_target_result(*args, **kwargs)
    finally:
        close_database_connection()


def _refresh_rollout_batches(change, targets: list) -> list:
    planned = _prepare_rollout_plan(
        targets,
        execution_mode=change.execution_mode,
        batch_size=int(change.batch_size or 0),
        canary_server_ids=[target.server_id for target in targets if target.is_canary],
        excluded_server_ids=[target.server_id for target in targets if target.excluded],
    )
    for target, plan in zip(targets, planned):
        values = {}
        if int(target.batch) != int(plan['batch']):
            values['batch'] = plan['batch']
        if int(target.is_canary) != int(plan['is_canary']):
            values['is_canary'] = plan['is_canary']
        if int(target.excluded) != int(plan['excluded']):
            values['excluded'] = plan['excluded']
        if plan['excluded'] and target.status != 'excluded':
            values['status'] = 'excluded'
        if values:
            change_sql.update_target(target.id, **values)
    return change_sql.list_targets(change.id)


def _deploy_batch(
    change,
    batch_targets: list,
    all_targets: list,
    *,
    actor_id: int | None = None,
) -> None:
    pending_targets = [
        target for target in batch_targets
        if not target.excluded and target.status != 'deployed'
    ]
    if not pending_targets:
        return
    batch_number = min(target.batch for target in pending_targets)
    change_automation.record_event(
        change.id,
        'deployment.batch_started',
        f'Deployment batch {batch_number + 1} started',
        actor_id=actor_id,
        details={
            'batch': batch_number,
            'targets': [target.id for target in pending_targets],
        },
    )

    affected_target_ids = [
        target.id for target in all_targets
        if not target.excluded and target.status == 'deployed'
    ]
    for target in pending_targets:
        change_sql.update_target(
            target.id,
            status='deploying',
            deployment_output=None,
            health_output=None,
        )
        change_automation.record_event(
            change.id,
            'target.deployment_started',
            f'Deployment started on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
        )

    worker_count = min(
        max(1, int(change.max_parallel or 1)),
        len(pending_targets),
    )
    failures = {}
    if worker_count == 1:
        for target in pending_targets:
            affected_target_ids.append(target.id)
            try:
                output, health_output = _apply_target_result(
                    change, target, change.draft_path, len(all_targets)
                )
                change_sql.update_target(
                    target.id,
                    status='deployed',
                    deployment_output=output,
                    health_output=health_output,
                    drift_status='in_sync',
                    drift_checked_at=change_automation.utc_now(),
                    drift_diff=None,
                    deployed_at=datetime.now(),
                )
                change_automation.record_event(
                    change.id,
                    'target.deployed',
                    f'Deployment completed on {target.server_name}',
                    target_id=target.id,
                    actor_id=actor_id,
                )
            except Exception as exc:
                failures[target.id] = exc
                change_sql.update_target(
                    target.id,
                    status='deployment_failed',
                    deployment_output=str(exc),
                    health_output=getattr(exc, 'output', None),
                )
                change_automation.record_event(
                    change.id,
                    'target.deployment_failed',
                    f'Deployment failed on {target.server_name}',
                    target_id=target.id,
                    actor_id=actor_id,
                    details={'error': _short_operation_error(exc)},
                )
                break
    else:
        affected_target_ids.extend(target.id for target in pending_targets)
        config_mod.normalize_config_file(change.draft_path)
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix='change-rollout',
        ) as executor:
            futures = {
                executor.submit(
                    copy_context().run,
                    _apply_target_result_worker,
                    change,
                    target,
                    change.draft_path,
                    len(all_targets),
                    normalize_config=False,
                ): target
                for target in pending_targets
            }
            for future in as_completed(futures):
                target = futures[future]
                try:
                    output, health_output = future.result()
                    change_sql.update_target(
                        target.id,
                        status='deployed',
                        deployment_output=output,
                        health_output=health_output,
                        drift_status='in_sync',
                        drift_checked_at=change_automation.utc_now(),
                        drift_diff=None,
                        deployed_at=datetime.now(),
                    )
                    change_automation.record_event(
                        change.id,
                        'target.deployed',
                        f'Deployment completed on {target.server_name}',
                        target_id=target.id,
                        actor_id=actor_id,
                    )
                except Exception as exc:
                    failures[target.id] = exc
                    change_sql.update_target(
                        target.id,
                        status='deployment_failed',
                        deployment_output=str(exc),
                        health_output=getattr(exc, 'output', None),
                    )
                    change_automation.record_event(
                        change.id,
                        'target.deployment_failed',
                        f'Deployment failed on {target.server_name}',
                        target_id=target.id,
                        actor_id=actor_id,
                        details={'error': _short_operation_error(exc)},
                    )

    if failures:
        failed_target = next(target for target in pending_targets if target.id in failures)
        for target in change_sql.list_targets(change.id):
            if not target.excluded and target.status not in ('deployed', 'deployment_failed'):
                change_sql.update_target(target.id, status='skipped')
        raise _RolloutFailure(
            f'{failed_target.server_name}: {failures[failed_target.id]}',
            affected_target_ids,
        ) from failures[failed_target.id]
    change_automation.record_event(
        change.id,
        'deployment.batch_completed',
        f'Deployment batch {batch_number + 1} completed',
        actor_id=actor_id,
        details={'batch': batch_number},
    )


def _deploy_rollout(
    change,
    *,
    resume: bool = False,
    actor_id: int | None = None,
) -> tuple[str, bool]:
    targets = change_sql.list_targets(change.id) if resume else change_sql.reset_targets(change.id)
    targets = _refresh_rollout_batches(change, targets)
    active_targets = [target for target in targets if not target.excluded]
    batch_numbers = sorted({target.batch for target in active_targets if target.status != 'deployed'})
    for batch_number in batch_numbers:
        current = change_sql.get_change(change.id)
        if current.status == 'pause_requested' and _finish_pending_pause(
            change, 'Deployment paused before the next batch', actor_id=actor_id
        ):
            output = _target_operation_output(change_sql.list_targets(change.id), 'deployment_output')
            return output, False

        current_targets = change_sql.list_targets(change.id)
        batch_targets = [
            target for target in current_targets
            if not target.excluded and target.batch == batch_number
        ]
        if actor_id is None:
            # Keep the internal helper easy to wrap in operational/test hooks that
            # predate timeline actor attribution.
            _deploy_batch(change, batch_targets, current_targets)
        else:
            _deploy_batch(change, batch_targets, current_targets, actor_id=actor_id)

        current_targets = change_sql.list_targets(change.id)
        remaining = [
            target for target in current_targets
            if not target.excluded and target.status != 'deployed'
        ]
        if not remaining:
            output = _target_operation_output(current_targets, 'deployment_output')
            return output, True

        current = change_sql.get_change(change.id)
        if current.status == 'pause_requested' and _finish_pending_pause(
            change, 'Deployment paused after the current batch', actor_id=actor_id
        ):
            output = _target_operation_output(current_targets, 'deployment_output')
            return output, False
        if current.manual_promotion:
            change_sql.update_change(change.id, status='awaiting_promotion')
            change_automation.record_event(
                change.id,
                'deployment.awaiting_promotion',
                'Deployment is waiting for manual promotion to the next batch',
                actor_id=actor_id,
            )
            output = _target_operation_output(current_targets, 'deployment_output')
            return output, False

    output = _target_operation_output(change_sql.list_targets(change.id), 'deployment_output')
    return output, True


def _rollback_targets(
    change,
    target_ids: list[int],
    *,
    actor_id: int | None = None,
) -> tuple[str, list[str]]:
    all_targets = change_sql.list_targets(change.id)
    target_id_set = set(target_ids)
    targets = [
        target for target in all_targets
        if target.id in target_id_set
    ]
    target_count = len(all_targets)
    failures = []
    for target in reversed(targets):
        change_sql.update_target(target.id, status='rolling_back')
        change_automation.record_event(
            change.id,
            'target.rollback_started',
            f'Rollback started on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
        )
        try:
            output = _apply_target(change, target, target.rollback_path, target_count)
            change_sql.update_target(
                target.id,
                status='rolled_back',
                rollback_output=output,
                drift_status='unknown',
                drift_checked_at=None,
                drift_diff=None,
            )
            change_automation.record_event(
                change.id,
                'target.rolled_back',
                f'Rollback completed on {target.server_name}',
                target_id=target.id,
                actor_id=actor_id,
            )
        except Exception as exc:
            failures.append(f'{target.server_name}: {exc}')
            change_sql.update_target(
                target.id,
                status='rollback_failed',
                rollback_output=str(exc),
            )
            change_automation.record_event(
                change.id,
                'target.rollback_failed',
                f'Rollback failed on {target.server_name}',
                target_id=target.id,
                actor_id=actor_id,
                details={'error': _short_operation_error(exc)},
            )
    current_targets = change_sql.list_targets(change.id)
    return _target_operation_output(current_targets, 'rollback_output'), failures


def _rollback_after_failure(
    change,
    deployment_error: str,
    target_ids: list[int] | None = None,
    *,
    actor_id: int | None = None,
):
    targets = change_sql.list_targets(change.id)
    if target_ids is None:
        target_ids = [
            target.id for target in targets
            if target.status in ('deployed', 'deploying', 'deployment_failed')
        ]
    rollback_output, failures = _rollback_targets(
        change, target_ids, actor_id=actor_id
    )
    failed_change = change_sql.update_change(
        change.id,
        status='auto_rollback_failed' if failures else 'auto_rolled_back',
        deployment_output=deployment_error,
        rollback_output=rollback_output,
        finished_at=change_automation.utc_now(),
        drift_status='unknown',
        drift_checked_at=None,
        drift_diff=None,
    )
    change_automation.record_event(
        change.id,
        'deployment.failed',
        'Deployment failed and automatic rollback '
        + ('also failed' if failures else 'completed'),
        status=failed_change.status,
        actor_id=actor_id,
        details={'error': _short_operation_error(deployment_error), 'rollback_failures': failures},
    )
    return failed_change


def _short_operation_error(error: Exception | str) -> str:
    output = ANSI_PATTERN.sub('', str(error)).replace('<br>', '\n')
    inactive_match = re.search(
        r'([A-Za-z0-9_.@-]+\.service is not active, cannot reload\.?)', output, re.IGNORECASE
    )
    if inactive_match:
        return inactive_match.group(1)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    useful_lines = [
        line for line in lines
        if '[NOTICE]' not in line and '[WARNING]' not in line and 'config : parsing' not in line
    ]
    summary = (useful_lines or lines or ['Unknown deployment error'])[-1]
    return summary if len(summary) <= 240 else f'{summary[:237]}...'


def deploy_change(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    ready_status = 'approved' if change.requires_approval else 'validated'
    allowed_status = (ready_status, *RETRYABLE_DEPLOY_STATUSES)
    if change.status not in allowed_status:
        raise RoxywiConflictError('The change is not ready for deployment')
    resume = change.status == 'deployment_interrupted'
    _ensure_rollout_targets(change)
    if resume:
        _reconcile_interrupted_rollout(change)
    else:
        _ensure_base_unchanged(change)
    _ensure_action_ready(change)
    started_at = change.started_at if resume and change.started_at else change_automation.utc_now()
    change = change_sql.transition_change(
        change_id,
        allowed_status,
        'deploying',
        started_at=started_at,
        finished_at=None,
    )
    change_automation.record_event(
        change.id,
        'deployment.started',
        'Configuration deployment started',
        actor_id=actor_id,
    )
    try:
        deployment_output, completed = _deploy_rollout(
            change, resume=resume, actor_id=actor_id
        )
        if completed:
            _save_successful_version(
                change, change.draft_path, change.diff, f'Change #{change.id}: {change.title}'
            )
    except Exception as exc:
        affected_target_ids = getattr(exc, 'affected_target_ids', None)
        failed_change = _rollback_after_failure(
            change, str(exc), affected_target_ids, actor_id=actor_id
        )
        if failed_change.status == 'auto_rolled_back':
            rollback_message = 'The previous configuration was restored automatically.'
        else:
            rollback_message = 'Automatic rollback also failed. Open change details for the full output.'
        raise RoxywiValidationError(
            f'Deployment failed. {rollback_message} Reason: {_short_operation_error(exc)}'
        ) from exc
    if not completed:
        return change_sql.update_change(change_id, deployment_output=deployment_output)
    finished_at = change_automation.utc_now()
    change = change_sql.update_change(
        change_id,
        status='deployed',
        deployment_output=deployment_output,
        deployed_at=datetime.now(),
        pause_requested=0,
        drift_status='in_sync',
        drift_checked_at=finished_at,
        drift_diff=None,
        finished_at=finished_at,
    )
    change_automation.record_event(
        change.id,
        'deployment.succeeded',
        'Configuration deployment completed successfully',
        actor_id=actor_id,
        details={'duration_seconds': (finished_at - started_at).total_seconds()},
    )
    return change


def pause_change(change_id: int, group_id: int, actor_id: int | None = None):
    """Request a safe pause; the active worker stops after the current batch."""
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    if change.status == 'awaiting_promotion':
        change = change_sql.transition_change(
            change_id, ('awaiting_promotion',), 'paused', pause_requested=0
        )
        change_automation.record_event(
            change.id,
            'deployment.paused',
            'Deployment was paused while waiting for promotion',
            actor_id=actor_id,
        )
        return change
    change = change_sql.transition_change(
        change_id, ('deploying',), 'pause_requested', pause_requested=1
    )
    change_automation.record_event(
        change.id,
        'deployment.pause_requested',
        'A safe deployment pause was requested',
        actor_id=actor_id,
    )
    return change


def _cancel_pending_pause(change, actor_id: int | None = None):
    """Atomically let the active rollout worker continue before it pauses."""
    try:
        change = change_sql.transition_change(
            change.id, ('pause_requested',), 'deploying', pause_requested=0
        )
    except RoxywiConflictError:
        # The active worker may have claimed the pause between the UI refresh and
        # this request. In that case resume the now-paused rollout normally.
        current = change_sql.get_change(change.id)
        if current.status == 'paused':
            return None
        raise
    change_automation.record_event(
        change.id,
        'deployment.pause_cancelled',
        'Pending deployment pause was cancelled',
        actor_id=actor_id,
    )
    return change


def _finish_pending_pause(change, message: str, actor_id: int | None = None) -> bool:
    """Claim a requested pause without overwriting a concurrent resume."""
    try:
        change_sql.transition_change(
            change.id, ('pause_requested',), 'paused', pause_requested=0
        )
    except RoxywiConflictError:
        current = change_sql.get_change(change.id)
        if current.status == 'deploying' and not current.pause_requested:
            return False
        if current.status == 'paused':
            return True
        raise
    change_automation.record_event(
        change.id,
        'deployment.paused',
        message,
        actor_id=actor_id,
    )
    return True


def _resume_rollout(
    change,
    group_id: int,
    *,
    promotion: bool = False,
    actor_id: int | None = None,
):
    require_feature(CHANGE_CENTER)
    _require_change_group(change, group_id)
    if promotion and change.status != 'awaiting_promotion':
        raise RoxywiConflictError('Only a rollout awaiting promotion can be promoted')
    if not promotion and change.status not in RESUMABLE_STATUSES:
        raise RoxywiConflictError('Only a paused or interrupted rollout can be resumed')
    _reconcile_interrupted_rollout(change)
    _ensure_action_ready(change)
    change = change_sql.transition_change(
        change.id,
        (change.status,),
        'deploying',
        pause_requested=0,
    )
    change_automation.record_event(
        change.id,
        'deployment.promoted' if promotion else 'deployment.resumed',
        'Deployment promoted to the next batch' if promotion else 'Deployment resumed',
        actor_id=actor_id,
    )
    try:
        deployment_output, completed = _deploy_rollout(
            change, resume=True, actor_id=actor_id
        )
        if completed:
            _save_successful_version(
                change, change.draft_path, change.diff, f'Change #{change.id}: {change.title}'
            )
    except Exception as exc:
        affected_target_ids = getattr(exc, 'affected_target_ids', None)
        failed_change = _rollback_after_failure(
            change, str(exc), affected_target_ids, actor_id=actor_id
        )
        rollback_message = (
            'The previous configuration was restored automatically.'
            if failed_change.status == 'auto_rolled_back'
            else 'Automatic rollback also failed. Open change details for the full output.'
        )
        raise RoxywiValidationError(
            f'Deployment failed. {rollback_message} Reason: {_short_operation_error(exc)}'
        ) from exc
    if not completed:
        return change_sql.update_change(change.id, deployment_output=deployment_output)
    finished_at = change_automation.utc_now()
    change = change_sql.update_change(
        change.id,
        status='deployed',
        deployment_output=deployment_output,
        deployed_at=datetime.now(),
        pause_requested=0,
        drift_status='in_sync',
        drift_checked_at=finished_at,
        drift_diff=None,
        finished_at=finished_at,
    )
    change_automation.record_event(
        change.id,
        'deployment.succeeded',
        'Configuration deployment completed successfully',
        actor_id=actor_id,
        details={
            'duration_seconds': (
                (finished_at - change.started_at).total_seconds() if change.started_at else None
            )
        },
    )
    return change


def resume_change(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    if change.status == 'pause_requested':
        continued = _cancel_pending_pause(change, actor_id=actor_id)
        if continued is not None:
            return continued
        change = change_sql.get_change(change_id)
    return _resume_rollout(
        change, group_id, actor_id=actor_id
    )


def promote_change(change_id: int, group_id: int, actor_id: int | None = None):
    return _resume_rollout(
        change_sql.get_change(change_id),
        group_id,
        promotion=True,
        actor_id=actor_id,
    )


def _target_action_context(change_id: int, target_id: int, group_id: int):
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    target = change_sql.get_change_target(change_id, target_id)
    return change, target


def _ensure_target_reload_ready(change, target) -> None:
    if change.action != 'reload':
        return
    try:
        active = _is_service_active(_target_server(target), change.service)
    except Exception as exc:
        raise RoxywiValidationError(
            f'Cannot verify {change.service.title()} state on {target.server_name}: '
            f'{_short_operation_error(exc)}'
        ) from exc
    if not active:
        raise RoxywiConflictError(
            f'Cannot deploy with reload because {change.service.title()} is not active on '
            f'{target.server_name}. Start the service or create the change with restart.'
        )


def retry_target(
    change_id: int,
    target_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    """Retry one rollout target without redeploying already successful nodes."""
    require_feature(CHANGE_CENTER)
    change, target = _target_action_context(change_id, target_id, group_id)
    if change.status not in TARGET_ACTION_STATUSES:
        raise RoxywiConflictError('Per-node retry is not available in the current change state')
    if target.excluded:
        raise RoxywiConflictError('Include this rollout target before retrying it')
    _reconcile_interrupted_rollout(change)
    target = change_sql.get_change_target(change_id, target_id)
    if target.status == 'deployed':
        raise RoxywiConflictError('This rollout target is already deployed')
    _ensure_target_reload_ready(change, target)
    change = change_sql.transition_change(change.id, (change.status,), 'deploying')
    change_sql.update_target(
        target.id,
        status='deploying',
        deployment_output=None,
        health_output=None,
    )
    change_automation.record_event(
        change.id,
        'target.deployment_started',
        f'Deployment retry started on {target.server_name}',
        target_id=target.id,
        actor_id=actor_id,
    )
    try:
        output, health_output = _apply_target_result(
            change,
            target,
            change.draft_path,
            len(change_sql.list_targets(change.id)),
        )
        change_sql.update_target(
            target.id,
            status='deployed',
            deployment_output=output,
            health_output=health_output,
            drift_status='in_sync',
            drift_checked_at=change_automation.utc_now(),
            drift_diff=None,
            deployed_at=datetime.now(),
        )
        change_automation.record_event(
            change.id,
            'target.deployed',
            f'Deployment retry completed on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
        )
    except Exception as exc:
        change_sql.update_target(
            target.id,
            status='deployment_failed',
            deployment_output=str(exc),
            health_output=getattr(exc, 'output', None),
        )
        change_sql.update_change(change.id, status='paused')
        change_automation.record_event(
            change.id,
            'target.deployment_failed',
            f'Deployment retry failed on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
            details={'error': _short_operation_error(exc)},
        )
        raise RoxywiValidationError(
            f'Deployment failed on {target.server_name}: {_short_operation_error(exc)}'
        ) from exc

    targets = change_sql.list_targets(change.id)
    completed = all(target.excluded or target.status == 'deployed' for target in targets)
    if completed:
        _save_successful_version(
            change, change.draft_path, change.diff, f'Change #{change.id}: {change.title}'
        )
        finished_at = change_automation.utc_now()
        change = change_sql.update_change(
            change.id,
            status='deployed',
            deployment_output=_target_operation_output(targets, 'deployment_output'),
            deployed_at=datetime.now(),
            drift_status='in_sync',
            drift_checked_at=finished_at,
            drift_diff=None,
            finished_at=finished_at,
        )
        change_automation.record_event(
            change.id,
            'deployment.succeeded',
            'Configuration deployment completed successfully',
            actor_id=actor_id,
        )
        return change
    return change_sql.update_change(
        change.id,
        status='paused',
        deployment_output=_target_operation_output(targets, 'deployment_output'),
    )


def rollback_target(
    change_id: int,
    target_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    """Restore the captured snapshot on one rollout target."""
    require_feature(CHANGE_CENTER)
    change, target = _target_action_context(change_id, target_id, group_id)
    if change.status not in (*TARGET_ACTION_STATUSES, 'deployed'):
        raise RoxywiConflictError('Per-node rollback is not available in the current change state')
    if target.excluded or target.status not in (
        'deployed', 'deployment_failed', 'deployment_interrupted', 'rollback_failed'
    ):
        raise RoxywiConflictError('This rollout target has no deployed configuration to roll back')
    change = change_sql.transition_change(change.id, (change.status,), 'rolling_back')
    change_sql.update_target(target.id, status='rolling_back')
    change_automation.record_event(
        change.id,
        'target.rollback_started',
        f'Rollback started on {target.server_name}',
        target_id=target.id,
        actor_id=actor_id,
    )
    try:
        output = _apply_target(
            change,
            target,
            target.rollback_path,
            len(change_sql.list_targets(change.id)),
        )
        change_sql.update_target(
            target.id,
            status='rolled_back',
            rollback_output=output,
            drift_status='unknown',
            drift_checked_at=None,
            drift_diff=None,
        )
        change_automation.record_event(
            change.id,
            'target.rolled_back',
            f'Rollback completed on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
        )
    except Exception as exc:
        change_sql.update_target(
            target.id,
            status='rollback_failed',
            rollback_output=str(exc),
        )
        change_sql.update_change(change.id, status='rollback_failed')
        change_automation.record_event(
            change.id,
            'target.rollback_failed',
            f'Rollback failed on {target.server_name}',
            target_id=target.id,
            actor_id=actor_id,
            details={'error': _short_operation_error(exc)},
        )
        raise RoxywiValidationError(
            f'Rollback failed on {target.server_name}: {_short_operation_error(exc)}'
        ) from exc

    targets = change_sql.list_targets(change.id)
    remaining_deployed = any(
        not item.excluded and item.status == 'deployed' for item in targets
    )
    status = 'paused' if remaining_deployed else 'rolled_back'
    if int(target.server_id) == int(change.server_id):
        reverse_diff = config_mod.diff_config(change.draft_path, change.rollback_path)
        _save_successful_version(
            change,
            change.rollback_path,
            reverse_diff,
            f'Rollback of change #{change.id}: {change.title}',
        )
    return change_sql.update_change(
        change.id,
        status=status,
        rollback_output=_target_operation_output(targets, 'rollback_output'),
        deployed_at=None if status == 'rolled_back' else change.deployed_at,
    )


def exclude_target(
    change_id: int,
    target_id: int,
    group_id: int,
    reason: str | None = None,
    actor_id: int | None = None,
):
    """Temporarily remove an unavailable slave from this change's rollout plan."""
    require_feature(CHANGE_CENTER)
    change, target = _target_action_context(change_id, target_id, group_id)
    allowed_statuses = (
        'draft', 'validation_failed', 'paused', 'awaiting_promotion',
        'deployment_interrupted', 'auto_rolled_back', 'auto_rollback_failed',
        'rollback_failed',
    )
    if change.status not in allowed_statuses:
        raise RoxywiConflictError('A rollout target cannot be excluded in the current change state')
    if target.role != 'slave':
        raise RoxywiConflictError('The master or standalone node cannot be excluded')
    if target.status in ('deployed', 'deploying', 'rolling_back'):
        raise RoxywiConflictError('Roll back this target before excluding it')
    change_sql.update_target(
        target.id,
        excluded=1,
        excluded_reason=reason or 'Temporarily excluded from rollout',
        is_canary=0,
        batch=-1,
        status='excluded',
    )
    _refresh_rollout_batches(change, change_sql.list_targets(change.id))
    change = change_sql.get_change(change.id)
    change_automation.record_event(
        change.id,
        'target.excluded',
        f'{target.server_name} was temporarily excluded from the rollout',
        target_id=target.id,
        actor_id=actor_id,
        details={'reason': reason},
    )
    return change


def include_target(
    change_id: int,
    target_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    """Return an excluded slave to the rollout after validating its candidate."""
    require_feature(CHANGE_CENTER)
    change, target = _target_action_context(change_id, target_id, group_id)
    if change.status not in (
        'draft', 'validation_failed', 'paused', 'awaiting_promotion',
        'deployment_interrupted', 'auto_rolled_back', 'auto_rollback_failed',
        'rollback_failed',
    ):
        raise RoxywiConflictError('A rollout target cannot be included in the current change state')
    if not target.excluded:
        raise RoxywiConflictError('This rollout target is already included')
    rollback_path = Path(target.rollback_path)
    try:
        if not rollback_path.is_file():
            config_mod.get_config(
                target.server_ip,
                str(rollback_path),
                service=change.service,
                config_file_name=change.remote_path,
            )
            try:
                os.chmod(rollback_path, 0o600)
            except OSError:
                pass
        output = config_mod.validate_candidate_config(
            target.server_ip,
            change.draft_path,
            change.service,
            config_file_name=change.remote_path,
        )
    except Exception as exc:
        change_sql.update_target(target.id, validation_output=str(exc))
        raise RoxywiValidationError(
            f'Cannot include {target.server_name}: {_short_operation_error(exc)}'
        ) from exc
    change_sql.update_target(
        target.id,
        excluded=0,
        excluded_reason=None,
        status='pending',
        validation_output=str(output or 'Configuration is valid'),
        deployment_output=None,
        health_output=None,
        rollback_output=None,
        drift_status='unknown',
        drift_checked_at=None,
        drift_diff=None,
        deployed_at=None,
    )
    _refresh_rollout_batches(change, change_sql.list_targets(change.id))
    change = change_sql.get_change(change.id)
    change_automation.record_event(
        change.id,
        'target.included',
        f'{target.server_name} was returned to the rollout',
        target_id=target.id,
        actor_id=actor_id,
    )
    return change


def rollback_change(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    previous_status = change.status
    targets = _ensure_rollout_targets(change)
    if previous_status == 'deployed':
        target_ids = [target.id for target in targets]
    else:
        target_ids = [
            target.id for target in targets
            if target.status in (
                'deployed', 'deploying', 'deployment_failed', 'deployment_interrupted',
                'rollback_failed', 'rolling_back',
            )
        ]
    if not target_ids:
        raise RoxywiConflictError('No changed rollout targets are available for rollback')
    change = change_sql.transition_change(
        change_id,
        (
            'deployed', 'rollback_failed', 'auto_rollback_failed',
            'deployment_interrupted', 'paused', 'awaiting_promotion',
        ),
        'rolling_back',
    )
    change_automation.record_event(
        change.id,
        'rollback.started',
        'Configuration rollback started',
        actor_id=actor_id,
    )
    try:
        rollback_output, failures = _rollback_targets(
            change, target_ids, actor_id=actor_id
        )
        if failures:
            raise RuntimeError('; '.join(failures))
        primary_was_affected = any(
            target.id in target_ids and int(target.server_id) == int(change.server_id)
            for target in targets
        )
        if previous_status == 'deployed' or primary_was_affected:
            reverse_diff = config_mod.diff_config(change.draft_path, change.rollback_path)
            _save_successful_version(
                change, change.rollback_path, reverse_diff,
                f'Rollback of change #{change.id}: {change.title}'
            )
    except Exception as exc:
        current_output = _target_operation_output(
            change_sql.list_targets(change.id), 'rollback_output'
        )
        change_sql.update_change(
            change_id,
            status='rollback_failed',
            rollback_output=current_output or str(exc),
            drift_status='unknown',
            drift_checked_at=None,
            drift_diff=None,
        )
        change_automation.record_event(
            change.id,
            'rollback.failed',
            'Configuration rollback failed',
            status='rollback_failed',
            actor_id=actor_id,
            details={'error': _short_operation_error(exc)},
        )
        raise RoxywiValidationError(
            f'Rollback failed: {_short_operation_error(exc)}'
        ) from exc
    change = change_sql.update_change(
        change_id,
        status='rolled_back',
        rollback_output=rollback_output,
        drift_status='unknown',
        drift_checked_at=None,
        drift_diff=None,
    )
    change_automation.record_event(
        change.id,
        'rollback.succeeded',
        'Configuration rollback completed successfully',
        actor_id=actor_id,
    )
    return change


def cancel_change(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    change = change_sql.transition_change(change_id, CANCELLABLE_STATUSES, 'cancelled')
    change_automation.record_event(
        change.id,
        'change.cancelled',
        'Configuration change was cancelled',
        actor_id=actor_id,
    )
    return change


def recover_change(change_id: int, group_id: int, actor_id: int | None = None, *, abandoned=False):
    """Unlock an abandoned workflow operation without touching the remote configuration."""
    if not abandoned:
        require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    _require_change_group(change, group_id)
    if change.status not in IN_PROGRESS_STATUSES:
        raise RoxywiConflictError('Only an in-progress operation can be recovered')
    if not abandoned and not is_recoverable(change):
        raise RoxywiConflictError(
            'The operation is still within the five-minute recovery timeout'
        )
    recovery = {
        'validating': (
            'validation_failed',
            'validation_output',
            'Validation was interrupted and unlocked. Run validation again.',
        ),
        'deploying': (
            'deployment_interrupted',
            'deployment_output',
            'Deployment was interrupted and unlocked. Verify the remote state, then deploy or roll back.',
        ),
        'pause_requested': (
            'paused',
            'deployment_output',
            'The pause request was interrupted and unlocked. Resume when ready.',
        ),
        'rolling_back': (
            'rollback_failed',
            'rollback_output',
            'Rollback was interrupted and unlocked. Run rollback again.',
        ),
    }
    status, output_field, recovery_message = recovery[change.status]
    target_status = {
        'validating': 'validation_failed',
        'deploying': 'deployment_interrupted',
        'pause_requested': 'deployment_interrupted',
        'rolling_back': 'rollback_failed',
    }[change.status]
    target_output_field = {
        'validating': 'validation_output',
        'deploying': 'deployment_output',
        'pause_requested': 'deployment_output',
        'rolling_back': 'rollback_output',
    }[change.status]
    active_target_status = 'deploying' if change.status == 'pause_requested' else change.status
    for target in change_sql.list_targets(change.id):
        if target.status == active_target_status:
            target_output = '\n'.join(filter(None, (
                getattr(target, target_output_field) or '',
                recovery_message,
            )))
            change_sql.update_target(
                target.id,
                status=target_status,
                **{target_output_field: target_output},
            )
    previous_output = getattr(change, output_field) or ''
    output = '\n'.join(filter(None, (previous_output, recovery_message)))
    change = change_sql.transition_change(
        change_id,
        (change.status,),
        status,
        pause_requested=0,
        **{output_field: output},
    )
    change_automation.record_event(
        change.id,
        'change.recovered',
        recovery_message,
        actor_id=actor_id,
    )
    return change
