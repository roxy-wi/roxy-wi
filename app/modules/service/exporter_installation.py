import os

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
from modules.service.installation import show_installation_output
from modules.server.ssh import return_ssh_keys_path

form = common.form


def haproxy_exp_installation():
    serv = form.getvalue('haproxy_exp_install')
    ver = form.getvalue('exporter_v')
    ext_prom = form.getvalue('ext_prom')
    script = "install_haproxy_exporter.sh"
    stats_port = sql.get_setting('stats_port')
    server_state_file = sql.get_setting('server_state_file')
    stats_user = sql.get_setting('stats_user')
    stats_password = sql.get_setting('stats_password')
    stat_page = sql.get_setting('stats_page')
    proxy = sql.get_setting('proxy')
    ssh_settings = return_ssh_keys_path(serv)

    os.system(f"cp scripts/{script} .")

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = [
        f"chmod +x {script} &&  ./{script} PROXY={proxy_serv} STAT_PORT={stats_port} STAT_FILE={server_state_file}"
        f" SSH_PORT={ssh_settings['port']} STAT_PAGE={stat_page} VER={ver} EXP_PROM={ext_prom} STATS_USER={stats_user}"
        f" STATS_PASS='{stats_password}' HOST={serv} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    show_installation_output(error, output, 'HAProxy exporter')

    os.remove(script)


def nginx_apache_exp_installation():
    if form.getvalue('nginx_exp_install'):
        service = 'nginx'
    elif form.getvalue('apache_exp_install'):
        service = 'apache'

    serv = common.is_ip_or_dns(form.getvalue('serv'))
    ver = common.checkAjaxInput(form.getvalue('exporter_v'))
    ext_prom = common.checkAjaxInput(form.getvalue('ext_prom'))
    script = f"install_{service}_exporter.sh"
    stats_user = sql.get_setting(f'{service}_stats_user')
    stats_password = sql.get_setting(f'{service}_stats_password')
    stats_port = sql.get_setting(f'{service}_stats_port')
    stats_page = sql.get_setting(f'{service}_stats_page')
    proxy = sql.get_setting('proxy')
    proxy_serv = ''
    ssh_settings = return_ssh_keys_path(serv)

    os.system(f"cp scripts/{script} .")

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    commands = [
        f"chmod +x {script} && ./{script} PROXY={proxy_serv} STAT_PORT={stats_port} SSH_PORT={ssh_settings['port']} STAT_PAGE={stats_page}" 
        f" STATS_USER={stats_user} STATS_PASS='{stats_password}' HOST={serv} VER={ver} EXP_PROM={ext_prom} USER={ssh_settings['user']} "
        f" PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    show_installation_output(error, output, f'{service.title()} exporter')

    os.remove(script)


def node_exp_installation():
    serv = common.is_ip_or_dns(form.getvalue('node_exp_install'))
    ver = common.checkAjaxInput(form.getvalue('exporter_v'))
    ext_prom = common.checkAjaxInput(form.getvalue('ext_prom'))
    script = "install_node_exporter.sh"
    proxy = sql.get_setting('proxy')
    proxy_serv = ''
    ssh_settings = return_ssh_keys_path(serv)

    os.system(f"cp scripts/{script} .")

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    commands = [
        f"chmod +x {script} &&  ./{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} VER={ver} EXP_PROM={ext_prom} "
        f"HOST={serv} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    show_installation_output(error, output, 'Node exporter')

    os.remove(script)
