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
service = common.checkAjaxInput(form.getvalue('service'))
act = form.getvalue("act")
token = form.getvalue("token")

if any((
        form.getvalue('new_metrics'), form.getvalue('new_http_metrics'), form.getvalue('new_waf_metrics'), form.getvalue('new_nginx_metrics'),
        form.getvalue('new_apache_metrics'), form.getvalue('metrics_hapwi_ram'), form.getvalue('metrics_hapwi_cpu'), form.getvalue('getoption'),
        form.getvalue('getsavedserver'), form.getvalue('smon_history_check'))
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

if form.getvalue('getcert_raw') is not None and serv is not None:
    cert_id = common.checkAjaxInput(form.getvalue('getcert_raw'))
    add_mod.get_ssl_raw_cert(serv, cert_id)

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
    service_common.overview_backends(serv, service)

if form.getvalue('show_userlists'):
    add_mod.show_userlist(serv)

if act == "overviewHapservers":
    service_common.get_overview_last_edit(serv, service)

if act == "overview":
    import modules.roxywi.overview as roxy_overview

    roxy_overview.show_overview(serv)

if act == "overviewwaf":
    import modules.roxywi.waf as roxy_waf

    waf_service = service
    serv = common.checkAjaxInput(serv)
    roxy_waf.waf_overview(serv, waf_service)

if act == "overviewServers":
    server_id = common.checkAjaxInput(form.getvalue('id'))
    name = common.checkAjaxInput(form.getvalue('name'))

    service_common.overview_service(serv, server_id, name, service)

if act == "overviewServices":
    import modules.roxywi.overview as roxy_overview

    roxy_overview.show_services_overview()

if form.getvalue('action'):
    import modules.service.haproxy as service_haproxy

    service_haproxy.stat_page_action(serv)

if serv is not None and act == "stats":
    service_common.get_stat_page(serv, service)

if serv is not None and any((form.getvalue('show_log'), form.getvalue('rows1'), form.getvalue('viewlogs'))):
    import modules.roxywi.logs as roxywi_logs

    waf = 0
    rows = form.getvalue('show_log')
    service = service

    if form.getvalue('rows1'):
        rows = form.getvalue('rows1')
        service = 'apache_internal'
    elif form.getvalue('show_log'):
        waf = form.getvalue('waf')
    elif form.getvalue('viewlogs'):
        serv = form.getvalue('viewlogs')
        rows = form.getvalue('rows')
        service = 'internal'

    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minute = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minute1 = form.getvalue('minut1')

    if roxywi_common.check_user_group():
        out = roxywi_logs.show_roxy_log(serv=serv, rows=rows, waf=waf, grep=grep, hour=hour, minute=minute, hour1=hour1,
                                 minute1=minute1, service=service)
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
    master = form.getvalue('master')
    eth = form.getvalue('interface')
    eth_slave = form.getvalue('slave_interface')
    vrrp_ip = form.getvalue('vrrpip')
    syn_flood = form.getvalue('syn_flood')
    virt_server = int(form.getvalue('virt_server'))
    return_to_master = form.getvalue('return_to_master')
    haproxy = form.getvalue('hap')
    nginx = form.getvalue('nginx')
    router_id = form.getvalue('router_id')

    try:
        service_mod.keepalived_master_install(master, eth, eth_slave, vrrp_ip, virt_server, syn_flood, return_to_master,
                                              haproxy, nginx, router_id)
    except Exception as e:
        print(f'{e}')

if form.getvalue('master_slave'):
    master = form.getvalue('master_slave')
    slave = form.getvalue('slave')
    eth = form.getvalue('interface')
    eth_slave = form.getvalue('slave_interface')
    vrrp_ip = form.getvalue('vrrpip')
    syn_flood = form.getvalue('syn_flood')
    haproxy = form.getvalue('hap')
    nginx = form.getvalue('nginx')
    router_id = form.getvalue('router_id')

    try:
        service_mod.keepalived_slave_install(master, slave, eth, eth_slave, vrrp_ip, syn_flood, haproxy, nginx, router_id)
    except Exception as e:
        print(f'{e}')

if form.getvalue('masteradd'):
    try:
        service_mod.keepalived_masteradd()
    except Exception as e:
        print(f'{e}')

if form.getvalue('masteradd_slave'):
    try:
        service_mod.keepalived_slaveadd()
    except Exception as e:
        print(f'{e}')

if form.getvalue('master_slave_hap'):
    master = form.getvalue('master_slave_hap')
    slave = form.getvalue('slave')
    server = form.getvalue('server')
    docker = form.getvalue('docker')

    if server == 'master':
        try:
            service_mod.install_haproxy(master, server=server, docker=docker, m_or_s='master', master=master, slave=slave)
        except Exception as e:
            print(f'{e}')
    elif server == 'slave':
        try:
            service_mod.install_haproxy(slave, server=server, docker=docker, m_or_s='slave', master=master, slave=slave)
        except Exception as e:
            print(f'{e}')

if form.getvalue('master_slave_nginx'):
    master = form.getvalue('master_slave_nginx')
    slave = form.getvalue('slave')
    server = form.getvalue('server')
    docker = form.getvalue('docker')

    if server == 'master':
        try:
            service_mod.install_service(master, 'nginx', docker, server=server)
        except Exception as e:
            print(f'{e}')
    elif server == 'slave':
        try:
            service_mod.install_service(slave, 'nginx', docker, server=server)
        except Exception as e:
            print(f'{e}')

if form.getvalue('install_grafana'):
    try:
        service_mod.grafana_install()
    except Exception as e:
        print(f'{e}')

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

    server = common.is_ip_or_dns(form.getvalue('server'))
    rpath = common.checkAjaxInput(form.getvalue('rpath'))
    time = common.checkAjaxInput(form.getvalue('time'))
    backup_type = common.checkAjaxInput(form.getvalue('type'))
    rserver = common.checkAjaxInput(form.getvalue('rserver'))
    cred = int(form.getvalue('cred'))
    deljob = common.checkAjaxInput(form.getvalue('deljob'))
    update = common.checkAjaxInput(form.getvalue('backupupdate'))
    description = common.checkAjaxInput(form.getvalue('description'))

    try:
        backup_mod.backup(server, rpath, time, backup_type, rserver, cred, deljob, update, description)
    except Exception as e:
        print(e)

if any((form.getvalue('s3_backup_server'), form.getvalue('dels3job'))):
    import modules.service.backup as backup_mod

    server = common.is_ip_or_dns(form.getvalue('s3_backup_server'))
    s3_server = common.checkAjaxInput(form.getvalue('s3_server'))
    bucket = common.checkAjaxInput(form.getvalue('s3_bucket'))
    secret_key = common.checkAjaxInput(form.getvalue('s3_secret_key'))
    access_key = common.checkAjaxInput(form.getvalue('s3_access_key'))
    time = common.checkAjaxInput(form.getvalue('time'))
    deljob = common.checkAjaxInput(form.getvalue('dels3job'))
    description = common.checkAjaxInput(form.getvalue('description'))

    backup_mod.s3_backup(server, s3_server, bucket, secret_key, access_key, time, deljob, description)

if form.getvalue('git_backup'):
    import modules.service.backup as backup_mod

    server_id = form.getvalue('server')
    service_id = form.getvalue('git_service')
    git_init = form.getvalue('git_init')
    repo = form.getvalue('git_repo')
    branch = form.getvalue('git_branch')
    period = form.getvalue('time')
    cred = form.getvalue('cred')
    deljob = form.getvalue('git_deljob')
    description = form.getvalue('description')

    backup_mod.git_backup(server_id, service_id, git_init, repo, branch, period, cred, deljob, description)

if form.getvalue('install_service'):
    server_ip = common.is_ip_or_dns(form.getvalue('install_service'))
    docker = common.checkAjaxInput(form.getvalue('docker'))

    if service in ('nginx', 'apache'):
        try:
            service_mod.install_service(server_ip, service, docker)
        except Exception as e:
            print(e)
    else:
        print('warning: wrong service')

if form.getvalue('haproxyaddserv'):
    try:
        service_mod.install_haproxy(form.getvalue('haproxyaddserv'), syn_flood=form.getvalue('syn_flood'),
                                    hapver=form.getvalue('hapver'), docker=form.getvalue('docker'))
    except Exception as e:
        print(e)

if form.getvalue('installwaf'):
    if service == 'haproxy':
        try:
            service_mod.waf_install(common.checkAjaxInput(form.getvalue('installwaf')))
        except Exception as e:
            print(e)
    else:
        try:
            service_mod.waf_nginx_install(common.checkAjaxInput(form.getvalue('installwaf')))
        except Exception as e:
            print(e)

if form.getvalue('geoip_install'):
    try:
        service_mod.geoip_installation()
    except Exception as e:
        print(e)

if form.getvalue('update_roxy_wi'):
    import modules.roxywi.roxy as roxy

    service = form.getvalue('service')

    try:
        roxy.update_roxy_wi(service)
    except Exception as e:
        print(e)

if form.getvalue('metrics_waf'):
    metrics_waf = common.checkAjaxInput(form.getvalue('metrics_waf'))
    sql.update_waf_metrics_enable(metrics_waf, form.getvalue('enable'))

if form.getvalue('table_metrics'):
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

if form.getvalue('edit_map'):
    group = common.checkAjaxInput(form.getvalue('group'))
    map_name = common.checkAjaxInput(form.getvalue('edit_map'))

    add_mod.edit_map(map_name, group)

if form.getvalue('map_create'):
    map_name = common.checkAjaxInput(form.getvalue('map_create'))
    group = common.checkAjaxInput(form.getvalue('group'))

    try:
        add_mod.create_map(serv, map_name, group)
    except Exception as e:
        print(e)

if form.getvalue('map_save'):
    group = common.checkAjaxInput(form.getvalue('group'))
    map_save = common.checkAjaxInput(form.getvalue('map_save'))
    content = form.getvalue('content')
    action = common.checkAjaxInput(form.getvalue('map_restart'))

    add_mod.save_map(map_save, content, group, serv, action)

if form.getvalue('map_delete'):
    map_name = common.checkAjaxInput(form.getvalue('map_delete'))
    group = common.checkAjaxInput( form.getvalue('group'))
    server_id = common.checkAjaxInput( form.getvalue('serv'))

    add_mod.delete_map(map_name, group, server_id)

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

    try:
        roxywi_user.delete_user()
    except Exception as e:
        print(e)

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
    add_to_smon = common.checkAjaxInput(form.getvalue('add_to_smon'))
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

            if add_to_smon:
                import modules.tools.smon as smon_mod

                user_group = roxywi_common.get_user_group(id=1)
                smon_mod.create_smon(hostname, ip, 0, 1, 0, 0, hostname, desc, 0, 0, 0, 56, 'ping', 0, 0, user_group, 0)

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
    roxywi_common.logging(server_ip, f'The server {name} has been updated ', roxywi=1, login=1, keep_history=1, service=service)

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
        roxywi_common.logging(server_ip, f'The server {name} has been update', roxywi=1, login=1, keep_history=1, service='server')

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

    try:
        ssh_mod.upload_ssh_key(name, user_group, key)
    except Exception as e:
        print(e)

if form.getvalue('new_receiver'):
    import modules.alerting.alerting as alerting

    token = common.checkAjaxInput(form.getvalue('new_receiver'))
    receiver_name = common.checkAjaxInput(form.getvalue('receiver_name'))
    channel = common.checkAjaxInput(form.getvalue('chanel'))
    group = common.checkAjaxInput(form.getvalue('group_receiver'))
    page = common.checkAjaxInput(form.getvalue('page'))
    page = page.split("#")[0]

    alerting.add_receiver_channel(receiver_name, token, channel, group, page)

if form.getvalue('receiver_del') is not None:
    import modules.alerting.alerting as alerting

    channel_id = common.checkAjaxInput(form.getvalue('receiver_del'))
    receiver_name = common.checkAjaxInput(form.getvalue('receiver_name'))

    alerting.delete_receiver_channel(channel_id, receiver_name)

if form.getvalue('update_receiver_token') is not None:
    import modules.alerting.alerting as alerting

    receiver_name = common.checkAjaxInput(form.getvalue('receiver_name'))
    token = common.checkAjaxInput(form.getvalue('update_receiver_token'))
    channel = common.checkAjaxInput(form.getvalue('update_receiver_channel'))
    group = common.checkAjaxInput(form.getvalue('update_receiver_group'))
    user_id = common.checkAjaxInput(form.getvalue('id'))

    alerting.update_receiver_channel(receiver_name, token, channel, group, user_id)

if form.getvalue('updatesettings') is not None:
    settings = common.checkAjaxInput(form.getvalue('updatesettings'))
    val = common.checkAjaxInput(form.getvalue('val'))
    user_group = roxywi_common.get_user_group(id=1)
    if sql.update_setting(settings, val, user_group):
        roxywi_common.logging('Roxy-WI server', f'The {settings} setting has been changed to: {val}', roxywi=1, login=1)
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

if form.getvalue('newsmonname') is not None:
    import modules.tools.smon as smon_mod

    user_group = roxywi_common.get_user_group(id=1)
    name = common.checkAjaxInput(form.getvalue('newsmonname'))
    hostname = common.checkAjaxInput(form.getvalue('newsmon'))
    port = common.checkAjaxInput(form.getvalue('newsmonport'))
    enable = common.checkAjaxInput(form.getvalue('newsmonenable'))
    url = common.checkAjaxInput(form.getvalue('newsmonurl'))
    body = common.checkAjaxInput(form.getvalue('newsmonbody'))
    group = common.checkAjaxInput(form.getvalue('newsmongroup'))
    desc = common.checkAjaxInput(form.getvalue('newsmondescription'))
    telegram = common.checkAjaxInput(form.getvalue('newsmontelegram'))
    slack = common.checkAjaxInput(form.getvalue('newsmonslack'))
    pd = common.checkAjaxInput(form.getvalue('newsmonpd'))
    check_type = common.checkAjaxInput(form.getvalue('newsmonchecktype'))
    resolver = common.checkAjaxInput(form.getvalue('newsmonresserver'))
    record_type = common.checkAjaxInput(form.getvalue('newsmondns_record_type'))
    packet_size = common.checkAjaxInput(form.getvalue('newsmonpacket_size'))

    smon_mod.create_smon(name, hostname, port, enable, url, body, group, desc, telegram, slack, pd, packet_size, check_type, resolver, record_type, user_group)

if form.getvalue('smondel') is not None:
    import modules.tools.smon as smon_mod

    smon_mod.delete_smon()

if form.getvalue('showsmon') is not None:
    import modules.tools.smon as smon_mod

    smon_mod.show_smon()

if form.getvalue('updateSmonName') is not None:
    import modules.tools.smon as smon_mod

    smon_mod.update_smon()

if form.getvalue('smon_history_check') is not None:
    import modules.tools.smon as smon_mod

    server_id = int(form.getvalue('server_id'))
    check_id = int(form.getvalue('check_id'))
    smon_mod.history_metrics(server_id, check_id)

if form.getvalue('smon_history_statuses') is not None:
    import modules.tools.smon as smon_mod

    dashboard_id = int(form.getvalue('dashboard_id'))
    check_id = int(form.getvalue('check_id'))
    smon_mod.history_statuses(dashboard_id, check_id)

if form.getvalue('smon_cur_status') is not None:
    import modules.tools.smon as smon_mod

    dashboard_id = int(form.getvalue('dashboard_id'))
    check_id = int(form.getvalue('check_id'))
    smon_mod.history_cur_status(dashboard_id, check_id)

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
        print('error: Cannot save ovpn file')
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

    roxywi_common.logging("Roxy-WI server", f" has been uploaded a new ovpn file {ovpn_file}", roxywi=1, login=1)

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
        cmd = f'sudo openvpn3 session-start --config /tmp/{openvpn}.ovpn'
    elif action == 'restart':
        cmd = f'sudo openvpn3 session-manage --config /tmp/{openvpn}.ovpn --restart'
    elif action == 'disconnect':
        cmd = f'sudo openvpn3 session-manage --config /tmp/{openvpn}.ovpn --disconnect'
    else:
        print('error: wrong action')
        sys.exit()
    try:
        server_mod.subprocess_execute(cmd)
        print(f"success: The {openvpn} has been {action}ed")
        roxywi_common.logging(openvpn, f' The ovpn session has been {action}ed ', roxywi=1, login=1)
    except IOError as e:
        print(e.args[0])
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

if form.getvalue('scan_ports') is not None:
    serv_id = common.checkAjaxInput(form.getvalue('scan_ports'))
    server = sql.select_servers(id=serv_id)
    ip = ''

    for s in server:
        ip = s[2]

    cmd = f"sudo nmap -sS {ip} |grep -E '^[[:digit:]]'|sed 's/  */ /g'"
    cmd1 = f"sudo nmap -sS {ip} |head -5|tail -2"

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

if form.getvalue('new_provider_name'):
    import modules.provisioning.provider as provider

    provider.create_provider()

if form.getvalue('providerdel'):
    import modules.provisioning.provider as provider

    provider.delete_provider()

if form.getvalue('awsinit') or form.getvalue('doinit') or form.getvalue('gcoreinitserver'):
    import modules.provisioning.server as prov_server

    prov_server.init_server()

if form.getvalue('awsvars') or form.getvalue('awseditvars'):
    import modules.provisioning.aws as aws

    aws.create_vars()

if form.getvalue('dovars') or form.getvalue('doeditvars'):
    import modules.provisioning.do as do

    do.create_vars()

if form.getvalue('dovalidate') or form.getvalue('doeditvalidate'):
    import modules.provisioning.do as do

    do.validate()

if form.getvalue('doworkspace'):
    import modules.provisioning.do as do

    do.new_workspace()

if form.getvalue('doeditworkspace'):
    import modules.provisioning.do as do

    do.edit_workspace()

if form.getvalue('awsvalidate') or form.getvalue('awseditvalidate'):
    import modules.provisioning.aws as aws

    aws.validate()

if form.getvalue('awsworkspace'):
    import modules.provisioning.aws as aws

    aws.new_workspace()

if form.getvalue('awseditworkspace'):
    import modules.provisioning.aws as aws

    aws.edit_workspace()

if any((form.getvalue('awsprovisining'), form.getvalue('awseditingprovisining'), form.getvalue('doprovisining'),
        form.getvalue('doeditprovisining'), form.getvalue('gcoreprovisining'), form.getvalue('gcoreeditgprovisining'))):
    import modules.provisioning.server as prov_server

    prov_server.create_server()

if form.getvalue('provisiningdestroyserver'):
    import modules.provisioning.server as prov_server

    prov_server.destroy_server()

if form.getvalue('gcorevars') or form.getvalue('gcoreeditvars'):
    import modules.provisioning.gcore as gcore

    gcore.gcore_create_vars()

if form.getvalue('gcorevalidate') or form.getvalue('gcoreeditvalidate'):
    import modules.provisioning.gcore as gcore

    gcore.validate()

if form.getvalue('gcoreworkspace'):
    import modules.provisioning.gcore as gcore

    gcore.new_workspace()

if form.getvalue('gcoreeditworkspace'):
    import modules.provisioning.gcore as gcore

    gcore.edit_workspace()

if form.getvalue('editServerId'):
    import modules.provisioning.server as prov_server_mod

    prov_server_mod.edit_server()

if form.getvalue('edit_provider_id'):
    import modules.provisioning.provider as provider_mod

    provider = form.getvalue('provider_name')
    provider_id = form.getvalue('edit_provider_id')

    edit_functions = {
        'aws': provider_mod.edit_aws_provider,
        'do': provider_mod.edit_DO_provider,
        'gcore': provider_mod.edit_gcore_provider,
    }

    edit_functions[provider](provider_id)

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
    import modules.tools.checker as checker_mod

    checker_mod.load_checker()

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

    template = template.render(openvpn=openvpn, openvpn_sess=openvpn_sess, openvpn_configs=openvpn_configs)
    print(template)

if form.getvalue('check_receiver'):
    import modules.alerting.alerting as alerting

    channel_id = form.getvalue('receiver_channel_id')
    receiver_name = form.getvalue('receiver_name')
    alerting.check_receiver(channel_id, receiver_name)

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
    service_dockerized = common.checkAjaxInput(form.getvalue('serverSettingsDockerized'))
    service_restart = common.checkAjaxInput(form.getvalue('serverSettingsRestart'))
    server_ip = sql.select_server_ip_by_id(server_id)
    service_docker = f'Service {service.title()} has been flagged as a dockerized'
    service_systemd = f'Service {service.title()} has been flagged as a system service'
    disable_restart = f'Restart option is disabled for {service.title()} service'
    enable_restart = f'Restart option is disabled for {service.title()} service'

    if service == 'haproxy':
        if sql.insert_or_update_service_setting(server_id, service, 'haproxy_enterprise', haproxy_enterprise):
            print('Ok')
            if haproxy_enterprise == '1':
                roxywi_common.logging(server_ip, 'Service has been flagged as an Enterprise version', roxywi=1, login=1,
                              keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a community version', roxywi=1, login=1,
                              keep_history=1, service=service)

    if sql.insert_or_update_service_setting(server_id, service, 'dockerized', service_dockerized):
        print('Ok')
        if service_dockerized == '1':
            roxywi_common.logging(server_ip, service_docker, roxywi=1, login=1, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, service_systemd, roxywi=1, login=1, keep_history=1, service=service)

    if sql.insert_or_update_service_setting(server_id, service, 'restart', service_restart):
        print('Ok')
        if service_restart == '1':
            roxywi_common.logging(server_ip, disable_restart, roxywi=1, login=1, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, enable_restart, roxywi=1, login=1, keep_history=1, service=service)

if act == 'showListOfVersion':
    config_mod.list_of_versions(serv, service)

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

    service_action.check_service(serv, user_uuid, service)

if form.getvalue('show_sub_ovw'):
    import modules.roxywi.overview as roxywi_overview

    roxywi_overview.show_sub_ovw()

if form.getvalue('updateHaproxyCheckerSettings'):
    import modules.tools.checker as checker_mod

    checker_mod.update_haproxy_settings()

if form.getvalue('updateKeepalivedCheckerSettings'):
    import modules.tools.checker as checker_mod

    checker_mod.update_keepalived_settings()

if form.getvalue('updateServiceCheckerSettings'):
    import modules.tools.checker as checker_mod

    checker_mod.update_service_settings()

if act == 'show_server_services':
    server_mod.show_server_services()

if form.getvalue('changeServerServicesId') is not None:
    server_mod.change_server_services()
