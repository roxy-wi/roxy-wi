#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import http.cookies
from uuid import UUID

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.server.ssh as ssh_mod
import modules.common.common as common
import modules.config.add as add_mod
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

if form.getvalue('checkSshConnect') is not None and serv is not None:
    try:
        print(server_mod.ssh_command(serv, ["ls -1t"]))
    except Exception as e:
        print(e)

if form.getvalue('getcerts') is not None and serv is not None:
    add_mod.get_ssl_certs(serv)

if form.getvalue('getcert') is not None and serv is not None:
    cert_id = common.checkAjaxInput(form.getvalue('getcert'))
    add_mod.get_ssl_cert(serv, cert_id)

if form.getvalue('delcert') is not None and serv is not None:
    cert_id = common.checkAjaxInput(form.getvalue('delcert'))
    add_mod.del_ssl_cert(serv, cert_id)

if serv and form.getvalue('ssl_cert'):
    ssl_name = common.checkAjaxInput(form.getvalue('ssl_name'))
    ssl_cont = form.getvalue('ssl_cert')
    add_mod.upload_ssl_cert(serv, ssl_name, ssl_cont)

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

if form.getvalue('maxconn_global') is not None:
    import modules.config.runtime as runtime

    runtime.change_maxconn_global()

if form.getvalue('maxconn_frontend') is not None:
    import modules.config.runtime as runtime

    runtime.change_maxconn_frontend()

if form.getvalue('maxconn_backend') is not None:
    import modules.config.runtime as runtime

    runtime.change_maxconn_backend()

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
    add_mod.show_userlist(serv)

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

    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_log_files.html')
    template = template.render(serv=serv, return_files=return_files, path_dir=log_path, lang=lang)
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
        service_mod.install_service(master, 'nginx', docker, server=server)
    elif server == 'slave':
        service_mod.install_service(slave, 'nginx', docker, server=server)

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

    service = 'node'
    exp_installation.node_keepalived_exp_installation(service)

if form.getvalue('keepalived_exp_install'):
    import modules.service.exporter_installation as exp_installation

    service = 'keepalived'
    exp_installation.node_keepalived_exp_installation(service)

if form.getvalue('backup') or form.getvalue('deljob') or form.getvalue('backupupdate'):
    import modules.service.backup as backup_mod

    serv = common.is_ip_or_dns(form.getvalue('server'))
    rpath = common.checkAjaxInput(form.getvalue('rpath'))
    time = common.checkAjaxInput(form.getvalue('time'))
    backup_type = common.checkAjaxInput(form.getvalue('type'))
    rserver = common.checkAjaxInput(form.getvalue('rserver'))
    cred = int(form.getvalue('cred'))
    deljob = common.checkAjaxInput(form.getvalue('deljob'))
    update = common.checkAjaxInput(form.getvalue('backupupdate'))
    description = common.checkAjaxInput(form.getvalue('description'))

    backup_mod.backup(serv, rpath, time, backup_type, rserver, cred, deljob, update, description)


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
    lang = roxywi_common.get_user_lang()
    group_id = roxywi_common.get_user_group(id=1)
    if service in ('nginx', 'apache'):
        metrics = sql.select_service_table_metrics(service, group_id)
    else:
        metrics = sql.select_table_metrics(group_id)

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/table_metrics.html')

    template = template.render(table_stat=metrics, service=service, lang=lang)
    print(template)

if form.getvalue('metrics_hapwi_ram'):
    import modules.roxywi.metrics as metric
    metrics_type = common.checkAjaxInput(form.getvalue('ip'))

    metric.show_ram_metrics(metrics_type)

if form.getvalue('metrics_hapwi_cpu'):
    import modules.roxywi.metrics as metric

    metrics_type = common.checkAjaxInput(form.getvalue('ip'))

    metric.show_cpu_metrics(metrics_type)

if form.getvalue('new_metrics'):
    import modules.roxywi.metrics as metric

    server_ip = common.is_ip_or_dns(form.getvalue('server'))
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(form.getvalue('time_range'))

    metric.haproxy_metrics(server_ip, hostname, time_range)

if form.getvalue('new_http_metrics'):
    import modules.roxywi.metrics as metric

    server_ip = common.is_ip_or_dns(form.getvalue('server'))
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(form.getvalue('time_range'))

    metric.haproxy_http_metrics(server_ip, hostname, time_range)

if any((form.getvalue('new_nginx_metrics'), form.getvalue('new_apache_metrics'), form.getvalue('new_waf_metrics'))):
    import modules.roxywi.metrics as metric

    server_ip = common.is_ip_or_dns(form.getvalue('server'))
    hostname = sql.get_hostname_by_server_ip(server_ip)
    time_range = common.checkAjaxInput(form.getvalue('time_range'))
    service = ''

    if form.getvalue('new_nginx_metrics'):
        service = 'nginx'
    elif form.getvalue('new_apache_metrics'):
        service = 'apache'
    elif form.getvalue('new_waf_metrics'):
        service = 'waf'

    metric.service_metrics(server_ip, hostname, service, time_range)

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
    color = common.checkAjaxInput(form.getvalue('color'))
    group = common.checkAjaxInput(form.getvalue('group'))
    bwlists = common.checkAjaxInput(form.getvalue('bwlists'))

    add_mod.get_bwlist(color, group, bwlists)

if form.getvalue('bwlists_create'):
    list_name = common.checkAjaxInput(form.getvalue('bwlists_create'))
    color = common.checkAjaxInput(form.getvalue('color'))
    group = common.checkAjaxInput(form.getvalue('group'))

    add_mod.create_bwlist(serv, list_name, color, group)

if form.getvalue('bwlists_save'):
    color = common.checkAjaxInput(form.getvalue('color'))
    group = common.checkAjaxInput(form.getvalue('group'))
    bwlists_save = common.checkAjaxInput(form.getvalue('bwlists_save'))
    list_con = form.getvalue('bwlists_content')
    action = common.checkAjaxInput(form.getvalue('bwlists_restart'))

    add_mod.save_bwlist(bwlists_save, list_con, color, group, serv, action)

if form.getvalue('bwlists_delete'):
    color = common.checkAjaxInput(form.getvalue('color'))
    list_name = common.checkAjaxInput(form.getvalue('bwlists_delete'))
    group = common.checkAjaxInput( form.getvalue('group'))

    add_mod.delete_bwlist(list_name, color, group, serv)

if form.getvalue('get_lists'):
    group = common.checkAjaxInput(form.getvalue('group'))
    color = common.checkAjaxInput(form.getvalue('color'))
    add_mod.get_bwlists_for_autocomplete(color, group)

if form.getvalue('get_ldap_email'):
    import modules.roxywi.user as roxywi_user

    roxywi_user.get_ldap_email()

if form.getvalue('change_waf_mode'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf.change_waf_mode()

error_mess = roxywi_common.return_error_message()

if form.getvalue('newuser') is not None:
    import modules.roxywi.user as roxywi_user

    email = common.checkAjaxInput(form.getvalue('newemail'))
    password = common.checkAjaxInput(form.getvalue('newpassword'))
    role = common.checkAjaxInput(form.getvalue('newrole'))
    new_user = common.checkAjaxInput(form.getvalue('newusername'))
    page = common.checkAjaxInput(form.getvalue('page'))
    activeuser = common.checkAjaxInput(form.getvalue('activeuser'))
    group = common.checkAjaxInput(form.getvalue('newgroupuser'))
    lang = roxywi_common.get_user_lang()

    if roxywi_user.create_user(new_user, email, password, role, activeuser, group):
        env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
        template = env.get_template('ajax/new_user.html')

        template = template.render(users=sql.select_users(user=new_user),
                                   groups=sql.select_groups(),
                                   page=page,
                                   roles=sql.select_roles(),
                                   adding=1,
                                   lang=lang)
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
    ip = common.is_ip_or_dns(form.getvalue('newip'))
    group = common.checkAjaxInput(form.getvalue('newservergroup'))
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
    lang = roxywi_common.get_user_lang()

    if ip == '':
        print('error: IP or DNS name is not valid')
        sys.exit()
    try:
        if server_mod.create_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx, apache, firewall):
            try:
                user_subscription = roxywi_common.return_user_status()
            except Exception as e:
                user_subscription = roxywi_common.return_unsubscribed_user_status()
                roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

            env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
            template = env.get_template('ajax/new_server.html')
            template = template.render(groups=sql.select_groups(), servers=sql.select_servers(server=ip),
                                       masters=sql.select_servers(get_master_servers=1), sshs=sql.select_ssh(group=group),
                                       page=page, user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'],
                                       adding=1,lang=lang)
            print(template)
            roxywi_common.logging(ip, f'A new server {hostname} has been created', roxywi=1, login=1, keep_history=1, service='server')

    except Exception as e:
        print(f'error: {e}')

if act == 'after_adding':
    hostname = common.checkAjaxInput(form.getvalue('servername'))
    ip = common.is_ip_or_dns(form.getvalue('newip'))
    group = common.checkAjaxInput(form.getvalue('newservergroup'))
    scan_server = common.checkAjaxInput(form.getvalue('scan_server'))

    try:
        server_mod.update_server_after_creating(hostname, ip, scan_server)
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
    roxywi_common.logging(server_ip, f'The server {name} has been updated ', roxywi=1, login=1, keep_history=1,
                  service=service)

if form.getvalue('updateserver') is not None:
    name = form.getvalue('updateserver')
    group = form.getvalue('servergroup')
    typeip = form.getvalue('typeip')
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
        sql.update_server(name, group, typeip, enable, master, serv_id, cred, port, desc, firewall, protected)
        roxywi_common.logging(f'the server {name}', ' has been updated ', roxywi=1, login=1)
        server_ip = sql.select_server_ip_by_id(serv_id)
        roxywi_common.logging(server_ip, f'The server {name} has been update', roxywi=1, login=1,
                      keep_history=1, service='server')

if form.getvalue('serverdel') is not None:
    server_id = common.checkAjaxInput(form.getvalue('serverdel'))

    server_mod.delete_server(server_id)

if form.getvalue('newgroup') is not None:
    newgroup = common.checkAjaxInput(form.getvalue('groupname'))
    desc = common.checkAjaxInput(form.getvalue('newdesc'))
    if newgroup is None:
        print(error_mess)
    else:
        try:
            if sql.add_group(newgroup, desc):
                env = Environment(loader=FileSystemLoader('templates/ajax/'), autoescape=True)
                template = env.get_template('/new_group.html')

                output_from_parsed_template = template.render(groups=sql.select_groups(group=newgroup))
                print(output_from_parsed_template)
                roxywi_common.logging('Roxy-WI server', f'A new group {newgroup} has been created', roxywi=1, login=1)
        except Exception as e:
            print(e)

if form.getvalue('groupdel') is not None:
    import modules.roxywi.group as group_mod

    group_id = common.checkAjaxInput(form.getvalue('groupdel'))
    group_mod.delete_group(group_id)


if form.getvalue('updategroup') is not None:
    import modules.roxywi.group as group_mod

    name = common.checkAjaxInput(form.getvalue('updategroup'))
    desc = common.checkAjaxInput(form.getvalue('descript'))
    group_id = common.checkAjaxInput(form.getvalue('id'))
    group_mod.update_group(group_id, name, desc)

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

if act == 'show_user_group_and_role':
    import modules.roxywi.user as roxy_user

    roxy_user.show_user_groups_and_roles()

if act == 'save_user_group_and_role':
    import modules.roxywi.user as roxy_user

    roxy_user.save_user_group_and_role()

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
        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/show_new_smon.html')
        template = template.render(
            smon=sql.select_smon_by_id(last_id),
            telegrams=sql.get_user_telegram_by_group(user_group),
            slacks=sql.get_user_slack_by_group(user_group),
            lang=lang
        )
        print(template)
        roxywi_common.logging('SMON', f' Has been add a new server {server} to SMON ', roxywi=1, login=1)

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
    lang = roxywi_common.get_user_lang()
    sort = common.checkAjaxInput(form.getvalue('sort'))
    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/smon_dashboard.html')
    template = template.render(smon=sql.smon_list(user_group), sort=sort, lang=lang, update=1)
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
            roxywi_common.logging('SMON', f' Has been update the server {ip} to SMON ', roxywi=1, login=1)
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

if form.getvalue('keepalivedBecameMaster'):
    import modules.roxywi.overview as roxywi_overview

    server_ip = common.is_ip_or_dns(form.getvalue('keepalivedBecameMaster'))
    roxywi_overview.keepalived_became_master(server_ip)

if form.getvalue('waf_rule_id'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf.switch_waf_rule(serv)

if form.getvalue('new_waf_rule'):
    import modules.roxywi.waf as roxy_waf

    roxy_waf.create_waf_rule(serv)

if form.getvalue('lets_domain'):
    lets_domain = common.checkAjaxInput(form.getvalue('lets_domain'))
    lets_email = common.checkAjaxInput(form.getvalue('lets_email'))

    add_mod.get_le_cert(serv, lets_domain, lets_email)

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
        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/scan_ports.html')
        template = template.render(ports=stdout, info=stdout1, lang=lang)
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
    import modules.roxywi.nettools as nettools

    nettools.ping_from_server()

if form.getvalue('nettools_telnet_server_from'):
    import modules.roxywi.nettools as nettools

    nettools.telnet_from_server()

if form.getvalue('nettools_nslookup_server_from'):
    import modules.roxywi.nettools as nettools

    nettools.nslookup_from_server()

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
        group_id = cookie.get('group')
        group_id = int(group_id.value)
        role_id = sql.get_user_role_by_uuid(user_uuid.value, group_id)
        params = sql.select_provisioning_params()
        providers = sql.select_providers(provider_group, key=provider_token)

        if role_id == 1:
            groups = sql.select_groups()
        else:
            groups = ''

        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/provisioning/providers.html')
        template = template.render(providers=providers, role=role_id, groups=groups, user_group=provider_group,
                                   adding=1, params=params, lang=lang)
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
            lang = roxywi_common.get_user_lang()

            env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
            template = env.get_template('ajax/provisioning/provisioned_servers.html')
            template = template.render(
                servers=new_server, groups=sql.select_groups(), user_group=group, lang=lang,
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
                lang = roxywi_common.get_user_lang()

                env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
                template = env.get_template('ajax/provisioning/provisioned_servers.html')
                template = template.render(
                    servers=new_server, groups=sql.select_groups(), user_group=group, lang=lang,
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
                lang = roxywi_common.get_user_lang()

                env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
                template = env.get_template('ajax/provisioning/provisioned_servers.html')
                template = template.render(servers=new_server,
                                           groups=sql.select_groups(),
                                           user_group=group,
                                           providers=sql.select_providers(group),
                                           role=user_params['role'],
                                           adding=1,
                                           params=params,
                                           lang=lang)
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
    lang = roxywi_common.get_user_lang()
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/aws_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params, lang=lang)
    print(template)

if form.getvalue('editGcoreServer'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('editGcoreServer')
    user_group = form.getvalue('editGcoreGroup')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    server = sql.select_gcore_server(server_id=server_id)
    lang = roxywi_common.get_user_lang()
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/gcore_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params, lang=lang)
    print(template)

if form.getvalue('editDoServer'):
    roxywi_common.check_user_group()
    server_id = form.getvalue('editDoServer')
    user_group = form.getvalue('editDoGroup')
    params = sql.select_provisioning_params()
    providers = sql.select_providers(int(user_group))
    server = sql.select_do_server(server_id=server_id)
    lang = roxywi_common.get_user_lang()
    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/do_edit_dialog.html')
    template = template.render(server=server, providers=providers, params=params, lang=lang)
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

    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_services.html')
    try:
        services = get_services_status()
    except Exception as e:
        print(e)

    template = template.render(services=services, lang=lang)
    print(template)

if form.getvalue('loadchecker'):
    from modules.roxywi.roxy import get_services_status

    lang = roxywi_common.get_user_lang()
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
                               page=page,
                               lang=lang)
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
    lang = roxywi_common.get_user_lang()

    template = template.render(services=services,
                               versions=versions,
                               checker_ver=checker_ver,
                               smon_ver=smon_ver,
                               metrics_ver=metrics_ver,
                               portscanner_ver=portscanner_ver,
                               socket_ver=socket_ver,
                               prometheus_exp_ver=prometheus_exp_ver,
                               keep_ver=keep_ver,
                               lang=lang)
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

    add_mod.get_saved_option(group, term)

if form.getvalue('newtoption'):
    option = common.checkAjaxInput(form.getvalue('newtoption'))
    group = common.checkAjaxInput(form.getvalue('newoptiongroup'))
    if option is None or group is None:
        print(error_mess)
    else:
       add_mod.create_saved_option(option, group)

if form.getvalue('updateoption') is not None:
    option = common.checkAjaxInput(form.getvalue('updateoption'))
    option_id = common.checkAjaxInput(form.getvalue('id'))
    if option is None or option_id is None:
        print(error_mess)
    else:
        sql.update_options(option, option_id)

if form.getvalue('optiondel') is not None:
    if sql.delete_option(common.checkAjaxInput(form.getvalue('optiondel'))):
        print("Ok")

if form.getvalue('getsavedserver'):
    group = common.checkAjaxInput(form.getvalue('getsavedserver'))
    term = common.checkAjaxInput(form.getvalue('term'))

    add_mod.get_saved_servers(group, term)

if form.getvalue('newsavedserver'):
    server = common.checkAjaxInput(form.getvalue('newsavedserver'))
    desc = common.checkAjaxInput(form.getvalue('newsavedserverdesc'))
    group = common.checkAjaxInput(form.getvalue('newsavedservergroup'))
    if server is None or group is None:
        print(error_mess)
    else:
        add_mod.create_saved_server(server, group, desc)

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
    users = sql.select_users()
    service_desc = sql.select_service(service)
    lang = roxywi_common.get_user_lang()

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
                               lang=lang)
    print(template)

if act == 'getSystemInfo':
    server_mod.show_system_info()

if act == 'updateSystemInfo':
    server_mod.update_system_info()

if act == 'server_is_up':
    server_ip = common.is_ip_or_dns(form.getvalue('server_is_up'))

    server_mod.server_is_up(server_ip)

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
    import modules.service.action as service_action

    cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
    user_uuid = cookie.get('uuid')
    server_id = common.checkAjaxInput(form.getvalue('server_id'))
    service = common.checkAjaxInput(form.getvalue('service'))

    service_action.check_service(serv, user_uuid, service)

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

if act == 'show_server_services':
    server_mod.show_server_services()

if form.getvalue('changeServerServicesId') is not None:
    server_mod.change_server_services()
