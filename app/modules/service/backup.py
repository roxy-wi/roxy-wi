import os

from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.cred as cred_sql
import app.modules.db.backup as backup_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.server.ssh as ssh_mod
import app.modules.server.server as server_mod
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
import app.modules.service.installation as installation_mod


def delete_backup(serv: str, backup_id: int) -> None:
    if backup_sql.check_exists_backup(serv):
        raise Exception(f'Backup job for {serv} already exists')

    backup_sql.delete_backups(backup_id)
    roxywi_common.logging('backup ', f' a backup job for server {serv} has been deleted', roxywi=1, login=1)


def backup(json_data) -> str:
    cred = int(json_data['cred'])
    server = common.is_ip_or_dns(json_data['server'])
    rserver = common.is_ip_or_dns(json_data['rserver'])
    ssh_settings = ssh_mod.return_ssh_keys_path(rserver, id=cred)
    update_id = ''
    description = ''
    if 'del_id' in json_data:
        time = ''
        rpath = ''
        backup_type = ''
        del_id = int(json_data['del_id'])
    else:
        del_id = ''
        rpath = common.checkAjaxInput(json_data['rpath'])
        backup_type = common.checkAjaxInput(json_data['type'])
        time = common.checkAjaxInput(json_data['time'])
        description = common.checkAjaxInput(json_data['description'])
        if backup_sql.check_exists_backup(server):
            return f'warning: Backup job for {server} already exists'

    if 'update_id' in json_data:
        update_id = int(json_data['update_id'])

    inv = {"server": {"hosts": {}}}
    server_ips = []
    inv['server']['hosts'][server] = {
        'HOST': rserver,
        "SERVER": server,
        "TYPE": backup_type,
        "TIME": time,
        "RPATH": rpath,
        "DELJOB": del_id,
        "USER": ssh_settings['user'],
        "KEY": ssh_settings['key']
    }
    server_ips.append(server)

    try:
        installation_mod.run_ansible(inv, server_ips, 'backup')
    except Exception as e:
        raise Exception(f'error: {e}')

    if not del_id and not update_id:
        if backup_sql.insert_backup_job(server, rserver, rpath, backup_type, time, cred, description):
            roxywi_common.logging('backup ', f' a new backup job for server {server} has been created', roxywi=1,
                                  login=1)
            return render_template(
                'ajax/new_backup.html', backups=backup_sql.select_backups(server=server, rserver=rserver), sshs=cred_sql.select_ssh()
            )

        else:
            raise Exception('Cannot add the job into DB')
    elif del_id:
        backup_sql.delete_backups(del_id)
        roxywi_common.logging('backup ', f' a backup job for server {server} has been deleted', roxywi=1, login=1)
        return 'ok'
    elif update_id:
        backup_sql.update_backup(server, rserver, rpath, backup_type, time, cred, description, update_id)
        roxywi_common.logging('backup ', f' a backup job for server {server} has been updated', roxywi=1, login=1)
        return 'ok'


def s3_backup(server, s3_server, bucket, secret_key, access_key, time, deljob, description) -> str:
    if deljob:
        time = ''
        secret_key = ''
        access_key = ''
        tag = 'delete'
    else:
        tag = 'add'
        if backup_sql.check_exists_s3_backup(server):
            raise Exception(f'error: Backup job for {server} already exists')

    inv = {"server": {"hosts": {}}}
    inv["server"]["hosts"]["localhost"] = {
        "SERVER": server,
        "S3_SERVER": s3_server,
        "BUCKET": bucket,
        "SECRET_KEY": secret_key,
        "ACCESS_KEY": access_key,
        "TIME": time,
        "action": tag
    }

    try:
        installation_mod.run_ansible(inv, [], 's3_backup')
    except Exception as e:
        raise Exception(f'error: {e}')

    if not deljob:
        try:
            backup_sql.insert_s3_backup_job(server, s3_server, bucket, secret_key, access_key, time, description)
        except Exception as e:
            raise Exception(e)
        roxywi_common.logging('backup ', f' a new S3 backup job for server {server} has been created', roxywi=1, login=1)
        return render_template('ajax/new_s3_backup.html', backups=backup_sql.select_s3_backups(server=server, s3_server=s3_server, bucket=bucket))
    elif deljob:
        backup_sql.delete_s3_backups(deljob)
        roxywi_common.logging('backup ', f' a S3 backup job for server {server} has been deleted', roxywi=1, login=1)
        return 'ok'


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
