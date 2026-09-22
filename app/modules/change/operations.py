"""Durable Change Center commands executed only by Operations workers."""

from contextlib import contextmanager
from datetime import timedelta
import os
from pathlib import Path
from uuid import uuid4

from peewee import SqliteDatabase

from app.modules.change import service, automation
from app.modules.common.execution_context import group_settings
from app.modules.common.file_lock import file_lock
from app.modules.common.time import utc_now
from app.modules.db import change as change_sql, service as service_sql, user as user_sql
from app.modules.db.db_model import ConfigChange, InstallationTasks, Server, User
from app.modules.operations.queue import deserialize_operation_payload, serialize_operation_payload
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi import logger
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiPermissionError, RoxywiValidationError
from app.modules.subscription.access import CHANGE_CENTER, require_feature


@contextmanager
def locked_change(change_id, group_id, *, idle=True):
    """Serialize enqueue and short metadata edits without holding locks over SSH."""
    database = ConfigChange._meta.database
    with change_sql._WRITE_LOCK:
        with database.atomic('IMMEDIATE') if isinstance(database, SqliteDatabase) else database.atomic():
            query = ConfigChange.select().where(ConfigChange.id == change_id)
            if not isinstance(database, SqliteDatabase):
                query = query.for_update()
            change = query.get()
            service._require_change_group(change, group_id)
            if idle and change.active_task_id:
                raise RoxywiConflictError('A Change Center operation is already queued or running')
            yield change


def _check_action(change, action, target_id):
    if target_id is not None:
        target = change_sql.get_change_target(change.id, target_id)
        allowed = service.TARGET_ACTION_STATUSES
        if action == 'rollback':
            allowed = (*allowed, 'deployed')
            if target.excluded or target.status not in (
                'deployed', 'deployment_failed', 'deployment_interrupted', 'rollback_failed'
            ):
                raise RoxywiConflictError('This rollout target has no deployed configuration to roll back')
        elif action == 'include':
            allowed = (*allowed, 'draft', 'validation_failed')
            if not target.excluded:
                raise RoxywiConflictError('This rollout target is already included')
        elif action == 'retry':
            if target.excluded or target.status == 'deployed':
                raise RoxywiConflictError('This rollout target cannot be retried')
        else:
            raise RoxywiValidationError('Unsupported target operation')
    else:
        allowed = {
            'validate': service.VALIDATABLE_STATUSES,
            'deploy': ('approved' if change.requires_approval else 'validated', *service.RETRYABLE_DEPLOY_STATUSES),
            'rollback': ('deployed', 'rollback_failed', 'auto_rollback_failed', 'deployment_interrupted', 'paused', 'awaiting_promotion'),
            'resume': service.RESUMABLE_STATUSES,
            'promote': ('awaiting_promotion',),
            'drift': ('deployed',),
        }.get(action)
        if allowed is None:
            raise RoxywiValidationError('Unsupported change operation')
    if change.status not in allowed:
        raise RoxywiConflictError('This operation is not available in the current change state')


def enqueue(change_id, action, group_id, actor_id, *, target_id=None, scheduled=False):
    require_feature(CHANGE_CENTER)
    with locked_change(change_id, group_id) as change:
        if scheduled:
            if action != 'deploy' or change.status != 'scheduled' or change.scheduled_at > utc_now():
                raise RoxywiConflictError('This scheduled deployment is not due')
            actor_id = change.scheduled_by or change.user_id
            change = change_sql.transition_change(
                change.id, ('scheduled',),
                change.schedule_base_status or ('approved' if change.requires_approval else 'validated'),
            )
        _check_action(change, action, target_id)
        targets = list(change_sql.list_targets(change.id))
        servers = {target.server_id: target.server_ip for target in targets}
        if not servers:
            server = Server.get_by_id(change.server_id)
            servers = {server.server_id: server.ip for server, _role in service._rollout_servers(server, change.service)}
        payload = {
            'change_id': change.id, 'action': action, 'target_id': target_id,
            'actor_id': actor_id, 'scheduled': scheduled, 'started': False,
            'servers': {str(key): value for key, value in servers.items()},
            'legacy_targets': not targets,
        }
        task = InstallationTasks.create(
            service_name=f'Change #{change.id}: {action}',
            server_ids=list(servers), user_id=actor_id, group_id=group_id,
            operation_id=str(uuid4()), operation_type='change',
            operation_payload=serialize_operation_payload(payload),
            status='created', updated_at=utc_now(),
        )
        ConfigChange.update(active_task_id=task.id, last_task_id=task.id).where(ConfigChange.id == change.id).execute()
        if action != 'drift' or actor_id is not None:
            automation.record_event(
                change.id, 'operation.queued', f'{action.title()} queued in Operations',
                target_id=target_id, actor_id=actor_id, details={'task_id': task.id},
            )
        return change_sql.get_change(change.id)


def serialize_operation(change):
    task_id = change.active_task_id or change.last_task_id
    if not task_id:
        return None
    task = InstallationTasks.get_or_none(InstallationTasks.id == task_id)
    if task is None:  # Completed Operations history may have been pruned.
        return None
    return {
        'id': task.id, 'operation_id': task.operation_id, 'status': task.status,
        'active': bool(change.active_task_id), 'error': task.error,
    }


def cleanup_history(*, now=None, retention_days=None, batch_size=500, max_batches=20):
    days = int(os.environ.get('ROXYWI_CHANGE_HISTORY_RETENTION_DAYS', '30')) if retention_days is None else retention_days
    if days < 0 or batch_size < 1 or max_batches < 1:
        raise ValueError('Change history retention and batch limits are invalid')
    if days == 0:
        return 0
    active = ConfigChange.select(ConfigChange.active_task_id).where(ConfigChange.active_task_id.is_null(False))
    latest = ConfigChange.select(ConfigChange.last_task_id).where(ConfigChange.last_task_id.is_null(False))
    eligible = (
        (InstallationTasks.operation_type == 'change')
        & InstallationTasks.status.in_(('completed', 'failed'))
        & (InstallationTasks.finish_date < (now or utc_now()) - timedelta(days=days))
        & InstallationTasks.id.not_in(active) & InstallationTasks.id.not_in(latest)
    )
    deleted = 0
    for _ in range(max_batches):
        with InstallationTasks._meta.database.atomic():
            ids = [task.id for task in InstallationTasks.select(InstallationTasks.id)
                   .where(eligible).order_by(InstallationTasks.id).limit(batch_size)]
            if not ids:
                break
            deleted += InstallationTasks.delete().where(InstallationTasks.id.in_(ids) & eligible).execute()
    return deleted


def _authorize(change, payload):
    # Recheck access at execution time, including scheduled commands whose
    # author or targets may have been removed since the schedule was created.
    actor = User.get_or_none(User.user_id == (payload['actor_id'] or change.user_id))
    role = user_sql.get_user_role_in_group(actor.user_id, change.group_id) if actor else None
    if not actor or not actor.enabled or role is None or int(role) > 3:
        raise RoxywiPermissionError('The operation author no longer has access to this group')
    service_id = str(service_sql.select_service_id_by_slug(change.service))
    if service_id not in actor.user_services.split():
        raise RoxywiPermissionError('The operation author no longer has access to this service')
    if payload.get('legacy_targets'):
        topology = service._rollout_servers(Server.get_by_id(change.server_id), change.service)
        if {str(server.server_id): server.ip for server, _role in topology} != payload['servers']:
            raise RoxywiConflictError('The rollout topology changed while waiting for Operations')
    for server_id, address in payload['servers'].items():
        server = Server.get_or_none(Server.server_id == int(server_id))
        if server is None or int(server.group_id) != int(change.group_id) or server.ip != address:
            raise RoxywiPermissionError('A rollout server was removed, moved or changed its address')
        service._require_server_service(server, change.service)


def _finish(task, change, status, error=None, *, audit=True):
    with locked_change(change.id, change.group_id, idle=False) as current:
        if current.active_task_id != task.id:
            raise RoxywiConflictError('The operation no longer owns this change')
        InstallationTasks.update(
            status=status, error=error, finish_date=utc_now(), updated_at=utc_now(),
        ).where(InstallationTasks.id == task.id).execute()
        ConfigChange.update(active_task_id=None).where(ConfigChange.id == change.id).execute()
        # Routine automatic drift checks already record meaningful drift
        # transitions. Keep their task history without flooding the audit trail.
        if audit or status == 'failed':
            automation.record_event(
                change.id, f'operation.{status}', error or 'Operations command completed',
                details={'task_id': task.id},
            )
    return status


def _interrupt(change):
    current = change_sql.get_change(change.id)
    if current.status in service.IN_PROGRESS_STATUSES:
        service.recover_change(current.id, current.group_id, abandoned=True)


def execute(task):
    task = InstallationTasks.get_by_id(task.id)
    if task.status in ('completed', 'failed'):
        return task.status
    change = ConfigChange.get_or_none(ConfigChange.active_task_id == task.id)
    if change is None:
        InstallationTasks.update(
            status='failed', error='The change or operation reservation no longer exists.',
            finish_date=utc_now(), updated_at=utc_now(),
        ).where(
            (InstallationTasks.id == task.id)
            & InstallationTasks.status.not_in(('completed', 'failed'))
        ).execute()
        return InstallationTasks.get_by_id(task.id).status
    lock_dir = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'change-locks'
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(lock_dir / f'{change.id}.lock'), group_settings(change.group_id):
        # An earlier worker may still be finishing after a DB/heartbeat outage.
        # Re-read only after its process lock has been released.
        task = InstallationTasks.get_by_id(task.id)
        if task.status in ('completed', 'failed'):
            return task.status
        change = change_sql.get_change(change.id)
        if change.active_task_id != task.id:
            raise RoxywiConflictError('The operation no longer owns this change')
        audit = True
        try:
            payload = deserialize_operation_payload(task.operation_payload)
            audit = payload['action'] != 'drift' or payload['actor_id'] is not None
            if payload['change_id'] != change.id:
                raise RoxywiConflictError('The operation payload does not match this change')
            if payload.get('started'):
                _interrupt(change)
                return _finish(task, change, 'failed', 'Operations was interrupted. Inspect the change and remote state before retrying.', audit=audit)
            require_feature(CHANGE_CENTER)
            _authorize(change, payload)
            if payload['scheduled'] and change.maintenance_window_end and change.maintenance_window_end < utc_now():
                change_sql.update_change(
                    change.id, status='schedule_missed', finished_at=utc_now(),
                    deployment_output='Maintenance window expired while waiting for Operations.',
                )
                automation.record_event(change.id, 'schedule.missed', 'Maintenance window expired while waiting for Operations')
                return _finish(task, change, 'failed', 'Maintenance window expired before deployment could start.')
            _check_action(change, payload['action'], payload['target_id'])
            # Durable marker precedes ALL remote IO. An expired lease must never
            # silently repeat a partially applied deployment or validation.
            payload['started'] = True
            InstallationTasks.update(operation_payload=serialize_operation_payload(payload)).where(InstallationTasks.id == task.id).execute()
            args = [change.id]
            if payload['target_id'] is not None:
                args.append(payload['target_id'])
                handler = getattr(service, f"{payload['action']}_target")
            elif payload['action'] == 'drift':
                handler = automation.check_change_drift
            else:
                handler = getattr(service, f"{payload['action']}_change")
            result = handler(*args, change.group_id, payload['actor_id'])
            if payload['action'] == 'validate' and result.status == 'validation_failed':
                return _finish(task, change, 'failed', 'Configuration validation failed. See the change details.')
        except Exception as exc:
            _interrupt(change)
            # Detailed validator/SSH output belongs to the change. Do not copy
            # credentials or configuration text from exceptions into task logs.
            logger.error(f'Change Center operation {task.id} failed ({type(exc).__name__})')
            error = (
                exc.public_message
                if isinstance(exc, (RoxywiPermissionError, RoxywiConflictError, RoxywiValidationError))
                else 'Change operation failed. See the change details.'
            )
            return _finish(task, change, 'failed', error, audit=audit)
        return _finish(task, change, 'completed', audit=audit)
