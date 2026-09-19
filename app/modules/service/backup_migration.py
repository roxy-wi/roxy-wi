"""Explicit, resumable cutover on the original package host, before moving its DB."""

import hashlib
import os
from pathlib import Path
import re
import subprocess

import psutil

from app.modules.common.time import utc_now
from app.modules.db.db_model import BackupSchedule, InstallationTasks
from app.modules.operations.queue import deserialize_operation_payload
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.service.backup_scheduler import transaction


MARKER = re.compile(r'^#Ansible: Roxy-WI (?:S3 )?Backup configs for server .+ (?:kp|hap|nginx|apache)_config$')


def remove_legacy_entries(crontab):
    lines = crontab.splitlines(keepends=True)
    retained = []
    removed = 0
    index = 0
    while index < len(lines):
        if MARKER.fullmatch(lines[index].strip()):
            if index + 1 >= len(lines) or not re.match(r'^\s*(?:@|\d|\*)', lines[index + 1]):
                raise ValueError('Unexpected legacy backup cron entry; manual inspection required')
            index += 2
            removed += 1
        else:
            retained.append(lines[index])
            index += 1
    return ''.join(retained), removed


def _crontab(*args, input=None):
    return subprocess.run(['crontab', '-u', 'root', *args], input=input,
                          text=True, capture_output=True, timeout=30,
                          env={**os.environ, 'LC_ALL': 'C'})


def _read_crontab():
    result = _crontab('-l')
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 1 and 'no crontab for root' in result.stderr.lower():
        return ''
    raise RuntimeError('Cannot read the original root crontab')


def _require_original_host(config):
    if (os.name != 'posix' or os.geteuid() != 0
            or config.get_config_var('main', 'deployment_mode', 'package') != 'package'):
        raise RuntimeError('Run migrate-backup-cron as root on the original package host before moving the database')


def migrate_legacy_cron():
    config = GetConfigVar()
    _require_original_host(config)
    for process in psutil.process_iter(['name', 'cmdline']):
        args = process.info['cmdline'] or []
        if (process.info['name'] in ('rsync', 's3cmd') or any('s3cmd' in arg for arg in args)):
            if any('/configs/' in arg for arg in args):
                raise RuntimeError('A legacy backup is running; wait for it to finish before cutover')
    for task in InstallationTasks.select().where(
        (InstallationTasks.operation_type == 'ansible')
        & InstallationTasks.status.in_(('created', 'published', 'running'))
    ):
        payload = deserialize_operation_payload(task.operation_payload)
        steps = payload.get('steps') or [payload]
        if any(step.get('ansible_role') in ('backup', 's3_backup') for step in steps):
            raise RuntimeError('Legacy backup setup operations must finish before cutover')
    original = _read_crontab()
    cleaned, removed = remove_legacy_entries(original)
    if original:
        root = Path(config.get_config_var('main', 'lib_path')) / 'backup-cron-migration'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / (hashlib.sha256(original.encode()).hexdigest() + '.crontab')
        if not path.exists():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(original)
    with transaction():
        if _read_crontab() != original:
            raise RuntimeError('Root crontab changed during cutover; retry')
        if removed and _crontab('-', input=cleaned).returncode != 0:
            raise RuntimeError('Cannot replace the root crontab; backup schedules remain paused')
        if remove_legacy_entries(_read_crontab())[1]:
            raise RuntimeError('Legacy backup cron entries still exist; backup schedules remain paused')
        activated = BackupSchedule.update(legacy_pending=False, next_run_at=utc_now()).where(
            BackupSchedule.legacy_pending == True
        ).execute()
    return removed, activated
