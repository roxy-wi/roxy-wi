import os
import http.cookies

import requests
from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.logs as roxy_logs
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod
import modules.service.common as service_common


def user_ovw() -> None:
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_users_ovw.html')

    lang = roxywi_common.get_user_lang()
    roles = sql.select_roles()
    user_params = roxywi_common.get_users_params()
    users_groups = sql.select_user_groups_with_names(1, all=1)
    user_group = roxywi_common.get_user_group(id=1)

    if (user_params['role'] == 2 or user_params['role'] == 3) and int(user_group) != 1:
        users = sql.select_users(group=user_group)
    else:
        users = sql.select_users()

    template = template.render(users=users, users_groups=users_groups, lang=lang, roles=roles)
    print(template)


def show_sub_ovw() -> None:
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    lang = roxywi_common.get_user_lang()
    template = env.get_template('ajax/show_sub_ovw.html')
    template = template.render(sub=sql.select_user_all(), lang=lang)
    print(template)


def show_overview(serv) -> None:
    import asyncio

    async def async_get_overview(serv1, serv2, user_uuid, server_id):
        user_id = sql.get_user_id_by_uuid(user_uuid)
        user_services = sql.select_user_services(user_id)

        haproxy = sql.select_haproxy(serv) if '1' in user_services else 0
        nginx = sql.select_nginx(serv) if '2' in user_services else 0
        keepalived = sql.select_keepalived(serv) if '3' in user_services else 0
        apache = sql.select_apache(serv) if '4' in user_services else 0

        waf = sql.select_waf_servers(serv2)
        haproxy_process = ''
        keepalived_process = ''
        nginx_process = ''
        apache_process = ''
        waf_process = ''

        try:
            waf_len = len(waf)
        except Exception:
            waf_len = 0

        if haproxy:
            cmd = f'echo "show info" |nc {serv2} {sql.get_setting("haproxy_sock_port")} -w 1|grep -e "Process_num"'
            haproxy_process = service_common.server_status(server_mod.subprocess_execute(cmd))

        if nginx:
            nginx_cmd = f'echo "something" |nc {serv2} {sql.get_setting("nginx_stats_port")} -w 1'
            nginx_process = service_common.server_status(server_mod.subprocess_execute(nginx_cmd))

        if apache:
            apache_cmd = f'echo "something" |nc {serv2} {sql.get_setting("apache_stats_port")} -w 1'
            apache_process = service_common.server_status(server_mod.subprocess_execute(apache_cmd))

        if keepalived:
            command = ["ps ax |grep keepalived|grep -v grep|wc -l|tr -d '\n'"]
            try:
                keepalived_process = server_mod.ssh_command(serv2, command)
            except Exception as e:
                print(f'error: {e} for server {serv2}')
                return

        if waf_len >= 1:
            command = ["ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"]
            try:
                waf_process = server_mod.ssh_command(serv2, command)
            except Exception as e:
                print(f'error: {e} for server {serv2}')
                return

        server_status = (serv1,
                         serv2,
                         haproxy,
                         haproxy_process,
                         waf_process,
                         waf,
                         keepalived,
                         keepalived_process,
                         nginx,
                         nginx_process,
                         server_id,
                         apache,
                         apache_process)
        return server_status

    async def get_runner_overview():
        env = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
                          extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do'])

        servers = []
        template = env.get_template('ajax/overview.html')
        cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
        user_uuid = cookie.get('uuid')
        group_id = cookie.get('group')
        group_id = int(group_id.value)
        lang = roxywi_common.get_user_lang()
        role = sql.get_user_role_by_uuid(user_uuid.value, group_id)
        futures = [async_get_overview(server[1], server[2], user_uuid.value, server[0]) for server in
                   sql.select_servers(server=serv)]
        for i, future in enumerate(asyncio.as_completed(futures)):
            result = await future
            servers.append(result)
        servers_sorted = sorted(servers, key=common.get_key)
        template = template.render(service_status=servers_sorted, role=role, lang=lang)
        print(template)

    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(get_runner_overview())
    ioloop.close()


def show_haproxy_binout(server_ip: str) -> None:
    port = sql.get_setting('haproxy_sock_port')
    bin_bout = []
    cmd = "echo 'show stat' |nc {} {} |cut -d ',' -f 1-2,9|grep -E '[0-9]'|awk -F',' '{{sum+=$3;}}END{{print sum;}}'".format(
        server_ip, port)
    bit_in, stderr = server_mod.subprocess_execute(cmd)
    bin_bout.append(bit_in[0])
    cmd = "echo 'show stat' |nc {} {} |cut -d ',' -f 1-2,10|grep -E '[0-9]'|awk -F',' '{{sum+=$3;}}END{{print sum;}}'".format(
        server_ip, port)
    bout, stderr1 = server_mod.subprocess_execute(cmd)
    bin_bout.append(bout[0])
    cmd = "echo 'show stat' |nc {} {} |cut -d ',' -f 1-2,5|grep -E '[0-9]'|awk -F',' '{{sum+=$3;}}END{{print sum;}}'".format(
        server_ip, port)
    cin, stderr2 = server_mod.subprocess_execute(cmd)
    bin_bout.append(cin[0])
    cmd = "echo 'show stat' |nc {} {} |cut -d ',' -f 1-2,8|grep -E '[0-9]'|awk -F',' '{{sum+=$3;}}END{{print sum;}}'".format(
        server_ip, port)
    cout, stderr3 = server_mod.subprocess_execute(cmd)
    bin_bout.append(cout[0])
    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
    template = env.get_template('ajax/bin_bout.html')
    template = template.render(bin_bout=bin_bout, serv=server_ip, service='haproxy', lang=lang)
    print(template)


def show_nginx_connections(server_ip: str) -> None:
    port = sql.get_setting('nginx_stats_port')
    user = sql.get_setting('nginx_stats_user')
    password = sql.get_setting('nginx_stats_password')
    page = sql.get_setting('nginx_stats_page')
    url = f'http://{server_ip}:{port}/{page}'

    r = requests.get(url, auth=(user, password))

    if r.status_code == 200:
        bin_bout = [0, 0]
        for num, line in enumerate(r.text.split('\n')):
            if num == 0:
                bin_bout.append(line.split(' ')[2])
            if num == 2:
                bin_bout.append(line.split(' ')[3])

        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('ajax/bin_bout.html')
        template = template.render(bin_bout=bin_bout, serv=server_ip, service='nginx', lang=lang)
        print(template)
    else:
        print('error: cannot connect to NGINX stat page')


def show_apache_bytes(server_ip: str) -> None:
    port = sql.get_setting('apache_stats_port')
    user = sql.get_setting('apache_stats_user')
    password = sql.get_setting('apache_stats_password')
    page = sql.get_setting('apache_stats_page')
    bin_bout = []
    url = f'http://{server_ip}:{port}/{page}?auto'

    r = requests.get(url, auth=(user, password))

    if r.status_code == 200:
        for line in r.text.split('\n'):
            if 'ReqPerSec' in line or 'BytesPerSec' in line:
                bin_bout.append(line.split(' ')[1])

        lang = roxywi_common.get_user_lang()
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('ajax/bin_bout.html')
        template = template.render(bin_bout=bin_bout, serv=server_ip, service='apache', lang=lang)
        print(template)
    else:
        print('error: cannot connect to Apache stat page')


def show_services_overview() -> None:
    import psutil
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_services_ovw.html')
    user_params = roxywi_common.get_users_params()
    grafana = 0
    metrics_worker = 0
    checker_worker = 0
    servers_group = []
    host = os.environ.get('HTTP_HOST', '')
    user_group = roxywi_common.get_user_group(id=1)
    lang = roxywi_common.get_user_lang()

    if (user_params['role'] == 2 or user_params['role'] == 3) and int(user_group) != 1:
        for s in user_params['servers']:
            servers_group.append(s[2])

    is_checker_worker = len(sql.select_all_alerts(group=user_group))
    is_metrics_worker = len(sql.select_servers_metrics_for_master(group=user_group))

    for pids in psutil.pids():
        if pids < 300:
            continue
        try:
            pid = psutil.Process(pids)
            cmdline_out = pid.cmdline()
            if len(cmdline_out) > 2:
                if 'checker_' in cmdline_out[1]:
                    if len(servers_group) > 0:
                        if cmdline_out[2] in servers_group:
                            checker_worker += 1
                    else:
                        checker_worker += 1
                elif 'metrics_' in cmdline_out[1]:
                    if len(servers_group) > 0:
                        if cmdline_out[2] in servers_group:
                            metrics_worker += 1
                    else:
                        metrics_worker += 1
                if len(servers_group) == 0:
                    if 'grafana' in cmdline_out[1]:
                        grafana += 1
        except psutil.NoSuchProcess:
            pass

    cmd = "systemctl is-active roxy-wi-metrics"
    metrics_master, stderr = server_mod.subprocess_execute(cmd)
    cmd = "systemctl is-active roxy-wi-checker"
    checker_master, stderr = server_mod.subprocess_execute(cmd)
    cmd = "systemctl is-active roxy-wi-keep_alive"
    keep_alive, stderr = server_mod.subprocess_execute(cmd)
    cmd = "systemctl is-active roxy-wi-smon"
    smon, stderr = server_mod.subprocess_execute(cmd)
    cmd = "systemctl is-active roxy-wi-portscanner"
    port_scanner, stderr = server_mod.subprocess_execute(cmd)
    cmd = "systemctl is-active roxy-wi-socket"
    socket, stderr = server_mod.subprocess_execute(cmd)

    rendered_template = template.render(
        role=user_params['role'], metrics_master=''.join(metrics_master), metrics_worker=metrics_worker,
        checker_master=''.join(checker_master), checker_worker=checker_worker, keep_alive=''.join(keep_alive),
        smon=''.join(smon), port_scanner=''.join(port_scanner), grafana=grafana, socket=''.join(socket),
        is_checker_worker=is_checker_worker, is_metrics_worker=is_metrics_worker, host=host,
        roxy_wi_log_id=roxy_logs.roxy_wi_log(log_id=1, file="roxy-wi-"),
        metrics_log_id=roxy_logs.roxy_wi_log(log_id=1, file="metrics"),
        checker_log_id=roxy_logs.roxy_wi_log(log_id=1, file="checker"),
        keep_alive_log_id=roxy_logs.roxy_wi_log(log_id=1, file="keep_alive"),
        socket_log_id=roxy_logs.roxy_wi_log(log_id=1, file="socket"), error=stderr, lang=lang
    )
    print(rendered_template)


def keepalived_became_master(server_ip) -> None:
    commands = ["sudo kill -USR2 $(cat /var/run/keepalived.pid) && sudo grep 'Became master' /tmp/keepalived.stats |awk '{print $3}'"]
    became_master = server_mod.ssh_command(server_ip, commands)
    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('ajax/bin_bout.html')
    template = template.render(bin_bout=became_master, serv=server_ip, service='keepalived', lang=lang)
    print(template)
