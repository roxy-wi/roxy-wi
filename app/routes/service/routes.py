import os
import sys
from functools import wraps

import distro
from flask import render_template, request, redirect, url_for, abort
from flask_login import login_required

from app import cache
from app.routes.service import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.service.action as service_action
import modules.service.common as service_common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.roxywi.overview as roxy_overview


def check_services(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        service = kwargs['service']
        if service not in ('haproxy', 'nginx', 'apache', 'keepalived'):
            abort(400, 'bad service')
        return fn(*args, **kwargs)
    return decorated_view


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>', defaults={'serv': None})
@bp.route('/<service>/<serv>')
@check_services
def services(service, serv):
    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    services = []
    servers: object
    autorefresh = 0
    waf_server = ''
    cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
    keep_alive, stderr = server_mod.subprocess_execute(cmd)

    service_desc = sql.select_service(service)
    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    if serv:
        if roxywi_common.check_is_server_in_group(serv):
            servers = sql.select_servers(server=serv)
            autorefresh = 1
            waf_server = sql.select_waf_servers(serv)
            server_id = sql.select_server_id_by_ip(serv)
            docker_settings = sql.select_docker_service_settings(server_id, service_desc.slug)
            restart_settings = sql.select_restart_service_settings(server_id, service_desc.slug)
        else:
            raise Exception('error: wrong group')
    else:
        servers = roxywi_common.get_dick_permit(virt=1, service=service_desc.slug)
        docker_settings = sql.select_docker_services_settings(service_desc.slug)
        restart_settings = sql.select_restart_services_settings(service_desc.slug)

    services_name = {'roxy-wi-checker': 'Master backends checker service',
                     'roxy-wi-keep_alive': 'Auto start service',
                     'roxy-wi-metrics': 'Master metrics service'}
    for s, v in services_name.items():
        if distro.id() == 'ubuntu':
            if s == 'roxy-wi-keep_alive':
                s = 'roxy-wi-keep-alive'
            cmd = "apt list --installed 2>&1 |grep " + s
        else:
            cmd = "rpm --query " + s + "-* |awk -F\"" + s + "\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
        service_ver, stderr = server_mod.subprocess_execute(cmd)
        try:
            services.append([s, service_ver[0]])
        except Exception:
            services.append([s, ''])

    haproxy_sock_port = sql.get_setting('haproxy_sock_port')
    servers_with_status1 = []
    out1 = ''
    if len(servers) == 1:
        serv = servers[0][2]
    for s in servers:
        servers_with_status = list()
        servers_with_status.append(s[0])
        servers_with_status.append(s[1])
        servers_with_status.append(s[2])
        servers_with_status.append(s[11])
        if service == 'nginx':
            h = (['', ''],)
            cmd = [
                "/usr/sbin/nginx -v 2>&1|awk '{print $3}' && systemctl status nginx |grep -e 'Active' |awk "
                "'{print $2, $9$10$11$12$13}' && ps ax |grep nginx:|grep -v grep |wc -l"]
            for service_set in docker_settings:
                if service_set.server_id == s[0] and service_set.setting == 'dockerized' and service_set.value == '1':
                    container_name = sql.get_setting('nginx_container_name')
                    cmd = [
                        "docker exec -it " + container_name + " /usr/sbin/nginx -v 2>&1|awk '{print $3}' && "
                                                              "docker ps -a -f name=" + container_name + " --format '{{.Status}}'|tail -1 && ps ax |grep nginx:"
                                                                                                         "|grep -v grep |wc -l"
                    ]
            try:
                out = server_mod.ssh_command(s[2], cmd)
                h = ()
                out1 = []
                for k in out.split():
                    out1.append(k)
                h = (out1,)
                servers_with_status.append(h)
                servers_with_status.append(h)
                servers_with_status.append(s[17])
            except Exception:
                servers_with_status.append(h)
                servers_with_status.append(h)
                servers_with_status.append(s[17])
        elif service == 'keepalived':
            h = (['', ''],)
            cmd = [
                "/usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}' && systemctl status keepalived |"
                "grep -e 'Active' |awk '{print $2, $9$10$11$12$13}' && ps ax |grep keepalived|grep -v grep |wc -l"
            ]
            try:
                out = server_mod.ssh_command(s[2], cmd)
                out1 = []
                for k in out.split():
                    out1.append(k)
                h = (out1,)
                servers_with_status.append(h)
                servers_with_status.append(h)
                servers_with_status.append(s[22])
            except Exception:
                servers_with_status.append(h)
                servers_with_status.append(h)
                servers_with_status.append(s[22])
        elif service == 'apache':
            h = (['', ''],)
            apache_stats_user = sql.get_setting('apache_stats_user')
            apache_stats_password = sql.get_setting('apache_stats_password')
            apache_stats_port = sql.get_setting('apache_stats_port')
            apache_stats_page = sql.get_setting('apache_stats_page')
            cmd = "curl -s -u %s:%s http://%s:%s/%s?auto |grep 'ServerVersion\|Processes\|ServerUptime:'" % (
                apache_stats_user, apache_stats_password, s[2], apache_stats_port, apache_stats_page
            )
            try:
                out = server_mod.subprocess_execute(cmd)
                if out != '':
                    for k in out:
                        servers_with_status.append(k)
                    servers_with_status.append(s[22])
            except Exception:
                servers_with_status.append(h)
                servers_with_status.append(h)
                servers_with_status.append(s[22])
        else:
            cmd = 'echo "show info" |nc %s %s -w 1 -v|grep -e "Ver\|Uptime:\|Process_num"' % (s[2], haproxy_sock_port)
            out = server_mod.subprocess_execute(cmd)

            for k in out:
                if "Connection refused" not in k:
                    out1 = out
                else:
                    out1 = False
                servers_with_status.append(out1)

            servers_with_status.append(s[12])

        servers_with_status.append(sql.is_master(s[2]))
        servers_with_status.append(sql.select_servers(server=s[2]))

        is_keepalived = sql.select_keepalived(s[2])

        if is_keepalived:
            try:
                cmd = ['sudo kill -USR1 `cat /var/run/keepalived.pid` && sudo grep State /tmp/keepalived.data -m 1 |'
                       'awk -F"=" \'{print $2}\'|tr -d \'[:space:]\' && sudo rm -f /tmp/keepalived.data']
                out = server_mod.ssh_command(s[2], cmd)
                out1 = ('1', out)
                servers_with_status.append(out1)
            except Exception as e:
                servers_with_status.append(str(e))
        else:
            servers_with_status.append('')

        servers_with_status1.append(servers_with_status)

    user_subscription = roxywi_common.return_user_subscription()

    return render_template(
        'hapservers.html', h2=1, autorefresh=autorefresh, role=user_params['role'], user=user, servers=servers_with_status1,
        keep_alive=''.join(keep_alive), serv=serv, service=service, services=services, user_services=user_params['user_services'],
        docker_settings=docker_settings, user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'],
        waf_server=waf_server, restart_settings=restart_settings, service_desc=service_desc, token=user_params['token'],
        lang=user_params['lang']
    )


@bp.post('/action/<service>/check-service')
@check_services
def check_service(service):
    user_uuid = request.cookies.get('uuid')
    server_ip = common.checkAjaxInput(request.form.get('server_ip'))

    try:
        return service_action.check_service(server_ip, user_uuid, service)
    except Exception:
        pass


@bp.route('/action/<service>/<server_ip>/<action>', methods=['GET'])
def action_service(service, server_ip, action):
    server_ip = common.is_ip_or_dns(server_ip)

    return service_action.common_action(server_ip, action, service)


@bp.route('/<service>/<server_ip>/last-edit')
def last_edit(service, server_ip):
    return service_common.get_overview_last_edit(server_ip, service)


@bp.route('/cpu-ram-metrics/<server_ip>/<server_id>/<name>/<service>')
def cpu_ram_metrics(server_ip, server_id, name, service):
    user_params = roxywi_common.get_users_params()

    if service == 'haproxy':
        cmd = 'echo "show info" |nc %s %s -w 1|grep -e "node\|Nbproc\|Maxco\|MB\|Nbthread"' % (server_ip, sql.get_setting('haproxy_sock_port'))
        out = server_mod.subprocess_execute(cmd)
        return_out = ""

        for k in out:
            if "Ncat:" not in k:
                for r in k:
                    return_out += r
                    return_out += "\n"
            else:
                return_out = "Cannot connect to HAProxy"
    else:
        return_out = ''

    server_status = (name, server_ip, return_out)

    servers = []
    user_id = request.cookies.get('uuid')
    group_id = int(request.cookies.get('group'))
    role = sql.get_user_role_by_uuid(user_id, group_id)

    servers.append(server_status)
    servers_sorted = sorted(servers, key=common.get_key)

    return render_template(
        'ajax/overviewServers.html', service_status=servers_sorted, role=role, id=server_id, service_page=service, lang=user_params['lang']
    )


@bp.route('/haproxy/bytes', methods=['POST'])
def show_haproxy_bytes():
    server_ip = common.is_ip_or_dns(request.form.get('showBytes'))

    return roxy_overview.show_haproxy_binout(server_ip)


@bp.route('/nginx/connections', methods=['POST'])
def show_nginx_connections():
    server_ip = common.is_ip_or_dns(request.form.get('nginxConnections'))

    return roxy_overview.show_nginx_connections(server_ip)


@bp.route('/apache/bytes', methods=['POST'])
def show_apache_bytes():
    server_ip = common.is_ip_or_dns(request.form.get('apachekBytes'))

    return roxy_overview.show_apache_bytes(server_ip)


@bp.route('/keepalived/become-master', methods=['POST'])
@cache.cached()
def show_keepalived_become_master():
    server_ip = common.is_ip_or_dns(request.form.get('keepalivedBecameMaster'))

    return roxy_overview.keepalived_became_master(server_ip)


@bp.route('/<service>/backends/<server_ip>')
@cache.cached()
def show_service_backends(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return service_common.overview_backends(server_ip, service)


@bp.route('/position/<int:server_id>/<int:pos>')
def change_pos(server_id, pos):
    return sql.update_server_pos(pos, server_id)


@bp.route('/haproxy/version/<server_ip>')
def get_haproxy_v(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return service_common.check_haproxy_version(server_ip)


@bp.route('/settings/<service>/<int:server_id>')
@check_services
def show_service_settings(service, server_id):
    settings = sql.select_service_settings(server_id, service)
    return render_template('ajax/service_settings.html', settings=settings, service=service)


@bp.post('/settings/<service>')
@check_services
def save_service_settings(service):
    server_id = common.checkAjaxInput(request.form.get('serverSettingsSave'))
    haproxy_enterprise = common.checkAjaxInput(request.form.get('serverSettingsEnterprise'))
    service_dockerized = common.checkAjaxInput(request.form.get('serverSettingsDockerized'))
    service_restart = common.checkAjaxInput(request.form.get('serverSettingsRestart'))
    server_ip = sql.select_server_ip_by_id(server_id)
    service_docker = f'Service {service.title()} has been flagged as a dockerized'
    service_systemd = f'Service {service.title()} has been flagged as a system service'
    disable_restart = f'Restart option is disabled for {service.title()} service'
    enable_restart = f'Restart option is disabled for {service.title()} service'

    if service == 'haproxy':
        if sql.insert_or_update_service_setting(server_id, service, 'haproxy_enterprise', haproxy_enterprise):
            if haproxy_enterprise == '1':
                roxywi_common.logging(server_ip, 'Service has been flagged as an Enterprise version', roxywi=1, login=1,
                                      keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a community version', roxywi=1, login=1,
                                      keep_history=1, service=service)

    if sql.insert_or_update_service_setting(server_id, service, 'dockerized', service_dockerized):
        if service_dockerized == '1':
            roxywi_common.logging(server_ip, service_docker, roxywi=1, login=1, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, service_systemd, roxywi=1, login=1, keep_history=1, service=service)

    if sql.insert_or_update_service_setting(server_id, service, 'restart', service_restart):
        if service_restart == '1':
            roxywi_common.logging(server_ip, disable_restart, roxywi=1, login=1, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, enable_restart, roxywi=1, login=1, keep_history=1, service=service)

    return 'ok'


@bp.post('/<service>/tools/update')
@check_services
def update_tools_enable(service):
    server_id = request.form.get('server_id')
    active = request.form.get('active')
    name = request.form.get('name')
    alert = request.form.get('alert_en')
    metrics = request.form.get('metrics')
    sql.update_hapwi_server(server_id, alert, metrics, active, service)
    server_ip = sql.select_server_ip_by_id(server_id)
    roxywi_common.logging(server_ip, f'The server {name} has been updated ', roxywi=1, login=1, keep_history=1,
                          service=service)

    return 'ok'


@bp.route('/check-restart/<server_ip>')
def check_restart(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    servers = roxywi_common.get_dick_permit(ip=server_ip)
    for server in servers:
        if server != "":
            return 'ok'

    return 'nothing'
