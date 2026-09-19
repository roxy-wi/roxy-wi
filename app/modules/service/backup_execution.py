"""Native Operations handler with a shared-volume lock, including lease recovery."""

import os
from contextlib import contextmanager
from pathlib import Path
import time

from app.modules.common.time import utc_now
from app.modules.db.db_model import BackupSchedule, InstallationTasks
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.service.backup_scheduler import MODELS
from app.modules.service.backup_transfer import transfer_backup


@contextmanager
def backup_lock(schedule_id):
    root = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'backup-locks'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never unlink lock files: another worker may already be waiting on the inode.
    with (root / f'{int(schedule_id)}.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (13, 36):
                        raise
                    time.sleep(0.1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def execute_backup(task):
    payload = deserialize_operation_payload(task.operation_payload)
    with backup_lock(payload['schedule_id']):
        # A previous worker may have completed while this recovered delivery
        # waited for the shared lock. Re-read before touching remote storage.
        current = InstallationTasks.get_or_none(
            (InstallationTasks.id == task.id)
            & (InstallationTasks.operation_id == task.operation_id)
        )
        if current is None:
            return 'missing'
        if current.status in ('completed', 'failed'):
            return current.status
        return _execute_locked(task, payload)


def _execute_locked(task, payload):
    # Persist both success and failure before releasing the transfer lock.
    # A recovered delivery must never observe a running task after its previous
    # attempt has stopped transferring but before that attempt records failure.
    try:
        schedule = BackupSchedule.get_by_id(payload['schedule_id'])
        if (schedule.legacy_pending or schedule.active_task_id != task.id
                or schedule.run_key != payload['run_key']):
            raise ValueError('Backup task no longer belongs to the active schedule')
        config = MODELS[schedule.kind].get_by_id(schedule.backup_id)
        transfer_backup(schedule.kind, config, schedule.run_key)
        InstallationTasks.update(status='completed', error=None,
                                 finish_date=utc_now(), updated_at=utc_now()).where(
            InstallationTasks.id == task.id
        ).execute()
        return 'completed'
    except Exception as error:
        # SDK/SSH errors can include signed URLs, usernames and credential data.
        detail = f'Backup failed ({type(error).__name__}); check source storage, destination access and credentials'
        InstallationTasks.update(status='failed', error=detail,
                                 finish_date=utc_now(), updated_at=utc_now()).where(
            InstallationTasks.id == task.id
        ).execute()
        return 'failed'
