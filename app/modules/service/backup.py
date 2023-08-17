import os

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.server.ssh as ssh_mod
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.service.installation as installation_mod


def backup(serv, rpath, time, backup_type, rserver, cred, deljob, update, description) -> None:
    script = 'backup.sh'
    ssh_settings = ssh_mod.return_ssh_keys_path('localhost', id=cred)

    if deljob:
        time = ''
        rpath = ''
        backup_type = ''
    elif update:
        deljob = ''
    else:
        deljob = ''
        if sql.check_exists_backup(serv):
            print(f'warning: Backup job for {serv} already exists')
            return None

    os.system(f"cp scripts/{script} .")

    commands = [
        f"chmod +x {script} && ./{script} HOST={rserver} SERVER={serv} TYPE={backup_type} SSH_PORT={ssh_settings['port']} "
        f"TIME={time} RPATH={rpath} DELJOB={deljob} USER={ssh_settings['user']} KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    for line in output:
        if any(s in line for s in ("Traceback", "FAILED")):
            try:
                print(f'error: {line}')
                break
            except Exception:
                print(f'error: {output}')
                break
    else:
        if not deljob and not update:
            if sql.insert_backup_job(serv, rserver, rpath, backup_type, time, cred, description):
                env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
                template = env.get_template('new_backup.html')
                template = template.render(
                    backups=sql.select_backups(server=serv, rserver=rserver), sshs=sql.select_ssh()
                )
                print(template)
                print('success: Backup job has been created')
                roxywi_common.logging('backup ', f' a new backup job for server {serv} has been created', roxywi=1, login=1)
            else:
                print('error: Cannot add the job into DB')
        elif deljob:
            sql.delete_backups(deljob)
            print('Ok')
            roxywi_common.logging('backup ', f' a backup job for server {serv} has been deleted', roxywi=1, login=1)
        elif update:
            sql.update_backup(serv, rserver, rpath, backup_type, time, cred, description, update)
            print('Ok')
            roxywi_common.logging('backup ', f' a backup job for server {serv} has been updated', roxywi=1, login=1)

    os.remove(script)


def s3_backup(server, s3_server, bucket, secret_key, access_key, time, deljob, description) -> None:
    script = 's3_backup.sh'
    tag = 'add'

    if deljob:
        time = ''
        secret_key = ''
        access_key = ''
        tag = 'delete'
    else:
        if sql.check_exists_s3_backup(server):
            raise Exception(f'error: Backup job for {server} already exists')

    os.system(f"cp scripts/{script} .")

    commands = [
        f"chmod +x {script} && ./{script} SERVER={server} S3_SERVER={s3_server} BUCKET={bucket} SECRET_KEY={secret_key} ACCESS_KEY={access_key} TIME={time} TAG={tag}"
    ]

    return_out = server_mod.subprocess_execute_with_rc(commands[0])

    if not deljob and not update:
        try:
            if installation_mod.show_installation_output(return_out['error'], return_out['output'], 'S3 backup', rc=return_out['rc'], api=1):
                try:
                    sql.insert_s3_backup_job(server, s3_server, bucket, secret_key, access_key, time, description)
                except Exception as e:
                    raise Exception(f'error: {e}')
        except Exception as e:
            raise Exception(e)
        env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
        template = env.get_template('new_s3_backup.html')
        template = template.render(backups=sql.select_s3_backups(server=server, s3_server=s3_server, bucket=bucket))
        print(template)
        print('success: Backup job has been created')
        roxywi_common.logging('backup ', f' a new S3 backup job for server {server} has been created', roxywi=1, login=1)
    elif deljob:
        sql.delete_s3_backups(deljob)
        print('Ok')
        roxywi_common.logging('backup ', f' a S3 backup job for server {server} has been deleted', roxywi=1, login=1)


def git_backup(server_id, service_id, git_init, repo, branch, period, cred, deljob, description) -> None:
    servers = roxywi_common.get_dick_permit()
    proxy = sql.get_setting('proxy')
    services = sql.select_services()
    server_ip = sql.select_server_ip_by_id(server_id)
    service_name = sql.select_service_name_by_id(service_id).lower()
    service_config_dir = sql.get_setting(service_name + '_dir')
    script = 'git_backup.sh'
    proxy_serv = ''
    ssh_settings = ssh_mod.return_ssh_keys_path('localhost', id=int(cred))

    os.system(f"cp scripts/{script} .")

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    if repo is None or git_init == '0':
        repo = ''
    if branch is None or branch == '0':
        branch = 'main'

    commands = [
        f"chmod +x {script} && ./{script} HOST={server_ip} DELJOB={deljob} SERVICE={service_name} INIT={git_init} "
        f"SSH_PORT={ssh_settings['port']} PERIOD={period} REPO={repo} BRANCH={branch} CONFIG_DIR={service_config_dir} "
        f"PROXY={proxy_serv} USER={ssh_settings['user']} KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    for line in output:
        if any(s in line for s in ("Traceback", "FAILED")):
            try:
                print('error: ' + line)
                break
            except Exception:
                print('error: ' + output)
                break
    else:
        if deljob == '0':
            if sql.insert_new_git(
                    server_id=server_id, service_id=service_id, repo=repo, branch=branch,
                    period=period, cred=cred, description=description
            ):
                gits = sql.select_gits(server_id=server_id, service_id=service_id)
                sshs = sql.select_ssh()

                lang = roxywi_common.get_user_lang()
                env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
                template = env.get_template('new_git.html')
                template = template.render(gits=gits, sshs=sshs, servers=servers, services=services, new_add=1, lang=lang)
                print(template)
                print('success: Git job has been created')
                roxywi_common.logging(
                    server_ip, ' A new git job has been created', roxywi=1, login=1, keep_history=1, service=service_name
                )
        else:
            if sql.delete_git(form.getvalue('git_backup')):
                print('Ok')
    os.remove(script)
