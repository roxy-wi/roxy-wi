import psutil
import requests
from flask import render_template, request
from flask_jwt_extended import get_jwt
from flask_jwt_extended import verify_jwt_in_request

import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.roxy as roxy_sql
import app.modules.db.user as user_sql
import app.modules.db.metric as metric_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.checker as checker_sql
import app.modules.common.common as common
import app.modules.tools.common as tools_common
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.service.common as service_common


def user_owv() -> str:
    lang = roxywi_common.get_user_lang_for_flask()
    roles = sql.select_roles()
    user_params = roxywi_common.get_users_params()
    users_groups = user_sql.select_user_groups_with_names(1, all=1)
    user_group = roxywi_common.get_user_group(id=1)

    if (user_params['role'] == 2 or user_params['role'] == 3) and int(user_group) != 1:
        users = user_sql.select_users(group=user_group)
    else:
        users = user_sql.select_users()

    return render_template('ajax/show_users_ovw.html', users=users, users_groups=users_groups, lang=lang, roles=roles)


def show_sub_ovw() -> str:
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template('ajax/show_sub_ovw.html', sub=roxy_sql.get_user(), lang=lang)


def show_overview(serv) -> str:
    servers = []
    verify_jwt_in_request()
    claims = get_jwt()
    lang = roxywi_common.get_user_lang_for_flask()
    role = user_sql.get_user_role_in_group(claims['user_id'], claims['group'])
    server = server_sql.get_server_by_ip(serv)
    user_services = user_sql.select_user_services(claims['user_id'])

    haproxy = server.apache if '1' in user_services else 0
    nginx = server.nginx if '2' in user_services else 0
    keepalived = server.keepalived if '3' in user_services else 0
    apache = server.apache if '4' in user_services else 0

    waf = waf_sql.select_waf_servers(server.ip)
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
        cmd = f'echo "show info" |nc {server.ip} {sql.get_setting("haproxy_sock_port")} -w 1|grep -e "Process_num"'
        try:
            haproxy_process = service_common.server_status(server_mod.subprocess_execute(cmd))
        except Exception as e:
            return f'error: {e} for server {server.hostname}'

    if nginx:
        nginx_cmd = f'echo "something" |nc {server.ip} {sql.get_setting("nginx_stats_port")} -w 1'
        try:
            nginx_process = service_common.server_status(server_mod.subprocess_execute(nginx_cmd))
        except Exception as e:
            return f'error: {e} for server {server.hostname}'

    if apache:
        apache_cmd = f'echo "something" |nc {server.ip} {sql.get_setting("apache_stats_port")} -w 1'
        try:
            apache_process = service_common.server_status(server_mod.subprocess_execute(apache_cmd))
        except Exception as e:
            return f'error: {e} for server {server.hostname}'

    if keepalived:
        command = "ps ax |grep keepalived|grep -v grep|wc -l|tr -d '\n'"
        try:
            keepalived_process = server_mod.ssh_command(server.ip, command)
        except Exception as e:
            return f'error: {e} for server {server.hostname}'

    if waf_len >= 1:
        command = "ps ax |grep waf/bin/modsecurity |grep -v grep |wc -l"
        try:
            waf_process = server_mod.ssh_command(server.ip, command)
        except Exception as e:
            return f'error: {e} for server {server.hostname}'

    server_status = (
        server.hostname, server.ip, haproxy, haproxy_process, waf_process, waf, keepalived, keepalived_process, nginx,
        nginx_process, server.server_id, apache, apache_process
    )

    servers.append(server_status)
    servers_sorted = sorted(servers, key=common.get_key)

    return render_template('ajax/overview.html', service_status=servers_sorted, role=role, lang=lang)


def show_haproxy_binout(server_ip: str) -> str:
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
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template('ajax/bin_bout.html', bin_bout=bin_bout, serv=server_ip, service='haproxy', lang=lang)


def show_nginx_connections(server_ip: str) -> str:
    port = sql.get_setting('nginx_stats_port')
    user = sql.get_setting('nginx_stats_user')
    password = sql.get_setting('nginx_stats_password')
    page = sql.get_setting('nginx_stats_page')
    url = f'http://{server_ip}:{port}/{page}'

    try:
        r = requests.get(url, auth=(user, password), timeout=5)
    except Exception as e:
        raise Exception(e)

    if r.status_code == 200:
        bin_bout = [0, 0]
        for num, line in enumerate(r.text.split('\n')):
            if num == 0:
                bin_bout.append(line.split(' ')[2])
            if num == 2:
                bin_bout.append(line.split(' ')[3])

        lang = roxywi_common.get_user_lang_for_flask()
        return render_template('ajax/bin_bout.html', bin_bout=bin_bout, serv=server_ip, service='nginx', lang=lang)
    else:
        raise Exception('Cannot connect to NGINX stat page')


def show_apache_bytes(server_ip: str) -> str:
    port = sql.get_setting('apache_stats_port')
    user = sql.get_setting('apache_stats_user')
    password = sql.get_setting('apache_stats_password')
    page = sql.get_setting('apache_stats_page')
    bin_bout = []
    url = f'http://{server_ip}:{port}/{page}?auto'

    try:
        r = requests.get(url, auth=(user, password), timeout=5)
    except Exception as e:
        raise Exception(e)

    if r.status_code == 200:
        for line in r.text.split('\n'):
            if 'ReqPerSec' in line or 'BytesPerSec' in line:
                bin_bout.append(line.split(' ')[1])

        lang = roxywi_common.get_user_lang_for_flask()
        return render_template('ajax/bin_bout.html', bin_bout=bin_bout, serv=server_ip, service='apache', lang=lang)
    else:
        raise Exception('Cannot connect to Apache stat page')


def show_services_overview():
    user_params = roxywi_common.get_users_params()
    grafana = 0
    metrics_worker = 0
    checker_worker = 0
    servers_group = []
    host = request.host
    user_group = roxywi_common.get_user_group(id=1)
    lang = roxywi_common.get_user_lang_for_flask()

    if (user_params['role'] == 2 or user_params['role'] == 3) and int(user_group) != 1:
        for s in user_params['servers']:
            servers_group.append(s[2])

    is_checker_worker = len(checker_sql.select_all_alerts(user_group))
    is_metrics_worker = len(metric_sql.select_servers_metrics_for_master(user_group))

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

    roxy_tools = roxy_sql.get_roxy_tools()
    roxy_tools_status = {}
    for tool in roxy_tools:
        if tool == 'roxy-wi-prometheus-exporter':
            continue
        status = tools_common.is_tool_active(tool)
        roxy_tools_status.setdefault(tool, status)

    return render_template(
        'ajax/show_services_ovw.html', role=user_params['role'], roxy_tools_status=roxy_tools_status, grafana=grafana,
        is_checker_worker=is_checker_worker, is_metrics_worker=is_metrics_worker, host=host,
        checker_worker=checker_worker, metrics_worker=metrics_worker, lang=lang
    )


def keepalived_became_master(server_ip) -> str:
    commands = "sudo kill -USR2 $(cat /var/run/keepalived.pid) && sudo grep 'Became master' /tmp/keepalived.stats |awk '{print $3}'"
    became_master = server_mod.ssh_command(server_ip, commands)
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template('ajax/bin_bout.html', bin_bout=became_master, serv=server_ip, service='keepalived', lang=lang)
