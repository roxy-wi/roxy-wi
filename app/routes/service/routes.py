from typing import Union

import distro
from flask import render_template, request, g
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress

from app import cache
from app.routes.service import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.overview as roxy_overview
from app.views.service.views import ServiceActionView, ServiceBackendView, ServiceView
from app.views.service.lets_encrypt_views import LetsEncryptView, LetsEncryptsView
from app.modules.roxywi.class_models import DomainName

bp.add_url_rule('/<service>/<server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/<any(start, stop, reload, restart):action>', view_func=ServiceActionView.as_view('service_action'), methods=['GET'])
bp.add_url_rule('/<service>/<server_id>/backend', view_func=ServiceBackendView.as_view('service_backend_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/backend', view_func=ServiceBackendView.as_view('service_backend'), methods=['GET'])
bp.add_url_rule('/<service>/<server_id>/status', view_func=ServiceView.as_view('service_ip'), methods=['GET'])
bp.add_url_rule('/<service>/<int:server_id>/status', view_func=ServiceView.as_view('service'), methods=['GET'])
bp.add_url_rule('/letsencrypt', view_func=LetsEncryptView.as_view('le_web'), methods=['POST'])
bp.add_url_rule('/letsencrypt/<int:le_id>', view_func=LetsEncryptView.as_view('le_web_id'), methods=['GET', 'PUT', 'DELETE'])
bp.add_url_rule('/letsencrypts', view_func=LetsEncryptsView.as_view('le_webs'), methods=['GET'])


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
            waf_server = waf_sql.select_waf_servers(serv)
            server_id = server_sql.get_server_by_ip(serv).server_id
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
        servers_with_status.append(server_sql.select_servers(server=s[2]))
        is_keepalived = s[13]

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
@validate()
def last_edit(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    return service_common.get_overview_last_edit(str(server_ip), service)


@bp.route('/<service>/ssl')
@check_services
@get_user_params()
def ssl_service(service):
    return render_template('ssl.html', lang=g.user_params['lang'])


@bp.route('/cpu-ram-metrics/<server_ip>/<server_id>/<name>/<service>')
@get_user_params()
@validate()
def cpu_ram_metrics(server_ip: Union[IPvAnyAddress, DomainName], server_id: int, name: str, service: str):
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

    servers = [[name, str(server_ip), return_out]]
    kwargs = {
        'service_status': sorted(servers, key=common.get_key),
        'id': server_id,
        'service_page': service,
        'lang': g.user_params['lang']
    }

    return render_template('ajax/overviewServers.html', **kwargs)


@bp.get('/haproxy/bytes/<server_ip>')
@validate()
def show_haproxy_bytes(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_haproxy_binout(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.get('/nginx/connections/<server_ip>')
@validate()
def show_nginx_connections(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_nginx_connections(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.get('/apache/bytes/<server_ip>')
@validate()
def show_apache_bytes(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return roxy_overview.show_apache_bytes(server_ip)
    except Exception as e:
        return f'error: {e}'


@bp.get('/keepalived/become-master/<server_ip>')
@validate()
@cache.cached()
def show_keepalived_become_master(server_ip: Union[IPvAnyAddress, DomainName]):
    return roxy_overview.keepalived_became_master(str(server_ip))


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
    server_id = int(request.form.get('serverSettingsSave'))
    service_dockerized = int(request.form.get('serverSettingsDockerized'))
    service_restart = int(request.form.get('serverSettingsRestart'))
    server_ip = server_sql.get_server(server_id).ip
    service_docker = f'Service {service.title()} has been flagged as a dockerized'
    service_systemd = f'Service {service.title()} has been flagged as a system service'
    disable_restart = f'Restart option is disabled for {service.title()} service'
    enable_restart = f'Restart option is disabled for {service.title()} service'

    if service_sql.insert_or_update_service_setting(server_id, service, 'dockerized', service_dockerized):
        if service_dockerized == '1':
            roxywi_common.logging(server_ip, service_docker, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, service_systemd, keep_history=1, service=service)

    if service_sql.insert_or_update_service_setting(server_id, service, 'restart', service_restart):
        if service_restart == '1':
            roxywi_common.logging(server_ip, disable_restart, keep_history=1, service=service)
        else:
            roxywi_common.logging(server_ip, enable_restart, keep_history=1, service=service)

    return 'ok'


@bp.post('/<service>/tools/update')
@check_services
def update_tools_enable(service):
    server_id = int(request.form.get('server_id'))
    active = request.form.get('active')
    name = request.form.get('name')
    alert = request.form.get('alert_en')
    metrics = request.form.get('metrics')
    service_sql.update_hapwi_server(server_id, alert, metrics, active, service)
    server_ip = server_sql.get_server(server_id).ip
    roxywi_common.logging(server_ip, f'The server {name} has been updated ', keep_history=1, service=service)

    return 'ok'


@bp.route('/check-restart/<server_ip>')
@validate()
def check_restart(server_ip: Union[IPvAnyAddress, DomainName]):
    servers = roxywi_common.get_dick_permit(ip=str(server_ip))
    for server in servers:
        if server != "":
            return 'ok'

    return 'nothing'
