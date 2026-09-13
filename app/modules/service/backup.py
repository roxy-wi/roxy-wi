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


def create_backup_inv(json_data: BackupRequest, del_id: int = 0) -> int:
    server = server_sql.get_server(json_data.server_id)
    ssh_settings = ssh_mod.return_ssh_keys_path(server.ip, json_data.cred_id)
    inv = {"server": {"hosts": {}}}
    server_ips = []
    inv['server']['hosts'][server.ip] = {
        'HOST': str(json_data.rserver),
        "SERVER": server.ip,
        "TYPE": json_data.type,
        "TIME": json_data.time,
        "RPATH": json_data.rpath,
        "DELJOB": del_id,
        "USER": ssh_settings['user'],
        "KEY": ssh_settings['key']
    }
    server_ips.append(str(server.ip))

    try:
        return installation_mod.run_ansible_thread(
            inv, server_ips, 'backup', 'Filesystem backup'
        )
    except Exception as e:
        raise Exception(f'error: {e}')


def create_s3_backup_inv(data: S3BackupRequest, tag: str) -> int:
    server = server_sql.get_server(data.server_id)
    inv = {"server": {"hosts": {}}}
    inv["server"]["hosts"]["localhost"] = {
        "SERVER": server.hostname,
        "S3_SERVER": str(data.s3_server),
        "BUCKET": data.bucket,
        "SECRET_KEY": data.secret_key,
        "ACCESS_KEY": data.access_key,
        "TIME": data.time,
        "action": tag
    }

    try:
        return installation_mod.run_ansible_thread(
            inv, [], 's3_backup', 'S3 backup', run_locally=True
        )
    except Exception as e:
        raise Exception(f'error: {e}')


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
    if backup_sql.check_exists_backup(json_data.server_id, 'fs'):
        raise RoxywiConflictError('FS backup for this server already exists')

    with InstallationTasks._meta.database.atomic():
        last_id = backup_sql.insert_backup_job(
            json_data.server_id, json_data.rserver, json_data.rpath, json_data.type,
            json_data.time, json_data.cred_id, json_data.description,
        )
        task_id = create_backup_inv(json_data)
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
    with InstallationTasks._meta.database.atomic():
        task_id = create_backup_inv(json_data, 1)
        backup_sql.delete_backup(backup_id, 'fs')
    roxywi_common.logging('backup ', f'A backup job for server {json_data.server_id} has been deleted', roxywi=1, login=1)
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def update_backup(json_data: BackupRequest, backup_id: int) -> tuple:
    with InstallationTasks._meta.database.atomic():
        task_id = create_backup_inv(json_data)
        backup_sql.update_backup_job(backup_id, 'fs', **json_data.model_dump(mode='json'))
    roxywi_common.logging('backup ', f'A backup job for server {json_data.server_id} has been updated', roxywi=1, login=1)
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def create_s3_backup(data: S3BackupRequest, is_api: bool) -> tuple:
    if backup_sql.check_exists_backup(data.server_id, 's3'):
        raise RoxywiConflictError('S3 backup for this server already exists')

    try:
        with InstallationTasks._meta.database.atomic():
            last_id = backup_sql.insert_s3_backup_job(**data.model_dump(mode='json'))
            task_id = create_s3_backup_inv(data, 'add')
        roxywi_common.logging('backup ', f'A new S3 backup job for server {data.server_id} has been created', roxywi=1, login=1)
    except Exception as e:
        raise Exception(e)

    if is_api:
        response = IdResponse(id=last_id).model_dump(mode='json')
    else:
        temp = render_template(
            'ajax/new_s3_backup.html',
            backups=backup_sql.select_s3_backups(**data.model_dump(mode='json')),
            lang=roxywi_common.get_user_lang_for_flask(),
        )
        response = IdDataResponse(id=last_id, data=temp).model_dump(mode='json')
    response.update({'status': 'accepted', 'tasks_ids': [task_id]})
    return response, 202


def update_s3_backup(data: S3BackupRequest, backup_id: int) -> tuple:
    with InstallationTasks._meta.database.atomic():
        task_id = create_s3_backup_inv(data, 'add')
        backup_sql.update_backup_job(backup_id, 's3', **data.model_dump(mode='json'))
    return {'status': 'accepted', 'tasks_ids': [task_id]}, 202


def delete_s3_backup(data: S3BackupRequest, backup_id: int) -> tuple:
    try:
        with InstallationTasks._meta.database.atomic():
            task_id = create_s3_backup_inv(data, 'delete')
            backup_sql.delete_backup(backup_id, 's3')
        roxywi_common.logging('backup ', f'The S3 backup job for server {data.server_id} has been deleted', roxywi=1, login=1)
    except Exception as e:
        raise e
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
