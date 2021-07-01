#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import funct
import sql

form = funct.form
serv = form.getvalue("serv")
act = form.getvalue("act")

if (form.getvalue('new_metrics') or
        form.getvalue('new_http_metrics') or
        form.getvalue('new_waf_metrics') or
        form.getvalue('metrics_hapwi_ram') or
        form.getvalue('metrics_hapwi_cpu')):
    print('Content-type: application/json\n')
else:
    print('Content-type: text/html\n')

if act == "checkrestart":
    servers = sql.get_dick_permit(ip=serv)
    for server in servers:
        if server != "":
            print("ok")
            sys.exit()
    sys.exit()

if form.getvalue('alert_consumer') is None:
    if not sql.check_token_exists(form.getvalue("token")):
        print('error: Your token has been expired')
        sys.exit()

if form.getvalue('getcerts') is not None and serv is not None:
    cert_path = sql.get_setting('cert_path')
    commands = ["sudo ls -1t " + cert_path + " |grep -E 'pem|crt|key'"]
    try:
        funct.ssh_command(serv, commands, ip="1")
    except Exception as e:
        print('error: Cannot connect to the server: ' + e.args[0])

if form.getvalue('checkSshConnect') is not None and serv is not None:
    print(funct.ssh_command(serv, ["ls -1t"]))

if form.getvalue('getcert') is not None and serv is not None:
    cert_id = form.getvalue('getcert')
    cert_path = sql.get_setting('cert_path')
    commands = ["openssl x509 -in " + cert_path + "/" + cert_id + " -text"]
    try:
        funct.ssh_command(serv, commands, ip="1")
    except Exception as e:
        print('error: Cannot connect to the server ' + e.args[0])

if form.getvalue('delcert') is not None and serv is not None:
    cert_id = form.getvalue('delcert')
    cert_path = sql.get_setting('cert_path')
    commands = ["sudo rm -f " + cert_path + "/" + cert_id]
    try:
        funct.ssh_command(serv, commands, ip="1")
    except Exception as e:
        print('error: Cannot delete the certificate ' + e.args[0])

if serv and form.getvalue('ssl_cert'):
    cert_local_dir = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('ssl_local_path')
    cert_path = sql.get_setting('cert_path')

    if not os.path.exists(cert_local_dir):
        os.makedirs(cert_local_dir)

    if form.getvalue('ssl_name') is None:
        print('error: Please enter desired name')
    else:
        name = form.getvalue('ssl_name')

    try:
        with open(name, "w") as ssl_cert:
            ssl_cert.write(form.getvalue('ssl_cert'))
    except IOError as e:
        print('error: Can\'t save ssl keys file. Check ssh keys path in config ' + e.args[0])

    MASTERS = sql.is_master(serv)
    for master in MASTERS:
        if master[0] is not None:
            funct.upload(master[0], cert_path, name)
    try:
        error = funct.upload(serv, cert_path, name)
        if error == '':
            print('success: SSL file has been uploaded to %s into: %s%s' % (serv, cert_path, '/' + name))
    except Exception as e:
        funct.logging('localhost', e.args[0], haproxywi=1)
    try:
        os.system("mv %s %s" % (name, cert_local_dir))
    except OSError as e:
        funct.logging('localhost', e.args[0], haproxywi=1)

    funct.logging(serv, "add.py#ssl uploaded a new SSL cert %s" % name, haproxywi=1, login=1)

if form.getvalue('backend') is not None:
    funct.show_backends(serv)

if form.getvalue('ip_select') is not None:
    funct.show_backends(serv)

if form.getvalue('ipbackend') is not None and form.getvalue('backend_server') is None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    backend = form.getvalue('ipbackend')
    cmd = 'echo "show servers state"|nc %s %s |grep "%s" |awk \'{print $4}\'' % (serv, haproxy_sock_port, backend)
    output, stderr = funct.subprocess_execute(cmd)
    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        print(i + '<br>')

if form.getvalue('ipbackend') is not None and form.getvalue('backend_server') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    backend = form.getvalue('ipbackend')
    backend_server = form.getvalue('backend_server')
    cmd = 'echo "show servers state"|nc %s %s |grep "%s" |grep "%s" |awk \'{print $5":"$19}\' |head -1' % (serv, haproxy_sock_port, backend, backend_server)
    output, stderr = funct.subprocess_execute(cmd)
    print(output[0])

if form.getvalue('backend_ip') is not None:
    backend_backend = form.getvalue('backend_backend')
    backend_server = form.getvalue('backend_server')
    backend_ip = form.getvalue('backend_ip')
    backend_port = form.getvalue('backend_port')
    if form.getvalue('backend_ip') is None:
        print('error: Backend IP must be IP and not 0')
        sys.exit()

    if form.getvalue('backend_port') is None:
        print('error: Backend port must be integer and not 0')
        sys.exit()

    haproxy_sock_port = sql.get_setting('haproxy_sock_port')

    MASTERS = sql.is_master(serv)
    for master in MASTERS:
        if master[0] is not None:
            cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (backend_backend, backend_server, backend_ip, backend_port, backend_port, master[0], haproxy_sock_port)
            output, stderr = funct.subprocess_execute(cmd)
            print(output[0])

    cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (backend_backend, backend_server, backend_ip, backend_port, backend_port, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        print('error: ' + stderr[0])
    else:
        print(output[0])
        configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
        cfg = configs_dir + serv + "-" + funct.get_data('config') + ".cfg"

        error = funct.get_config(serv, cfg)
        cmd = 'string=`grep %s %s -n -A25 |grep "server %s" |head -1|awk -F"-" \'{print $1}\'` && sed -Ei "$( echo $string)s/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5]):[0-9]+/%s:%s/g" %s' % (backend_backend, cfg, backend_server, backend_ip, backend_port, cfg)
        output, stderr = funct.subprocess_execute(cmd)
        stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save='save')

if form.getvalue('maxconn_select') is not None:
    serv = form.getvalue('maxconn_select')
    funct.get_backends_from_config(serv, backends='frontend')

if form.getvalue('maxconn_frontend') is not None:
    frontend = form.getvalue('maxconn_frontend')
    maxconn = form.getvalue('maxconn_int')
    if form.getvalue('maxconn_int') is None:
        print('error: Maxconn must be integer and not 0')
        sys.exit()

    haproxy_sock_port = sql.get_setting('haproxy_sock_port')

    MASTERS = sql.is_master(serv)
    for master in MASTERS:
        if master[0] is not None:
            if frontend == 'global':
                cmd = 'echo "set maxconn %s %s" |nc %s %s' % (frontend, maxconn, master[0], haproxy_sock_port)
            else:
                cmd = 'echo "set maxconn frontend %s %s" |nc %s %s' % (frontend, maxconn, master[0], haproxy_sock_port)
            output, stderr = funct.subprocess_execute(cmd)

    if frontend == 'global':
        cmd = 'echo "set maxconn %s %s" |nc %s %s' % (frontend, maxconn, serv, haproxy_sock_port)
    else:
        cmd = 'echo "set maxconn frontend %s %s" |nc %s %s' % (frontend, maxconn, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        print(stderr[0])
    elif output[0] == '':
        configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
        cfg = configs_dir + serv + "-" + funct.get_data('config') + ".cfg"

        error = funct.get_config(serv, cfg)
        cmd = 'string=`grep %s %s -n -A5 |grep maxcon -n |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` && sed -Ei "$( echo $string)s/[0-9]+/%s/g" %s' % (frontend, cfg, maxconn, cfg)
        output, stderr = funct.subprocess_execute(cmd)
        stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save='save')
        print('success: Maxconn for %s has been set to %s ' % (frontend, maxconn))
    else:
        print('error: ' + output[0])

if form.getvalue('table_serv_select') is not None:
    print(funct.get_all_stick_table())

if form.getvalue('table_select') is not None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True,
                      extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
    table = form.getvalue('table_select')

    if table == 'All':
        template = env.get_template('/stick_tables.html')
        tables = funct.get_all_stick_table()
        table = []
        for t in tables.split(','):
            if t != '':
                table_id = []
                tables_head = []
                tables_head1, table1 = funct.get_stick_table(t)
                table_id.append(tables_head1)
                table_id.append(table1)
                table.append(table_id)

        template = template.render(table=table)
    else:
        template = env.get_template('/stick_table.html')
        tables_head, table = funct.get_stick_table(table)
        template = template.render(tables_head=tables_head, table=table)

    print(template)

if form.getvalue('ip_for_delete') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    ip = form.getvalue('ip_for_delete')
    table = form.getvalue('table_for_delete')

    cmd = 'echo "clear table %s key %s" |nc %s %s' % (table, ip, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    if stderr[0] != '':
        print('error: ' + stderr[0])

if form.getvalue('table_for_clear') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    table = form.getvalue('table_for_clear')

    cmd = 'echo "clear table %s " |nc %s %s' % (table, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    if stderr[0] != '':
        print('error: ' + stderr[0])

if form.getvalue('list_serv_select') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    cmd = 'echo "show acl"|nc %s %s |grep "loaded from" |awk \'{print $1,$2}\'' % (serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    print(output)

if form.getvalue('list_select_id') is not None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
                      extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
    template = env.get_template('ajax/list.html')
    list_id = form.getvalue('list_select_id')
    list_name = form.getvalue('list_select_name')

    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    cmd = 'echo "show acl #%s"|nc %s %s' % (list_id, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)

    template = template.render(list=output, list_id=list_id, list_name=list_name)
    print(template)

if form.getvalue('list_id_for_delete') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    lists_path = sql.get_setting('lists_path')
    fullpath = funct.get_config_var('main', 'fullpath')
    ip_id = form.getvalue('list_ip_id_for_delete')
    ip = form.getvalue('list_ip_for_delete')
    list_id = form.getvalue('list_id_for_delete')
    list_name = form.getvalue('list_name')
    user_group = funct.get_user_group(id=1)

    cmd = "sed -i 's!%s$!!' %s/%s/%s/%s" % (ip, fullpath, lists_path, user_group, list_name)
    cmd1 = "sed -i '/^$/d' %s/%s/%s/%s" % (fullpath, lists_path, user_group, list_name)
    output, stderr = funct.subprocess_execute(cmd)
    output1, stderr1 = funct.subprocess_execute(cmd1)
    if output:
        print('error: ' + str(output))
    if stderr:
        print('error: ' + str(stderr))
    if output1:
        print('error: ' + str(output1))
    if stderr1:
        print('error: ' + str(stderr1))

    cmd = 'echo "del acl #%s #%s" |nc %s %s' % (list_id, ip_id, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    if output[0] != '':
        print('error: ' + output[0])
    if stderr[0] != '':
        print('error: ' + stderr[0])

if form.getvalue('list_ip_for_add') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    lists_path = sql.get_setting('lists_path')
    fullpath = funct.get_config_var('main', 'fullpath')
    ip = form.getvalue('list_ip_for_add')
    list_id = form.getvalue('list_id_for_add')
    list_name = form.getvalue('list_name')
    user_group = funct.get_user_group(id=1)

    cmd = 'echo "%s" >> %s/%s/%s/%s' % (ip, fullpath, lists_path, user_group, list_name)
    output, stderr = funct.subprocess_execute(cmd)
    if output:
        print('error: ' + str(output))
    if stderr:
        print('error: ' + str(stderr))

    cmd = 'echo "add acl #%s %s" |nc %s %s' % (list_id, ip, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    if output[0]:
        print('error: ' + output[0])
    if stderr:
        print('error: ' + stderr[0])

if form.getvalue('sessions_select') is not None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True,
                      extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'], trim_blocks=True, lstrip_blocks=True)
    serv = form.getvalue('sessions_select')
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')

    cmd = 'echo "show sess" |nc %s %s' % (serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)

    template = env.get_template('/sessions_table.html')
    template = template.render(sessions=output)

    print(template)

if form.getvalue('sessions_select_show') is not None:
    serv = form.getvalue('sessions_select_show')
    sess_id = form.getvalue('sessions_select_id')
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')

    cmd = 'echo "show sess %s" |nc %s %s' % (sess_id, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)

    output, stderr = funct.subprocess_execute(cmd)

    if stderr:
        print('error: ' + stderr[0])
    else:
        for o in output:
            print(o + '<br />')

if form.getvalue('session_delete_id') is not None:
    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    sess_id = form.getvalue('session_delete_id')

    cmd = 'echo "shutdown session %s" |nc %s %s' % (sess_id, serv, haproxy_sock_port)
    output, stderr = funct.subprocess_execute(cmd)
    if output[0] != '':
        print('error: ' + output[0])
    if stderr[0] != '':
        print('error: ' + stderr[0])

if form.getvalue("change_pos") is not None:
    pos = form.getvalue('change_pos')
    sql.update_server_pos(pos, serv)

if form.getvalue('ip') is not None and serv is not None:
    commands = ["sudo ip a |grep inet |egrep -v  '::1' |awk '{ print $2 }' |awk -F'/' '{ print $1 }'"]
    funct.ssh_command(serv, commands, ip="1")

if form.getvalue('showif'):
    commands = ["sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}'  |awk -F':' '{print $1}'"]
    funct.ssh_command(serv, commands, ip="1")

if form.getvalue('action_hap') is not None and serv is not None:
    action = form.getvalue('action_hap')

    if funct.check_haproxy_config(serv):
        haproxy_enterprise = sql.get_setting('haproxy_enterprise')
        if haproxy_enterprise == '1':
            haproxy_service_name = "hapee-2.0-lb"
        else:
            haproxy_service_name = "haproxy"

        commands = ["sudo systemctl %s %s" % (action, haproxy_service_name)]
        funct.ssh_command(serv, commands)
        funct.logging(serv, 'HAProxy has been ' + action + 'ed', haproxywi=1, login=1)
        print("success: HAProxy has been %s" % action)
    else:
        print("error: Bad config, check please")

if form.getvalue('action_nginx') is not None and serv is not None:
    action = form.getvalue('action_nginx')

    commands = ["sudo systemctl %s nginx" % action]
    funct.ssh_command(serv, commands)
    funct.logging(serv, 'Nginx has been ' + action + 'ed', haproxywi=1, login=1)
    print("success: Nginx has been %s" % action)

if form.getvalue('action_keepalived') is not None and serv is not None:
    action = form.getvalue('action_keepalived')

    commands = ["sudo systemctl %s keepalived" % action]
    funct.ssh_command(serv, commands)
    funct.logging(serv, 'Keepalived has been ' + action + 'ed', haproxywi=1, login=1)
    print("success: Keepalived has been %s" % action)

if form.getvalue('action_waf') is not None and serv is not None:
    serv = form.getvalue('serv')
    action = form.getvalue('action_waf')
    funct.logging(serv, 'WAF service was ' + action + 'ed', haproxywi=1, login=1)
    commands = ["sudo systemctl %s waf" % action]
    funct.ssh_command(serv, commands)

if form.getvalue('action_service') is not None:
    action = form.getvalue('action_service')
    if action == 'stop':
        cmd = "sudo systemctl disable %s --now" % serv
    elif action == "start":
        cmd = "sudo systemctl enable %s --now" % serv
    elif action == "restart":
        cmd = "sudo systemctl restart %s --now" % serv
    output, stderr = funct.subprocess_execute(cmd)
    funct.logging('localhost', ' The service ' + serv + ' was ' + action + 'ed', haproxywi=1, login=1)

if act == "overviewHapserverBackends":
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('haproxyservers_backends.html')
    service = form.getvalue('service')

    if service == 'haproxy':
        configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
        format_file = 'cfg'
    elif service == 'nginx':
        configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
        format_file = 'conf'
    elif service == 'keepalived':
        configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
        format_file = 'conf'

    try:
        sections = funct.get_sections(configs_dir + funct.get_files(dir=configs_dir, format=format_file)[0], service=service)
    except Exception as e:
        funct.logging('localhost', str(e), haproxywi=1)

        try:
            cfg = configs_dir + serv + "-" + funct.get_data('config') + '.' + format_file
        except Exception as e:
            funct.logging('localhost', ' Cannot generate cfg path ' + str(e), haproxywi=1)
        try:
            if service == 'nginx':
                error = funct.get_config(serv, cfg, nginx=1)
            elif service == 'keepalived':
                error = funct.get_config(serv, cfg, keepalived=1)
            else:
                error = funct.get_config(serv, cfg)
        except Exception as e:
            funct.logging('localhost', ' Cannot download config ' + str(e), haproxywi=1)
        try:
            sections = funct.get_sections(cfg, service=service)
        except Exception as e:
            funct.logging('localhost', ' Cannot get sections from config file ' + str(e), haproxywi=1)
            sections = 'Cannot get backends'

    template = template.render(backends=sections, serv=serv, service=service)
    print(template)

if form.getvalue('show_userlists'):
    configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
    format_file = 'cfg'

    try:
        sections = funct.get_userlists(configs_dir + funct.get_files(dir=configs_dir, format=format_file)[0])
    except Exception as e:
        funct.logging('localhost', str(e), haproxywi=1)
        try:
            cfg = configs_dir + serv + "-" + funct.get_data('config') + '.' + format_file
        except Exception as e:
            funct.logging('localhost', ' Cannot generate cfg path ' + str(e), haproxywi=1)
        try:
            error = funct.get_config(serv, cfg)
        except Exception as e:
            funct.logging('localhost', ' Cannot download config ' + str(e), haproxywi=1)
        try:
            sections = funct.get_userlists(cfg)
        except Exception as e:
            funct.logging('localhost', ' Cannot get Userlists from config file ' + str(e), haproxywi=1)
            sections = 'error: Cannot get Userlists'

    print(sections)

if act == "overviewHapservers":
    if form.getvalue('service') == 'nginx':
        config_path = sql.get_setting('nginx_config_path')
    else:
        config_path = sql.get_setting('haproxy_config_path')
    commands = ["ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % config_path]
    try:
        print(funct.ssh_command(serv, commands))
    except Exception as e:
        print('error: Cannot get last date ' + str(e))

if act == "overview":
    import asyncio
    import http.cookies
    from jinja2 import Environment, FileSystemLoader

    async def async_get_overview(serv1, serv2):
        haproxy = sql.select_haproxy(serv2)
        keepalived = sql.select_keealived(serv2)
        nginx = sql.select_nginx(serv2)
        waf = sql.select_waf_servers(serv2)
        haproxy_process = ''
        keepalived_process = ''
        nginx_process = ''
        waf_process = ''

        if haproxy == 1:
            cmd = 'echo "show info" |nc %s %s -w 1|grep -e "Process_num"' % (serv2, sql.get_setting('haproxy_sock_port'))
            haproxy_process = funct.server_status(funct.subprocess_execute(cmd))

        if keepalived == 1:
            command = ["ps ax |grep keepalived|grep -v grep|wc -l"]
            keepalived_process = funct.ssh_command(serv2, command)

        if nginx == 1:
            # command = ["ps ax |grep nginx:|grep -v grep|wc -l"]
            # nginx_process = funct.ssh_command(serv2, command)
            nginx_cmd = 'echo "something" |nc %s %s -w 1' % (serv2, sql.get_setting('nginx_stats_port'))
            nginx_process = funct.server_status(funct.subprocess_execute(nginx_cmd))

        if len(waf) == 1:
            commands2 = ["ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"]
            waf_process = funct.ssh_command(serv2, commands2)

        server_status = (serv1,
                         serv2,
                         haproxy_process,
                         sql.select_servers(server=serv2, keep_alive=1),
                         waf_process,
                         waf,
                         keepalived,
                         keepalived_process,
                         nginx,
                         nginx_process)
        return server_status


    async def get_runner_overview():
        env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True,
                          extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])

        servers = []
        template = env.get_template('overview.html')
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_id = cookie.get('uuid')
        futures = [async_get_overview(server[1], server[2]) for server in sql.select_servers(server=serv)]
        for i, future in enumerate(asyncio.as_completed(futures)):
            result = await future
            servers.append(result)
        servers_sorted = sorted(servers, key=funct.get_key)
        template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value))
        print(template)


    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(get_runner_overview())
    ioloop.close()

if act == "overviewwaf":
    import asyncio
    import http.cookies
    from jinja2 import Environment, FileSystemLoader

    async def async_get_overviewWaf(serv1, serv2):
        haproxy_path = sql.get_setting('haproxy_dir')
        commands0 = ["ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"]
        commands1 = ["cat %s/waf/modsecurity.conf  |grep SecRuleEngine |grep -v '#' |awk '{print $2}'" % haproxy_path]

        server_status = (serv1, serv2,
                         funct.ssh_command(serv2, commands0),
                         funct.ssh_command(serv2, commands1).strip(),
                         sql.select_waf_metrics_enable_server(serv2))
        return server_status


    async def get_runner_overviewWaf():
        env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True,
                          extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
        template = env.get_template('overivewWaf.html')

        servers = []
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_id = cookie.get('uuid')
        futures = [async_get_overviewWaf(server[1], server[2]) for server in sql.select_servers(server=serv)]
        for i, future in enumerate(asyncio.as_completed(futures)):
            result = await future
            servers.append(result)
        servers_sorted = sorted(servers, key=funct.get_key)
        template = template.render(service_status=servers_sorted, role=sql.get_user_role_by_uuid(user_id.value))
        print(template)


    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(get_runner_overviewWaf())
    ioloop.close()

if act == "overviewServers":
    import asyncio


    async def async_get_overviewServers(serv1, serv2, service):
        if service == 'haproxy':
            cmd = 'echo "show info" |nc %s %s -w 1|grep -e "node\|Nbproc\|Maxco\|MB\|Nbthread"' % (serv2, sql.get_setting('haproxy_sock_port'))
            out = funct.subprocess_execute(cmd)
            return_out = ""

            for k in out:
                if "Ncat:" not in k:
                    for r in k:
                        return_out += r
                        return_out += "<br />"
                else:
                    return_out = "Cannot connect to HAProxy"
        else:
            return_out = ''

        server_status = (serv1, serv2, return_out)
        return server_status


    async def get_runner_overviewServers(**kwargs):
        import http.cookies
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader('templates/ajax'),
                          extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])
        template = env.get_template('overviewServers.html')

        servers = []
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_id = cookie.get('uuid')
        role = sql.get_user_role_by_uuid(user_id.value)
        futures = [async_get_overviewServers(kwargs.get('server1'), kwargs.get('server2'), kwargs.get('service'))]

        for i, future in enumerate(asyncio.as_completed(futures)):
            result = await future
            servers.append(result)
        servers_sorted = sorted(servers, key=funct.get_key)
        template = template.render(service_status=servers_sorted, role=role, id=kwargs.get('id'), service_page=service)
        print(template)


    server_id = form.getvalue('id')
    name = form.getvalue('name')
    service = form.getvalue('service')
    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(get_runner_overviewServers(server1=name, server2=serv, id=server_id, service=service))
    ioloop.close()

if form.getvalue('action'):
    import requests

    haproxy_user = sql.get_setting('stats_user')
    haproxy_pass = sql.get_setting('stats_password')
    stats_port = sql.get_setting('stats_port')
    stats_page = sql.get_setting('stats_page')

    postdata = {
        'action': form.getvalue('action'),
        's': form.getvalue('s'),
        'b': form.getvalue('b')
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 5.1; rv:20.0) Gecko/20100101 Firefox/20.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate'
    }

    q = requests.post('http://' + serv + ':' + stats_port + '/' + stats_page,
                      headers=headers,
                      data=postdata,
                      auth=(haproxy_user, haproxy_pass))

if serv is not None and act == "stats":
    import requests

    if form.getvalue('service') == 'nginx':
        haproxy_user = sql.get_setting('nginx_stats_user')
        haproxy_pass = sql.get_setting('nginx_stats_password')
        stats_port = sql.get_setting('nginx_stats_port')
        stats_page = sql.get_setting('nginx_stats_page')
    else:
        haproxy_user = sql.get_setting('stats_user')
        haproxy_pass = sql.get_setting('stats_password')
        stats_port = sql.get_setting('stats_port')
        stats_page = sql.get_setting('stats_page')
    try:
        response = requests.get('http://%s:%s/%s' % (serv, stats_port, stats_page), auth=(haproxy_user, haproxy_pass))
    except requests.exceptions.ConnectTimeout:
        print('error: Oops. Connection timeout occurred!')
    except requests.exceptions.ReadTimeout:
        print('error: Oops. Read timeout occurred')
    except requests.exceptions.HTTPError as errh:
        print("error: Http Error:", errh)
    except requests.exceptions.ConnectionError as errc:
        print('error: Error Connecting: %s' % errc)
    except requests.exceptions.Timeout as errt:
        print("error: Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("error: OOps: Something Else", err)

    data = response.content
    if form.getvalue('service') == 'nginx':
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
        template = env.get_template('ajax/nginx_stats.html')

        servers_with_status = list()
        h = ()
        out1 = []
        for k in data.decode('utf-8').split():
            out1.append(k)
        h = (out1,)
        servers_with_status.append(h)

        template = template.render(out=servers_with_status)
        print(template)
    else:
        print(data.decode('utf-8'))

if serv is not None and form.getvalue('rows') is not None:
    rows = form.getvalue('rows')
    waf = form.getvalue('waf')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    service = form.getvalue('service')
    out = funct.show_haproxy_log(serv, rows=rows, waf=waf, grep=grep, hour=hour, minut=minut, hour1=hour1,
                                 minut1=minut1, service=service)
    print(out)

if serv is not None and form.getvalue('rows1') is not None:
    rows = form.getvalue('rows1')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    out = funct.show_haproxy_log(serv, rows=rows, waf='0', grep=grep, hour=hour, minut=minut, hour1=hour1,
                                 minut1=minut1, service='apache')
    print(out)

if form.getvalue('viewlogs') is not None:
    viewlog = form.getvalue('viewlogs')
    rows = form.getvalue('rows')
    grep = form.getvalue('grep')
    hour = form.getvalue('hour')
    minut = form.getvalue('minut')
    hour1 = form.getvalue('hour1')
    minut1 = form.getvalue('minut1')
    if funct.check_user_group():
        out = funct.show_haproxy_log(serv=viewlog, rows=rows, waf='0', grep=grep, hour=hour, minut=minut, hour1=hour1,
                                     minut1=minut1, service='internal')
    print(out)

if serv is not None and act == "showMap":
    import networkx as nx
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    stats_port = sql.get_setting('stats_port')
    haproxy_config_path = sql.get_setting('haproxy_config_path')
    hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
    date = funct.get_data('config')
    cfg = hap_configs_dir + serv + "-" + date + ".cfg"

    print('<center>')
    print("<h4>Map from %s</h4><br />" % serv)

    G = nx.DiGraph()

    error = funct.get_config(serv, cfg)
    if error:
        print(error)
    try:
        conf = open(cfg, "r")
    except IOError:
        print('error: Can\'t read import config file')

    node = ""
    line_new2 = [1, ""]
    i, k = 800, 800
    j, m = 0, 0
    for line in conf:
        if line.startswith('listen') or line.startswith('frontend'):
            if "stats" not in line:
                node = line
                i = i - 750
        if line.find("backend") == 0:
            node = line
            i = i - 700
            G.add_node(node, pos=(k, i), label_pos=(k, i + 100))

        if "bind" in line or (line.startswith('listen') and ":" in line) or (
                line.startswith('frontend') and ":" in line):
            try:
                bind = line.split(":")
                if stats_port not in bind[1]:
                    bind[1] = bind[1].strip(' ')
                    bind = bind[1].split("crt")
                    node = node.strip(' \t\n\r')
                    node = node + ":" + bind[0]
                    G.add_node(node, pos=(k, i), label_pos=(k, i + 100))
            except Exception:
                pass

        if "server " in line or "use_backend" in line or "default_backend" in line and "stats" not in line and "#" not in line:
            if "timeout" not in line and "default-server" not in line and "#" not in line and "stats" not in line:
                i = i - 1050
                j = j + 1
                if "check" in line:
                    line_new = line.split("check")
                else:
                    line_new = line.split("if ")
                if "server" in line:
                    line_new1 = line_new[0].split("server")
                    line_new[0] = line_new1[1]
                    line_new2 = line_new[0].split(":")
                    line_new[0] = line_new2[0]

                line_new[0] = line_new[0].strip(' \t\n\r')

                try:
                    backend_server_port = line_new2[1].strip(' \t\n\r')
                    backend_server_port = 'port: ' + backend_server_port
                except Exception as e:
                    backend_server_port = ''

                if j % 2 == 0:
                    G.add_node(line_new[0], pos=(k + 230, i - 335), label_pos=(k + 225, i - 180))
                else:
                    G.add_node(line_new[0], pos=(k - 230, i - 0), label_pos=(k - 225, i + 180))

                if line_new2[1] != "":
                    G.add_edge(node, line_new[0], port=backend_server_port)
                else:
                    G.add_edge(node, line_new[0], port='')

    os.system("/bin/rm -f " + cfg)

    pos = nx.get_node_attributes(G, 'pos')
    pos_label = nx.get_node_attributes(G, 'label_pos')
    edge_labels = nx.get_edge_attributes(G, 'port')

    try:
        plt.figure(10, figsize=(10, 15))
        nx.draw(G, pos, with_labels=False, font_weight='bold', width=3, alpha=0.1, linewidths=5)
        nx.draw_networkx_nodes(G, pos, node_color="skyblue", node_size=100, alpha=0.8, node_shape="p")
        nx.draw_networkx_labels(G, pos=pos_label, alpha=1, font_color="green", font_size=10)
        nx.draw_networkx_edges(G, pos, width=0.5, alpha=0.5, edge_color="#5D9CEB", arrows=False)
        nx.draw_networkx_edge_labels(G, pos, label_pos=0.5, font_color="blue", edge_labels=edge_labels, font_size=8)

        plt.savefig("map.png")
        plt.show()
    except Exception as e:
        print(str(e))

    cmd = "rm -f " + os.path.dirname(os.getcwd()) + "/map*.png && mv map.png " + os.path.dirname(
        os.getcwd()) + "/map" + date + ".png"
    output, stderr = funct.subprocess_execute(cmd)
    print(stderr)

    print('<img src="/map%s.png" alt="map">' % date)

if form.getvalue('servaction') is not None:
    server_state_file = sql.get_setting('server_state_file')
    haproxy_sock = sql.get_setting('haproxy_sock')
    enable = form.getvalue('servaction')
    backend = form.getvalue('servbackend')
    cmd = 'echo "%s %s" |sudo socat stdio %s' % (enable, backend, haproxy_sock)

    if form.getvalue('save') == "on":
        save_command = 'echo "show servers state" | sudo socat %s stdio > %s' % (haproxy_sock, server_state_file)
        command = [cmd + ';' + save_command]
    else:
        command = [cmd]

    if enable != "show":
        print(
            '<center><h3>You %s %s on HAProxy %s. <a href="viewsttats.py?serv=%s" title="View stat" target="_blank">Look it</a> or <a href="runtimeapi.py" title="Runtime API">Edit something else</a></h3><br />' % (enable, backend, serv, serv))

    print(funct.ssh_command(serv, command, show_log="1"))
    action = 'runtimeapi.py ' + enable + ' ' + backend
    funct.logging(serv, action)

if act == "showCompareConfigs":
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_compare_configs.html')
    left = form.getvalue('left')
    right = form.getvalue('right')

    if form.getvalue('service') == 'nginx':
        return_files = funct.get_files(funct.get_config_var('configs', 'nginx_save_configs_dir'), 'conf')
    elif form.getvalue('service') == 'keepalived':
        return_files = funct.get_files(funct.get_config_var('configs', 'kp_save_configs_dir'), 'conf')
    else:
        return_files = funct.get_files()

    template = template.render(serv=serv, right=right, left=left, return_files=return_files)
    print(template)

if serv is not None and form.getvalue('right') is not None:
    from jinja2 import Environment, FileSystemLoader

    left = form.getvalue('left')
    right = form.getvalue('right')
    if form.getvalue('service') == 'nginx':
        configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
    elif form.getvalue('service') == 'keepalived':
        configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
    else:
        configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
    cmd = 'diff -pub %s%s %s%s' % (configs_dir, left, configs_dir, right)
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
                      extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"])
    template = env.get_template('ajax/compare.html')

    output, stderr = funct.subprocess_execute(cmd)
    template = template.render(stdout=output)

    print(template)
    print(stderr)

if serv is not None and act == "configShow":
    import http.cookies

    cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
    user_uuid = cookie.get('uuid')
    role_id = sql.get_user_role_by_uuid(user_uuid.value)
    service = form.getvalue('service')

    if service == 'keepalived':
        configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
        cfg = '.conf'
    elif service == 'nginx':
        configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
        cfg = '.conf'
    else:
        configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
        cfg = '.cfg'

    if form.getvalue('configver') is None:
        cfg = configs_dir + serv + "-" + funct.get_data('config') + cfg
        if service == 'nginx':
            funct.get_config(serv, cfg, nginx=1)
        elif service == 'keepalived':
            funct.get_config(serv, cfg, keepalived=1)
        else:
            funct.get_config(serv, cfg)
    else:
        cfg = configs_dir + form.getvalue('configver')
    try:
        conf = open(cfg, "r")
    except IOError:
        print('<div class="alert alert-danger">Can\'t read config file</div>')
        
    is_serv_protected = sql.is_serv_protected(serv)

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True, trim_blocks=True, lstrip_blocks=True,
                      extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"])
    template = env.get_template('config_show.html')

    template = template.render(conf=conf,
                               serv=serv,
                               configver=form.getvalue('configver'),
                               role=role_id,
                               service=service,
                               is_serv_protected=is_serv_protected)
    print(template)

    if form.getvalue('configver') is None:
        os.system("/bin/rm -f " + cfg)

if form.getvalue('master'):
    master = form.getvalue('master')
    slave = form.getvalue('slave')
    ETH = form.getvalue('interface')
    IP = form.getvalue('vrrpip')
    syn_flood = form.getvalue('syn_flood')
    virt_server = form.getvalue('virt_server')
    haproxy = form.getvalue('hap')
    nginx = form.getvalue('nginx')
    script = "install_keepalived.sh"
    fullpath = funct.get_config_var('main', 'fullpath')
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(master)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=master)
    for server in servers:
        ssh_port = str(server[10])

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    os.system("cp scripts/%s ." % script)

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " SSH_PORT=" + ssh_port +
                " ETH=" + ETH + " IP=" + str(IP) + " MASTER=MASTER" + " SYN_FLOOD=" + syn_flood + " HOST=" + str(master) +
                " USER=" + str(ssh_user_name) + " PASS=" + str(ssh_user_password) + " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'master Keepalived')

    sql.update_keepalived(master)

    if virt_server is not None:
        group_id = sql.get_group_id_by_server_ip(master)
        cred_id = sql.get_cred_id_by_server_ip(master)
        hostname = sql.get_hostname_by_server_ip(master)
        sql.add_server(hostname+'-VIP', IP, group_id, '1', '1', '1', cred_id, ssh_port, 'VRRP IP for '+master, haproxy, nginx, '0')

if form.getvalue('master_slave'):
    master = form.getvalue('master')
    slave = form.getvalue('slave')
    ETH = form.getvalue('interface')
    IP = form.getvalue('vrrpip')
    syn_flood = form.getvalue('syn_flood')
    script = "install_keepalived.sh"
    fullpath = funct.get_config_var('main', 'fullpath')
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(slave)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=slave)
    for server in servers:
        ssh_port = str(server[10])

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    os.system("cp scripts/%s ." % script)

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " SSH_PORT=" + ssh_port +
                " ETH=" + ETH + " IP=" + IP + " MASTER=BACKUP" + " HOST=" + str(slave) +
                " USER=" + str(ssh_user_name) + " PASS=" + str(ssh_user_password) + " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'slave Keepalived')

    os.system("rm -f %s" % script)
    sql.update_server_master(master, slave)
    sql.update_keepalived(slave)

if form.getvalue('masteradd'):
    master = form.getvalue('masteradd')
    slave = form.getvalue('slaveadd')
    ETH = form.getvalue('interfaceadd')
    IP = form.getvalue('vrrpipadd')
    kp = form.getvalue('kp')
    script = "install_keepalived.sh"
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(master)

    if ssh_enable == 0:
        ssh_key_name = ''

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    os.system("cp scripts/%s ." % script)

    servers = sql.select_servers(server=master)
    for server in servers:
        ssh_port = str(server[10])

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv +
                " SSH_PORT=" + ssh_port + " ETH=" + ETH +
                " IP=" + str(IP) + " MASTER=MASTER" + " RESTART=" + kp + " ADD_VRRP=1 HOST=" + str(master) +
                " USER=" + str(ssh_user_name) + " PASS=" + str(ssh_user_password) + " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'master VRRP address')

if form.getvalue('masteradd_slave'):
    master = form.getvalue('masteradd_slave')
    slave = form.getvalue('slaveadd')
    ETH = form.getvalue('interfaceadd')
    IP = form.getvalue('vrrpipadd')
    kp = form.getvalue('kp')
    script = "install_keepalived.sh"
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(slave)

    if ssh_enable == 0:
        ssh_key_name = ''

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    os.system("cp scripts/%s ." % script)

    servers = sql.select_servers(server=slave)
    for server in servers:
        ssh_port = str(server[10])

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv +
                " SSH_PORT=" + ssh_port + " ETH=" + ETH +
                " IP=" + str(IP) + " MASTER=BACKUP" + " RESTART=" + kp + " ADD_VRRP=1 HOST=" + str(slave) +
                " USER=" + str(ssh_user_name) + " PASS=" + str(ssh_user_password) + " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'slave VRRP address')

    os.system("rm -f %s" % script)

if form.getvalue('master_slave_hap'):
    master = form.getvalue('master_slave_hap')
    slave = form.getvalue('slave')
    server = form.getvalue('server')

    if server == 'master':
        funct.install_haproxy(master, server=server)
    elif server == 'slave':
        funct.install_haproxy(slave, server=server)

if form.getvalue('master_slave_nginx'):
    master = form.getvalue('master_slave_nginx')
    slave = form.getvalue('slave')
    server = form.getvalue('server')

    if server == 'master':
        funct.install_nginx(master, server=server)
    elif server == 'slave':
        funct.install_nginx(slave, server=server)

if form.getvalue('install_grafana'):
    script = "install_grafana.sh"
    proxy = sql.get_setting('proxy')

    os.system("cp scripts/%s ." % script)

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv]

    output, error = funct.subprocess_execute(commands[0])

    if error:
        funct.logging('localhost', error, haproxywi=1)
        import socket

        print(
            'success: Grafana and Prometheus servers were installed. You can find Grafana on http://' + socket.gethostname() + ':3000<br>')
    else:
        for l in output:
            if "Traceback" in l or "FAILED" in l:
                try:
                    print(l)
                    break
                except Exception:
                    print(output)
                    break
        else:
            import socket

            print(
                'success: Grafana and Prometheus servers were installed. You can find Grafana on http://' + socket.gethostname() + ':3000<br>')

    os.system("rm -f %s" % script)

if form.getvalue('haproxy_exp_install'):
    serv = form.getvalue('haproxy_exp_install')
    script = "install_haproxy_exporter.sh"
    stats_port = sql.get_setting('stats_port')
    server_state_file = sql.get_setting('server_state_file')
    stats_user = sql.get_setting('stats_user')
    stats_password = sql.get_setting('stats_password')
    stat_page = sql.get_setting('stats_page')
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(serv)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    os.system("cp scripts/%s ." % script)

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv +
                " STAT_PORT=" + stats_port + " STAT_FILE=" + server_state_file +
                " SSH_PORT=" + ssh_port + " STAT_PAGE=" + stat_page +
                " STATS_USER=" + stats_user + " STATS_PASS=" + stats_password + " HOST=" + serv +
                " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'HAProxy exporter')

    os.system("rm -f %s" % script)

if form.getvalue('nginx_exp_install'):
    serv = form.getvalue('nginx_exp_install')
    script = "install_nginx_exporter.sh"
    stats_user = sql.get_setting('nginx_stats_user')
    stats_password = sql.get_setting('nginx_stats_password')
    stats_port = sql.get_setting('nginx_stats_port')
    stats_page = sql.get_setting('nginx_stats_page')
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(serv)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    os.system("cp scripts/%s ." % script)

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv +
                " STAT_PORT=" + stats_port + " SSH_PORT=" + ssh_port + " STAT_PAGE=" + stats_page +
                " STATS_USER=" + stats_user + " STATS_PASS=" + stats_password + " HOST=" + serv +
                " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'Nginx exporter')

    os.system("rm -f %s" % script)

if form.getvalue('node_exp_install'):
    serv = form.getvalue('node_exp_install')
    script = "install_node_exporter.sh"
    proxy = sql.get_setting('proxy')
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(serv)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    os.system("cp scripts/%s ." % script)

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " SSH_PORT=" + ssh_port + 
                " HOST=" + serv + " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'Node exporter')

    os.system("rm -f %s" % script)

if form.getvalue('backup') or form.getvalue('deljob') or form.getvalue('backupupdate'):
    serv = form.getvalue('server')
    rpath = form.getvalue('rpath')
    time = form.getvalue('time')
    type = form.getvalue('type')
    rserver = form.getvalue('rserver')
    cred = form.getvalue('cred')
    deljob = form.getvalue('deljob')
    update = form.getvalue('backupupdate')
    description = form.getvalue('description')
    script = "backup.sh"
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path('localhost', id=int(cred))

    if deljob:
        time = ''
        rpath = ''
        type = ''
    elif update:
        deljob = ''
    else:
        deljob = ''
        if sql.check_exists_backup(serv):
            print('warning: Backup job for %s already exists' % serv)
            sys.exit()

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    os.system("cp scripts/%s ." % script)

    commands = ["chmod +x " + script + " &&  ./" + script + "  HOST=" + rserver + "  SERVER=" + serv + " TYPE=" + type +
                " SSH_PORT=" + ssh_port + " TIME=" + time +
                " RPATH=" + rpath + " DELJOB=" + deljob + " USER=" + str(ssh_user_name) + " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    if error:
        funct.logging('backup', error, haproxywi=1)
        print('error: ' + error)
    else:
        for l in output:
            if "msg" in l or "FAILED" in l:
                try:
                    l = l.split(':')[1]
                    l = l.split('"')[1]
                    print('error: ' + l + "<br>")
                    break
                except Exception:
                    print('error: ' + output)
                    break
        else:
            if not deljob and not update:
                if sql.insert_backup_job(serv, rserver, rpath, type, time, cred, description):
                    from jinja2 import Environment, FileSystemLoader

                    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
                    template = env.get_template('new_backup.html')
                    template = template.render(backups=sql.select_backups(server=serv, rserver=rserver),
                                               sshs=sql.select_ssh())
                    print(template)
                    print('success: Backup job has created')
                    funct.logging('backup ', ' has created a new backup job for server ' + serv, haproxywi=1, login=1)
                else:
                    print('error: Cannot add job into DB')
            elif deljob:
                sql.delete_backups(deljob)
                print('Ok')
                funct.logging('backup ', ' has deleted a backup job for server ' + serv, haproxywi=1, login=1)
            elif update:
                sql.update_backup(serv, rserver, rpath, type, time, cred, description, update)
                print('Ok')
                funct.logging('backup ', ' has updated a backup job for server ' + serv, haproxywi=1, login=1)

if form.getvalue('install_nginx'):
    funct.install_nginx(form.getvalue('install_nginx'))

if form.getvalue('haproxyaddserv'):
    funct.install_haproxy(form.getvalue('haproxyaddserv'), syn_flood=form.getvalue('syn_flood'),
                          hapver=form.getvalue('hapver'))

if form.getvalue('installwaf'):
    funct.waf_install(form.getvalue('installwaf'))

if form.getvalue('update_haproxy_wi'):
    service = form.getvalue('service')
    services = ['roxy-wi-checker', 'haproxy-wi', 'roxy-wi-keep_alive', 'roxy-wi-smon', 'roxy-wi-metrics']
    if service not in services:
        print('error: ' + service + ' is not part of Roxy-WI')
        sys.exit()
    funct.update_haproxy_wi(service)

if form.getvalue('metrics_waf'):
    sql.update_waf_metrics_enable(form.getvalue('metrics_waf'), form.getvalue('enable'))

if form.getvalue('table_metrics'):
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('table_metrics.html')

    template = template.render(table_stat=sql.select_table_metrics())
    print(template)

if form.getvalue('metrics_hapwi_ram'):
    ip = form.getvalue('ip')
    metrics = {'chartData': {}}
    rams = ''

    if ip == '1':
        cmd = "free -m |grep Mem |awk '{print $2,$3,$4,$5,$6,$7}'"
        metric, error = funct.subprocess_execute(cmd)
    else:
        commands = ["free -m |grep Mem |awk '{print $2,$3,$4,$5,$6,$7}'"]
        metric, error = funct.subprocess_execute(commands[0])

    for i in metric:
        rams = i

    metrics['chartData']['rams'] = rams

    import json

    print(json.dumps(metrics))

if form.getvalue('metrics_hapwi_cpu'):
    ip = form.getvalue('ip')
    metrics = {'chartData': {}}
    cpus = ''

    if ip == '1':
        cmd = "top -b -n 1 |grep Cpu |awk -F':' '{print $2}'|awk  -F' ' 'BEGIN{ORS=\" \";} { for (i=1;i<=NF;i+=2) print $i}'"
        metric, error = funct.subprocess_execute(cmd)
    else:
        commands = [
            "top -b -n 1 |grep Cpu |awk -F':' '{print $2}'|awk  -F' ' 'BEGIN{ORS=\" \";} { for (i=1;i<=NF;i+=2) print $i}'"]
        metric, error = funct.subprocess_execute(commands[0])

    for i in metric:
        cpus = i

    metrics['chartData']['cpus'] = cpus

    import json

    print(json.dumps(metrics))

if form.getvalue('new_metrics'):
    serv = form.getvalue('server')
    time_range = form.getvalue('time_range')
    metric = sql.select_metrics(serv, time_range=time_range)
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
    metrics['chartData']['server'] = server

    import json

    print(json.dumps(metrics))

if form.getvalue('new_http_metrics'):
    serv = form.getvalue('server')
    time_range = form.getvalue('time_range')
    metric = sql.select_metrics_http(serv, time_range=time_range)
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
    metrics['chartData']['server'] = server

    import json

    print(json.dumps(metrics))

if form.getvalue('new_waf_metrics'):
    serv = form.getvalue('server')
    time_range = form.getvalue('time_range')
    metric = sql.select_waf_metrics(serv, time_range=time_range)
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
    metrics['chartData']['server'] = serv

    import json

    print(json.dumps(metrics))

if form.getvalue('get_hap_v'):
    output = funct.check_haproxy_version(serv)
    print(output)

if form.getvalue('get_nginx_v'):
    cmd = ['/usr/sbin/nginx -v']
    print(funct.ssh_command(serv, cmd))

if form.getvalue('get_exporter_v'):
    print(funct.check_service(serv, form.getvalue('get_exporter_v')))

if form.getvalue('bwlists'):
    list_path = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('lists_path') + "/" + form.getvalue('group') + "/" + form.getvalue('color') + "/" + form.getvalue('bwlists')
    try:
        file = open(list_path, "r")
        file_read = file.read()
        file.close()
        print(file_read)
    except IOError:
        print('error: Cat\'n read ' + form.getvalue('color') + ' list , ')

if form.getvalue('bwlists_create'):
    color = form.getvalue('color')
    list_name = form.getvalue('bwlists_create').split('.')[0]
    list_name += '.lst'
    list_path = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('lists_path') + "/" + form.getvalue('group') + "/" + color + "/" + list_name
    try:
        open(list_path, 'a').close()
        print('success: ')
        try:
            funct.logging(serv, 'has created  ' + color + ' list ' + list_name, haproxywi=1, login=1)
        except Exception:
            pass
    except IOError as e:
        print('error: Cannot create new ' + color + ' list. %s , ' % e)

if form.getvalue('bwlists_save'):
    color = form.getvalue('color')
    bwlists_save = form.getvalue('bwlists_save')
    list_path = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('lists_path') + "/" + form.getvalue('group') + "/" + color + "/" + bwlists_save
    try:
        with open(list_path, "w") as file:
            file.write(form.getvalue('bwlists_content'))
    except IOError as e:
        print('error: Cannot save ' + color + ' list. %s , ' % e)

    path = sql.get_setting('haproxy_dir') + "/" + color
    servers = []

    if serv != 'all':
        servers.append(serv)

        MASTERS = sql.is_master(serv)
        for master in MASTERS:
            if master[0] is not None:
                servers.append(master[0])
    else:
        server = sql.get_dick_permit()
        for s in server:
            servers.append(s[2])

    for serv in servers:
        funct.ssh_command(serv, ["sudo mkdir " + path])
        funct.ssh_command(serv, ["sudo chown $(whoami) " + path])
        error = funct.upload(serv, path + "/" + bwlists_save, list_path, dir='fullpath')

        if error:
            print('error: Upload fail: %s , ' % error)
        else:
            print('success: Edited ' + color + ' list was uploaded to ' + serv + ' , ')
            try:
                funct.logging(serv, 'has edited  ' + color + ' list ' + bwlists_save, haproxywi=1, login=1)
            except Exception:
                pass

            haproxy_enterprise = sql.get_setting('haproxy_enterprise')
            if haproxy_enterprise == '1':
                haproxy_service_name = "hapee-2.0-lb"
            else:
                haproxy_service_name = "haproxy"

            if form.getvalue('bwlists_restart') == 'restart':
                funct.ssh_command(serv, ["sudo systemctl restart " + haproxy_service_name])
            elif form.getvalue('bwlists_restart') == 'reload':
                funct.ssh_command(serv, ["sudo systemctl reload " + haproxy_service_name])

if form.getvalue('bwlists_delete'):
    color = form.getvalue('color')
    bwlists_delete = form.getvalue('bwlists_delete')
    list_path = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('lists_path') + "/" + form.getvalue('group') + "/" + color + "/" + bwlists_delete
    try:
        os.remove(list_path)
    except IOError as e:
        print('error: Cannot delete ' + color + ' list. %s , ' % e)

    path = sql.get_setting('haproxy_dir') + "/" + color
    servers = []

    if serv != 'all':
        servers.append(serv)

        MASTERS = sql.is_master(serv)
        for master in MASTERS:
            if master[0] is not None:
                servers.append(master[0])
    else:
        server = sql.get_dick_permit()
        for s in server:
            servers.append(s[2])

    for serv in servers:
        error = funct.ssh_command(serv, ["sudo rm " + path + "/" + bwlists_delete], return_err=1)

        if error:
            print('error: Deleting fail: %s , ' % error)
        else:
            print('success: ' + color + ' list was delete on ' + serv + ' , ')
            try:
                funct.logging(serv, 'has deleted  ' + color + ' list ' + bwlists_save, haproxywi=1, login=1)
            except Exception:
                pass

if form.getvalue('get_lists'):
    list_path = os.path.dirname(os.getcwd()) + "/" + sql.get_setting('lists_path') + "/" + form.getvalue('group') + "/" + form.getvalue('color')
    lists = funct.get_files(dir=list_path, format="lst")
    for l in lists:
        print(l)

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

    l = ldap.initialize('{}://{}:{}/'.format(ldap_proto, server, port))

    try:
        l.protocol_version = ldap.VERSION3
        l.set_option(ldap.OPT_REFERRALS, 0)

        bind = l.simple_bind_s(user, password)

        criteria = "(&(objectClass=" + ldap_class_search + ")(" + ldap_user_attribute + "=" + username + "))"
        attributes = [ldap_search_field]
        result = l.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

        results = [entry for dn, entry in result if isinstance(entry, dict)]
        try:
            print('["' + results[0][ldap_search_field][0].decode("utf-8") + '","' + domain + '"]')
        except Exception:
            print('error: user not found')
    finally:
        l.unbind()

if form.getvalue('change_waf_mode'):
    waf_mode = form.getvalue('change_waf_mode')
    server_hostname = form.getvalue('server_hostname')
    haproxy_dir = sql.get_setting('haproxy_dir')
    serv = sql.select_server_by_name(server_hostname)
    commands = ["sudo sed -i 's/^SecRuleEngine.*/SecRuleEngine %s/' %s/waf/modsecurity.conf " % (waf_mode, haproxy_dir)]
    funct.ssh_command(serv, commands)
    funct.logging(serv, 'Was changed WAF mod to ' + waf_mode, haproxywi=1, login=1)

error_mess = 'error: All fields must be completed'

if form.getvalue('newuser') is not None:
    email = form.getvalue('newemail')
    password = form.getvalue('newpassword')
    role = form.getvalue('newrole')
    new_user = form.getvalue('newusername')
    page = form.getvalue('page')
    activeuser = form.getvalue('activeuser')
    group = form.getvalue('newgroupuser')
    role_id = sql.get_role_id_by_name(role)

    if funct.check_user_group():
        if funct.is_admin(level=role_id):
            if sql.add_user(new_user, email, password, role, activeuser, group):
                from jinja2 import Environment, FileSystemLoader

                env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
                template = env.get_template('ajax/new_user.html')

                template = template.render(users=sql.select_users(user=new_user),
                                           groups=sql.select_groups(),
                                           page=page,
                                           roles=sql.select_roles(),
                                           adding=1)
                print(template)
                funct.logging('a new user ' + new_user, ' has created ', haproxywi=1, login=1)
        else:
            funct.logging(new_user, ' tried to privilege escalation', haproxywi=1, login=1)

if form.getvalue('userdel') is not None:
    userdel = form.getvalue('userdel')
    user = sql.select_users(id=userdel)
    username = ''
    for u in user:
        username = u[1]
    if sql.delete_user(userdel):
        sql.delete_user_groups(userdel)
        funct.logging(username, ' has deleted user ', haproxywi=1, login=1)
        print("Ok")

if form.getvalue('updateuser') is not None:
    email = form.getvalue('email')
    role = form.getvalue('role')
    new_user = form.getvalue('updateuser')
    id = form.getvalue('id')
    activeuser = form.getvalue('activeuser')
    group = form.getvalue('usergroup')
    role_id = sql.get_role_id_by_name(role)

    if funct.check_user_group():
        if funct.is_admin(level=role_id):
            sql.update_user(new_user, email, role, id, activeuser)
            funct.logging(new_user, ' has updated user ', haproxywi=1, login=1)
        else:
            funct.logging(new_user, ' tried to privilege escalation', haproxywi=1, login=1)

if form.getvalue('updatepassowrd') is not None:
    password = form.getvalue('updatepassowrd')
    user_id = form.getvalue('id')
    user = sql.select_users(id=user_id)
    for u in user:
        username = u[1]
    sql.update_user_password(password, user_id)
    funct.logging('user ' + username, ' has changed password ', haproxywi=1, login=1)
    print("Ok")

if form.getvalue('newserver') is not None:
    hostname = form.getvalue('servername')
    ip = form.getvalue('newip')
    group = form.getvalue('newservergroup')
    scan_server = form.getvalue('scan_server')
    typeip = form.getvalue('typeip')
    haproxy = form.getvalue('haproxy')
    nginx = form.getvalue('nginx')
    firewall = form.getvalue('firewall')
    enable = form.getvalue('enable')
    master = form.getvalue('slave')
    cred = form.getvalue('cred')
    page = form.getvalue('page')
    page = page.split("#")[0]
    port = form.getvalue('newport')
    desc = form.getvalue('desc')

    if sql.add_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx, firewall):

        try:
            if scan_server == '1':
                nginx_config_path = sql.get_setting('nginx_config_path')
                haproxy_config_path = sql.get_setting('haproxy_config_path')
                haproxy_dir = sql.get_setting('haproxy_dir')
                keepalived_config_path = '/etc/keepalived/keepalived.conf'

                if funct.is_file_exists(ip, nginx_config_path):
                    sql.update_nginx(ip)

                if funct.is_file_exists(ip, haproxy_config_path):
                    sql.update_haproxy(ip)

                if funct.is_file_exists(ip, keepalived_config_path):
                    sql.update_keepalived(ip)

                if funct.is_file_exists(ip, haproxy_dir + '/waf/bin/modsecurity'):
                    sql.insert_waf_metrics_enable(ip, "0")

                if funct.is_service_active(ip, 'firewalld'):
                    sql.update_firewall(ip)
        except:
            pass

        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
        template = env.get_template('ajax/new_server.html')

        template = template.render(groups=sql.select_groups(),
                                   servers=sql.select_servers(server=ip),
                                   roles=sql.select_roles(),
                                   masters=sql.select_servers(get_master_servers=1),
                                   sshs=sql.select_ssh(group=group),
                                   page=page,
                                   adding=1)
        print(template)
        funct.logging('a new server ' + hostname, ' has been created  ', haproxywi=1, login=1)

if form.getvalue('updatehapwiserver') is not None:
    hapwi_id = form.getvalue('updatehapwiserver')
    active = form.getvalue('active')
    name = form.getvalue('name')
    alert = form.getvalue('alert_en')
    metrics = form.getvalue('metrics')
    service_name = form.getvalue('service_name')
    sql.update_hapwi_server(hapwi_id, alert, metrics, active, service_name)
    funct.logging('the server ' + name, ' has been updated ', haproxywi=1, login=1)

if form.getvalue('updateserver') is not None:
    name = form.getvalue('updateserver')
    group = form.getvalue('servergroup')
    typeip = form.getvalue('typeip')
    haproxy = form.getvalue('haproxy')
    nginx = form.getvalue('nginx')
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
        sql.update_server(name, group, typeip, enable, master, serv_id, cred, port, desc, haproxy, nginx, firewall, protected)
        funct.logging('the server ' + name, ' has been updated ', haproxywi=1, login=1)

if form.getvalue('serverdel') is not None:
    serverdel = form.getvalue('serverdel')
    server = sql.select_servers(id=serverdel)
    for s in server:
        hostname = s[1]
        ip = s[2]
    if sql.check_exists_backup(ip):
        print('warning: Delete the backup first ')
        sys.exit()
    if sql.delete_server(serverdel):
        sql.delete_waf_server(serverdel)
        sql.delete_port_scanner_settings(serverdel)
        print("Ok")
        funct.logging(hostname, ' has been deleted server with ', haproxywi=1, login=1)

if form.getvalue('newgroup') is not None:
    newgroup = form.getvalue('groupname')
    desc = form.getvalue('newdesc')
    if newgroup is None:
        print(error_mess)
    else:
        if sql.add_group(newgroup, desc):
            from jinja2 import Environment, FileSystemLoader

            env = Environment(loader=FileSystemLoader('templates/ajax/'), autoescape=True)
            template = env.get_template('/new_group.html')

            output_from_parsed_template = template.render(groups=sql.select_groups(group=newgroup))
            print(output_from_parsed_template)
            funct.logging('a new group ' + newgroup, ' created  ', haproxywi=1, login=1)

if form.getvalue('groupdel') is not None:
    groupdel = form.getvalue('groupdel')
    group = sql.select_groups(id=groupdel)
    for g in group:
        groupname = g[1]
    if sql.delete_group(groupdel):
        print("Ok")
        funct.logging(groupname, ' has deleted group ', haproxywi=1, login=1)

if form.getvalue('updategroup') is not None:
    name = form.getvalue('updategroup')
    descript = form.getvalue('descript')
    group_id = form.getvalue('id')
    if name is None:
        print(error_mess)
    else:
        group = sql.select_groups(id=group_id)
        for g in group:
            groupname = g[1]
        sql.update_group(name, descript, group_id)
        funct.logging('the group ' + groupname, ' has update  ', haproxywi=1, login=1)

if form.getvalue('new_ssh'):
    user_group = funct.get_user_group()
    name = form.getvalue('new_ssh')
    name = name + '_' + user_group
    enable = form.getvalue('ssh_enable')
    group = form.getvalue('new_group')
    username = form.getvalue('ssh_user')
    password = form.getvalue('ssh_pass')
    page = form.getvalue('page')
    page = page.split("#")[0]

    if username is None or name is None:
        print(error_mess)
    else:
        if sql.insert_new_ssh(name, enable, group, username, password):
            from jinja2 import Environment, FileSystemLoader

            env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
            template = env.get_template('/new_ssh.html')
            output_from_parsed_template = template.render(groups=sql.select_groups(), sshs=sql.select_ssh(name=name),
                                                          page=page)
            print(output_from_parsed_template)
            funct.logging(name, ' has created a new SSH credentials  ', haproxywi=1, login=1)

if form.getvalue('sshdel') is not None:
    fullpath = funct.get_config_var('main', 'fullpath')
    sshdel = form.getvalue('sshdel')

    for sshs in sql.select_ssh(id=sshdel):
        ssh_enable = sshs[2]
        name = sshs[1]
        ssh_key_name = fullpath + '/keys/%s.pem' % sshs[1]

    if ssh_enable == 1:
        cmd = 'rm -f %s' % ssh_key_name
        try:
            funct.subprocess_execute(cmd)
        except Exception:
            pass
    if sql.delete_ssh(sshdel):
        print("Ok")
        funct.logging(name, ' has deleted the SSH credentials  ', haproxywi=1, login=1)

if form.getvalue('updatessh'):
    ssh_id = form.getvalue('id')
    name = form.getvalue('name')
    enable = form.getvalue('ssh_enable')
    group = form.getvalue('group')
    username = form.getvalue('ssh_user')
    password = form.getvalue('ssh_pass')

    if username is None:
        print(error_mess)
    else:
        fullpath = funct.get_config_var('main', 'fullpath')

        for sshs in sql.select_ssh(id=ssh_id):
            ssh_enable = sshs[2]
            ssh_key_name = fullpath + '/keys/%s.pem' % sshs[1]
            new_ssh_key_name = fullpath + '/keys/%s.pem' % name

        if ssh_enable == 1:
            cmd = 'mv %s %s' % (ssh_key_name, new_ssh_key_name)
            cmd1 = 'chmod 600 %s' % new_ssh_key_name
            try:
                funct.subprocess_execute(cmd)
                funct.subprocess_execute(cmd1)
            except Exception:
                pass
        sql.update_ssh(ssh_id, name, enable, group, username, password)
        funct.logging('the SSH ' + name, ' has updated credentials ', haproxywi=1, login=1)

if form.getvalue('ssh_cert'):
    import paramiko

    user_group = funct.get_user_group()
    name = form.getvalue('name')
    key = paramiko.pkey.load_private_key(form.getvalue('ssh_cert'))
    ssh_keys = os.path.dirname(os.getcwd()) + '/keys/' + name + '.pem'

    try:
        split_name = name.split('_')[1]
        split_name = True
    except Exception:
        split_name = False

    if not os.path.isfile(ssh_keys) and not split_name:
        name = name + '_' + user_group

    if not os.path.exists(os.getcwd() + '/keys/'):
        os.makedirs(os.getcwd() + '/keys/')

    ssh_keys = os.path.dirname(os.getcwd()) + '/keys/' + name + '.pem'

    try:
        cloud = sql.is_cloud()
        if cloud != '':
            key.write_private_key_file(ssh_keys, password=cloud)
        else:
            key.write_private_key_file(ssh_keys)
    except IOError:
        print('error: Cannot save SSH key file. Check SSH keys path in config')
    else:
        print('success: SSH key has been saved into: %s </div>' % ssh_keys)

    try:
        cmd = 'chmod 600 %s' % ssh_keys
        funct.subprocess_execute(cmd)
    except IOError as e:
        funct.logging('localhost', e.args[0], haproxywi=1)

    funct.logging("localhost", " has been uploaded a new SSH cert %s" % ssh_keys, haproxywi=1, login=1)

if form.getvalue('newtelegram'):
    token = form.getvalue('newtelegram')
    channel = form.getvalue('chanel')
    group = form.getvalue('telegramgroup')
    page = form.getvalue('page')
    page = page.split("#")[0]

    if token is None or channel is None or group is None:
        print(error_mess)
    else:
        if sql.insert_new_telegram(token, channel, group):
            from jinja2 import Environment, FileSystemLoader

            env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
            template = env.get_template('/new_telegram.html')
            output_from_parsed_template = template.render(groups=sql.select_groups(),
                                                          telegrams=sql.select_telegram(token=token), page=page)
            print(output_from_parsed_template)
            funct.logging(channel, ' has created a new Telegram channel ', haproxywi=1, login=1)

if form.getvalue('newslack'):
    token = form.getvalue('newslack')
    channel = form.getvalue('chanel')
    group = form.getvalue('slackgroup')
    page = form.getvalue('page')
    page = page.split("#")[0]

    if token is None or channel is None or group is None:
        print(error_mess)
    else:
        if sql.insert_new_slack(token, channel, group):
            from jinja2 import Environment, FileSystemLoader

            env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
            template = env.get_template('/new_slack.html')
            output_from_parsed_template = template.render(groups=sql.select_groups(),
                                                          slacks=sql.select_slack(token=token), page=page)
            print(output_from_parsed_template)
            funct.logging(channel, ' has created a new Slack channel ', haproxywi=1, login=1)

if form.getvalue('telegramdel') is not None:
    telegramdel = form.getvalue('telegramdel')
    telegram = sql.select_telegram(id=telegramdel)
    for t in telegram:
        telegram_name = t[1]
    if sql.delete_telegram(telegramdel):
        print("Ok")
        funct.logging(telegram_name, ' has deleted the Telegram channel ', haproxywi=1, login=1)

if form.getvalue('slackdel') is not None:
    slackdel = form.getvalue('slackdel')
    slack = sql.select_slack(id=slackdel)
    for t in slack:
        slack_name = t[1]
    if sql.delete_slack(slackdel):
        print("Ok")
        funct.logging(slack_name, ' has deleted the Slack channel ', haproxywi=1, login=1)

if form.getvalue('updatetoken') is not None:
    token = form.getvalue('updatetoken')
    channel = form.getvalue('updategchanel')
    group = form.getvalue('updatetelegramgroup')
    user_id = form.getvalue('id')
    if token is None or channel is None or group is None:
        print(error_mess)
    else:
        sql.update_telegram(token, channel, group, user_id)
        funct.logging('group ' + group, ' Telegram token has updated channel: ' + channel, haproxywi=1, login=1)

if form.getvalue('update_slack_token') is not None:
    token = form.getvalue('update_slack_token')
    channel = form.getvalue('updategchanel')
    group = form.getvalue('updateslackgroup')
    user_id = form.getvalue('id')
    if token is None or channel is None or group is None:
        print(error_mess)
    else:
        sql.update_slack(token, channel, group, user_id)
        funct.logging('group ' + group, ' Slack token has updated channel: ' + channel, haproxywi=1, login=1)

if form.getvalue('updatesettings') is not None:
    settings = form.getvalue('updatesettings')
    val = form.getvalue('val')
    if sql.update_setting(settings, val):
        funct.logging('value ' + val, ' changed settings ' + settings, haproxywi=1, login=1)
        print("Ok")

if form.getvalue('getusergroups'):
    group_id = form.getvalue('getusergroups')
    groups = []
    u_g = sql.select_user_groups(id=group_id)
    for g in u_g:
        groups.append(g[0])
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_user_groups.html')
    template = template.render(groups=sql.select_groups(), user_groups=groups, id=group_id)
    print(template)

if form.getvalue('changeUserGroupId') is not None:
    group_id = form.getvalue('changeUserGroupId')
    groups = form.getvalue('changeUserGroups')
    user = form.getvalue('changeUserGroupsUser')
    if sql.delete_user_groups(group_id):
        for group in groups:
            if group[0] == ',':
                continue
            sql.update_user_groups(groups=group[0], id=group_id)

    funct.logging('localhost', ' has upgraded groups for user: ' + user, haproxywi=1, login=1)

if form.getvalue('changeUserCurrentGroupId') is not None:
    group_id = form.getvalue('changeUserCurrentGroupId')
    user_uuid = form.getvalue('changeUserGroupsUser')

    if sql.update_user_current_groups(group_id, user_uuid):
        print('Ok')
    else:
        print('error: Cannot change group')

if form.getvalue('getcurrentusergroup') is not None:
    import http.cookies

    cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
    user_id = cookie.get('uuid')
    group = cookie.get('group')
    group_id = sql.get_user_id_by_uuid(user_id.value)
    groups = sql.select_user_groups_with_names(id=group_id)

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_user_current_group.html')
    template = template.render(groups=groups, group=group.value, id=group_id)
    print(template)

if form.getvalue('newsmon') is not None:
    user_group = funct.get_user_group(id=1)
    server = form.getvalue('newsmon')
    port = form.getvalue('newsmonport')
    enable = form.getvalue('newsmonenable')
    http = form.getvalue('newsmonproto')
    uri = form.getvalue('newsmonuri')
    body = form.getvalue('newsmonbody')
    group = form.getvalue('newsmongroup')
    desc = form.getvalue('newsmondescription')
    telegram = form.getvalue('newsmontelegram')

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

    if sql.insert_smon(server, port, enable, http, uri, body, group, desc, telegram, user_group):
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/show_new_smon.html')
        template = template.render(
            smon=sql.select_smon(user_group, ip=server, port=port, proto=http, uri=uri, body=body),
            telegrams=sql.get_user_telegram_by_group(user_group))
        print(template)
        funct.logging('SMON', ' Has been add a new server ' + server + ' to SMON ', haproxywi=1, login=1)

if form.getvalue('smondel') is not None:
    user_group = funct.get_user_group(id=1)
    smon_id = form.getvalue('smondel')

    if funct.check_user_group():
        if sql.delete_smon(smon_id, user_group):
            print('Ok')
            funct.logging('SMON', ' Has been delete server from SMON ', haproxywi=1, login=1)

if form.getvalue('showsmon') is not None:
    user_group = funct.get_user_group(id=1)
    sort = form.getvalue('sort')

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/smon_dashboard.html')
    template = template.render(smon=sql.smon_list(user_group), sort=sort)
    print(template)

if form.getvalue('updateSmonIp') is not None:
    smon_id = form.getvalue('id')
    ip = form.getvalue('updateSmonIp')
    port = form.getvalue('updateSmonPort')
    en = form.getvalue('updateSmonEn')
    http = form.getvalue('updateSmonHttp')
    body = form.getvalue('updateSmonBody')
    telegram = form.getvalue('updateSmonTelegram')
    group = form.getvalue('updateSmonGroup')
    desc = form.getvalue('updateSmonDesc')

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

    if sql.update_smon(smon_id, ip, port, body, telegram, group, desc, en):
        print("Ok")
        funct.logging('SMON', ' Has been update the server ' + ip + ' to SMON ', haproxywi=1, login=1)

if form.getvalue('showBytes') is not None:
    serv = form.getvalue('showBytes')
    port = sql.get_setting('haproxy_sock_port')
    bin_bout = []
    cmd = "echo 'show stat' |nc " + serv + " " + port + " |cut -d ',' -f 1-2,9|grep -E '[0-9]'|awk -F',' '{sum+=$3;}END{print sum;}'"
    bin, stderr = funct.subprocess_execute(cmd)
    bin_bout.append(bin[0])
    cmd = "echo 'show stat' |nc " + serv + " " + port + " |cut -d ',' -f 1-2,10|grep -E '[0-9]'|awk -F',' '{sum+=$3;}END{print sum;}'"
    bin, stderr = funct.subprocess_execute(cmd)
    bin_bout.append(bin[0])
    cmd = "echo 'show stat' |nc " + serv + " " + port + " |cut -d ',' -f 1-2,5|grep -E '[0-9]'|awk -F',' '{sum+=$3;}END{print sum;}'"
    bin, stderr = funct.subprocess_execute(cmd)
    bin_bout.append(bin[0])
    cmd = "echo 'show stat' |nc " + serv + " " + port + " |cut -d ',' -f 1-2,8|grep -E '[0-9]'|awk -F',' '{sum+=$3;}END{print sum;}'"
    bin, stderr = funct.subprocess_execute(cmd)
    bin_bout.append(bin[0])

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/bin_bout.html')
    template = template.render(bin_bout=bin_bout, serv=serv)
    print(template)

if form.getvalue('nginxConnections'):
    import requests
    serv = form.getvalue('nginxConnections')
    port = sql.get_setting('nginx_stats_port')
    user = sql.get_setting('nginx_stats_user')
    password = sql.get_setting('nginx_stats_password')
    page = sql.get_setting('nginx_stats_page')

    r = requests.get('http://' + serv + ':' + port + '/' + page, auth=(user, password))

    if r.status_code == 200:
        bin_bout = [0, 0]
        for num, line in enumerate(r.text.split('\n')):
            if num == 0:
                bin_bout.append(line.split(' ')[2])
            if num == 2:
                bin_bout.append(line.split(' ')[3])

        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('ajax/bin_bout.html')
        template = template.render(bin_bout=bin_bout, serv=serv, service='nginx')
        print(template)
    else:
        print('error: cannot connect to Nginx stat page')

if form.getvalue('alert_consumer'):
    try:
        user_group = funct.get_user_group(id=1)
        if funct.check_user_group():
            message = sql.select_alerts(user_group)
            for m in message:
                print(m[0] + ': ' + m[1] + ' date: ' + m[2] + ';')
    except Exception:
        pass

if form.getvalue('waf_rule_id'):
    enable = form.getvalue('waf_en')
    rule_id = form.getvalue('waf_rule_id')
    haproxy_path = sql.get_setting('haproxy_dir')
    rule_file = sql.select_waf_rule_by_id(rule_id)
    conf_file_path = haproxy_path + 'waf/modsecurity.conf'
    rule_file_path = 'Include ' + haproxy_path + '/waf/rules/' + rule_file

    if enable == '0':
        cmd = ["sudo sed -i 's!" + rule_file_path + "!#" + rule_file_path + "!' " + conf_file_path]
        en_for_log = 'disable'
    else:
        cmd = ["sudo sed -i 's!#" + rule_file_path + "!" + rule_file_path + "!' " + conf_file_path]
        en_for_log = 'enable'

    try:
        funct.logging('WAF', ' Has been ' + en_for_log + ' WAF rule: ' + rule_file + ' for the server ' + serv,
                      haproxywi=1, login=1)
    except Exception:
        pass

    print(funct.ssh_command(serv, cmd))
    sql.update_enable_waf_rules(rule_id, serv, enable)

if form.getvalue('lets_domain'):
    serv = form.getvalue('serv')
    lets_domain = form.getvalue('lets_domain')
    lets_email = form.getvalue('lets_email')
    proxy = sql.get_setting('proxy')
    ssl_path = sql.get_setting('cert_path')
    haproxy_dir = sql.get_setting('haproxy_dir')
    script = "letsencrypt.sh"
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(serv)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    os.system("cp scripts/%s ." % script)

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " haproxy_dir=" + haproxy_dir +
                " DOMAIN=" + lets_domain + " EMAIL=" + lets_email + " SSH_PORT=" + ssh_port + " SSL_PATH=" + ssl_path +
                " HOST=" + serv + " USER=" + ssh_user_name + " PASS=" + ssh_user_password + " KEY=" + ssh_key_name]

    output, error = funct.subprocess_execute(commands[0])

    if error:
        funct.logging('localhost', error, haproxywi=1)
        print(error)
    else:
        for l in output:
            if "msg" in l or "FAILED" in l:
                try:
                    l = l.split(':')[1]
                    l = l.split('"')[1]
                    print(l + "<br>")
                    break
                except Exception:
                    print(output)
                    break
        else:
            print('success: Certificate has been created')

    os.system("rm -f %s" % script)

if form.getvalue('uploadovpn'):
    name = form.getvalue('ovpnname')

    ovpn_file = os.path.dirname('/tmp/') + "/" + name + '.ovpn'

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
        funct.subprocess_execute(cmd)
    except IOError as e:
        funct.logging('localhost', e.args[0], haproxywi=1)

    try:
        cmd = 'sudo cp %s /etc/openvpn3/%s.conf' % (ovpn_file, name)
        funct.subprocess_execute(cmd)
    except IOError as e:
        funct.logging('localhost', e.args[0], haproxywi=1)

    funct.logging("localhost", " has been uploaded a new ovpn file %s" % ovpn_file, haproxywi=1, login=1)

if form.getvalue('openvpndel') is not None:
    openvpndel = form.getvalue('openvpndel')

    cmd = 'sudo openvpn3 config-remove --config /tmp/%s.ovpn --force' % openvpndel
    try:
        funct.subprocess_execute(cmd)
        print("Ok")
        funct.logging(openvpndel, ' has deleted the ovpn file ', haproxywi=1, login=1)
    except IOError as e:
        print(e.args[0])
        funct.logging('localhost', e.args[0], haproxywi=1)

if form.getvalue('actionvpn') is not None:
    openvpn = form.getvalue('openvpnprofile')
    action = form.getvalue('actionvpn')

    if action == 'start':
        cmd = 'sudo openvpn3 session-start --config /tmp/%s.ovpn' % openvpn
    elif action == 'restart':
        cmd = 'sudo openvpn3 session-manage --config /tmp/%s.ovpn --restart' % openvpn
    elif action == 'disconnect':
        cmd = 'sudo openvpn3 session-manage --config /tmp/%s.ovpn --disconnect' % openvpn
    try:
        funct.subprocess_execute(cmd)
        print("success: The " + openvpn + " has been " + action + "ed")
        funct.logging(openvpn, ' has ' + action + ' the ovpn session ', haproxywi=1, login=1)
    except IOError as e:
        print(e.args[0])
        funct.logging('localhost', e.args[0], haproxywi=1)

if form.getvalue('scan_ports') is not None:
    serv_id = form.getvalue('scan_ports')
    server = sql.select_servers(id=serv_id)

    for s in server:
        ip = s[2]

    cmd = "sudo nmap -sS %s |grep -E '^[[:digit:]]'|sed 's/  */ /g'" % ip
    cmd1 = "sudo nmap -sS %s |head -5|tail -2" % ip

    stdout, stderr = funct.subprocess_execute(cmd)
    stdout1, stderr1 = funct.subprocess_execute(cmd1)

    if stderr != '':
        print(stderr)
    else:
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/scan_ports.html')
        template = template.render(ports=stdout, info=stdout1)
        print(template)

if form.getvalue('viewFirewallRules') is not None:
    serv = form.getvalue('viewFirewallRules')

    cmd = ["sudo iptables -L INPUT -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"]
    cmd1 = ["sudo iptables -L IN_public_allow -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"]
    cmd2 = ["sudo iptables -L OUTPUT -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"]

    input_chain = funct.ssh_command(serv, cmd, raw=1)

    input_chain2 = []
    for each_line in input_chain:
        input_chain2.append(each_line.strip('\n'))

    if 'error:' in input_chain:
        print(input_chain)
        sys.exit()

    IN_public_allow = funct.ssh_command(serv, cmd1, raw=1)
    output_chain = funct.ssh_command(serv, cmd2, raw=1)

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/firewall_rules.html')
    template = template.render(input=input_chain2, IN_public_allow=IN_public_allow, output=output_chain)
    print(template)

if form.getvalue('geoipserv') is not None:
    serv = form.getvalue('geoipserv')
    haproxy_dir = sql.get_setting('haproxy_dir')

    cmd = ["ls " + haproxy_dir + "/geoip/"]
    print(funct.ssh_command(serv, cmd))

if form.getvalue('geoip_install'):
    serv = form.getvalue('geoip_install')
    geoip_update = form.getvalue('geoip_update')
    proxy = sql.get_setting('proxy')
    maxmind_key = sql.get_setting('maxmind_key')
    haproxy_dir = sql.get_setting('haproxy_dir')
    script = 'install_geoip.sh'
    ssh_enable, ssh_user_name, ssh_user_password, ssh_key_name = funct.return_ssh_keys_path(serv)

    if ssh_enable == 0:
        ssh_key_name = ''

    servers = sql.select_servers(server=serv)
    for server in servers:
        ssh_port = str(server[10])

    if proxy is not None and proxy != '' and proxy != 'None':
        proxy_serv = proxy
    else:
        proxy_serv = ''

    os.system("cp scripts/%s ." % script)

    commands = ["chmod +x " + script + " &&  ./" + script + " PROXY=" + proxy_serv + " SSH_PORT=" + ssh_port +
                " UPDATE=" + str(geoip_update) + " maxmind_key=" + maxmind_key + " haproxy_dir=" + haproxy_dir +
                " HOST=" + str(serv) + " USER=" + str(ssh_user_name) + " PASS=" + str(ssh_user_password) +
                " KEY=" + str(ssh_key_name)]

    output, error = funct.subprocess_execute(commands[0])

    funct.show_installation_output(error, output, 'GeoLite2 Database')

    os.system("rm -f %s" % script)

if form.getvalue('nettools_icmp_server_from'):
    server_from = form.getvalue('nettools_icmp_server_from')
    server_to = form.getvalue('nettools_icmp_server_to')
    action = form.getvalue('nettools_action')
    stderr = ''

    if action == 'nettools_ping':
        action_for_sending = 'ping -c 4 -W 1 -s 56 -O '
    elif action == 'nettools_trace':
        action_for_sending = 'tracepath -m 10 '

    action_for_sending = action_for_sending + server_to

    if server_from == 'localhost':
        output, stderr = funct.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = funct.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print('error: '+stderr)
        sys.exit()
    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        print(i + '<br>')

if form.getvalue('nettools_telnet_server_from'):
    server_from = form.getvalue('nettools_telnet_server_from')
    server_to = form.getvalue('nettools_telnet_server_to')
    port_to = form.getvalue('nettools_telnet_port_to')
    stderr = ''

    if server_from == 'localhost':
        action_for_sending = 'echo "exit"|nc ' + server_to + ' ' + port_to + ' -t -w 1s'
        output, stderr = funct.subprocess_execute(action_for_sending)
    else:
        action_for_sending = ['echo "exit"|nc ' + server_to + ' ' + port_to + ' -t -w 1s']
        output = funct.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print('error: '+stderr[5:-1])
        sys.exit()
    count_string = 0
    for i in output:
        if i == ' ':
            continue
        i = i.strip()
        if i == 'Ncat: Connection timed out.':
            print('error: ' + i[5:-1])
            break
        print(i + '<br>')
        count_string += 1
        if count_string > 1:
            break

if form.getvalue('nettools_nslookup_server_from'):
    server_from = form.getvalue('nettools_nslookup_server_from')
    dns_name = form.getvalue('nettools_nslookup_name')
    record_type = form.getvalue('nettools_nslookup_record_type')
    stderr = ''

    action_for_sending = 'dig ' + dns_name + ' ' + record_type + ' |grep -e "SERVER\|' + dns_name + '"'

    if server_from == 'localhost':
        output, stderr = funct.subprocess_execute(action_for_sending)
    else:
        action_for_sending = [action_for_sending]
        output = funct.ssh_command(server_from, action_for_sending, raw=1)

    if stderr != '':
        print('error: '+stderr[5:-1])
        sys.exit()
    count_string = 0
    print('<b>There are the next records for ' + dns_name + ' domain:</b> <br />')
    for i in output:
        if 'dig: command not found.' in i:
            print('error: Install bind-utils before using NSLookup')
            break
        if ';' in i and ';; SERVER:' not in i:
            continue
        if 'SOA' in i and record_type != 'SOA':
            print('<b>There are not any records for this type')
            break
        if ';; SERVER:' in i:
            i = i[10:-1]
            print('<br><b>From NS server:</b><br>')
        i = i.strip()
        print(i + '<br>')
        count_string += 1

if form.getvalue('portscanner_history_server_id'):
    server_id = form.getvalue('portscanner_history_server_id')
    enabled = form.getvalue('portscanner_enabled')
    notify = form.getvalue('portscanner_notify')
    history = form.getvalue('portscanner_history')

    servers = sql.select_servers(id=server_id)

    for s in servers:
        user_group_id = s[3]

    if sql.insert_port_scanner_settings(server_id, user_group_id, enabled, notify, history):
        print('ok')
    else:
        if sql.update_port_scanner_settings(server_id, user_group_id, enabled, notify, history):
            print('ok')

if form.getvalue('show_versions'):
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/check_version.html')
    template = template.render(versions=funct.versions())
    print(template)

if form.getvalue('get_group_name_by_id'):
    print(sql.get_group_name_by_id(form.getvalue('get_group_name_by_id')))

if form.getvalue('do_new_name') or form.getvalue('aws_new_name') or form.getvalue('gcore_new_name'):
    funct.check_user_group()
    is_add = False
    if form.getvalue('do_new_name'):
        provider_name = form.getvalue('do_new_name')
        provider_group = form.getvalue('do_new_group')
        provider_token = form.getvalue('do_new_token')

        if sql.add_provider_do(provider_name, provider_group, provider_token):
            is_add = True

    elif form.getvalue('aws_new_name'):
        provider_name = form.getvalue('aws_new_name')
        provider_group = form.getvalue('aws_new_group')
        provider_token = form.getvalue('aws_new_key')
        provider_secret = form.getvalue('aws_new_secret')

        if sql.add_provider_aws(provider_name, provider_group, provider_token, provider_secret):
            is_add = True

    elif form.getvalue('gcore_new_name'):
        provider_name = form.getvalue('gcore_new_name')
        provider_group = form.getvalue('gcore_new_group')
        provider_token = form.getvalue('gcore_new_user')
        provider_pass = form.getvalue('gcore_new_pass')

        if sql.add_provider_gcore(provider_name, provider_group, provider_token, provider_pass):
            is_add = True

    if is_add:
        from jinja2 import Environment, FileSystemLoader
        import http.cookies
        import os

        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_uuid = cookie.get('uuid')
        role_id = sql.get_user_role_by_uuid(user_uuid.value)

        if role_id == 1:
            groups = sql.select_groups()
        else:
            groups = ''

        env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
        template = env.get_template('ajax/provisioning/providers.html')
        template = template.render(providers=sql.select_providers(provider_group, key=provider_token), role=role_id, groups=groups, user_group=provider_group, adding=1)
        print(template)

if form.getvalue('providerdel'):
    funct.check_user_group()
    if sql.delete_provider(form.getvalue('providerdel')):
        print('Ok')
        funct.logging('localhost', 'Provider has been deleted', provisioning=1)

if form.getvalue('awsinit') or form.getvalue('doinit') or form.getvalue('gcoreinitserver'):
    funct.check_user_group()
    cmd = 'cd scripts/terraform/ && sudo terraform init -upgrade -no-color'
    output, stderr = funct.subprocess_execute(cmd)
    if stderr != '':
        print('error: '+stderr)
    else:
        if "Terraform initialized in an empty directory" in output[0]:
            print('error: There is not need modules')
        elif "mkdir .terraform: permission denied" in output[0]:
            print('error: Cannot init. Check permission to folder')

        print(output[0])

if form.getvalue('awsvars') or form.getvalue('awseditvars'):
    if form.getvalue('awsvars'):
        awsvars = form.getvalue('awsvars')
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
    elif form.getvalue('awseditvars'):
        awsvars = form.getvalue('awseditvars')
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

    aws_key, aws_secret = sql.select_aws_provider(provider)

    cmd = 'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={} ' \
          'group={} size={} os={} floating_ip={} volume_size={} server_name={} AWS_ACCESS_KEY={} ' \
          'AWS_SECRET_KEY={} firewall={} public_ip={} ssh_name={} delete_on_termination={} volume_type={} ' \
          'cloud=aws"'.format(region, group, size, oss, floating_ip, volume_size, awsvars, aws_key, aws_secret,
                                firewall, public_ip, ssh_name, delete_on_termination, volume_type)

    output, stderr = funct.subprocess_execute(cmd)
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

    cmd = 'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={} ' \
          'group={} size={} os={} floating_ip={} ssh_ids={} server_name={} token={} backup={} monitoring={} ' \
          'privet_net={} firewall={} floating_ip={} ssh_name={} cloud=do"'.format(region, group, size, oss, floating_ip,
                                                                           ssh_ids, dovars, token, backup, monitoring,
                                                                           privet_net, firewall, floating_ip, ssh_name)
    output, stderr = funct.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
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

    cmd = 'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.do_module -var-file vars/' + workspace + '_'+group+'_do.tfvars'
    output, stderr = funct.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
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
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        if sql.add_server_do(region, size, privet_net, floating_ip, ssh_ids, ssh_name, workspace, oss, firewall, monitoring,
                          backup, provider, group, 'Creating'):

            from jinja2 import Environment, FileSystemLoader

            user, user_id, role, token, servers = funct.get_users_params()
            new_server = sql.select_provisioned_servers(new=workspace, group=group, type='do')

            env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
            template = env.get_template('ajax/provisioning/provisioned_servers.html')
            template = template.render(servers=new_server,
                                       groups=sql.select_groups(),
                                       user_group=group,
                                       providers=sql.select_providers(group),
                                       role=role,
                                       adding=1)
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
    if sql.update_server_do(size, privet_net, floating_ip, ssh_ids, ssh_name, oss, firewall, monitoring, backup, provider,
                         group, 'Creating', server_id):

        cmd = 'cd scripts/terraform/ && sudo terraform workspace select ' + workspace + '_' + group + '_do'
        output, stderr = funct.subprocess_execute(cmd)

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

if form.getvalue('awsvalidate') or form.getvalue('awseditvalidate'):
    if form.getvalue('awsvalidate'):
        workspace = form.getvalue('awsvalidate')
        group = form.getvalue('aws_create_group')
    elif form.getvalue('awseditvalidate'):
        workspace = form.getvalue('awseditvalidate')
        group = form.getvalue('aws_edit_group')

    cmd = 'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.aws_module -var-file vars/' + workspace + '_'+group+'_aws.tfvars'
    output, stderr = funct.subprocess_execute(cmd)
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

    cmd = 'cd scripts/terraform/ && sudo terraform workspace new ' + workspace + '_' + group + '_aws'
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        if sql.add_server_aws(region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                          provider, group, 'Creating', delete_on_termination, volume_type):

            from jinja2 import Environment, FileSystemLoader

            user, user_id, role, token, servers = funct.get_users_params()
            new_server = sql.select_provisioned_servers(new=workspace, group=group, type='aws')

            env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
            template = env.get_template('ajax/provisioning/provisioned_servers.html')
            template = template.render(servers=new_server,
                                       groups=sql.select_groups(),
                                       user_group=group,
                                       providers=sql.select_providers(group),
                                       role=role,
                                       adding=1)
            print(template)

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

    if sql.update_server_aws(region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall,
                             provider, group, 'Editing', server_id, delete_on_termination, volume_type):

        try:
            cmd = 'cd scripts/terraform/ && sudo terraform workspace select ' + workspace + '_' + group + '_aws'
            output, stderr = funct.subprocess_execute(cmd)
        except Exception as e:
            print('error: ' +str(e))
            
        if stderr != '':
            stderr = stderr.strip()
            stderr = repr(stderr)
            stderr = stderr.replace("'", "")
            stderr = stderr.replace("\'", "")
            sql.update_provisioning_server_error(stderr, group, workspace, provider)
            print('error: ' + stderr)
        else:
            print('ok')

if (
        form.getvalue('awsprovisining') or
        form.getvalue('awseditingprovisining') or
        form.getvalue('doprovisining') or
        form.getvalue('doeditprovisining') or
        form.getvalue('gcoreprovisining') or
        form.getvalue('gcoreeditgprovisining')
    ):
    funct.check_user_group()
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

    tfvars = workspace + '_'+group+'_' + cloud + '.tfvars'
    cmd = 'cd scripts/terraform/ && sudo terraform apply -auto-approve -no-color -input=false -target=module.' + cloud + '_module -var-file vars/' + tfvars
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider_id)
        sql.update_provisioning_server_error(stderr, group, workspace, provider_id)
        print('error: '+stderr)
    else:
        if cloud == 'aws':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.aws_module.aws_eip.floating_ip[0]|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
            output, stderr = funct.subprocess_execute(cmd)
            if stderr != '':
                cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'
        else:
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.' + cloud + '_module.' + state_name + '.hapwi|grep -Eo "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}"'

        output, stderr = funct.subprocess_execute(cmd)
        ips = ''
        for ip in output:
            ips += ip
            ips += ' '
        print(ips)
        sql.update_provisioning_server_status('Created', group, workspace, provider_id, update_ip=ips)

        if cloud == 'gcore':
            cmd = 'cd scripts/terraform/ && sudo terraform state show module.gcore_module.gcore_instance.hapwi|grep "name"|grep -v -e "_name\|name_" |head -1 |awk -F"\\\"" \'{print $2}\''
            output, stderr = funct.subprocess_execute(cmd)
            print(':'+output[0])
            sql.update_provisioning_server_gcore_name(workspace, output[0], group, provider_id)

        funct.logging('localhost', 'Server ' + workspace + ' has been ' + action, provisioning=1)

if form.getvalue('provisiningdestroyserver'):
    funct.check_user_group()
    server_id = form.getvalue('provisiningdestroyserver')
    workspace = form.getvalue('servername')
    group = form.getvalue('group')
    cloud_type = form.getvalue('type')
    provider_id = form.getvalue('provider_id')

    tf_workspace = workspace + '_' + group + '_' + cloud_type

    cmd = 'cd scripts/terraform/ && sudo terraform init -upgrade -no-color && sudo terraform workspace select ' + tf_workspace
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider_id)
        sql.update_provisioning_server_error(stderr, group, workspace, provider_id)
        print('error: ' + stderr)
    else:
        cmd = 'cd scripts/terraform/ && sudo terraform destroy -auto-approve -no-color -target=module.'+cloud_type+'_module -var-file vars/' + tf_workspace + '.tfvars'
        output, stderr = funct.subprocess_execute(cmd)

        if stderr != '':
            print('error: ' + stderr)
        else:
            cmd = 'cd scripts/terraform/ && sudo terraform workspace select default && sudo terraform workspace delete -force ' + tf_workspace
            output, stderr = funct.subprocess_execute(cmd)

            print('ok')
            funct.logging('localhost', 'Server has been destroyed', provisioning=1)
            sql.delete_provisioned_servers(server_id)

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

    gcore_user, gcore_pass = sql.select_gcore_provider(provider)

    cmd = 'cd scripts/terraform/ && sudo ansible-playbook var_generator.yml -i inventory -e "region={} ' \
          'group={} size={} os={} network_name={} volume_size={} server_name={} username={} ' \
          'pass={} firewall={} network_type={} ssh_name={} delete_on_termination={} project={} volume_type={} ' \
          'cloud=gcore"'.format(region, group, size, oss, network_name, volume_size, gcorevars, gcore_user, gcore_pass,
                                firewall, network_type, ssh_name, delete_on_termination, project, volume_type)

    output, stderr = funct.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
    else:
        print('ok')

if form.getvalue('gcorevalidate') or form.getvalue('gcoreeditvalidate'):
    if form.getvalue('gcorevalidate'):
        workspace = form.getvalue('gcorevalidate')
        group = form.getvalue('gcore_create_group')
    elif form.getvalue('gcoreeditvalidate'):
        workspace = form.getvalue('gcoreeditvalidate')
        group = form.getvalue('gcore_edit_group')

    cmd = 'cd scripts/terraform/ && sudo terraform plan -no-color -input=false -target=module.gcore_module -var-file vars/' + workspace + '_'+group+'_gcore.tfvars'
    output, stderr = funct.subprocess_execute(cmd)
    if stderr != '':
        print('error: ' + stderr)
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
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        stderr = stderr.strip()
        stderr = repr(stderr)
        stderr = stderr.replace("'", "")
        stderr = stderr.replace("\'", "")
        sql.update_provisioning_server_status('Error', group, workspace, provider)
        sql.update_provisioning_server_error(stderr, group, workspace, provider)
        print('error: ' + stderr)
    else:
        if sql.add_server_gcore(project, region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                          provider, group, 'Creating', delete_on_termination, volume_type):

            from jinja2 import Environment, FileSystemLoader

            user, user_id, role, token, servers = funct.get_users_params()
            new_server = sql.select_provisioned_servers(new=workspace, group=group, type='gcore')

            env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
            template = env.get_template('ajax/provisioning/provisioned_servers.html')
            template = template.render(servers=new_server,
                                       groups=sql.select_groups(),
                                       user_group=group,
                                       providers=sql.select_providers(group),
                                       role=role,
                                       adding=1)
            print(template)

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

    if sql.update_server_gcore(region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
                             provider, group, 'Editing', server_id, delete_on_termination, volume_type, project):

        try:
            cmd = 'cd scripts/terraform/ && sudo terraform workspace select ' + workspace + '_' + group + '_gcore'
            output, stderr = funct.subprocess_execute(cmd)
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

if form.getvalue('editAwsServer'):
    funct.check_user_group()
    server_id = form.getvalue('editAwsServer')
    user_group = form.getvalue('editAwsGroup')
    from jinja2 import Environment, FileSystemLoader

    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/aws_edit_dialog.html')
    template = template.render(server=sql.select_aws_server(server_id=server_id), providers=sql.select_providers(int(user_group)))
    print(template)

if form.getvalue('editGcoreServer'):
    funct.check_user_group()
    server_id = form.getvalue('editGcoreServer')
    user_group = form.getvalue('editGcoreGroup')
    from jinja2 import Environment, FileSystemLoader

    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/gcore_edit_dialog.html')
    template = template.render(server=sql.select_gcore_server(server_id=server_id), providers=sql.select_providers(int(user_group)))
    print(template)

if form.getvalue('editDoServer'):
    funct.check_user_group()
    server_id = form.getvalue('editDoServer')
    user_group = form.getvalue('editDoGroup')
    from jinja2 import Environment, FileSystemLoader

    env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/provisioning/do_edit_dialog.html')
    template = template.render(server=sql.select_do_server(server_id=server_id), providers=sql.select_providers(int(user_group)))
    print(template)

if form.getvalue('edit_do_provider'):
    funct.check_user_group()
    provider_id = form.getvalue('edit_do_provider')
    new_name = form.getvalue('edit_do_provider_name')
    new_token = form.getvalue('edit_do_provider_token')

    if sql.update_do_provider(new_name, new_token, provider_id):
        print('ok')
        funct.logging('localhost', 'Provider has been renamed. New name is ' + new_name, provisioning=1)

if form.getvalue('edit_gcore_provider'):
    funct.check_user_group()
    provider_id = form.getvalue('edit_gcore_provider')
    new_name = form.getvalue('edit_gcore_provider_name')
    new_user = form.getvalue('edit_gcore_provider_user')
    new_pass = form.getvalue('edit_gcore_provider_pass')

    if sql.update_gcore_provider(new_name, new_user, new_pass, provider_id):
        print('ok')
        funct.logging('localhost', 'Provider has been renamed. New name is ' + new_name, provisioning=1)

if form.getvalue('edit_aws_provider'):
    funct.check_user_group()
    provider_id = form.getvalue('edit_aws_provider')
    new_name = form.getvalue('edit_aws_provider_name')
    new_key = form.getvalue('edit_aws_provider_key')
    new_secret = form.getvalue('edit_aws_provider_secret')

    if sql.update_aws_provider(new_name, new_key, new_secret, provider_id):
        print('ok')
        funct.logging('localhost', 'Provider has been renamed. New name is ' + new_name, provisioning=1)

if form.getvalue('loadservices'):
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_services.html')
    services = funct.get_services_status()

    template = template.render(services=services)
    print(template)

if form.getvalue('loadchecker'):
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_telegram.html')
    services = funct.get_services_status()
    groups = sql.select_groups()
    page = form.getvalue('page')
    if page == 'servers.py':
        user_group = funct.get_user_group(id=1)
        telegrams = sql.get_user_telegram_by_group(user_group)
        slacks = sql.get_user_slack_by_group(user_group)
    else:
        telegrams = sql.select_telegram()
        slacks = sql.select_slack()

    template = template.render(services=services,
                               telegrams=telegrams,
                               groups=groups,
                               slacks=slacks,
                               page=page)
    print(template)

if form.getvalue('load_update_hapwi'):
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_updatehapwi.html')

    versions = funct.versions()
    checker_ver = funct.check_new_version(service='checker')
    smon_ver = funct.check_new_version(service='smon')
    metrics_ver = funct.check_new_version(service='metrics')
    keep_ver = funct.check_new_version(service='keep')
    portscanner_ver = funct.check_new_version(service='portscanner')
    services = funct.get_services_status()

    template = template.render(services=services,
                               versions=versions,
                               checker_ver=checker_ver,
                               smon_ver=smon_ver,
                               metrics_ver=metrics_ver,
                               portscanner_ver=portscanner_ver,
                               keep_ver=keep_ver)
    print(template)

if form.getvalue('loadopenvpn'):
    import platform
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/load_openvpn.html')
    openvpn_configs = ''
    openvpn_sess = ''
    openvpn = ''

    try:
        os_name = platform.linux_distribution()[0]
    except Exception:
        os_name = ''

    if os_name == 'CentOS Linux' or os_name == 'Red Hat Enterprise Linux Server':
        stdout, stderr = funct.subprocess_execute("rpm --query openvpn3-client")
        if stdout[0] != 'package openvpn3-client is not installed' and stderr != '/bin/sh: rpm: command not found':
            cmd = "sudo openvpn3 configs-list |grep -E 'ovpn|(^|[^0-9])[0-9]{4}($|[^0-9])' |grep -v net|awk -F\"    \" '{print $1}'|awk 'ORS=NR%2?\" \":\"\\n\"'"
            openvpn_configs, stderr = funct.subprocess_execute(cmd)
            cmd = "sudo openvpn3 sessions-list|grep -E 'Config|Status'|awk -F\":\" '{print $2}'|awk 'ORS=NR%2?\" \":\"\\n\"'| sed 's/^ //g'"
            openvpn_sess, stderr = funct.subprocess_execute(cmd)
            openvpn = stdout[0]

    template = template.render(openvpn=openvpn,
                               openvpn_sess=openvpn_sess,
                               openvpn_configs=openvpn_configs)
    print(template)

if form.getvalue('check_telegram'):
    telegram_id = form.getvalue('check_telegram')
    mess = 'Test message from Roxy-WI'
    funct.telegram_send_mess(mess, telegram_channel_id=telegram_id)

if form.getvalue('check_slack'):
    slack_id = form.getvalue('check_slack')
    mess = 'Test message from Roxy-WI'
    funct.slack_send_mess(mess, slack_channel_id=slack_id)
