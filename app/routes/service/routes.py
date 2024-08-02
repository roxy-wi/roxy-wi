import distro
from flask import render_template, request, g
from flask_jwt_extended import jwt_required, get_jwt

from app import cache
from app.routes.service import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.user as user_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.service.keepalived as keepalived
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.overview as roxy_overview
from app.views.service.views import ServiceActionView, ServiceBackendView, ServiceView


bp.add_url_rule('/<service>/<server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action'), methods=['GET'])
bp.add_url_rule('/<service>/<server_id>/backend', view_func=ServiceBackendView.as_view('service_backend_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/backend', view_func=ServiceBackendView.as_view('service_backend'), methods=['GET'])
bp.add_url_rule('/<service>/<server_id>/status', view_func=ServiceView.as_view('service_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/status', view_func=ServiceView.as_view('service'), methods=['GET'])

@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/<service>', defaults={'serv': None})
@bp.route('/<service>/<serv>')
@check_services
@get_user_params()
def services(service, serv):
    tools = []
    service_desc = service_sql.select_service(service)
    servers = roxywi_common.get_dick_permit(virt=1, service=service_desc.slug)
    servers_with_status1 = []
    autorefresh = 0
    waf_server = ''
    cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
    keep_alive, stderr = server_mod.subprocess_execute(cmd)
    services_name = {'roxy-wi-checker': 'Master backends checker service',
                     'roxy-wi-keep_alive': 'Auto start service',
                     'roxy-wi-metrics': 'Master metrics service'}

    if len(servers) == 1:
        serv = servers[0][2]

    if serv:
        if roxywi_common.check_is_server_in_group(serv):
            servers = server_sql.select_servers(server=serv)
            autorefresh = 1
            waf_server = waf_sql.select_waf_servers(serv)
            server_id = server_sql.select_server_id_by_ip(serv)
            docker_settings = service_sql.select_docker_service_settings(server_id, service_desc.slug)
            restart_settings = service_sql.select_restart_service_settings(server_id, service_desc.slug)
        else:
            raise Exception('error: wrong group')
    else:
        docker_settings = service_sql.select_docker_services_settings(service_desc.slug)
        restart_settings = service_sql.select_restart_services_settings(service_desc.slug)

    for s, v in services_name.items():
        if distro.id() == 'ubuntu':
            if s == 'roxy-wi-keep_alive':
                s = 'roxy-wi-keep-alive'
            cmd = f"apt list --installed 2>&1 |grep {s}"
        else:
            cmd = "rpm --query " + s + "-* |awk -F\"" + s + "\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
        service_ver, stderr = server_mod.subprocess_execute(cmd)
        try:
            tools.append([s, service_ver[0]])
        except Exception:
            tools.append([s, ''])

    for s in servers:
        servers_with_status = list()
        servers_with_status.append(s[0])
        servers_with_status.append(s[1])
        servers_with_status.append(s[2])
        servers_with_status.append(s[11])
        if service == 'nginx':
            h = (['', ''],)
            cmd = ("/usr/sbin/nginx -v 2>&1|awk '{print $3}' && systemctl status nginx |grep -e 'Active' |awk "
                   "'{print $2, $9$10$11$12$13}' && ps ax |grep nginx:|grep -v grep |wc -l")
            for service_set in docker_settings:
                if service_set.server_id == s[0] and service_set.setting == 'dockerized' and service_set.value == '1':
                    container_name = sql.get_setting('nginx_container_name')
                    cmd =  ("docker exec -it " + container_name + " /usr/sbin/nginx -v 2>&1|awk '{print $3}' "
                            "&& docker ps -a -f name=" + container_name + " --format '{{.Status}}'|tail -1 && ps ax |grep nginx:|grep -v grep |wc -l")
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
            status1, status2 = keepalived.get_status(s[2])
            servers_with_status.append(status1)
            servers_with_status.append(status2)
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
            haproxy_sock_port = sql.get_setting('haproxy_sock_port')
            cmd = f'echo "show info" |nc {s[2]} {haproxy_sock_port} -w 1 -v|grep -e "Ver\|Uptime:\|Process_num"'
            out = server_mod.subprocess_execute(cmd)

            for k in out:
                if "Connection refused" not in k:
                    out1 = out
                else:
                    out1 = False
                servers_with_status.append(out1)

            servers_with_status.append(s[12])

        servers_with_status.append(server_sql.select_servers(server=s[2]))
        is_keepalived = service_sql.select_keepalived(s[2])

        if is_keepalived:
            try:
                cmd = ('sudo kill -USR1 `cat /var/run/keepalived.pid` && sudo grep State /tmp/keepalived.data -m 1 |'
                       'awk -F"=" \'{print $2}\'|tr -d \'[:space:]\' && sudo rm -f /tmp/keepalived.data')
                out = server_mod.ssh_command(s[2], cmd)
                out1 = ('1', out)
                servers_with_status.append(out1)
            except Exception as e:
                servers_with_status.append(str(e))
        else:
            servers_with_status.append('')

        servers_with_status1.append(servers_with_status)

    kwargs = {
        'clusters': ha_sql.select_ha_cluster_name_and_slaves(),
        'master_slave': server_sql.is_master(0, master_slave=1),
        'user_subscription': roxywi_common.return_user_subscription(),
        'autorefresh': autorefresh,
        'servers': servers_with_status1,
        'lang': g.user_params['lang'],
        'serv': serv,
        'service': service,
        'services': tools,
        'service_desc': service_desc,
        'restart_settings': restart_settings,
        'docker_settings': docker_settings,
        'waf_server': waf_server,
        'keep_alive': ''.join(keep_alive)
    }

    return render_template('service.html', **kwargs)


@bp.route('/<service>/<server_ip>/last-edit')
@check_services
def last_edit(service, server_ip):
    return service_common.get_overview_last_edit(server_ip, service)


@bp.route('/cpu-ram-metrics/<server_ip>/<server_id>/<name>/<service>')
@get_user_params()
def cpu_ram_metrics(server_ip, server_id, name, service):
    if service == 'haproxy':
        sock_port = sql.get_setting('haproxy_sock_port')
        cmd = f'echo "show info" |nc {server_ip} {sock_port} -w 1|grep -e "node\|Nbproc\|Maxco\|MB\|Nbthread"'
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

    servers = [[name, server_ip, return_out]]
    claims = get_jwt()
    kwargs = {
        'service_status': sorted(servers, key=common.get_key),
        'role': user_sql.get_user_role_in_group(claims['user_id'], claims['group']),
        'id': server_id,
        'service_page': service,
        'lang': g.user_params['lang']
    }

    return render_template('ajax/overviewServers.html', **kwargs)


@bp.post('/haproxy/bytes')
def show_haproxy_bytes():
    server_ip = common.is_ip_or_dns(request.form.get('showBytes'))

    try:
        return roxy_overview.show_haproxy_binout(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.post('/nginx/connections')
def show_nginx_connections():
    server_ip = common.is_ip_or_dns(request.form.get('nginxConnections'))

    try:
        return roxy_overview.show_nginx_connections(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.post('/apache/bytes')
def show_apache_bytes():
    server_ip = common.is_ip_or_dns(request.form.get('apachekBytes'))

    try:
        return roxy_overview.show_apache_bytes(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.post('/keepalived/become-master')
@cache.cached()
def show_keepalived_become_master():
    server_ip = common.is_ip_or_dns(request.form.get('keepalivedBecameMaster'))

    return roxy_overview.keepalived_became_master(server_ip)


@bp.route('/position/<int:server_id>/<int:pos>')
def change_pos(server_id, pos):
    return server_sql.update_server_pos(pos, server_id)


@bp.route('/settings/<service>/<int:server_id>')
@check_services
def show_service_settings(service, server_id):
    settings = service_sql.select_service_settings(server_id, service)
    return render_template('ajax/service_settings.html', settings=settings, service=service)


@bp.post('/settings/<service>')
@check_services
def save_service_settings(service):
    server_id = common.checkAjaxInput(request.form.get('serverSettingsSave'))
    haproxy_enterprise = common.checkAjaxInput(request.form.get('serverSettingsEnterprise'))
    service_dockerized = common.checkAjaxInput(request.form.get('serverSettingsDockerized'))
    service_restart = common.checkAjaxInput(request.form.get('serverSettingsRestart'))
    server_ip = server_sql.select_server_ip_by_id(server_id)
    service_docker = f'Service {service.title()} has been flagged as a dockerized'
    service_systemd = f'Service {service.title()} has been flagged as a system service'
    disable_restart = f'Restart option is disabled for {service.title()} service'
    enable_restart = f'Restart option is disabled for {service.title()} service'

    if service == 'haproxy':
        if service_sql.insert_or_update_service_setting(server_id, service, 'haproxy_enterprise', haproxy_enterprise):
            if haproxy_enterprise == '1':
                roxywi_common.logging(server_ip, 'Service has been flagged as an Enterprise version', roxywi=1, login=1,
                                      keep_history=1, service=service)
            else:
                roxywi_common.logging(server_ip, 'Service has been flagged as a community version', roxywi=1, login=1,
                                      keep_history=1, service=service)

    if service_sql.insert_or_update_service_setting(server_id, service, 'dockerized', service_dockerized):
        if service_dockerized == '1':
            roxywi_common.logging(server_ip, service_docker, roxywi=1, login=1, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, service_systemd, roxywi=1, login=1, keep_history=1, service=service)

    if service_sql.insert_or_update_service_setting(server_id, service, 'restart', service_restart):
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
    service_sql.update_hapwi_server(server_id, alert, metrics, active, service)
    server_ip = server_sql.select_server_ip_by_id(server_id)
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
