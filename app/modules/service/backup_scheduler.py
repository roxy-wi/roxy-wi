"""Database schedules; RabbitMQ carries only the durable Operations task identity."""

import os
from contextlib import contextmanager
from datetime import timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from peewee import SqliteDatabase
from tzlocal import get_localzone_name

from app.modules.common.time import utc_now
from app.modules.db.db_model import Backup, S3Backup, BackupSchedule, InstallationTasks, Server
from app.modules.operations.queue import serialize_operation_payload
from app.modules.roxywi.exception import RoxywiConflictError


MODELS = {'fs': Backup, 's3': S3Backup}
ACTIVE_STATUSES = ('created', 'published', 'running')


def schedule_timezone():
    return os.environ.get('ROXYWI_BACKUP_TIMEZONE') or get_localzone_name()


def next_run(period, zone, after):
    if period not in ('hourly', 'daily', 'weekly', 'monthly'):
        raise ValueError('Unsupported backup period')
    local_zone = ZoneInfo(zone)
    wall = after.replace(tzinfo=timezone.utc).astimezone(local_zone).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    if period != 'hourly':
        wall = wall.replace(hour=0)
    if period == 'weekly':
        wall -= timedelta(days=(wall.weekday() + 1) % 7)
    elif period == 'monthly':
        wall = wall.replace(day=1)
    # Advance wall-calendar boundaries, not 24-hour durations across DST.
    # Round trips discard nonexistent local times; both folds remain eligible.
    while True:
        candidates = []
        for fold in (0, 1):
            instant = wall.replace(tzinfo=local_zone, fold=fold).astimezone(timezone.utc)
            if instant.astimezone(local_zone).replace(tzinfo=None) == wall:
                candidate = instant.replace(tzinfo=None)
                if candidate > after:
                    candidates.append(candidate)
        if candidates:
            return min(candidates)
        if period == 'monthly':
            wall = wall.replace(year=wall.year + (wall.month == 12), month=wall.month % 12 + 1)
        else:
            wall += {'hourly': timedelta(hours=1), 'daily': timedelta(days=1),
                     'weekly': timedelta(days=7)}[period]


@contextmanager
def transaction():
    database = BackupSchedule._meta.database
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        yield


def locked_schedule(schedule_id):
    query = BackupSchedule.select().where(BackupSchedule.id == schedule_id)
    if not isinstance(BackupSchedule._meta.database, SqliteDatabase):
        query = query.for_update()
    return query.get()


def ensure_unique_server(kind, server_id, exclude_id=None):
    # Serialize creation against the existing server row in MySQL; SQLite's
    # IMMEDIATE transaction already serializes writers. Use locking reads to
    # avoid a stale REPEATABLE READ snapshot after another creator commits.
    query = Server.select().where(Server.server_id == server_id)
    if not isinstance(BackupSchedule._meta.database, SqliteDatabase):
        query = query.for_update()
    query.get()
    model = MODELS[kind]
    query = model.select().where(model.server_id == str(server_id))
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if not isinstance(BackupSchedule._meta.database, SqliteDatabase):
        query = query.for_update()
    if query.exists():
        raise RoxywiConflictError('Backup for this server already exists')


def ensure_editable(kind, backup_id):
    schedule = BackupSchedule.get_or_none(kind=kind, backup_id=backup_id)
    if schedule is None:
        raise RoxywiConflictError('Backup schedule is missing; run database migrations')
    schedule = locked_schedule(schedule.id)
    if schedule.legacy_pending:
        raise RoxywiConflictError('Run migrate-backup-cron on the original host before changing this backup')
    task = _current_task(schedule.active_task_id)
    if task is not None and task.status in ACTIVE_STATUSES:
        raise RoxywiConflictError('Backup is queued or running; wait until it finishes')
    return schedule


def _current_task(task_id):
    query = InstallationTasks.select().where(InstallationTasks.id == task_id)
    if not isinstance(BackupSchedule._meta.database, SqliteDatabase):
        # An earlier consistent read in this transaction must not hide a task
        # created while we waited for the schedule row lock under MySQL RR.
        query = query.for_update()
    return query.get_or_none()


def configure(kind, backup_id, period, *, existing=None):
    zone = existing.timezone if existing else schedule_timezone()
    values = dict(next_run_at=next_run(period, zone, utc_now()), retry_at=None,
                  active_task_id=None, failures=0)
    if existing:
        BackupSchedule.update(**values).where(BackupSchedule.id == existing.id).execute()
        return existing.id
    return BackupSchedule.create(kind=kind, backup_id=backup_id, timezone=zone, **values).id


def _enqueue(schedule, config, now):
    server = Server.get_or_none(Server.server_id == int(config.server_id))
    task_id = InstallationTasks.insert(
        service_name=f'{"S3" if schedule.kind == "s3" else "Filesystem"} backup #{config.id}',
        server_ids=[int(config.server_id)], group_id=server.group_id if server else None, user_id=None,
        operation_id=str(uuid4()), operation_type='backup',
        operation_payload=serialize_operation_payload({
            'schedule_id': schedule.id, 'run_key': schedule.run_key,
        }), status='created', start_date=now, updated_at=now,
    ).execute()
    schedule.active_task_id = schedule.last_task_id = task_id
    schedule.retry_at = None


def dispatch_due_backups(now=None, limit=100):
    now = now or utc_now()
    candidates = list(BackupSchedule.select(BackupSchedule.id).where(
        (BackupSchedule.legacy_pending == False)
        & ((BackupSchedule.next_run_at <= now) | (BackupSchedule.retry_at <= now)
           | BackupSchedule.active_task_id.is_null(False))
    ).order_by(BackupSchedule.next_run_at))
    queued = 0
    for candidate in candidates:
        if queued >= limit:
            break
        with transaction():
            try:
                schedule = locked_schedule(candidate.id)
            except BackupSchedule.DoesNotExist:
                continue  # Deleted after the initial candidate read.
            if schedule.legacy_pending:
                continue
            config = MODELS[schedule.kind].get_or_none(MODELS[schedule.kind].id == schedule.backup_id)
            if config is None:
                continue
            if schedule.active_task_id is not None:
                task = _current_task(schedule.active_task_id)
                if task is not None and task.status in ACTIVE_STATUSES:
                    continue
                schedule.active_task_id = None
                if task is not None and task.status == 'completed':
                    schedule.failures = 0
                else:
                    schedule.failures += 1
                    if schedule.failures < 3:
                        schedule.retry_at = now + timedelta(seconds=60 * 2 ** (schedule.failures - 1))
                    else:
                        schedule.retry_at = None
                        # Do not immediately start another cycle after a long outage.
                        schedule.next_run_at = next_run(config.time, schedule.timezone, now)
            if schedule.retry_at is not None:
                if schedule.retry_at <= now:
                    _enqueue(schedule, config, now)
                    queued += 1
            elif schedule.next_run_at <= now:
                schedule.run_key = str(uuid4())
                schedule.failures = 0
                schedule.next_run_at = next_run(config.time, schedule.timezone, now)
                _enqueue(schedule, config, now)
                queued += 1
            schedule.save()
    return queued


def schedule_state(kind, backup_id):
    schedule = BackupSchedule.get_or_none(kind=kind, backup_id=backup_id)
    if schedule is None:
        return None
    task = InstallationTasks.get_or_none(InstallationTasks.id == schedule.last_task_id)
    return {
        'timezone': schedule.timezone,
        'next_run_at': schedule.next_run_at.isoformat() + 'Z',
        'retry_at': schedule.retry_at.isoformat() + 'Z' if schedule.retry_at else None,
        'migration_required': schedule.legacy_pending,
        'last_task_id': schedule.last_task_id,
        'last_status': task.status if task else None,
    }


def cleanup_backup_history(now=None, retention_days=None, *, batch_size=500, max_batches=20):
    """Prune terminal backup history without removing scheduler/retry state."""
    if retention_days is None:
        retention_days = int(os.environ.get('ROXYWI_BACKUP_HISTORY_RETENTION_DAYS', '30'))
    if retention_days < 0:
        raise ValueError('Backup history retention days must be non-negative')
    if retention_days == 0:
        return 0
    if batch_size < 1 or max_batches < 1:
        raise ValueError('Backup history cleanup batch limits must be positive')
    cutoff = (now or utc_now()) - timedelta(days=retention_days)
    active = BackupSchedule.select(BackupSchedule.active_task_id).where(
        BackupSchedule.active_task_id.is_null(False)
    )
    latest = BackupSchedule.select(BackupSchedule.last_task_id).where(
        BackupSchedule.last_task_id.is_null(False)
    )
    eligible = (
        (InstallationTasks.operation_type == 'backup')
        & InstallationTasks.status.in_(('completed', 'failed'))
        & (InstallationTasks.finish_date < cutoff)
        & InstallationTasks.id.not_in(active)
        & InstallationTasks.id.not_in(latest)
    )
    deleted = 0
    # Bound both each transaction and total work per scheduler invocation.
    for _ in range(max_batches):
        with transaction():
            ids = [row.id for row in InstallationTasks.select(InstallationTasks.id)
                   .where(eligible).order_by(InstallationTasks.id).limit(batch_size)]
            if not ids:
                break
            # Recheck status/references in the DELETE itself: MySQL's earlier
            # consistent read may predate a concurrent scheduler transaction.
            deleted += InstallationTasks.delete().where(
                InstallationTasks.id.in_(ids) & eligible
            ).execute()
    return deleted
