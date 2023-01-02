#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import http.cookies
from uuid import UUID

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.server.ssh as ssh_mod
import modules.common.common as common
import modules.config.config as config_mod
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.server.server as server_mod
import modules.service.common as service_common
import modules.service.installation as service_mod

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)

form = common.form
serv = common.is_ip_or_dns(form.getvalue('serv'))
act = form.getvalue("act")
token = form.getvalue("token")

if (
        form.getvalue('new_metrics')
        or form.getvalue('new_http_metrics')
        or form.getvalue('new_waf_metrics')
        or form.getvalue('new_nginx_metrics')
        or form.getvalue('new_apache_metrics')
        or form.getvalue('metrics_hapwi_ram')
        or form.getvalue('metrics_hapwi_cpu')
        or form.getvalue('getoption')
        or form.getvalue('getsavedserver')
):
    print('Content-type: application/json\n')
else:
    print('Content-type: text/html\n')

if act == "checkrestart":
    servers = roxywi_common.get_dick_permit(ip=serv)
    for server in servers:
        if server != "":
            print("ok")
            sys.exit()
    sys.exit()

try:
    uuid_obj = UUID(token, version=4)
except ValueError:
    print('error: Your token is not valid')
    sys.exit()
except Exception:
    print('error: There is no token')
    sys.exit()

if not sql.check_token_exists(token):
    print('error: Your token has been expired')
    sys.exit()

if form.getvalue('getcerts') is not None and serv is not None:
    config_mod.get_ssl_certs(serv)

if form.getvalue('checkSshConnect') is not None and serv is not None:
    try:
        print(server_mod.ssh_command(serv, ["ls -1t"]))
    except Exception as e:
        print(e)

if form.getvalue('getcert') is not None and serv is not None:
    config_mod.get_ssl_cert(serv)

if form.getvalue('delcert') is not None and serv is not None:
    config_mod.del_ssl_cert(serv)

if serv and form.getvalue('ssl_cert'):
    config_mod.upload_ssl_cert(serv)

if form.getvalue('backend') is not None:
    import modules.config.runtime as runtime
    runtime.show_backends(serv)

if form.getvalue('ip_select') is not None:
    import modules.config.runtime as runtime
    runtime.show_backends(serv)

if form.getvalue('ipbackend') is not None and form.getvalue('backend_server') is None:
    import modules.config.runtime as runtime

    runtime.show_frontend_backend()

if form.getvalue('ipbackend') is not None and form.getvalue('backend_server') is not None:
    import modules.config.runtime as runtime

    runtime.show_server()

if form.getvalue('backend_ip') is not None:
    import modules.config.runtime as runtime

    runtime.change_ip_and_port()

if form.getvalue('maxconn_select') is not None:
    import modules.config.runtime as runtime
    serv = common.checkAjaxInput(form.getvalue('maxconn_select'))
    runtime.get_backends_from_config(serv, backends='frontend')

if form.getvalue('maxconn_frontend') is not None:
    import modules.config.runtime as runtime

    runtime.change_maxconn()

if form.getvalue('table_serv_select') is not None:
    import modules.config.runtime as runtime
    print(runtime.get_all_stick_table())

if form.getvalue('table_select') is not None:
    import modules.config.runtime as runtime

    runtime.table_select()

if form.getvalue('ip_for_delete') is not None:
    import modules.config.runtime as runtime

    runtime.delete_ip_from_stick_table()

if form.getvalue('table_for_clear') is not None:
    import modules.config.runtime as runtime

    runtime.clear_stick_table()

if form.getvalue('list_serv_select') is not None:
    import modules.config.runtime as runtime

    runtime.list_of_lists()

if form.getvalue('list_select_id') is not None:
    import modules.config.runtime as runtime

    runtime.show_lists()

if form.getvalue('list_id_for_delete') is not None:
    import modules.config.runtime as runtime

    runtime.delete_ip_from_list()

if form.getvalue('list_ip_for_add') is not None:
    import modules.config.runtime as runtime

    runtime.add_ip_to_list()

if form.getvalue('sessions_select') is not None:
    import modules.config.runtime as runtime

    runtime.select_session()

if form.getvalue('sessions_select_show') is not None:
    import modules.config.runtime as runtime

    runtime.show_session()

if form.getvalue('session_delete_id') is not None:
    import modules.config.runtime as runtime

    runtime.delete_session()

if form.getvalue("change_pos") is not None:
    pos = common.checkAjaxInput(form.getvalue('change_pos'))
    server_id = common.checkAjaxInput(form.getvalue('pos_server_id'))
    sql.update_server_pos(pos, server_id)

if form.getvalue('show_ip') is not None and serv is not None:
    commands = ['sudo hostname -i | tr " " "\n"|grep -v "%"']
    server_mod.ssh_command(serv, commands, ip="1")

if form.getvalue('showif'):
    commands = ["sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}' |awk -F':' '{print $1}'"]
    server_mod.ssh_command(serv, commands, ip="1")

if form.getvalue('action_hap') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_hap')
    service_action.action_haproxy(serv, action)

if form.getvalue('action_nginx') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_nginx')
    service_action.action_nginx(serv, action)

if form.getvalue('action_keepalived') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_keepalived')
    service_action.action_keepalived(serv, action)

if form.getvalue('action_waf') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_waf')
    service_action.action_haproxy_waf(serv, action)

if form.getvalue('action_waf_nginx') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_waf_nginx')
    service_action.action_nginx_waf(serv, action)

if form.getvalue('action_apache') is not None and serv is not None:
    import modules.service.action as service_action

    action = form.getvalue('action_apache')
    service_action.action_apache(serv, action)

if form.getvalue('action_service') is not None:
    import modules.roxywi.roxy as roxy

    action = common.checkAjaxInput(form.getvalue('action_service'))
    roxy.action_service(action, serv)

if act == "overviewHapserverBackends":
    service = common.checkAjaxInput(form.getvalue('service'))

    service_common.overview_backends(serv, service)

if form.getvalue('show_userlists'):
    configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    format_file = 'cfg'

    try:
        sections = config_mod.get_userlists(configs_dir + roxywi_common.get_files(configs_dir, format_file)[0])
    except Exception as e:
        roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
        try:
            cfg = f'{configs_dir}{serv}-{get_date.return_date("config")}.{format_file}'
        except Exception as e:
            roxywi_common.logging('Roxy-WI server', f' Cannot generate a cfg path {e}', roxywi=1)
        try:
            error = config_mod.get_config(serv, cfg)
        except Exception as e:
            roxywi_common.logging('Roxy-WI server', f' Cannot download a config {e}', roxywi=1)
        try:
            sections = config_mod.get_userlists(cfg)
        except Exception as e:
            roxywi_common.logging('Roxy-WI server', f' Cannot get Userlists from the config file {e}', roxywi=1)
            sections = 'error: Cannot get Userlists'

    print(sections)

if act == "overviewHapservers":
    service = common.checkAjaxInput(form.getvalue('service'))

    service_common.get_overview_last_edit(serv, service)

if act == "overview":
    import modules.roxywi.overview as roxy_overview

    roxy_overview.show_overview(serv)

if act == "overviewwaf":
    import modules.roxywi.waf as roxy_waf

    waf_service = common.checkAjaxInput(form.getvalue('service'))
    serv = common.checkAjaxInput(serv)
    roxy_waf.waf_overview(serv, waf_service)

if act == "overviewServers":
    server_id = common.checkAjaxInput(form.getvalue('id'))
    name = common.checkAjaxInput(form.getvalue('name'))
    service = common.checkAjaxInput(form.getvalue('service'))

    service_common.overview_service(serv, server_id, name, service)

if act == "overviewServices":
    import modules.roxywi.overview as roxy_overview

    roxy_overview.show_services_overview()

if form.getvalue('action'):
    import modules.service.haproxy as service_haproxy

    service_haproxy.stat_page_action(serv)

if serv is not None and act == "stats":
    service = common.checkAjaxInput(form.getvalue('service'))

    service_common.get_stat_page(serv, service)

if serv is not None and form.getvalue('show_log') is not None:
    import modules.roxywi.logs as roxywi_logs

    rows = form.getvalue('show_log')
    waf = form.getvalue('waf')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    service = form.getvalue('service')
    out = roxywi_logs.show_roxy_log(serv, rows=rows, waf=waf, grep=grep, hour=hour, minut=minut, hour1=hour1,
                                 minut1=minut1, service=service)
    print(out)

if serv is not None and form.getvalue('rows1') is not None:
    import modules.roxywi.logs as roxywi_logs

    rows = form.getvalue('rows1')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    out = roxywi_logs.show_roxy_log(serv, rows=rows, waf='0', grep=grep, hour=hour, minut=minut, hour1=hour1,
                                 minut1=minut1, service='apache_internal')
    print(out)

if form.getvalue('viewlogs') is not None:
    import modules.roxywi.logs as roxywi_logs

    viewlog = form.getvalue('viewlogs')
    rows = form.getvalue('rows')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    if roxywi_common.check_user_group():
        out = roxywi_logs.show_roxy_log(serv=viewlog, rows=rows, waf='0', grep=grep, hour=hour, minut=minut, hour1=hour1,
                                     minut1=minut1, service='internal')
        print(out)

if serv is not None and act == "showMap":
    import modules.service.haproxy as service_haproxy

    service_haproxy.show_map(serv)

if form.getvalue('servaction') is not None:
    import modules.service.haproxy as service_haproxy

    service_haproxy.runtime_command(serv)

if act == "showCompareConfigs":
    config_mod.show_compare_config(serv)

if serv is not None and form.getvalue('right') is not None:
    config_mod.compare_config()

if serv is not None and act == "configShow":
    config_mod.show_config(serv)

if act == 'configShowFiles':
    config_mod.show_config_files(serv)

if act == 'showRemoteLogFiles':
    service = form.getvalue('service')
    log_path = sql.get_setting(f'{service}_path_logs')
    return_files = server_mod.get_remote_files(serv, log_path, 'log')
    if 'error: ' in return_files:
        print(return_files)
        sys.exit()

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_log_files.html')
    template = template.render(serv=serv, return_files=return_files, path_dir=log_path)
    print(template)

if form.getvalue('master'):
    service_mod.keepalived_master_install()

if form.getvalue('master_slave'):
    service_mod.keepalived_slave_install()

if form.getvalue('masteradd'):
    service_mod.keepalived_masteradd()

if form.getvalue('masteradd_slave'):
    service_mod.keepalived_slaveadd()

if form.getvalue('master_slave_hap'):
    master = form.getvalue('master_slave_hap')
    slave = form.getvalue('slave')
    server = form.getvalue('server')
    docker = form.getvalue('docker')

    if server == 'master':
        service_mod.install_haproxy(master, server=server, docker=docker)
    elif server == 'slave':
        service_mod.install_haproxy(slave, server=server, docker=docker)

if form.getvalue('master_slave_nginx'):
    master = form.getvalue('master_slave_nginx')
    slave = form.getvalue('slave')
    server = form.getvalue('server')
    docker = form.getvalue('docker')

    if server == 'master':
        service_mod.install_nginx(master, server=server, docker=docker)
    elif server == 'slave':
        service_mod.install_nginx(slave, server=server, docker=docker)

if form.getvalue('install_grafana'):
    service_mod.grafana_install()

if form.getvalue('haproxy_exp_install'):
    import modules.service.exporter_installation as exp_installation

    exp_installation.haproxy_exp_installation()

if form.getvalue('nginx_exp_install') or form.getvalue('apache_exp_install'):
    import modules.service.exporter_installation as exp_installation

    exp_installation.nginx_apache_exp_installation()

if form.getvalue('node_exp_install'):
    import modules.service.exporter_installation as exp_installation

    exp_installation.node_exp_installation()

if form.getvalue('backup') or form.getvalue('deljob') or form.getvalue('backupupdate'):
    serv = form.getvalue('server')
    rpath = form.getvalue('rpath')
    time = form.getvalue('time')
    backup_type = form.getvalue('type')
    rserver = form.getvalue('rserver')
    cred = form.getvalue('cred')
    deljob = form.getvalue('deljob')
    update = form.getvalue('backupupdate')
    description = form.getvalue('description')
    script = 'backup.sh'
    ssh_settings = ssh_mod.return_ssh_keys_path('localhost', id=int(cred))

    if deljob:
        time = ''
        rpath = ''
        backup_type = ''
    elif update:
        deljob = ''
    else:
        deljob = ''
        if sql.check_exists_backup(serv):
            print('warning: Backup job for %s already exists' % serv)
            sys.exit()

    os.system(f"cp scripts/{script} .")

    commands = [
        f"chmod +x {script} &&  ./{script}  HOST={rserver}  SERVER={serv} TYPE={backup_type} SSH_PORT={ssh_settings['port']} "
        f"TIME={time} RPATH={rpath} DELJOB={deljob} USER={ssh_settings['user']} KEY={ssh_settings['key']}"
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
        if not deljob and not update:
            if sql.insert_backup_job(serv, rserver, rpath, backup_type, time, cred, description):
                env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
                template = env.get_template('new_backup.html')
                template = template.render(
                    backups=sql.select_backups(server=serv, rserver=rserver), sshs=sql.select_ssh()
                )
                print(template)
                print('success: Backup job has been created')
                roxywi_common.logging('backup ', ' a new backup job for server ' + serv + ' has been created', roxywi=1,
                              login=1)
            else:
                print('error: Cannot add the job into DB')
        elif deljob:
            sql.delete_backups(deljob)
            print('Ok')
            roxywi_common.logging('backup ', ' a backup job for server ' + serv + ' has been deleted', roxywi=1, login=1)
        elif update:
            sql.update_backup(serv, rserver, rpath, backup_type, time, cred, description, update)
            print('Ok')
            roxywi_common.logging('backup ', ' a backup job for server ' + serv + ' has been updated', roxywi=1, login=1)

    os.remove(script)

if form.getvalue('git_backup'):
    server_id = form.getvalue('server')
    service_id = form.getvalue('git_service')
    git_init = form.getvalue('git_init')
    repo = form.getvalue('git_repo')
    branch = form.getvalue('git_branch')
    period = form.getvalue('time')
    cred = form.getvalue('cred')
    deljob = form.getvalue('git_deljob')
    description = form.getvalue('description')
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
        f"chmod +x {script} &&  ./{script} HOST={server_ip} DELJOB={deljob} SERVICE={service_name} INIT={git_init} "
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

                env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
                template = env.get_template('new_git.html')
                template = template.render(gits=gits, sshs=sshs, servers=servers, services=services, new_add=1)
                print(template)
                print('success: Git job has been created')
                roxywi_common.logging(
                    server_ip, ' A new git job has been created', roxywi=1, login=1,
                    keep_history=1, service=service_name
                )
        else:
            if sql.delete_git(form.getvalue('git_backup')):
                print('Ok')
    os.remove(script)

if form.getvalue('install_service'):
    server_ip = common.is_ip_or_dns(form.getvalue('install_service'))
    service = common.checkAjaxInput(form.getvalue('service'))
    docker = common.checkAjaxInput(form.getvalue('docker'))

    if service in ('nginx', 'apache'):
        service_mod.install_service(server_ip, service, docker)
    else:
        print('warning: wrong service')

if form.getvalue('haproxyaddserv'):
    service_mod.install_haproxy(form.getvalue('haproxyaddserv'), syn_flood=form.getvalue('syn_flood'),
                          hapver=form.getvalue('hapver'), docker=form.getvalue('docker'))

if form.getvalue('installwaf'):
    service = form.getvalue('service')
    if service == 'haproxy':
        service_mod.waf_install(common.checkAjaxInput(form.getvalue('installwaf')))
    else:
        service_mod.waf_nginx_install(common.checkAjaxInput(form.getvalue('installwaf')))

if form.getvalue('geoip_install'):
    service_mod.geoip_installation()

if form.getvalue('update_roxy_wi'):
    import modules.roxywi.roxy as roxy

    service = form.getvalue('service')
    services = ['roxy-wi-checker',
                'roxy-wi',
                'roxy-wi-keep_alive',
                'roxy-wi-smon',
                'roxy-wi-metrics',
                'roxy-wi-portscanner',
                'roxy-wi-socket',
                'roxy-wi-prometheus-exporter']
    if service not in services:
        print(f'error: {service} is not part of Roxy-WI')
        sys.exit()
    roxy.update_roxy_wi(service)

if form.getvalue('metrics_waf'):
    metrics_waf = common.checkAjaxInput(form.getvalue('metrics_waf'))
    sql.update_waf_metrics_enable(metrics_waf, form.getvalue('enable'))

if form.getvalue('table_metrics'):
    service = form.getvalue('service')
    roxywi_common.check_user_group()
    group_id = roxywi_common.get_user_group(id=1)
    if service in ('nginx', 'apache'):
        metrics = sql.select_service_table_metrics(service, group_id)
    else:
        metrics = sql.select_table_metrics(group_id)

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('table_metrics.html')

    template = template.render(table_stat=metrics, service=service)
    print(template)

if form.getvalue('metrics_hapwi_ram'):
    ip = form.getvalue('ip')
    metrics = {'chartData': {}}
    rams = ''

    if ip == '1':
        import psutil

        rams_list = psutil.virtual_memory()
        rams += str(round(rams_list.total / 1048576, 2)) + ' '
        rams += str(round(rams_list.used / 1048576, 2)) + ' '
        rams += str(round(rams_list.free / 1048576, 2)) + ' '
        rams += str(round(rams_list.shared / 1048576, 2)) + ' '
        rams += str(round(rams_list.cached / 1048576, 2)) + ' '
        rams += str(round(rams_list.available / 1048576, 2)) + ' '
    else:
        commands = ["free -m |grep Mem |awk '{print $2,$3,$4,$5,$6,$7}'"]
        metric, error = server_mod.subprocess_execute(commands[0])

        for i in metric:
            rams = i

    metrics['chartData']['rams'] = rams

    print(json.dumps(metrics))

if form.getvalue('metrics_hapwi_cpu'):
    ip = form.getvalue('ip')
    metrics = {'chartData': {}}
    cpus = ''

    if ip == '1':
        import psutil

        cpus_list = psutil.cpu_times_percent(interval=1, percpu=False)
        cpus += str(cpus_list.user) + ' '
        cpus += str(cpus_list.system) + ' '
        cpus += str(cpus_list.nice) + ' '
        cpus += str(cpus_list.idle) + ' '
        cpus += str(cpus_list.iowait) + ' '
        cpus += str(cpus_list.irq) + ' '
        cpus += str(cpus_list.softirq) + ' '
        cpus += str(cpus_list.steal) + ' '
    else:
        commands = [
            "top -b -n 1 |grep Cpu |awk -F':' '{print $2}'|awk  -F' ' 'BEGIN{ORS=\" \";} { for (i=1;i<=NF;i+=2) print $i}'"]
        metric, error = server_mod.subprocess_execute(commands[0])

        for i in metric:
            cpus = i

    metrics['chartData']['cpus'] = cpus

    print(json.dumps(metrics))

if form.getvalue('new_metrics'):
    serv = form.getvalue('server')
    hostname = sql.get_hostname_by_server_ip(serv)
    time_range = form.getvalue('time_range')
    metric = sql.select_metrics(serv, 'haproxy', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''
    curr_ssl_con = ''
    sess_rate = ''
    server = ''

    for i in metric:
        label = str(i[5])
        label = label.split(' ')[1]
        labels += label + ','
        curr_con += str(i[1]) + ','
        curr_ssl_con += str(i[2]) + ','
        sess_rate += str(i[3]) + ','
        server = str(i[0])

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con
    metrics['chartData']['curr_ssl_con'] = curr_ssl_con
    metrics['chartData']['sess_rate'] = sess_rate
    metrics['chartData']['server'] = hostname + ' (' + server + ')'

    print(json.dumps(metrics))

if form.getvalue('new_http_metrics'):
    serv = form.getvalue('server')
    hostname = sql.get_hostname_by_server_ip(serv)
    time_range = common.checkAjaxInput(form.getvalue('time_range'))
    metric = sql.select_metrics(serv, 'http_metrics', time_range=time_range)
    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    http_2xx = ''
    http_3xx = ''
    http_4xx = ''
    http_5xx = ''
    server = ''

    for i in metric:
        label = str(i[5])
        label = label.split(' ')[1]
        labels += label + ','
        http_2xx += str(i[1]) + ','
        http_3xx += str(i[2]) + ','
        http_4xx += str(i[3]) + ','
        http_5xx += str(i[4]) + ','
        server = str(i[0])

    metrics['chartData']['labels'] = labels
    metrics['chartData']['http_2xx'] = http_2xx
    metrics['chartData']['http_3xx'] = http_3xx
    metrics['chartData']['http_4xx'] = http_4xx
    metrics['chartData']['http_5xx'] = http_5xx
    metrics['chartData']['server'] = f'{hostname} ({server})'

    print(json.dumps(metrics))

if any((form.getvalue('new_nginx_metrics'), form.getvalue('new_apache_metrics'), form.getvalue('new_waf_metrics'))):
    serv = form.getvalue('server')
    hostname = sql.get_hostname_by_server_ip(serv)
    time_range = common.checkAjaxInput(form.getvalue('time_range'))
    service = ''

    if form.getvalue('new_nginx_metrics'):
        service = 'nginx'
    elif form.getvalue('new_apache_metrics'):
        service = 'apache'
    elif form.getvalue('new_waf_metrics'):
        service = 'waf'

    metric = sql.select_metrics(serv, service, time_range=time_range)

    metrics = {'chartData': {}}
    metrics['chartData']['labels'] = {}
    labels = ''
    curr_con = ''

    for i in metric:
        label = str(i[2])
        label = label.split(' ')[1]
        labels += label + ','
        curr_con += str(i[1]) + ','

    metrics['chartData']['labels'] = labels
    metrics['chartData']['curr_con'] = curr_con
    metrics['chartData']['server'] = f'{hostname} ({serv})'

    print(json.dumps(metrics))

if form.getvalue('get_hap_v'):
    print(service_common.check_haproxy_version(serv))

if form.getvalue('get_service_v'):
    service = common.checkAjaxInput(form.getvalue('get_service_v'))
    server_ip = common.is_ip_or_dns(serv)

    service_common.show_service_version(server_ip, service)

if form.getvalue('get_keepalived_v'):
    cmd = ["sudo /usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}'"]
    print(server_mod.ssh_command(serv, cmd))

if form.getvalue('get_exporter_v'):
    print(service_common.get_exp_version(serv, form.getvalue('get_exporter_v')))

if form.getvalue('bwlists'):
    lib_path = get_config.get_config_var('main', 'lib_path')
    color = common.checkAjaxInput(form.getvalue('color'))
    group = common.checkAjaxInput(form.getvalue('group'))
    bwlists = common.checkAjaxInput(form.getvalue('bwlists'))
    list_path = f"{lib_path}/{sql.get_setting('lists_path')}/{group}/{color}/{bwlists}"

    try:
        file = open(list_path, "r")
        file_read = file.read()
        file.close()
        print(file_read)
    except IOError:
        print(f"error: Cannot read {color} list")

if form.getvalue('bwlists_create'):
    color = common.checkAjaxInput(form.getvalue('color'))
    lib_path = get_config.get_config_var('main', 'lib_path')
    list_name = f"{form.getvalue('bwlists_create').split('.')[0]}.lst"
    list_path = f"{lib_path}/{sql.get_setting('lists_path')}/{form.getvalue('group')}/{color}/{list_name}"
    try:
        open(list_path, 'a').close()
        print('success: ')
        try:
            roxywi_common.logging(serv, f'A new list {color} {list_name} has been created', roxywi=1, login=1)
        except Exception:
            pass
    except IOError as e:
        print(f'error: Cannot create a new {color} list. {e}, ')

if form.getvalue('bwlists_save'):
    color = common.checkAjaxInput(form.getvalue('color'))
    group = common.checkAjaxInput(form.getvalue('group'))
    bwlists_save = common.checkAjaxInput(form.getvalue('bwlists_save'))
    lib_path = get_config.get_config_var('main', 'lib_path')
    list_path = f"{lib_path}/{sql.get_setting('lists_path')}/{group}/{color}/{bwlists_save}"
    try:
        with open(list_path, "w") as file:
            file.write(form.getvalue('bwlists_content'))
    except IOError as e:
        print(f'error: Cannot save {color} list. {e}')

    path = sql.get_setting('haproxy_dir') + "/" + color
    servers = []

    if serv != 'all':
        servers.append(serv)

        MASTERS = sql.is_master(serv)
        for master in MASTERS:
            if master[0] is not None:
                servers.append(master[0])
    else:
        server = roxywi_common.get_dick_permit()
        for s in server:
            servers.append(s[2])

    for serv in servers:
        server_mod.ssh_command(serv, [f"sudo mkdir {path}"])
        server_mod.ssh_command(serv, [f"sudo chown $(whoami) {path}"])
        error = config_mod.upload(serv, path + "/" + bwlists_save, list_path, dir='fullpath')

        if error:
            print('error: Upload fail: %s , ' % error)
        else:
            print('success: Edited ' + color + ' list was uploaded to ' + serv + ' , ')
            try:
                roxywi_common.logging(serv, f'Has been edited the {color} list {bwlists_save}', roxywi=1, login=1)
            except Exception:
                pass

            server_id = sql.select_server_id_by_ip(server_ip=serv)
            haproxy_enterprise = sql.select_service_setting(server_id, 'haproxy', 'haproxy_enterprise')
            if haproxy_enterprise == '1':
                haproxy_service_name = "hapee-2.0-lb"
            else:
                haproxy_service_name = "haproxy"

            if form.getvalue('bwlists_restart') == 'restart':
                server_mod.ssh_command(serv, [f"sudo systemctl restart {haproxy_service_name}"])
            elif form.getvalue('bwlists_restart') == 'reload':
                server_mod.ssh_command(serv, [f"sudo systemctl reload {haproxy_service_name}"])

if form.getvalue('bwlists_delete'):
    color = common.checkAjaxInput(form.getvalue('color'))
    bwlists_delete = common.checkAjaxInput(form.getvalue('bwlists_delete'))
    lib_path = get_config.get_config_var('main', 'lib_path')
    group = common.checkAjaxInput( form.getvalue('group'))
    list_path = f"{lib_path}/{sql.get_setting('lists_path')}/{group}/{color}/{bwlists_delete}"
    try:
        os.remove(list_path)
    except IOError as e:
        print(f'error: Cannot delete {color} list. {e} , ')

    path = sql.get_setting('haproxy_dir') + "/" + color
    servers = []

    if serv != 'all':
        servers.append(serv)

        MASTERS = sql.is_master(serv)
        for master in MASTERS:
            if master[0] is not None:
                servers.append(master[0])
    else:
        server = roxywi_common.get_dick_permit()
        for s in server:
            servers.append(s[2])

    for serv in servers:
        error = server_mod.ssh_command(serv, [f"sudo rm {path}/{bwlists_delete}"], return_err=1)

        if error:
            print(f'error: Deleting fail: {error} , ')
        else:
            print(f'success: the {color} list has been deleted on {serv} , ')
            try:
                roxywi_common.logging(serv, f'has been deleted the {color} list {bwlists_delete}', roxywi=1, login=1)
            except Exception:
                pass

if form.getvalue('get_lists'):
    lib_path = get_config.get_config_var('main', 'lib_path')
    group = common.checkAjaxInput(form.getvalue('group'))
    color = common.checkAjaxInput(form.getvalue('color'))
    list_path = f"{lib_path}/{sql.get_setting('lists_path')}/{group}/{color}"
    lists = roxywi_common.get_files(list_path, "lst")
    for line in lists:
        print(line)

if form.getvalue('get_ldap_email'):
    username = form.getvalue('get_ldap_email')
    import ldap

    server = sql.get_setting('ldap_server')
    port = sql.get_setting('ldap_port')
    user = sql.get_setting('ldap_user')
    password = sql.get_setting('ldap_password')
    ldap_base = sql.get_setting('ldap_base')
    domain = sql.get_setting('ldap_domain')
    ldap_search_field = sql.get_setting('ldap_search_field')
    ldap_class_search = sql.get_setting('ldap_class_search')
    ldap_user_attribute = sql.get_setting('ldap_user_attribute')
    ldap_type = sql.get_setting('ldap_type')

    ldap_proto = 'ldap' if ldap_type == "0" else 'ldaps'

    ldap_bind = ldap.initialize('{}://{}:{}/'.format(ldap_proto, server, port))

    try:
        ldap_bind.protocol_version = ldap.VERSION3
        ldap_bind.set_option(ldap.OPT_REFERRALS, 0)

        bind = ldap_bind.simple_bind_s(user, password)

        criteria = "(&(objectClass=" + ldap_class_search + ")(" + ldap_user_attribute + "=" + username + "))"
        attributes = [ldap_search_field]
        result = ldap_bind.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

        results = [entry for dn, entry in result if isinstance(entry, dict)]
        try:
            print('["' + results[0][ldap_search_field][0].decode("utf-8") + '","' + domain + '"]')
        except Exception:
            print('error: user not found')
    finally:
        ldap_bind.unbind()

if form.getvalue('change_waf_mode'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf. change_waf_mode()

error_mess = 'error: All fields must be completed'

if form.getvalue('newuser') is not None:
    import modules.roxywi.user as roxywi_user

    email = common.checkAjaxInput(form.getvalue('newemail'))
    password = common.checkAjaxInput(form.getvalue('newpassword'))
    role = common.checkAjaxInput(form.getvalue('newrole'))
    new_user = common.checkAjaxInput(form.getvalue('newusername'))
    page = common.checkAjaxInput(form.getvalue('page'))
    activeuser = common.checkAjaxInput(form.getvalue('activeuser'))
    group = common.checkAjaxInput(form.getvalue('newgroupuser'))

    if roxywi_user.create_user(new_user, email, password, role, activeuser, group):
        env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
        template = env.get_template('ajax/new_user.html')

        template = template.render(users=sql.select_users(user=new_user),
                                   groups=sql.select_groups(),
                                   page=page,
                                   roles=sql.select_roles(),
                                   adding=1)
        print(template)

if form.getvalue('userdel') is not None:
    import modules.roxywi.user as roxywi_user

    roxywi_user.delete_user()

if form.getvalue('updateuser') is not None:
    import modules.roxywi.user as roxywi_user

    roxywi_user.update_user()

if form.getvalue('updatepassowrd') is not None:
    import modules.roxywi.user as roxywi_user

    roxywi_user.update_user_password()

if form.getvalue('newserver') is not None:
    hostname = common.checkAjaxInput(form.getvalue('servername'))
    ip = form.getvalue('newip')
    ip = common.is_ip_or_dns(ip)
    group = common.checkAjaxInput(form.getvalue('newservergroup'))
    scan_server = common.checkAjaxInput(form.getvalue('scan_server'))
    typeip = common.checkAjaxInput(form.getvalue('typeip'))
    haproxy = common.checkAjaxInput(form.getvalue('haproxy'))
    nginx = common.checkAjaxInput(form.getvalue('nginx'))
    apache = common.checkAjaxInput(form.getvalue('apache'))
    firewall = common.checkAjaxInput(form.getvalue('firewall'))
    enable = common.checkAjaxInput(form.getvalue('enable'))
    master = common.checkAjaxInput(form.getvalue('slave'))
    cred = common.checkAjaxInput(form.getvalue('cred'))
    page = common.checkAjaxInput(form.getvalue('page'))
    page = page.split("#")[0]
    port = common.checkAjaxInput(form.getvalue('newport'))
    desc = common.checkAjaxInput(form.getvalue('desc'))

    if ip == '':
        print('error: IP or DNS name is not valid')
        sys.exit()
    try:
        if server_mod.create_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx, apache, firewall, scan_server):
            try:
                user_subscription = roxywi_common.return_user_status()
            except Exception as e:
                user_subscription = roxywi_common.return_unsubscribed_user_status()
                roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

            env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
            template = env.get_template('ajax/new_server.html')

            template = template.render(groups=sql.select_groups(),
                                       servers=sql.select_servers(server=ip),
                                       masters=sql.select_servers(get_master_servers=1),
                                       sshs=sql.select_ssh(group=group),
                                       page=page,
                                       user_status=user_subscription['user_status'],
                                       user_plan=user_subscription['user_plan'],
                                       adding=1)
            print(template)
            roxywi_common.logging(ip, f'A new server {hostname} has been created', roxywi=1, login=1,
                          keep_history=1, service='server')
    except Exception as e:
        print(e)

if form.getvalue('updatehapwiserver') is not None:
    hapwi_id = form.getvalue('updatehapwiserver')
    active = form.getvalue('active')
    name = form.getvalue('name')
    alert = form.getvalue('alert_en')
    metrics = form.getvalue('metrics')
    service = form.getvalue('service_name')
    sql.update_hapwi_server(hapwi_id, alert, metrics, active, service)
    server_ip = sql.select_server_ip_by_id(hapwi_id)
    roxywi_common.logging(server_ip, 'The server ' + name + ' has been updated ', roxywi=1, login=1, keep_history=1,
                  service=service)

if form.getvalue('updateserver') is not None:
    name = form.getvalue('updateserver')
    group = form.getvalue('servergroup')
    typeip = form.getvalue('typeip')
    haproxy = form.getvalue('haproxy')
    nginx = form.getvalue('nginx')
    apache = form.getvalue('apache')
    firewall = form.getvalue('firewall')
    enable = form.getvalue('enable')
    master = form.getvalue('slave')
    serv_id = form.getvalue('id')
    cred = form.getvalue('cred')
    port = form.getvalue('port')
    protected = form.getvalue('protected')
    desc = form.getvalue('desc')

    if name is None or port is None:
        print(error_mess)
    else:
        sql.update_server(name, group, typeip, enable, master, serv_id, cred, port, desc, haproxy, nginx, apache,
                          firewall, protected)
        roxywi_common.logging('the server ' + name, ' has been updated ', roxywi=1, login=1)
        server_ip = sql.select_server_ip_by_id(serv_id)
        roxywi_common.logging(server_ip, 'The server ' + name + ' has been update', roxywi=1, login=1,
                      keep_history=1, service='server')

if form.getvalue('serverdel') is not None:
    server_id = common.checkAjaxInput(form.getvalue('serverdel'))
    server = sql.select_servers(id=server_id)
    server_ip = ''
    for s in server:
        hostname = s[1]
        server_ip = s[2]
    if sql.check_exists_backup(server_ip):
        print('warning: Delete the backup first ')
        sys.exit()
    if sql.delete_server(server_id):
        sql.delete_waf_server(server_id)
        sql.delete_port_scanner_settings(server_id)
        sql.delete_waf_rules(server_ip)
        sql.delete_action_history(server_id)
        sql.delete_system_info(server_id)
        sql.delete_service_settings(server_id)
        print("Ok")
        roxywi_common.logging(server_ip, f'The server {hostname} has been deleted', roxywi=1, login=1)

if form.getvalue('newgroup') is not None:
    newgroup = common.checkAjaxInput(form.getvalue('groupname'))
    desc = common.checkAjaxInput(form.getvalue('newdesc'))
    if newgroup is None:
        print(error_mess)
    else:
        if sql.add_group(newgroup, desc):
            env = Environment(loader=FileSystemLoader('templates/ajax/'), autoescape=True)
            template = env.get_template('/new_group.html')

            output_from_parsed_template = template.render(groups=sql.select_groups(group=newgroup))
            print(output_from_parsed_template)
            roxywi_common.logging('Roxy-WI server', f'A new group {newgroup} has been created', roxywi=1, login=1)

if form.getvalue('groupdel') is not None:
    groupdel = common.checkAjaxInput(form.getvalue('groupdel'))
    group = sql.select_groups(id=groupdel)
    for g in group:
        groupname = g.name
    if sql.delete_group(groupdel):
        print("Ok")
        roxywi_common.logging('Roxy-WI server', f'The {groupname} has been deleted', roxywi=1, login=1)

if form.getvalue('updategroup') is not None:
    name = common.checkAjaxInput(form.getvalue('updategroup'))
    descript = common.checkAjaxInput(form.getvalue('descript'))
    group_id = common.checkAjaxInput(form.getvalue('id'))
    if name is None:
        print(error_mess)
    else:
        try:
            sql.update_group(name, descript, group_id)
            roxywi_common.logging('Roxy-WI server', f'The {name} has been updated', roxywi=1, login=1)
        except Exception as e:
            print('error: ' + str(e))

if form.getvalue('new_ssh'):
    ssh_mod.create_ssh_cred()

if form.getvalue('sshdel') is not None:
    ssh_mod.delete_ssh_key()

if form.getvalue('updatessh'):
    ssh_mod.update_ssh_key()

if form.getvalue('ssh_cert'):
    user_group = roxywi_common.get_user_group()
    name = common.checkAjaxInput(form.getvalue('name'))
    key = form.getvalue('ssh_cert')

    ssh_mod.upload_ssh_key(name, user_group, key)

if form.getvalue('newtelegram'):
    import modules.alerting.alerting as alerting

    token = common.checkAjaxInput(form.getvalue('newtelegram'))
    channel = common.checkAjaxInput(form.getvalue('chanel'))
    group = common.checkAjaxInput(form.getvalue('telegramgroup'))
    page = common.checkAjaxInput(form.getvalue('page'))
    page = page.split("#")[0]

    alerting.add_telegram_channel(token, channel, group, page)

if form.getvalue('newslack'):
    import modules.alerting.alerting as alerting

    token = common.checkAjaxInput(form.getvalue('newslack'))
    channel = common.checkAjaxInput(form.getvalue('chanel'))
    group = common.checkAjaxInput(form.getvalue('slackgroup'))
    page = common.checkAjaxInput(form.getvalue('page'))
    page = page.split("#")[0]

    alerting.add_slack_channel(token, channel, group, page)

if form.getvalue('telegramdel') is not None:
    import modules.alerting.alerting as alerting

    channel_id = common.checkAjaxInput(form.getvalue('telegramdel'))

    alerting.delete_telegram_channel(channel_id)

if form.getvalue('slackdel') is not None:
    import modules.alerting.alerting as alerting

    channel_id = common.checkAjaxInput(form.getvalue('slackdel'))

    alerting.delete_slack_channel(channel_id)

if form.getvalue('updatetoken') is not None:
    import modules.alerting.alerting as alerting

    token = common.checkAjaxInput(form.getvalue('updatetoken'))
    channel = common.checkAjaxInput(form.getvalue('updategchanel'))
    group = common.checkAjaxInput(form.getvalue('updatetelegramgroup'))
    user_id = common.checkAjaxInput(form.getvalue('id'))

    alerting.update_telegram(token, channel, group, user_id)

if form.getvalue('update_slack_token') is not None:
    import modules.alerting.alerting as alerting

    token = common.checkAjaxInput(form.getvalue('update_slack_token'))
    channel = common.checkAjaxInput(form.getvalue('updategchanel'))
    group = common.checkAjaxInput(form.getvalue('updateslackgroup'))
    user_id = common.checkAjaxInput(form.getvalue('id'))

    alerting.update_slack()


if form.getvalue('updatesettings') is not None:
    settings = common.checkAjaxInput(form.getvalue('updatesettings'))
    val = common.checkAjaxInput(form.getvalue('val'))
    user_group = roxywi_common.get_user_group(id=1)
    if sql.update_setting(settings, val, user_group):
        roxywi_common.logging('Roxy-WI server', f'The {settings} setting has been changed to: {val}', roxywi=1,
                      login=1)
        print("Ok")

if form.getvalue('getuserservices'):
    import modules.roxywi.user as roxy_user

    roxy_user.get_user_services()


if form.getvalue('getusergroups'):
    import modules.roxywi.user as roxy_user

    roxy_user.get_user_groups()

if form.getvalue('changeUserGroupId') is not None:
    import modules.roxywi.user as roxy_user

    roxy_user.change_user_group()

if form.getvalue('changeUserServicesId') is not None:
    import modules.roxywi.user as roxy_user

    roxy_user.change_user_services()

if form.getvalue('changeUserCurrentGroupId') is not None:
    import modules.roxywi.user as roxy_user

    roxy_user.change_user_active_group()

if form.getvalue('getcurrentusergroup') is not None:
    import modules.roxywi.user as roxy_user

    cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
    user_id = cookie.get('uuid')
    group = cookie.get('group')

    roxy_user.get_user_active_group(user_id, group)

if form.getvalue('newsmon') is not None:
    user_group = roxywi_common.get_user_group(id=1)
    server = common.checkAjaxInput(form.getvalue('newsmon'))
    port = common.checkAjaxInput(form.getvalue('newsmonport'))
    enable = common.checkAjaxInput(form.getvalue('newsmonenable'))
    http = common.checkAjaxInput(form.getvalue('newsmonproto'))
    uri = common.checkAjaxInput(form.getvalue('newsmonuri'))
    body = common.checkAjaxInput(form.getvalue('newsmonbody'))
    group = common.checkAjaxInput(form.getvalue('newsmongroup'))
    desc = common.checkAjaxInput(form.getvalue('newsmondescription'))
    telegram = common.checkAjaxInput(form.getvalue('newsmontelegram'))
    slack = common.checkAjaxInput(form.getvalue('newsmonslack'))

    try:
        port = int(port)
    except Exception:
        print('SMON error: port must number')
        sys.exit()
    if port > 65535 or port < 0:
        print('SMON error: port must be 0-65535')
        sys.exit()
    if port == 80 and http == 'https':
        print('SMON error: Cannot be HTTPS with 80 port')
        sys.exit()
    if port == 443 and http == 'http':
        print('SMON error: Cannot be HTTP with 443 port')
        sys.exit()

    last_id = sql.insert_smon(server, port, enable, http, uri, body, group, desc, telegram, slack, user_group)
    if last_id:
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/show_new_smon.html')
        template = template.render(
            smon=sql.select_smon_by_id(last_id),
            telegrams=sql.get_user_telegram_by_group(user_group),
            slacks=sql.get_user_slack_by_group(user_group))
        print(template)
        roxywi_common.logging('SMON', ' Has been add a new server ' + server + ' to SMON ', roxywi=1, login=1)

if form.getvalue('smondel') is not None:
    user_group = roxywi_common.get_user_group(id=1)
    smon_id = common.checkAjaxInput(form.getvalue('smondel'))

    if roxywi_common.check_user_group():
        try:
            if sql.delete_smon(smon_id, user_group):
                print('Ok')
                roxywi_common.logging('SMON', ' Has been delete server from SMON ', roxywi=1, login=1)
        except Exception as e:
            print(e)

if form.getvalue('showsmon') is not None:
    user_group = roxywi_common.get_user_group(id=1)
    sort = common.checkAjaxInput(form.getvalue('sort'))
    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/smon_dashboard.html')
    template = template.render(smon=sql.smon_list(user_group), sort=sort)
    print(template)

if form.getvalue('updateSmonIp') is not None:
    smon_id = common.checkAjaxInput(form.getvalue('id'))
    ip = common.checkAjaxInput(form.getvalue('updateSmonIp'))
    port = common.checkAjaxInput(form.getvalue('updateSmonPort'))
    en = common.checkAjaxInput(form.getvalue('updateSmonEn'))
    http = common.checkAjaxInput(form.getvalue('updateSmonHttp'))
    body = common.checkAjaxInput(form.getvalue('updateSmonBody'))
    telegram = common.checkAjaxInput(form.getvalue('updateSmonTelegram'))
    slack = common.checkAjaxInput(form.getvalue('updateSmonSlack'))
    group = common.checkAjaxInput(form.getvalue('updateSmonGroup'))
    desc = common.checkAjaxInput(form.getvalue('updateSmonDesc'))

    try:
        port = int(port)
    except Exception:
        print('SMON error: port must number')
        sys.exit()
    if port > 65535 or port < 0:
        print('SMON error: port must be 0-65535')
        sys.exit()
    if port == 80 and http == 'https':
        print('SMON error: Cannot be https with 80 port')
        sys.exit()
    if port == 443 and http == 'http':
        print('SMON error: Cannot be HTTP with 443 port')
        sys.exit()

    roxywi_common.check_user_group()
    try:
        if sql.update_smon(smon_id, ip, port, body, telegram, slack, group, desc, en):
            print("Ok")
            roxywi_common.logging('SMON', ' Has been update the server ' + ip + ' to SMON ', roxywi=1, login=1)
    except Exception as e:
        print(e)

if form.getvalue('showBytes') is not None:
    import modules.roxywi.overview as roxywi_overview

    server_ip = common.is_ip_or_dns(form.getvalue('showBytes'))
    roxywi_overview.show_haproxy_binout(server_ip)

if form.getvalue('nginxConnections'):
    import modules.roxywi.overview as roxywi_overview

    server_ip = common.is_ip_or_dns(form.getvalue('nginxConnections'))
    roxywi_overview.show_nginx_connections(server_ip)

if form.getvalue('apachekBytes'):
    import modules.roxywi.overview as roxywi_overview

    server_ip = common.is_ip_or_dns(form.getvalue('apachekBytes'))
    roxywi_overview.show_apache_bytes(server_ip)

if form.getvalue('waf_rule_id'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf.switch_waf_rule(serv)

if form.getvalue('new_waf_rule'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf.create_waf_rule(serv)

if form.getvalue('lets_domain'):
    serv = common.checkAjaxInput(form.getvalue('serv'))
    lets_domain = common.checkAjaxInput(form.getvalue('lets_domain'))
    lets_email = common.checkAjaxInput(form.getvalue('lets_email'))
    proxy = sql.get_setting('proxy')
    ssl_path = common.return_nice_path(sql.get_setting('cert_path'))
    haproxy_dir = sql.get_setting('haproxy_dir')
    script = "letsencrypt.sh"
    proxy_serv = ''
    ssh_settings = ssh_mod.return_ssh_keys_path(serv)

    os.system(f"cp scripts/{script} .")

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy

    commands = [
        f"chmod +x {script} &&  ./{script} PROXY={proxy_serv} haproxy_dir={haproxy_dir} DOMAIN={lets_domain} "
        f"EMAIL={lets_email} SSH_PORT={ssh_settings['port']} SSL_PATH={ssl_path} HOST={serv} USER={ ssh_settings['user']} "
        f"PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
    ]

    output, error = server_mod.subprocess_execute(commands[0])

    if error:
        roxywi_common.logging('Roxy-WI server', error, roxywi=1)
        print(error)
    else:
        for line in output:
            if any(s in line for s in ("msg", "FAILED")):
                try:
                    line = line.split(':')[1]
                    line = line.split('"')[1]
                    print(line + "<br>")
                    break
                except Exception:
                    print(output)
                    break
        else:
            print('success: Certificate has been created')

    os.remove(script)

if form.getvalue('uploadovpn'):
    name = common.checkAjaxInput(form.getvalue('ovpnname'))

    ovpn_file = f"{os.path.dirname('/tmp/')}/{name}.ovpn"

    try:
        with open(ovpn_file, "w") as conf:
            conf.write(form.getvalue('uploadovpn'))
    except IOError as e:
        print(str(e))
        print('error: Can\'t save ovpn file')
    else:
        print('success: ovpn file has been saved </div>')

    try:
        cmd = 'sudo openvpn3 config-import --config %s --persistent' % ovpn_file
        server_mod.subprocess_execute(cmd)
    except IOError as e:
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

    try:
        cmd = 'sudo cp %s /etc/openvpn3/%s.conf' % (ovpn_file, name)
        server_mod.subprocess_execute(cmd)
    except IOError as e:
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

    roxywi_common.logging("Roxy-WI server", " has been uploaded a new ovpn file %s" % ovpn_file, roxywi=1, login=1)

if form.getvalue('openvpndel') is not None:
    openvpndel = common.checkAjaxInput(form.getvalue('openvpndel'))

    cmd = f'sudo openvpn3 config-remove --config /tmp/{openvpndel}.ovpn --force'
    try:
        server_mod.subprocess_execute(cmd)
        print("Ok")
        roxywi_common.logging(openvpndel, ' has deleted the ovpn file ', roxywi=1, login=1)
    except IOError as e:
        print(e.args[0])
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

if form.getvalue('actionvpn') is not None:
    openvpn = common.checkAjaxInput(form.getvalue('openvpnprofile'))
    action = common.checkAjaxInput(form.getvalue('actionvpn'))

    if action == 'start':
        cmd = 'sudo openvpn3 session-start --config /tmp/%s.ovpn' % openvpn
    elif action == 'restart':
        cmd = 'sudo openvpn3 session-manage --config /tmp/%s.ovpn --restart' % openvpn
    elif action == 'disconnect':
        cmd = 'sudo openvpn3 session-manage --config /tmp/%s.ovpn --disconnect' % openvpn
    try:
        server_mod.subprocess_execute(cmd)
        print("success: The " + openvpn + " has been " + action + "ed")
        roxywi_common.logging(openvpn, ' has ' + action + ' the ovpn session ', roxywi=1, login=1)
    except IOError as e:
        print(e.args[0])
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

if form.getvalue('scan_ports') is not None:
    serv_id = common.checkAjaxInput(form.getvalue('scan_ports'))
    server = sql.select_servers(id=serv_id)
    ip = ''

    for s in server:
        ip = s[2]

    cmd = "sudo nmap -sS %s |grep -E '^[[:digit:]]'|sed 's/  */ /g'" % ip
    cmd1 = "sudo nmap -sS %s |head -5|tail -2" % ip

    stdout, stderr = server_mod.subprocess_execute(cmd)
    stdout1, stderr1 = server_mod.subprocess_execute(cmd1)

    if stderr != '':
        print(stderr)
    else:
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/scan_ports.html')
        template = template.render(ports=stdout, info=stdout1)
        print(template)

if form.getvalue('viewFirewallRules') is not None:
    server_mod.show_firewalld_rules()

if form.getvalue('geoipserv') is not None:
    serv = common.checkAjaxInput(form.getvalue('geoipserv'))
    service = common.checkAjaxInput(form.getvalue('geoip_service'))
    if service in ('haproxy', 'nginx'):
        service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))

        cmd = [f"ls {service_dir}geoip/"]
        print(server_mod.ssh_command(serv, cmd))
    else:
        print('warning: select a server and service first')

if form.getvalue('nettools_icmp_server_from'):
    server_from = common.checkAjaxInput(form.getvalue('nettools_icmp_server_from'))
    server_to = common.checkAjaxInput(form.getvalue('nettools_icmp_server_to'))
    server_to = common.is_ip_or_dns(server_to)
    action = common.checkAjaxInput(form.getvalue('nettools_action'))
    stderr = ''
    action_for_sending = ''

    if server_to == '':
        print('warning: enter a correct IP or DNS name')
        sys.exit()

    if action == 'nettools_ping':
        action_for_sending = 'ping -c 4 -W 1 -s 56 -O '
    elif action == 'nettools_trace':
        action_for_sending = 'tracepath -m 10 '

    action_for_sending = action_for_sending + server_to

    if server_from == 'localhost':
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1, timeout=15)

    if stderr != '':
        print(f'error: {stderr}')
        sys.exit()
    for i in output:
        if i == ' ' or i == '':
            continue
        i = i.strip()
        if 'PING' in i:
            print('<span style="color: var(--link-dark-blue); display: block; margin-top: -20px;">')
        elif 'no reply' in i or 'no answer yet' in i or 'Too many hops' in i or '100% packet loss' in i:
            print('<span style="color: var(--red-color);">')
        elif 'ms' in i and '100% packet loss' not in i:
            print('<span style="color: var(--green-color);">')
        else:
            print('<span>')

        print(i + '</span><br />')

if form.getvalue('nettools_telnet_server_from'):
    server_from = common.checkAjaxInput(form.getvalue('nettools_telnet_server_from'))
    server_to = common.checkAjaxInput(form.getvalue('nettools_telnet_server_to'))
    server_to = common.is_ip_or_dns(server_to)
    port_to = common.checkAjaxInput(form.getvalue('nettools_telnet_port_to'))
    stderr = ''

    if server_to == '':
        print('warning: enter a correct IP or DNS name')
        sys.exit()

    if server_from == 'localhost':
        action_for_sending = f'echo "exit"|nc {server_to} {port_to} -t -w 1s'
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [f'echo "exit"|nc {server_to} {port_to} -t -w 1s']
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print(f'error: <b>{stderr[5:]}</b>')
        sys.exit()
    count_string = 0
    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        if i == 'Ncat: Connection timed out.':
            print(f'error: <b>{i[5:]}</b>')
            break
        print(i + '<br>')
        count_string += 1
        if count_string > 1:
            break

if form.getvalue('nettools_nslookup_server_from'):
    server_from = common.checkAjaxInput(form.getvalue('nettools_nslookup_server_from'))
    dns_name = common.checkAjaxInput(form.getvalue('nettools_nslookup_name'))
    dns_name = common.is_ip_or_dns(dns_name)
    record_type = common.checkAjaxInput(form.getvalue('nettools_nslookup_record_type'))
    stderr = ''

    if dns_name == '':
        print('warning: enter a correct DNS name')
        sys.exit()

    action_for_sending = f'dig {dns_name} {record_type} |grep -e "SERVER\|{dns_name}"'

    if server_from == 'localhost':
        output, stderr = server_mod.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = server_mod.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print('error: ' + stderr[5:-1])
        sys.exit()
    count_string = 0
    print(
        f'<b style="display: block; margin-top:10px;">The <i style="color: var(--blue-color)">{dns_name}</i> domain has the following records:</b>')
    for i in output:
        if 'dig: command not found.' in i:
            print('error: Install bind-utils before using NSLookup')
            break
        if ';' in i and ';; SERVER:' not in i:
            continue
        if 'SOA' in i and record_type != 'SOA':
            print('<b style="color: red">There are not any records for this type')
            break
        if ';; SERVER:' in i:
            i = i[10:]
            print('<br><b>From NS server:</b><br>')
        i = i.strip()
        print('<i>' + i + '</i><br>')
        count_string += 1

if form.getvalue('portscanner_history_server_id'):
    server_id = common.checkAjaxInput(form.getvalue('portscanner_history_server_id'))
    enabled = common.checkAjaxInput(form.getvalue('portscanner_enabled'))
    notify = common.checkAjaxInput(form.getvalue('portscanner_notify'))
    history = common.checkAjaxInput(form.getvalue('portscanner_history'))
    user_group_id = [server[3] for server in sql.select_servers(id=server_id)]

    try:
        if sql.insert_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
            print('ok')
        else:
            if sql.update_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
                print('ok')
    except Exception as e:
        print(e)

if form.getvalue('show_versions'):
    import modules.roxywi.roxy as roxy
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/check_version.html')
    template = template.render(versions=roxy.versions())
    print(template)

if form.getvalue('get_group_name_by_id'):
    print(sql.get_group_name_by_id(form.getvalue('get_group_name_by_id')))

if any((form.getvalue('do_new_name'), form.getvalue('aws_new_name'), form.getvalue('gcore_new_name'))):
    roxywi_common.check_user_group()
    is_add = False
    if form.getvalue('do_new_name'):
        provider_name = common.checkAjaxInput(form.getvalue('do_new_name'))
        provider_group = common.checkAjaxInput(form.getvalue('do_new_group'))
        provider_token = common.checkAjaxInput(form.getvalue('do_new_token'))

        if sql.add_provider_do(provider_name, provider_group, provider_token):
            is_add = True

    elif form.getvalue('aws_new_name'):
        provider_name = common.checkAjaxInput(form.getvalue('aws_new_name'))
        provider_group = common.checkAjaxInput(form.getvalue('aws_new_group'))
        provider_token = common.checkAjaxInput(form.getvalue('aws_new_key'))
        provider_secret = common.checkAjaxInput(form.getvalue('aws_new_secret'))

        if sql.add_provider_aws(provider_name, provider_group, provider_token, provider_secret):
            is_add = True

    elif form.getvalue('gcore_new_name'):
        provider_name = common.checkAjaxInput(form.getvalue('gcore_new_name'))
        provider_group = common.checkAjaxInput(form.getvalue('gcore_new_group'))
        provider_token = common.checkAjaxInput(form.getvalue('gcore_new_user'))
        provider_pass = common.checkAjaxInput(form.getvalue('gcore_new_pass'))

        if sql.add_provider_gcore(provider_name, provider_group, provider_token, provider_pass):
            is_add = True

    if is_add:
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_uuid = cookie.get('uuid')
        role_id = sql.get_user_role_by_uuid(user_uuid.value)
        params = sql.select_provisioning_params()
        providers = sql.select_providers(provider_group, key=provider_token)

        if role_id == 1:
            groups = sql.select_groups()
        else:
            groups = ''

        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/provisioning/providers.html')
        template = template.render(providers=providers, role=role_id, groups=groups, user_group=provider_group,
                                   adding=1, params=params)
        print(template)

if form.getvalue('providerdel'):
    roxywi_common.check_user_group()
    try:
        if sql.delete_provider(common.checkAjaxInput(form.getvalue('providerdel'))):
            print('Ok')
            roxywi_common.logging('Roxy-WI server', 'Provider has been deleted', provisioning=1)
    except Exception as e:
        print(e)

if form.getvalue('awsinit') or form.getvalue('doinit') or form.getvalue('gcoreinitserver'):
    roxywi_common.check_user_group()
    cmd = 'cd scripts/terraform/ && sudo terraform init -upgrade -no-color'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
    else:
        if "Terraform initialized in an empty directory" in output[0]:
            print('error: There is not need modules')
        elif "mkdir .terraform: permission denied" in output[0]:
            print('error: Cannot init. Check permission to folder')

        print(output[0])

if form.getvalue('awsvars') or form.getvalue('awseditvars'):
    if form.getvalue('awsvars'):
        awsvars = common.checkAjaxInput(form.getvalue('awsvars'))
        group = common.checkAjaxInput(form.getvalue('aws_create_group'))
        provider = common.checkAjaxInput(form.getvalue('aws_create_provider'))
        region = common.checkAjaxInput(form.getvalue('aws_create_regions'))
        size = common.checkAjaxInput(form.getvalue('aws_create_size'))
        oss = common.checkAjaxInput(form.getvalue('aws_create_oss'))
        ssh_name = common.checkAjaxInput(form.getvalue('aws_create_ssh_name'))
        volume_size = common.checkAjaxInput(form.getvalue('aws_create_volume_size'))
        volume_type = common.checkAjaxInput(form.getvalue('aws_create_volume_type'))
        delete_on_termination = common.checkAjaxInput(form.getvalue('aws_create_delete_on_termination'))
        floating_ip = common.checkAjaxInput(form.getvalue('aws_create_floating_net'))
        firewall = common.checkAjaxInput(form.getvalue('aws_create_firewall'))
        public_ip = common.checkAjaxInput(form.getvalue('aws_create_public_ip'))
    elif form.getvalue('awseditvars'):
        awsvars = common.checkAjaxInput(form.getvalue('awseditvars'))
        group = common.checkAjaxInput(form.getvalue('aws_editing_group'))
        provider = common.checkAjaxInput(form.getvalue('aws_editing_provider'))
        region = common.checkAjaxInput(form.getvalue('aws_editing_regions'))
        size = common.checkAjaxInput(form.getvalue('aws_editing_size'))
        oss = common.checkAjaxInput(form.getvalue('aws_editing_oss'))
        ssh_name = common.checkAjaxInput(form.getvalue('aws_editing_ssh_name'))
        volume_size = common.checkAjaxInput(form.getvalue('aws_editing_volume_size'))
        volume_type = common.checkAjaxInput(form.getvalue('aws_editing_volume_type'))
        delete_on_termination = common.checkAjaxInput(form.getvalue('aws_editing_delete_on_termination'))
        floating_ip = common.checkAjaxInput(form.getvalue('aws_editing_floating_net'))
        firewall = common.checkAjaxInput(form.getvalue('aws_editing_firewall'))
        public_ip = common.checkAjaxInput(form.getvalue('aws_editing_public_ip'))

    aws_key, aws_secret = sql.select_aws_provider(provider)

    cmd = f'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={region} ' \
          f'group={group} size={size} os={oss} floating_ip={floating_ip} volume_size={volume_size} server_name={awsvars} ' \
          f'AWS_ACCESS_KEY={aws_key} AWS_SECRET_KEY={aws_secret} firewall={firewall} public_ip={public_ip} ' \
          f'ssh_name={ssh_name} delete_on_termination={delete_on_termination} volume_type={volume_type} cloud=aws"'

    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
    else:
        print('ok')

if form.getvalue('dovars') or form.getvalue('doeditvars'):
    if form.getvalue('dovars'):
        dovars = form.getvalue('dovars')
        group = form.getvalue('do_create_group')
        provider = form.getvalue('do_create_provider')
        region = form.getvalue('do_create_regions')
        size = form.getvalue('do_create_size')
        oss = form.getvalue('do_create_oss')
        ssh_name = form.getvalue('do_create_ssh_name')
        ssh_ids = form.getvalue('do_create_ssh_ids')
        backup = form.getvalue('do_create_backup')
        privet_net = form.getvalue('do_create_private_net')
        floating_ip = form.getvalue('do_create_floating_net')
        monitoring = form.getvalue('do_create_monitoring')
        firewall = form.getvalue('do_create_firewall')
    elif form.getvalue('doeditvars'):
        dovars = form.getvalue('doeditvars')
        group = form.getvalue('do_edit_group')
        provider = form.getvalue('do_edit_provider')
        region = form.getvalue('do_edit_regions')
        size = form.getvalue('do_edit_size')
        oss = form.getvalue('do_edit_oss')
        ssh_name = form.getvalue('do_edit_ssh_name')
        ssh_ids = form.getvalue('do_edit_ssh_ids')
        backup = form.getvalue('do_edit_backup')
        privet_net = form.getvalue('do_edit_private_net')
        floating_ip = form.getvalue('do_edit_floating_net')
        monitoring = form.getvalue('do_edit_monitoring')
        firewall = form.getvalue('do_edit_firewall')

    token = sql.select_do_provider(provider)

    cmd = f'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={region} ' \
          f'group={group} size={size} os={oss} floating_ip={floating_ip} ssh_ids={ssh_ids} server_name={dovars} ' \
          f'token={token} backup={backup} monitoring={monitoring} privet_net={privet_net} firewall={firewall} ' \
          f'floating_ip={floating_ip} ssh_name={ssh_name} cloud=do"'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print(cmd)
        print(output)

if form.getvalue('dovalidate') or form.getvalue('doeditvalidate'):
    if form.getvalue('dovalidate'):
        workspace = form.getvalue('dovalidate')
        group = form.getvalue('do_create_group')
    elif form.getvalue('doeditvalidate'):
        workspace = form.getvalue('doeditvalidate')
        group = form.getvalue('do_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.do_module -var-file vars/{workspace}_{group}_do.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')

if form.getvalue('doworkspace'):
    workspace = form.getvalue('doworkspace')
    group = form.getvalue('do_create_group')
    provider = form.getvalue('do_create_provider')
    region = form.getvalue('do_create_regions')
    size = form.getvalue('do_create_size')
    oss = form.getvalue('do_create_oss')
    ssh_name = form.getvalue('do_create_ssh_name')
    ssh_ids = form.getvalue('do_create_ssh_ids')
    backup = form.getvalue('do_create_backup')
    privet_net = form.getvalue('do_create_private_net')
    floating_ip = form.getvalue('do_create_floating_net')
    monitoring = form.getvalue('do_create_monitoring')
    firewall = form.getvalue('do_create_firewall')

    cmd = 'cd scripts/terraform/ && sudo terraform workspace new ' + workspace + '_' + group + '_do'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        if sql.add_server_do(
                region, size, privet_net, floating_ip, ssh_ids, ssh_name, workspace, oss, firewall, monitoring,
                backup, provider, group, 'Creating'
        ):
            user_params = roxywi_common.get_users_params()
            new_server = sql.select_provisioned_servers(new=workspace, group=group, type='do')
            params = sql.select_provisioning_params()

            env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
            template = env.get_template('ajax/provisioning/provisioned_servers.html')
            template = template.render(
                servers=new_server, groups=sql.select_groups(), user_group=group,
                providers=sql.select_providers(group), role=user_params['role'], adding=1, params=params
            )
            print(template)

if form.getvalue('doeditworkspace'):
    workspace = form.getvalue('doeditworkspace')
    group = form.getvalue('do_edit_group')
    provider = form.getvalue('do_edit_provider')
    region = form.getvalue('do_edit_regions')
    size = form.getvalue('do_edit_size')
    oss = form.getvalue('do_edit_oss')
    ssh_name = form.getvalue('do_edit_ssh_name')
    ssh_ids = form.getvalue('do_edit_ssh_ids')
    backup = form.getvalue('do_edit_backup')
    privet_net = form.getvalue('do_edit_private_net')
    floating_ip = form.getvalue('do_edit_floating_net')
    monitoring = form.getvalue('do_edit_monitoring')
    firewall = form.getvalue('do_edit_firewall')
    server_id = form.getvalue('server_id')
    try:
        if sql.update_server_do(
                size, privet_net, floating_ip, ssh_ids, ssh_name, oss, firewall, monitoring, backup, provider,
                group, 'Creating', server_id
        ):

            cmd = 'cd scripts/terraform/ && sudo terraform workspace select ' + workspace + '_' + group + '_do'
            output, stderr = server_mod.subprocess_execute(cmd)

            if stderr != '':
                stderr = stderr.strip()
                stderr = repr(stderr)
                stderr = stderr.replace("'", "")
                stderr = stderr.replace("\'", "")
                sql.update_provisioning_server_status('Error', group, workspace, provider)
                sql.update_provisioning_server_error(stderr, group, workspace, provider)
                print('error: ' + stderr)
            else:
                print(cmd)
                print(output)
    except Exception as e:
        print(e)

if form.getvalue('awsvalidate') or form.getvalue('awseditvalidate'):
    if form.getvalue('awsvalidate'):
        workspace = form.getvalue('awsvalidate')
        group = form.getvalue('aws_create_group')
    elif form.getvalue('awseditvalidate'):
        workspace = form.getvalue('awseditvalidate')
        group = form.getvalue('aws_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.aws_module -var-file vars/{workspace}_{group}_aws.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
    else:
        print('ok')

if form.getvalue('awsworkspace'):
    workspace = form.getvalue('awsworkspace')
    group = form.getvalue('aws_create_group')
    provider = form.getvalue('aws_create_provider')
    region = form.getvalue('aws_create_regions')
    size = form.getvalue('aws_create_size')
    oss = form.getvalue('aws_create_oss')
    ssh_name = form.getvalue('aws_create_ssh_name')
    volume_size = form.getvalue('aws_create_volume_size')
    volume_type = form.getvalue('aws_create_volume_type')
    delete_on_termination = form.getvalue('aws_create_delete_on_termination')
    floating_ip = form.getvalue('aws_create_floating_net')
    firewall = form.getvalue('aws_create_firewall')
    public_ip = form.getvalue('aws_create_public_ip')

    cmd = f'cd scripts/terraform/ && sudo terraform workspace new {workspace}_{group}_aws'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        try:
            if sql.add_server_aws(
                    region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                    provider, group, 'Creating', delete_on_termination, volume_type
            ):
                user_params = roxywi_common.get_users_params()
                new_server = sql.select_provisioned_servers(new=workspace, group=group, type='aws')
                params = sql.select_provisioning_params()

                env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
                template = env.get_template('ajax/provisioning/provisioned_servers.html')
                template = template.render(
                    servers=new_server, groups=sql.select_groups(), user_group=group,
                    providers=sql.select_providers(group), role=user_params['role'], adding=1, params=params
                )
                print(template)
        except Exception as e:
            print(e)

if form.getvalue('awseditworkspace'):
    workspace = form.getvalue('awseditworkspace')
    group = form.getvalue('aws_editing_group')
    provider = form.getvalue('aws_editing_provider')
    region = form.getvalue('aws_editing_regions')
    size = form.getvalue('aws_editing_size')
    oss = form.getvalue('aws_editing_oss')
    ssh_name = form.getvalue('aws_editing_ssh_name')
    volume_size = form.getvalue('aws_editing_volume_size')
    volume_type = form.getvalue('aws_editing_volume_type')
    delete_on_termination = form.getvalue('aws_editing_delete_on_termination')
    floating_ip = form.getvalue('aws_editing_floating_net')
    firewall = form.getvalue('aws_editing_firewall')
    public_ip = form.getvalue('aws_editing_public_ip')
    server_id = form.getvalue('server_id')

    try:
        if sql.update_server_aws(
                region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                provider, group, 'Editing', server_id, delete_on_termination, volume_type
        ):

            try:
                cmd = f'cd scripts/terraform/ && sudo terraform workspace select {workspace}_{group}_aws'
                output, stderr = server_mod.subprocess_execute(cmd)
            except Exception as e:
                print('error: ' + str(e))

            if stderr != '':
                stderr = stderr.strip()
                stderr = repr(stderr)
                stderr = stderr.replace("'", "")
                stderr = stderr.replace("\'", "")
                sql.update_provisioning_server_error(stderr, group, workspace, provider)
                print('error: ' + stderr)
            else:
                print('ok')
    except Exception as e:
        print(e)

if (
        form.getvalue('awsprovisining')
        or form.getvalue('awseditingprovisining')
        or form.getvalue('doprovisining')
        or form.getvalue('doeditprovisining')
        or form.getvalue('gcoreprovisining')
        or form.getvalue('gcoreeditgprovisining')
):
    roxywi_common.check_user_group()

    if form.getvalue('awsprovisining'):
        workspace = form.getvalue('awsprovisining')
        group = form.getvalue('aws_create_group')
        provider_id = form.getvalue('aws_create_provider')
        action = 'created'
        cloud = 'aws'
        state_name = 'aws_instance'
    elif form.getvalue('awseditingprovisining'):
        workspace = form.getvalue('awseditingprovisining')
        group = form.getvalue('aws_edit_group')
        provider_id = form.getvalue('aws_edit_provider')
        action = 'modified'
        cloud = 'aws'
        state_name = 'aws_instance'
    elif form.getvalue('doprovisining'):
        workspace = form.getvalue('doprovisining')
        group = form.getvalue('do_create_group')
        provider_id = form.getvalue('do_create_provider')
        action = 'created'
        cloud = 'do'
        state_name = 'digitalocean_droplet'
    elif form.getvalue('doeditprovisining'):
        workspace = form.getvalue('doeditprovisining')
        group = form.getvalue('do_edit_group')
        provider_id = form.getvalue('do_edit_provider')
        action = 'modified'
        cloud = 'do'
        state_name = 'digitalocean_droplet'
    elif form.getvalue('gcoreprovisining'):
        workspace = form.getvalue('gcoreprovisining')
        group = form.getvalue('gcore_create_group')
        provider_id = form.getvalue('gcore_create_provider')
        action = 'created'
        cloud = 'gcore'
        state_name = 'gcore_instance'
    elif form.getvalue('gcoreeditgprovisining'):
        workspace = form.getvalue('gcoreeditgprovisining')
        group = form.getvalue('gcore_edit_group')
        provider_id = form.getvalue('gcore_edit_provider')
        action = 'modified'
        cloud = 'gcore'
        state_name = 'gcore_instance'

    tfvars = f'{workspace}_{group}_{cloud}.tfvars'
    cmd = f'cd scripts/terraform/ && sudo terraform apply -auto-approve -no-color -input=false -target=module.{cloud}_module -var-file vars/{tfvars}'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider_id)
        sql.update_provisioning_server_error(stderr, group, workspace, provider_id)
        print('error: ' + stderr)
    else:
        if cloud == 'aws':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.aws_module.aws_eip.floating_ip[0]|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
            output, stderr = server_mod.subprocess_execute(cmd)
            if stderr != '':
                cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
        else:
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'

        output, stderr = server_mod.subprocess_execute(cmd)
        ips = ''
        for ip in output:
            ips += ip
            ips += ' '

        if cloud == 'gcore':
            ips = ips.split(' ')[0]

        print(ips)
        try:
            sql.update_provisioning_server_status('Created', group, workspace, provider_id, update_ip=ips)
        except Exception as e:
            print(e)

        if cloud == 'gcore':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.gcore_module.gcore_instance.hapwi|grep "name"|grep -v -e "_name\|name_" |head -1 |awk -F"\\\"" \'{print $2}\''
            output, stderr = server_mod.subprocess_execute(cmd)
            print(':' + output[0])
            try:
                sql.update_provisioning_server_gcore_name(workspace, output[0], group, provider_id)
            except Exception as e:
                print(e)

        roxywi_common.logging('Roxy-WI server', f'Server {workspace} has been {action}', provisioning=1)

if form.getvalue('provisiningdestroyserver'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('provisiningdestroyserver')
    workspace = form.getvalue('servername')
    group = form.getvalue('group')
    cloud_type = form.getvalue('type')
    provider_id = form.getvalue('provider_id')

    tf_workspace = f'{workspace}_{group}_{cloud_type}'

    cmd = f'cd scripts/terraform/ && sudo terraform init -upgrade -no-color && sudo terraform workspace select {tf_workspace}'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider_id)
        sql.update_provisioning_server_error(stderr, group, workspace, provider_id)
        print('error: ' + stderr)
    else:
        cmd = f'cd scripts/terraform/ && sudo terraform destroy -auto-approve -no-color -target=module.{cloud_type}_module -var-file vars/{tf_workspace}.tfvars'
        output, stderr = server_mod.subprocess_execute(cmd)

        if stderr != '':
            print(f'error: {stderr}')
        else:
            cmd = f'cd scripts/terraform/ && sudo terraform workspace select default && sudo terraform workspace delete -force {tf_workspace}'
            output, stderr = server_mod.subprocess_execute(cmd)

            print('ok')
            roxywi_common.logging('Roxy-WI server', 'Server has been destroyed', provisioning=1)
            try:
                sql.delete_provisioned_servers(server_id)
            except Exception as e:
                print(e)

if form.getvalue('gcorevars') or form.getvalue('gcoreeditvars'):
    if form.getvalue('gcorevars'):
        gcorevars = form.getvalue('gcorevars')
        group = form.getvalue('gcore_create_group')
        provider = form.getvalue('gcore_create_provider')
        region = form.getvalue('gcore_create_regions')
        project = form.getvalue('gcore_create_project')
        size = form.getvalue('gcore_create_size')
        oss = form.getvalue('gcore_create_oss')
        ssh_name = form.getvalue('gcore_create_ssh_name')
        volume_size = form.getvalue('gcore_create_volume_size')
        volume_type = form.getvalue('gcore_create_volume_type')
        delete_on_termination = form.getvalue('gcore_create_delete_on_termination')
        network_name = form.getvalue('gcore_create_network_name')
        firewall = form.getvalue('gcore_create_firewall')
        network_type = form.getvalue('gcore_create_network_type')
    elif form.getvalue('gcoreeditvars'):
        gcorevars = form.getvalue('gcoreeditvars')
        group = form.getvalue('gcore_edit_group')
        provider = form.getvalue('gcore_edit_provider')
        region = form.getvalue('gcore_edit_regions')
        project = form.getvalue('gcore_edit_project')
        size = form.getvalue('gcore_edit_size')
        oss = form.getvalue('gcore_edit_oss')
        ssh_name = form.getvalue('gcore_edit_ssh_name')
        volume_size = form.getvalue('gcore_edit_volume_size')
        volume_type = form.getvalue('gcore_edit_volume_type')
        delete_on_termination = form.getvalue('gcore_edit_delete_on_termination')
        network_name = form.getvalue('gcore_edit_network_name')
        firewall = form.getvalue('gcore_edit_firewall')
        network_type = form.getvalue('gcore_edit_network_type')

    try:
        gcore_user, gcore_pass = sql.select_gcore_provider(provider)
    except Exception as e:
        print(e)

    cmd = 'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={} ' \
          'group={} size={} os={} network_name={} volume_size={} server_name={} username={} ' \
          'pass={} firewall={} network_type={} ssh_name={} delete_on_termination={} project={} volume_type={} ' \
          'cloud=gcore"'.format(region, group, size, oss, network_name, volume_size, gcorevars, gcore_user, gcore_pass,
                                firewall, network_type, ssh_name, delete_on_termination, project, volume_type)

    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')

if form.getvalue('gcorevalidate') or form.getvalue('gcoreeditvalidate'):
    if form.getvalue('gcorevalidate'):
        workspace = form.getvalue('gcorevalidate')
        group = form.getvalue('gcore_create_group')
    elif form.getvalue('gcoreeditvalidate'):
        workspace = form.getvalue('gcoreeditvalidate')
        group = form.getvalue('gcore_edit_group')

    cmd = f'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.gcore_module -var-file vars/{workspace}_{group}_gcore.tfvars'
    output, stderr = server_mod.subprocess_execute(cmd)
    if stderr != '':
        print(f'error: {stderr}')
    else:
        print('ok')

if form.getvalue('gcoreworkspace'):
    workspace = form.getvalue('gcoreworkspace')
    group = form.getvalue('gcore_create_group')
    provider = form.getvalue('gcore_create_provider')
    region = form.getvalue('gcore_create_regions')
    project = form.getvalue('gcore_create_project')
    size = form.getvalue('gcore_create_size')
    oss = form.getvalue('gcore_create_oss')
    ssh_name = form.getvalue('gcore_create_ssh_name')
    volume_size = form.getvalue('gcore_create_volume_size')
    volume_type = form.getvalue('gcore_create_volume_type')
    delete_on_termination = form.getvalue('gcore_create_delete_on_termination')
    network_type = form.getvalue('gcore_create_network_type')
    firewall = form.getvalue('gcore_create_firewall')
    network_name = form.getvalue('gcore_create_network_name')

    cmd = 'cd scripts/terraform/ && sudo terraform workspace new ' + workspace + '_' + group + '_gcore'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        try:
            if sql.add_server_gcore(
                    project, region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                    provider, group, 'Creating', delete_on_termination, volume_type
            ):
                user_params = roxywi_common.get_users_params()
                new_server = sql.select_provisioned_servers(new=workspace, group=group, type='gcore')
                params = sql.select_provisioning_params()

                env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
                template = env.get_template('ajax/provisioning/provisioned_servers.html')
                template = template.render(servers=new_server,
                                           groups=sql.select_groups(),
                                           user_group=group,
                                           providers=sql.select_providers(group),
                                           role=user_params['role'],
                                           adding=1,
                                           params=params)
                print(template)
        except Exception as e:
            print(e)

if form.getvalue('gcoreeditworkspace'):
    workspace = form.getvalue('gcoreeditworkspace')
    group = form.getvalue('gcore_edit_group')
    provider = form.getvalue('gcore_edit_provider')
    region = form.getvalue('gcore_edit_regions')
    project = form.getvalue('gcore_edit_project')
    size = form.getvalue('gcore_edit_size')
    oss = form.getvalue('gcore_edit_oss')
    ssh_name = form.getvalue('gcore_edit_ssh_name')
    volume_size = form.getvalue('gcore_edit_volume_size')
    volume_type = form.getvalue('gcore_edit_volume_type')
    delete_on_termination = form.getvalue('gcore_edit_delete_on_termination')
    network_type = form.getvalue('gcore_edit_network_type')
    firewall = form.getvalue('gcore_edit_firewall')
    network_name = form.getvalue('gcore_edit_network_name')
    server_id = form.getvalue('server_id')

    try:
        if sql.update_server_gcore(
                region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                provider, group, 'Editing', server_id, delete_on_termination, volume_type, project
        ):

            try:
                cmd = 'cd scripts/terraform/ && sudo terraform workspace select ' + workspace + '_' + group + '_gcore'
                output, stderr = server_mod.subprocess_execute(cmd)
            except Exception as e:
                print('error: ' + str(e))

            if stderr != '':
                stderr = stderr.strip()
                stderr = repr(stderr)
                stderr = stderr.replace("'", "")
                stderr = stderr.replace("\'", "")
                sql.update_provisioning_server_error(stderr, group, workspace, provider)
                print('error: ' + stderr)
            else:
                print('ok')
    except Exception as e:
        print(e)

if form.getvalue('editAwsServer'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('editAwsServer')
    user_group = form.getvalue('editAwsGroup')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    server = sql.select_gcore_server(server_id=server_id)
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/aws_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params)
    print(template)

if form.getvalue('editGcoreServer'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('editGcoreServer')
    user_group = form.getvalue('editGcoreGroup')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    server = sql.select_gcore_server(server_id=server_id)
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/gcore_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params)
    print(template)

if form.getvalue('editDoServer'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('editDoServer')
    user_group = form.getvalue('editDoGroup')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    server = sql.select_do_server(server_id=server_id)
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/do_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params)
    print(template)

if form.getvalue('edit_do_provider'):
    roxywi_common.check_user_group()
    provider_id = form.getvalue('edit_do_provider')
    new_name = form.getvalue('edit_do_provider_name')
    new_token = form.getvalue('edit_do_provider_token')

    try:
        if sql.update_do_provider(new_name, new_token, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been renamed. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)

if form.getvalue('edit_gcore_provider'):
    roxywi_common.check_user_group()
    provider_id = form.getvalue('edit_gcore_provider')
    new_name = form.getvalue('edit_gcore_provider_name')
    new_user = form.getvalue('edit_gcore_provider_user')
    new_pass = form.getvalue('edit_gcore_provider_pass')

    try:
        if sql.update_gcore_provider(new_name, new_user, new_pass, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been renamed. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)

if form.getvalue('edit_aws_provider'):
    roxywi_common.check_user_group()
    provider_id = form.getvalue('edit_aws_provider')
    new_name = form.getvalue('edit_aws_provider_name')
    new_key = form.getvalue('edit_aws_provider_key')
    new_secret = form.getvalue('edit_aws_provider_secret')

    try:
        if sql.update_aws_provider(new_name, new_key, new_secret, provider_id):
            print('ok')
            roxywi_common.logging('Roxy-WI server', f'Provider has been renamed. New name is {new_name}', provisioning=1)
    except Exception as e:
        print(e)

if form.getvalue('loadservices'):
    from modules.roxywi.roxy import get_services_status

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_services.html')
    try:
        services = get_services_status()
    except Exception as e:
        print(e)

    template = template.render(services=services)
    print(template)

if form.getvalue('loadchecker'):
    from modules.roxywi.roxy import get_services_status

    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/load_telegram.html')
    services = get_services_status()
    groups = sql.select_groups()
    page = form.getvalue('page')

    try:
        user_subscription = roxywi_common.return_user_status()
    except Exception as e:
        user_subscription = roxywi_common.return_unsubscribed_user_status()
        roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

    if user_subscription['user_status']:
        haproxy_settings = sql.select_checker_settings(1)
        nginx_settings = sql.select_checker_settings(2)
        keepalived_settings = sql.select_checker_settings(3)
        apache_settings = sql.select_checker_settings(4)
        if page == 'servers.py':
            user_group = roxywi_common.get_user_group(id=1)
            telegrams = sql.get_user_telegram_by_group(user_group)
            slacks = sql.get_user_slack_by_group(user_group)
            haproxy_servers = roxywi_common.get_dick_permit(haproxy=1, only_group=1)
            nginx_servers = roxywi_common.get_dick_permit(nginx=1, only_group=1)
            apache_servers = roxywi_common.get_dick_permit(apache=1, only_group=1)
            keepalived_servers = roxywi_common.get_dick_permit(keepalived=1, only_group=1)
        else:
            telegrams = sql.select_telegram()
            slacks = sql.select_slack()
            haproxy_servers = roxywi_common.get_dick_permit(haproxy=1)
            nginx_servers = roxywi_common.get_dick_permit(nginx=1)
            apache_servers = roxywi_common.get_dick_permit(apache=1)
            keepalived_servers = roxywi_common.get_dick_permit(keepalived=1)
    else:
        telegrams = ''
        slacks = ''

    template = template.render(services=services,
                               telegrams=telegrams,
                               groups=groups,
                               slacks=slacks,
                               user_status=user_subscription['user_status'],
                               user_plan=user_subscription['user_plan'],
                               haproxy_servers=haproxy_servers,
                               nginx_servers=nginx_servers,
                               apache_servers=apache_servers,
                               keepalived_servers=keepalived_servers,
                               haproxy_settings=haproxy_settings,
                               nginx_settings=nginx_settings,
                               keepalived_settings=keepalived_settings,
                               apache_settings=apache_settings,
                               page=page)
    print(template)

if form.getvalue('load_update_hapwi'):
    import modules.roxywi.roxy as roxy

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_updateroxywi.html')

    versions = roxy.versions()
    checker_ver = roxy.check_new_version('checker')
    smon_ver = roxy.check_new_version('smon')
    metrics_ver = roxy.check_new_version('metrics')
    keep_ver = roxy.check_new_version('keep_alive')
    portscanner_ver = roxy.check_new_version('portscanner')
    socket_ver = roxy.check_new_version('socket')
    prometheus_exp_ver = roxy.check_new_version('prometheus-exporter')
    services = roxy.get_services_status()

    template = template.render(services=services,
                               versions=versions,
                               checker_ver=checker_ver,
                               smon_ver=smon_ver,
                               metrics_ver=metrics_ver,
                               portscanner_ver=portscanner_ver,
                               socket_ver=socket_ver,
                               prometheus_exp_ver=prometheus_exp_ver,
                               keep_ver=keep_ver)
    print(template)

if form.getvalue('loadopenvpn'):
    import distro

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_openvpn.html')
    openvpn_configs = ''
    openvpn_sess = ''
    openvpn = ''

    if distro.id() == 'ubuntu':
        stdout, stderr = server_mod.subprocess_execute("apt show openvpn3 2>&1|grep E:")
    elif distro.id() == 'centos' or distro.id() == 'rhel':
        stdout, stderr = server_mod.subprocess_execute("rpm --query openvpn3-client")

    if (
            (stdout[0] != 'package openvpn3-client is not installed' and stderr != '/bin/sh: rpm: command not found')
            and stdout[0] != 'E: No packages found'
    ):
        cmd = "sudo openvpn3 configs-list |grep -E 'ovpn|(^|[^0-9])[0-9]{4}($|[^0-9])' |grep -v net|awk -F\"    \" '{print $1}'|awk 'ORS=NR%2?\" \":\"\\n\"'"
        openvpn_configs, stderr = server_mod.subprocess_execute(cmd)
        cmd = "sudo openvpn3 sessions-list|grep -E 'Config|Status'|awk -F\":\" '{print $2}'|awk 'ORS=NR%2?\" \":\"\\n\"'| sed 's/^ //g'"
        openvpn_sess, stderr = server_mod.subprocess_execute(cmd)
        openvpn = stdout[0]

    template = template.render(openvpn=openvpn,
                               openvpn_sess=openvpn_sess,
                               openvpn_configs=openvpn_configs)
    print(template)

if form.getvalue('check_telegram'):
    import modules.alerting.alerting as alerting

    telegram_id = form.getvalue('check_telegram')
    mess = 'Test message from Roxy-WI'
    alerting.telegram_send_mess(mess, telegram_channel_id=telegram_id)

if form.getvalue('check_slack'):
    import modules.alerting.alerting as alerting

    slack_id = form.getvalue('check_slack')
    mess = 'Test message from Roxy-WI'
    alerting.slack_send_mess(mess, slack_channel_id=slack_id)

if form.getvalue('check_rabbitmq_alert'):
    import modules.alerting.alerting as alerting

    alerting.check_rabbit_alert()

if form.getvalue('check_email_alert'):
    import modules.alerting.alerting as alerting

    alerting.check_email_alert()

if form.getvalue('getoption'):
    group = form.getvalue('getoption')
    term = form.getvalue('term')
    options = sql.select_options(group=group, term=term)

    a = {}
    v = 0

    for i in options:
        a[v] = i.options
        v = v + 1

    print(json.dumps(a))

if form.getvalue('newtoption'):
    option = form.getvalue('newtoption')
    group = form.getvalue('newoptiongroup')
    if option is None or group is None:
        print(error_mess)
    else:
        if sql.insert_new_option(option, group):
            env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
            template = env.get_template('/new_option.html')

            template = template.render(options=sql.select_options(option=option))
            print(template)

if form.getvalue('updateoption') is not None:
    option = form.getvalue('updateoption')
    option_id = form.getvalue('id')
    if option is None or option_id is None:
        print(error_mess)
    else:
        sql.update_options(option, option_id)

if form.getvalue('optiondel') is not None:
    if sql.delete_option(form.getvalue('optiondel')):
        print("Ok")

if form.getvalue('getsavedserver'):
    group = form.getvalue('getsavedserver')
    term = form.getvalue('term')
    servers = sql.select_saved_servers(group=group, term=term)

    a = {}
    v = 0
    for i in servers:
        a[v] = {}
        a[v]['value'] = {}
        a[v]['desc'] = {}
        a[v]['value'] = i.server
        a[v]['desc'] = i.description
        v = v + 1

    print(json.dumps(a))

if form.getvalue('newsavedserver'):
    savedserver = form.getvalue('newsavedserver')
    description = form.getvalue('newsavedserverdesc')
    group = form.getvalue('newsavedservergroup')
    if savedserver is None or group is None:
        print(error_mess)
    else:
        if sql.insert_new_savedserver(savedserver, description, group):
            env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
            template = env.get_template('/new_saved_servers.html')

            template = template.render(server=sql.select_saved_servers(server=savedserver))
            print(template)

if form.getvalue('updatesavedserver') is not None:
    savedserver = form.getvalue('updatesavedserver')
    description = form.getvalue('description')
    savedserver_id = form.getvalue('id')
    if savedserver is None or savedserver_id is None:
        print(error_mess)
    else:
        sql.update_savedserver(savedserver, description, savedserver_id)

if form.getvalue('savedserverdel') is not None:
    if sql.delete_savedserver(common.checkAjaxInput(form.getvalue('savedserverdel'))):
        print("Ok")

if form.getvalue('show_users_ovw') is not None:
    import modules.roxywi.overview as roxywi_overview

    roxywi_overview.user_ovw()

if form.getvalue('serverSettings') is not None:
    server_id = common.checkAjaxInput(form.getvalue('serverSettings'))
    service = common.checkAjaxInput(form.getvalue('serverSettingsService'))
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_service_settings.html')

    template = template.render(settings=sql.select_service_settings(server_id, service), service=service)
    print(template)

if form.getvalue('serverSettingsSave') is not None:
    server_id = common.checkAjaxInput(form.getvalue('serverSettingsSave'))
    service = common.checkAjaxInput(form.getvalue('serverSettingsService'))
    haproxy_enterprise = common.checkAjaxInput(form.getvalue('serverSettingsEnterprise'))
    haproxy_dockerized = common.checkAjaxInput(form.getvalue('serverSettingshaproxy_dockerized'))
    nginx_dockerized = common.checkAjaxInput(form.getvalue('serverSettingsnginx_dockerized'))
    apache_dockerized = common.checkAjaxInput(form.getvalue('serverSettingsapache_dockerized'))
    haproxy_restart = common.checkAjaxInput(form.getvalue('serverSettingsHaproxyrestart'))
    nginx_restart = common.checkAjaxInput(form.getvalue('serverSettingsNginxrestart'))
    apache_restart = common.checkAjaxInput(form.getvalue('serverSettingsApache_restart'))
    server_ip = sql.select_server_ip_by_id(server_id)

    if service == 'haproxy':
        if sql.insert_or_update_service_setting(server_id, service, 'haproxy_enterprise', haproxy_enterprise):
            print('Ok')
            if haproxy_enterprise == '1':
                roxywi_common.logging(server_ip, 'Service has been flagged as an Enterprise version', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a community version', roxywi=1, login=1,
                              keep_history=1, service=service)
        if sql.insert_or_update_service_setting(server_id, service, 'dockerized', haproxy_dockerized):
            print('Ok')
            if haproxy_dockerized == '1':
                roxywi_common.logging(server_ip, 'Service has been flagged as a dockerized', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a system service', roxywi=1, login=1,
                              keep_history=1, service=service)
        if sql.insert_or_update_service_setting(server_id, service, 'restart', haproxy_restart):
            print('Ok')
            if haproxy_restart == '1':
                roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                              keep_history=1, service=service)

    if service == 'nginx':
        if sql.insert_or_update_service_setting(server_id, service, 'dockerized', nginx_dockerized):
            print('Ok')
            if nginx_dockerized:
                roxywi_common.logging(server_ip, 'Service has been flagged as a dockerized', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a system service', roxywi=1, login=1,
                              keep_history=1, service=service)
        if sql.insert_or_update_service_setting(server_id, service, 'restart', nginx_restart):
            print('Ok')
            if nginx_restart == '1':
                roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                              keep_history=1, service=service)

    if service == 'apache':
        if sql.insert_or_update_service_setting(server_id, service, 'dockerized', apache_dockerized):
            print('Ok')
            if apache_dockerized:
                roxywi_common.logging(server_ip, 'Service has been flagged as a dockerized', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a system service', roxywi=1, login=1,
                              keep_history=1, service=service)
            if sql.insert_or_update_service_setting(server_id, service, 'restart', apache_restart):
                print('Ok')
                if apache_restart == '1':
                    roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                                  keep_history=1, service=service)
                else:
                    roxywi_common.logging(server_ip, 'Restart option is disabled for this service', roxywi=1, login=1,
                                  keep_history=1, service=service)

if act == 'showListOfVersion':
    service = common.checkAjaxInput(form.getvalue('service'))
    configver = common.checkAjaxInput(form.getvalue('configver'))
    for_delver = common.checkAjaxInput(form.getvalue('for_delver'))
    style = common.checkAjaxInput(form.getvalue('style'))
    users = sql.select_users()
    service_desc = sql.select_service(service)

    if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
        configs = sql.select_config_version(serv, service_desc.slug)
        action = f'versions.py?service={service_desc.slug}'

        if service in ('haproxy', 'nginx', 'apache'):
            configs_dir = get_config.get_config_var('configs', f'{service_desc.service}_save_configs_dir')
        else:
            configs_dir = get_config.get_config_var('configs', 'kp_save_configs_dir')

        if service == 'haproxy':
            files = roxywi_common.get_files()
        else:
            files = roxywi_common.get_files(configs_dir, 'conf')

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
                      extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"])
    template = env.get_template('ajax/show_list_version.html')

    template = template.render(serv=serv,
                               service=service,
                               action=action,
                               return_files=files,
                               configver=configver,
                               for_delver=for_delver,
                               configs=configs,
                               users=users,
                               style=style)
    print(template)

if act == 'getSystemInfo':
    server_mod.show_system_info()

if act == 'updateSystemInfo':
    server_mod.update_system_info()

if act == 'findInConfigs':
    server_ip = serv
    server_ip = common.is_ip_or_dns(server_ip)
    finding_words = form.getvalue('words')
    service = form.getvalue('service')
    log_path = sql.get_setting(service + '_dir')
    log_path = common.return_nice_path(log_path)
    commands = [f'sudo grep "{finding_words}" {log_path}*/*.conf -C 2 -Rn']
    return_find = server_mod.ssh_command(server_ip, commands, raw=1)
    return_find = config_mod.show_finding_in_config(return_find, grep=finding_words)

    if 'error: ' in return_find:
        print(return_find)
        sys.exit()
    print(return_find)

if act == 'check_service':
    import socket
    from contextlib import closing

    cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
    user_uuid = cookie.get('uuid')
    user_id = sql.get_user_id_by_uuid(user_uuid.value)
    user_services = sql.select_user_services(user_id)
    server_id = common.checkAjaxInput(form.getvalue('server_id'))
    service = common.checkAjaxInput(form.getvalue('service'))

    if '1' in user_services:
        if service == 'haproxy':
            haproxy_sock_port = sql.get_setting('haproxy_sock_port')
            cmd = 'echo "show info" |nc %s %s -w 1 -v|grep Name' % (serv, haproxy_sock_port)
            out = server_mod.subprocess_execute(cmd)
            for k in out[0]:
                if "Name" in k:
                    print('up')
                    break
            else:
                print('down')
    if '2' in user_services:
        if service == 'nginx':
            nginx_stats_port = sql.get_setting('nginx_stats_port')

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(5)

                try:
                    if sock.connect_ex((serv, nginx_stats_port)) == 0:
                        print('up')
                    else:
                        print('down')
                except Exception:
                    print('down')
    if '4' in user_services:
        if service == 'apache':
            apache_stats_port = sql.get_setting('apache_stats_port')

            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(5)

                try:
                    if sock.connect_ex((serv, apache_stats_port)) == 0:
                        print('up')
                    else:
                        print('down')
                except Exception as e:
                    print('down' + str(e))

if form.getvalue('show_sub_ovw'):
    import modules.roxywi.overview as roxywi_overview

    roxywi_overview.show_sub_ovw()

if form.getvalue('updateHaproxyCheckerSettings'):
    setting_id = form.getvalue('updateHaproxyCheckerSettings')
    email = form.getvalue('email')
    service_alert = form.getvalue('server')
    backend_alert = form.getvalue('backend')
    maxconn_alert = form.getvalue('maxconn')
    telegram_id = form.getvalue('telegram_id')
    slack_id = form.getvalue('slack_id')

    if sql.update_haproxy_checker_settings(email, telegram_id, slack_id, service_alert, backend_alert,
                                           maxconn_alert, setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')

if form.getvalue('updateKeepalivedCheckerSettings'):
    setting_id = form.getvalue('updateKeepalivedCheckerSettings')
    email = form.getvalue('email')
    service_alert = form.getvalue('server')
    backend_alert = form.getvalue('backend')
    telegram_id = form.getvalue('telegram_id')
    slack_id = form.getvalue('slack_id')

    if sql.update_keepalived_checker_settings(email, telegram_id, slack_id, service_alert, backend_alert, setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')

if form.getvalue('updateServiceCheckerSettings'):
    setting_id = form.getvalue('updateServiceCheckerSettings')
    email = form.getvalue('email')
    service_alert = form.getvalue('server')
    telegram_id = form.getvalue('telegram_id')
    slack_id = form.getvalue('slack_id')

    if sql.update_service_checker_settings(email, telegram_id, slack_id, service_alert, setting_id):
        print('ok')
    else:
        print('error: Cannot update Checker settings')
