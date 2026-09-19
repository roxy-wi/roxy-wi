from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.cred as cred_sql
import app.modules.db.backup as backup_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.server.ssh as ssh_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.installation as installation_mod
from app.modules.db.db_model import InstallationTasks
from app.modules.subscription.access import GIT_BACKUP, require_feature
from app.modules.roxywi.class_models import BackupRequest, IdResponse, IdDataResponse, S3BackupRequest, GitBackupRequest
from app.modules.roxywi.exception import RoxywiConflictError
from app.modules.service import backup_scheduler


def _schedule_receipt(kind, server_id, action):
    """Keep the existing 202/tasks_ids contract for synchronous schedule changes."""
    from app.modules.common.time import utc_now
    claims = roxywi_common.get_jwt_token_claims()
    return InstallationTasks.insert(
        service_name=f'{"S3" if kind == "s3" else "Filesystem"} backup schedule {action}',
        server_ids=[server_id], user_id=claims.get('user_id'), group_id=claims.get('group'),
        operation_type='backup', status='completed',
        start_date=utc_now(), finish_date=utc_now(), updated_at=utc_now(),
    ).execute()


def _validate_config(kind, data):
    from pathlib import PurePosixPath
    from app.modules.service.backup_transfer import endpoint_url
    backup_scheduler.next_run(data.time, backup_scheduler.schedule_timezone(), backup_scheduler.utc_now())
    server = server_sql.get_server(data.server_id)
    if kind == 'fs':
        if not data.rserver or not data.rpath or data.type not in ('backup', 'synchronization'):
            raise ValueError('Backup destination, path and type are required')
        path = PurePosixPath(data.rpath)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Backup destination must be an absolute path without parent traversal')
        ssh_mod.return_ssh_keys_path(server.ip, data.cred_id)
    else:
        if not data.s3_server or not data.bucket or not data.access_key or not data.secret_key:
            raise ValueError('S3 endpoint, bucket and credentials are required')
        endpoint_url(data.s3_server)


def create_git_backup_inv(data: GitBackupRequest, server_ip: str, service: str, del_job: int = 0) -> int:
    require_feature(GIT_BACKUP)
    service_config_dir = sql.get_setting(service + '_dir')
    ssh_settings = ssh_mod.return_ssh_keys_path(server_ip, data.cred_id)
    inv = {"server": {"hosts": {}}}
    inv["server"]["hosts"][server_ip] = {
        "REPO": data.repo,
        "CONFIG_DIR": service_config_dir,
        "PERIOD": data.time,
        "INIT": data.init,
        "BRANCH": data.branch,
        "SERVICE": service,
        "DELJOB": del_job,
        "KEY": ssh_settings['key']
    }

    try:
        return installation_mod.run_ansible_thread(
            inv, [server_ip], 'git_backup', 'Git backup'
        )
    except Exception as e:
        raise Exception(f'error: {e}')


def create_backup(json_data: BackupRequest, is_api: bool) -> tuple:
    _validate_config('fs', json_data)
    if backup_sql.check_exists_backup(json_data.server_id, 'fs'):
        raise RoxywiConflictError('FS backup for this server already exists')

    with backup_scheduler.transaction():
        backup_scheduler.ensure_unique_server('fs', json_data.server_id)
        last_id = backup_sql.insert_backup_job(
            json_data.server_id, json_data.rserver, json_data.rpath, json_data.type,
            json_data.time, json_data.cred_id, json_data.description,
        )
        backup_scheduler.configure('fs', last_id, json_data.time)
        task_id = _schedule_receipt('fs', json_data.server_id, 'created')
    roxywi_common.logging('backup ', f'A new backup job for server {json_data.server_id} has been created', roxywi=1, login=1)
    if is_api:
        response = IdResponse(id=last_id).model_dump(mode='json')
    else:
        data = render_template(
            'ajax/new_backup.html',
            backups=backup_sql.select_backups(backup_id=last_id),
            sshs=cred_sql.select_ssh(),
            servers=roxywi_common.get_dick_permit(virt=1, disable=0, only_group=1),
            lang=roxywi_common.get_user_lang_for_flask(),
        )
        response = IdDataResponse(data=data, id=last_id).model_dump(mode='json')
    response.update({'status': 'accepted', 'tasks_ids': [task_id]})
    return response, 202


def delete_backup(json_data: BackupRequest, backup_id: int) -> tuple:
    with backup_scheduler.transaction():
        schedule = backup_scheduler.ensure_editable('fs', backup_id)
        stored = backup_sql.get_backup(backup_id, 'fs')
        task_id = _schedule_receipt('fs', int(stored.server_id), 'deleted')
        backup_sql.delete_backup(backup_id, 'fs')
        schedule.delete_instance()
    roxywi_common.logging('backup ', f'A backup job for server {json_data.server_id} has been deleted', roxywi=1, login=1)
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def update_backup(json_data: BackupRequest, backup_id: int) -> tuple:
    _validate_config('fs', json_data)
    with backup_scheduler.transaction():
        schedule = backup_scheduler.ensure_editable('fs', backup_id)
        backup_scheduler.ensure_unique_server('fs', json_data.server_id, exclude_id=backup_id)
        backup_sql.update_backup_job(backup_id, 'fs', **json_data.model_dump(mode='json'))
        backup_scheduler.configure('fs', backup_id, json_data.time, existing=schedule)
        task_id = _schedule_receipt('fs', json_data.server_id, 'updated')
    roxywi_common.logging('backup ', f'A backup job for server {json_data.server_id} has been updated', roxywi=1, login=1)
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def create_s3_backup(data: S3BackupRequest, is_api: bool) -> tuple:
    _validate_config('s3', data)
    if backup_sql.check_exists_backup(data.server_id, 's3'):
        raise RoxywiConflictError('S3 backup for this server already exists')

    with backup_scheduler.transaction():
        backup_scheduler.ensure_unique_server('s3', data.server_id)
        last_id = backup_sql.insert_s3_backup_job(**data.model_dump(mode='json'))
        backup_scheduler.configure('s3', last_id, data.time)
        task_id = _schedule_receipt('s3', data.server_id, 'created')
    roxywi_common.logging('backup ', f'A new S3 backup job for server {data.server_id} has been created', roxywi=1, login=1)

    if is_api:
        response = IdResponse(id=last_id).model_dump(mode='json')
    else:
        temp = render_template(
            'ajax/new_s3_backup.html',
            backups=backup_sql.select_s3_backups(backup_id=last_id),
            server_name=server_sql.get_server(data.server_id).hostname,
            lang=roxywi_common.get_user_lang_for_flask(),
        )
        response = IdDataResponse(id=last_id, data=temp).model_dump(mode='json')
    response.update({'status': 'accepted', 'tasks_ids': [task_id]})
    return response, 202


def update_s3_backup(data: S3BackupRequest, backup_id: int) -> tuple:
    _validate_config('s3', data)
    with backup_scheduler.transaction():
        schedule = backup_scheduler.ensure_editable('s3', backup_id)
        backup_scheduler.ensure_unique_server('s3', data.server_id, exclude_id=backup_id)
        backup_sql.update_backup_job(backup_id, 's3', **data.model_dump(mode='json'))
        backup_scheduler.configure('s3', backup_id, data.time, existing=schedule)
        task_id = _schedule_receipt('s3', data.server_id, 'updated')
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def delete_s3_backup(data: S3BackupRequest, backup_id: int) -> tuple:
    with backup_scheduler.transaction():
        schedule = backup_scheduler.ensure_editable('s3', backup_id)
        stored = backup_sql.get_backup(backup_id, 's3')
        task_id = _schedule_receipt('s3', int(stored.server_id), 'deleted')
        backup_sql.delete_backup(backup_id, 's3')
        schedule.delete_instance()
    roxywi_common.logging('backup ', f'The S3 backup job for server {data.server_id} has been deleted', roxywi=1, login=1)
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def create_git_backup(data: GitBackupRequest, is_api: bool) -> tuple:
    require_feature(GIT_BACKUP)
    server_ip = server_sql.get_server(data.server_id).ip
    service_name = service_sql.select_service_name_by_id(data.service_id).lower()
    try:
        with InstallationTasks._meta.database.atomic():
            last_id = backup_sql.insert_new_git(
                server_id=data.server_id, service_id=data.service_id, repo=data.repo,
                branch=data.branch, time=data.time, cred=data.cred_id,
                description=data.description,
            )
            task_id = create_git_backup_inv(data, server_ip, service_name)
        roxywi_common.logging(server_ip, 'A new git job has been created', roxywi=1, login=1, keep_history=1,
                              service=service_name)
    except Exception as e:
        raise Exception(e)

    if is_api:
        response = IdResponse(id=last_id).model_dump(mode='json')
    else:
        kwargs = {
            "gits": backup_sql.select_gits(server_id=data.server_id, service_id=data.service_id),
            "sshs": cred_sql.select_ssh(),
            "servers": roxywi_common.get_dick_permit(),
            "services": service_sql.select_services(),
            "new_add": 1,
            "lang": roxywi_common.get_user_lang_for_flask()
        }

        temp = render_template('ajax/new_git.html', **kwargs)
        response = IdDataResponse(id=last_id, data=temp).model_dump(mode='json')
    response.update({'status': 'accepted', 'tasks_ids': [task_id]})
    return response, 202


def update_git_backup(data: GitBackupRequest, backup_id: int) -> tuple:
    require_feature(GIT_BACKUP)
    server = server_sql.get_server(data.server_id)
    service_name = service_sql.select_service_name_by_id(data.service_id).lower()
    with InstallationTasks._meta.database.atomic():
        task_id = create_git_backup_inv(data, server.ip, service_name)
        backup_sql.update_backup_job(
            backup_id, 'git', **data.model_dump(mode='json', exclude={'init'})
        )
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def delete_git_backup(data: GitBackupRequest, backup_id: int) -> tuple:
    require_feature(GIT_BACKUP)
    server_ip = server_sql.get_server(data.server_id).ip
    service_name = service_sql.select_service_name_by_id(data.service_id).lower()
    with InstallationTasks._meta.database.atomic():
        task_id = create_git_backup_inv(data, server_ip, service_name, 1)
        backup_sql.delete_backup(backup_id, 'git')

    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202
