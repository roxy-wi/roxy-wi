import os

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.server.ssh as ssh_mod
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common


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
            sys.exit()

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
                roxywi_common.logging('backup ', f' a new backup job for server {serv} has been created', roxywi=1,
                                      login=1)
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


def create_s3_backup() -> None:
    ...


def delete_s3_backup() -> None:
    ...


def show_s3_backup():
    ...
