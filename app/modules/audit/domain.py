"""Typed bridges from actual domain outcomes, excluding arbitrary job output."""
import re
import hashlib
from pathlib import Path

from app.modules.audit import events
from app.modules.roxywi import logger


def _snapshot_digest(change, filename):
    if not filename:
        return None
    from app.modules.config.common import get_config_dir
    try:
        folder = (Path(get_config_dir(change.service)).resolve() / 'changes')
        path = Path(filename).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or path.stat().st_size > 16*1024*1024:
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def change_event(change, event, target=None):
    try:
        if not events.enabled():
            return
        timeline_type = re.sub(r'[^a-z0-9_.-]', '_', str(event.event_type).lower())
        kind = (timeline_type if timeline_type.startswith('change.') else 'change.'+timeline_type)[:128]
        status = str(event.status or change.status)
        leaf = timeline_type.rsplit('.', 1)[-1]
        failed = (leaf in {'failed', 'missed'} or leaf.endswith('_failed') or
                  status in {'failed', 'conflict', 'validation_failed', 'rollback_failed',
                             'auto_rollback_failed', 'schedule_missed'})
        succeeded = leaf in {'succeeded', 'applied', 'completed', 'deployed', 'rolled_back',
                             'auto_rolled_back', 'validated', 'approved', 'batch_completed',
                             'cancelled', 'pause_cancelled', 'paused', 'recovered'}
        outcome = ('failed' if failed else 'succeeded' if succeeded else
                   'unknown' if status == 'deployment_interrupted' else 'accepted')
        details = {'change_id': change.id, 'subject_type': change.service, 'status': status,
                   'before_digest': _snapshot_digest(change, getattr(target, 'rollback_path', None) or change.rollback_path),
                   'after_digest': _snapshot_digest(change, change.draft_path)}
        if (status in {'rolled_back', 'auto_rolled_back'} or leaf in {'rolled_back', 'auto_rolled_back'}
                or timeline_type == 'rollback.succeeded'):
            details['before_digest'], details['after_digest'] = details['after_digest'], details['before_digest']
        if target:
            details['target_id'] = target.id
        events.record(kind, outcome, user_id=event.actor_id or change.user_id,
                      group_id=int(change.group_id), details=details, force=True)
    except Exception:
        # This event is a result: do not misreport an already executed change as
        # rolled back merely because its external audit result could not persist.
        logger.error('Change audit result could not be recorded', change_id=change.id)


def operation_started(task):
    if not events.enabled():
        return None
    user_id = task.__data__.get('user_id')
    group_id = task.__data__.get('group_id')
    context = dict(user_id=user_id, group_id=group_id, actor=events.actor_name(user_id))
    details = {'operation_id': task.operation_id, 'task_id': task.id,
               'subject_type': task.operation_type, 'status': 'running'}
    events.record('operation.started', 'requested', **context, details=details)
    return context, details


def operation_finished(task, context, raised):
    if context is None:
        return
    actor, details = context
    status = str(task.status)
    outcome = 'failed' if raised or status == 'failed' else 'succeeded' if status == 'completed' else 'unknown'
    try:
        events.record('operation.finished', outcome, **actor,
                      details={**details, 'status': status}, force=True)
    except Exception:
        logger.error('Operation audit result could not be recorded', operation_id=task.operation_id, task_id=task.id)
