import os
import shutil
import datetime

import distro

from app import scheduler
import app.modules.db.sql as sql
import app.modules.roxywi.roxy as roxy
import app.modules.tools.common as tools_common
import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


@scheduler.task('interval', id='update_plan', minutes=55, misfire_grace_time=None)
def update_user_status():
    app = scheduler.app
    with app.app_context():
        roxy.update_plan()


@scheduler.task('interval', id='check_new_version', days=1, misfire_grace_time=None)
def check_new_version():
    app = scheduler.app
    with app.app_context():
        tools = sql.get_roxy_tools()
        for tool in tools:
            ver = roxy.check_new_version(tool)
            sql.update_tool_new_version(tool, ver)


@scheduler.task('interval', id='update_cur_tool_versions', days=1, misfire_grace_time=None)
def update_cur_tool_versions():
    app = scheduler.app
    with app.app_context():
        tools_common.update_cur_tool_versions()


@scheduler.task('interval', id='delete_old_uuid', minutes=60, misfire_grace_time=None)
def delete_old_uuid():
    app = scheduler.app
    with app.app_context():
        sql.delete_old_uuid()


@scheduler.task('interval', id='delete_action_history_for_period', minutes=70, misfire_grace_time=None)
def delete_action_history_for_period():
    app = scheduler.app
    with app.app_context():
        sql.delete_action_history_for_period()


@scheduler.task('interval', id='delete_old_logs', hours=1, misfire_grace_time=None)
def delete_old_logs():
    app = scheduler.app
    with app.app_context():
        time_storage = sql.get_setting('log_time_storage')
        log_path = get_config.get_config_var('main', 'log_path')
        try:
            time_storage_hours = time_storage * 24
            for dirpath, dirnames, filenames in os.walk(log_path):
                for file in filenames:
                    curpath = os.path.join(dirpath, file)
                    file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
                    if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
                        os.remove(curpath)
        except Exception as e:
            print(f'error: cannot delete old log files: {e}')


@scheduler.task('interval', id='update_owner_on_log', hours=12, misfire_grace_time=None)
def update_owner_on_log():
    log_path = get_config.get_config_var('main', 'log_path')
    try:
        if distro.id() == 'ubuntu':
            os.system(f'sudo chown www-data:www-data -R {log_path}')
        else:
            os.system(f'sudo chown apache:apache -R {log_path}')
    except Exception:
        pass


@scheduler.task('interval', id='delete_ansible_artifacts', hours=24, misfire_grace_time=None)
def delete_ansible_artifacts():
    full_path = get_config.get_config_var('main', 'fullpath')
    ansible_path = f'{full_path}/app/scripts/ansible'
    folders = ['artifacts', 'env']

    for folder in folders:
        if os.path.isdir(f'{ansible_path}/{folder}'):
            try:
                shutil.rmtree(f'{ansible_path}/{folder}')
            except Exception as e:
                raise Exception(f'error: Cron cannot delete ansible folders: {e}')
