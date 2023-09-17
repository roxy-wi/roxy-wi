import os

import modules.db.sql as sql
import modules.server.server as server_mod
from modules.service.installation import show_installation_output, show_success_installation
from modules.server.ssh import return_ssh_keys_path


def haproxy_exp_installation(serv, ver, ext_prom):
    script = "install_haproxy_exporter.sh"
    stats_port = sql.get_setting('stats_port')
    server_state_file = sql.get_setting('server_state_file')
    stats_user = sql.get_setting('stats_user')
    stats_password = sql.get_setting('stats_password')
    stat_page = sql.get_setting('stats_page')
    proxy = sql.get_setting('proxy')
    ssh_settings = return_ssh_keys_path(serv)
    full_path = '/var/www/haproxy-wi/app'
    service = 'HAProxy exporter'

    try:
        os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")
    except Exception as e:
        raise Exception(f'error: {e}')

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = [
        f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} STAT_PORT={stats_port} STAT_FILE={server_state_file}"
        f" SSH_PORT={ssh_settings['port']} STAT_PAGE={stat_page} VER={ver} EXP_PROM={ext_prom} STATS_USER={stats_user}"
        f" STATS_PASS='{stats_password}' HOST={serv} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    return_out = server_mod.subprocess_execute_with_rc(commands[0])

    try:
        show_installation_output(return_out['error'], return_out['output'], service, rc=return_out['rc'])
    except Exception as e:
        raise Exception(f'error: read output: {e}')

    try:
        os.remove(f'{full_path}/{script}')
    except Exception:
        pass

    return show_success_installation(service)


def nginx_apache_exp_installation(serv, service, ver, ext_prom):
    script = f"install_{service}_exporter.sh"
    stats_user = sql.get_setting(f'{service}_stats_user')
    stats_password = sql.get_setting(f'{service}_stats_password')
    stats_port = sql.get_setting(f'{service}_stats_port')
    stats_page = sql.get_setting(f'{service}_stats_page')
    proxy = sql.get_setting('proxy')
    proxy_serv = ''
    ssh_settings = return_ssh_keys_path(serv)
    full_path = '/var/www/haproxy-wi/app'
    service = f'{service.title()} exporter'

    try:
        os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")
    except Exception as e:
        raise Exception(f'error: {e}')

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    commands = [
        f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} STAT_PORT={stats_port} SSH_PORT={ssh_settings['port']} "
        f"STAT_PAGE={stats_page} STATS_USER={stats_user} STATS_PASS='{stats_password}' HOST={serv} VER={ver} EXP_PROM={ext_prom} "
        f"USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    return_out = server_mod.subprocess_execute_with_rc(commands[0])

    try:
        show_installation_output(return_out['error'], return_out['output'], service, rc=return_out['rc'])
    except Exception as e:
        raise Exception(f'error: read output: {e}')

    try:
        os.remove(f'{full_path}/{script}')
    except Exception:
        pass

    return show_success_installation(service)


def node_keepalived_exp_installation(service: str, serv: str, ver: str, ext_prom: int) -> None:
    script = f"install_{service}_exporter.sh"
    proxy = sql.get_setting('proxy')
    proxy_serv = ''
    ssh_settings = return_ssh_keys_path(serv)
    full_path = '/var/www/haproxy-wi/app'
    service = 'Node exporter'

    try:
        os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")
    except Exception as e:
        raise Exception(f'error: {e}')

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    commands = [
        f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} VER={ver} EXP_PROM={ext_prom} "
        f"HOST={serv} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    return_out = server_mod.subprocess_execute_with_rc(commands[0])

    try:
        show_installation_output(return_out['error'], return_out['output'], service, rc=return_out['rc'])
    except Exception as e:
        raise Exception(f'error: read output: {e}')

    try:
        os.remove(f'{full_path}/{script}')
    except Exception:
        pass

    return show_success_installation(service)
