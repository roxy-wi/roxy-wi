from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.cred as cred_sql
import app.modules.db.backup as backup_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.server.ssh as ssh_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.installation as installation_mod
from app.modules.roxywi.class_models import BackupRequest, IdResponse, IdDataResponse, BaseResponse, S3BackupRequest


def create_backup_inv(json_data: BackupRequest, del_id: int = 0) -> None:
    ssh_settings = ssh_mod.return_ssh_keys_path(str(json_data.server), id=json_data.cred_id)
    inv = {"server": {"hosts": {}}}
    server_ips = []
    inv['server']['hosts'][str(json_data.server)] = {
        'HOST': str(json_data.rserver),
        "SERVER": str(json_data.server),
        "TYPE": json_data.type,
        "TIME": json_data.time,
        "RPATH": json_data.rpath,
        "DELJOB": del_id,
        "USER": ssh_settings['user'],
        "KEY": ssh_settings['key']
    }
    server_ips.append(str(json_data.server))

    try:
        installation_mod.run_ansible(inv, server_ips, 'backup')
    except Exception as e:
        raise Exception(f'error: {e}')


def create_s3_backup_inv(data: S3BackupRequest, tag: str) -> None:
    inv = {"server": {"hosts": {}}}
    inv["server"]["hosts"]["localhost"] = {
        "SERVER": str(data.server),
        "S3_SERVER": str(data.s3_server),
        "BUCKET": data.bucket,
        "SECRET_KEY": data.secret_key,
        "ACCESS_KEY": data.access_key,
        "TIME": data.time,
        "action": tag
    }

    try:
        installation_mod.run_ansible(inv, [], 's3_backup')
    except Exception as e:
        raise Exception(f'error: {e}')


def create_backup(json_data: BackupRequest, is_api: bool) -> tuple:
    if backup_sql.check_exists_backup(json_data.server):
        raise Exception(f'warning: Backup job for {json_data.server} already exists')

    create_backup_inv(json_data)

    last_id = backup_sql.insert_backup_job(json_data.server, json_data.rserver, json_data.rpath, json_data.type,
                                           json_data.time, json_data.cred_id, json_data.description)
    roxywi_common.logging('backup ', f' a new backup job for server {json_data.server} has been created', roxywi=1, login=1)
    if is_api:
        return IdResponse(id=last_id).model_dump(mode='json'), 201
    else:
        data = render_template(
            'ajax/new_backup.html',
            backups=backup_sql.select_backups(server=json_data.server, rserver=json_data.rserver),
            sshs=cred_sql.select_ssh()
        )
        return IdDataResponse(data=data, id=last_id).model_dump(mode='json'), 201



def delete_backup(json_data: BackupRequest, backup_id: int) -> tuple:
    create_backup_inv(json_data, backup_id)
    backup_sql.delete_backups(backup_id)
    roxywi_common.logging('backup ', f' a backup job for server {json_data.server} has been deleted', roxywi=1, login=1)
    return BaseResponse().model_dump(mode='json'), 204


def update_backup(json_data: BackupRequest, backup_id: int) -> tuple:
    create_backup_inv(json_data)
    backup_sql.update_backup(json_data.server, json_data.rserver, json_data.rpath, json_data.type,
                             json_data.time, json_data.cred_id, json_data.description, backup_id)
    roxywi_common.logging('backup ', f' a backup job for server {json_data.server} has been updated', roxywi=1, login=1)
    return BaseResponse().model_dump(mode='json'), 201


def create_s3_backup(data: S3BackupRequest, is_api: bool) -> tuple:
    # if deljob:
    #     time = ''
    #     secret_key = ''
    #     access_key = ''
    #     tag = 'delete'
    # else:
    #     tag = 'add'
    if backup_sql.check_exists_s3_backup(data.server):
        raise Exception(f'Backup job for {data.server} already exists')

    try:
        create_s3_backup_inv(data, 'add')
    except Exception as e:
        raise e

    # if not deljob:
    try:
        last_id = backup_sql.insert_s3_backup_job(**data.model_dump(mode='json'))
        roxywi_common.logging('backup ', f'a new S3 backup job for server {data.server} has been created', roxywi=1, login=1)
    except Exception as e:
        raise Exception(e)

    if is_api:
        return IdResponse(id=last_id).model_dump(mode='json'), 201
    else:
        temp = render_template('ajax/new_s3_backup.html', backups=backup_sql.select_s3_backups(**data.model_dump(mode='json')))
        return IdDataResponse(id=last_id, data=temp).model_dump(mode='json'), 201
    # elif deljob:
    #     backup_sql.delete_s3_backups(deljob)
    #     roxywi_common.logging('backup ', f' a S3 backup job for server {server} has been deleted', roxywi=1, login=1)
    #     return 'ok'



def delete_s3_backup(data: S3BackupRequest, backup_id: int) -> None:
    try:
        create_s3_backup_inv(data, 'delete')
        backup_sql.delete_s3_backups(backup_id)
        roxywi_common.logging('backup ', f'a S3 backup job for server {data.server} has been deleted', roxywi=1, login=1)
    except Exception as e:
        raise e


def git_backup(server_id, service_id, git_init, repo, branch, period, cred, del_job, description, backup_id) -> str:
    server_ip = server_sql.select_server_ip_by_id(server_id)
    service_name = service_sql.select_service_name_by_id(service_id).lower()
    service_config_dir = sql.get_setting(service_name + '_dir')
    ssh_settings = ssh_mod.return_ssh_keys_path(server_ip, id=cred)

    if repo is None or git_init == '0':
        repo = ''
    if branch is None or branch == '0':
        branch = 'main'

    inv = {"server": {"hosts": {}}}
    inv["server"]["hosts"][server_ip] = {
        "REPO": repo,
        "CONFIG_DIR": service_config_dir,
        "PERIOD": period,
        "INIT": git_init,
        "BRANCH": branch,
        "SERVICE": service_name,
        "DELJOB": del_job,
        "KEY": ssh_settings['key']
    }

    try:
        installation_mod.run_ansible(inv, [server_ip], 'git_backup')
    except Exception as e:
        raise Exception(f'error: {e}')

    if not del_job:
        backup_sql.insert_new_git(server_id=server_id, service_id=service_id, repo=repo, branch=branch, period=period, cred=cred, description=description)
        kwargs = {
            "gits": backup_sql.select_gits(server_id=server_id, service_id=service_id),
            "sshs":  cred_sql.select_ssh(),
            "servers": roxywi_common.get_dick_permit(),
            "services": service_sql.select_services(),
            "new_add": 1,
            "lang": roxywi_common.get_user_lang_for_flask()
        }
        roxywi_common.logging(server_ip, 'A new git job has been created', roxywi=1, login=1, keep_history=1, service=service_name)
        return render_template('ajax/new_git.html', **kwargs)
    else:
        if backup_sql.delete_git(backup_id):
            return 'ok'
