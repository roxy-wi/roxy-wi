from flask import render_template, request, g
from flask_login import login_required

from app.routes.install import bp
from middleware import get_user_params, check_services
import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.server.server as server_mod
import modules.service.common as service_common
import modules.service.installation as service_mod
import modules.service.exporter_installation as exp_installation


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def install_monitoring():
    roxywi_auth.page_for_admin(level=2)

    user_params = g.user_params
    is_needed_tool = common.is_tool('ansible')
    geoip_country_codes = sql.select_geoip_country_codes()

    return render_template(
        'install.html', role=user_params['role'], user=user_params['user'], servers=user_params['servers'],
        user_services=user_params['user_services'], lang=user_params['lang'], geoip_country_codes=geoip_country_codes,
        is_needed_tool=is_needed_tool, token=user_params['token']
    )


@bp.post('/<service>')
@check_services
def install_service(service):
    json_data = request.form.get('jsonData')
    generate_functions = {
        'haproxy': service_mod.generate_haproxy_inv,
        'nginx': service_mod.generate_service_inv,
        'apache': service_mod.generate_service_inv,
        'keepalived': service_mod.generate_kp_inv,
    }

    try:
        inv, server_ips = generate_functions[service](json_data, service)
        service_mod.service_actions_after_install(server_ips, service, json_data)
        return service_mod.run_ansible(inv, server_ips, service, service), 201
    except Exception as e:
        return str(e)


@bp.route('/<service>/version/<server_ip>')
def get_service_version(service, server_ip):
    if service in ('haproxy', 'nginx', 'apache'):
        return service_common.show_service_version(server_ip, service)
    elif service == 'keepalived':
        cmd = ["sudo /usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}'"]
        return server_mod.ssh_command(server_ip, cmd)
    else:
        return 'error: Wrong service'


@bp.post('/exporter/<exporter>')
def install_exporter(exporter):
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    ver = common.checkAjaxInput(request.form.get('exporter_v'))
    ext_prom = common.checkAjaxInput(request.form.get('ext_prom'))

    if exporter == 'haproxy':
        return exp_installation.haproxy_exp_installation(server_ip, ver, ext_prom)
    elif exporter in ('nginx', 'apache'):
        return exp_installation.nginx_apache_exp_installation(server_ip, exporter, ver, ext_prom)
    elif exporter in ('keepalived', 'node'):
        return exp_installation.node_keepalived_exp_installation(exporter, server_ip, ver, ext_prom)
    else:
        return 'error: Wrong exporter'


@bp.route('/exporter/<exporter>/version/<server_ip>')
def get_exporter_version(exporter, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return service_common.get_exp_version(server_ip, exporter)


@bp.route('/grafana')
def install_grafana():
    try:
        return service_mod.grafana_install()
    except Exception as e:
        return f'{e}'


@bp.post('/waf/<service>/<server_ip>')
def install_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service == 'haproxy':
        try:
            return service_mod.waf_install(server_ip)
        except Exception as e:
            return str(e)
    elif service == 'nginx':
        try:
            return service_mod.waf_nginx_install(server_ip)
        except Exception as e:
            return str(e)
    else:
        return 'error: Wrong service'


@bp.post('/geoip')
def install_geoip():
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    geoip_update = common.checkAjaxInput(request.form.get('update'))
    service = request.form.get('service')

    try:
        return service_mod.geoip_installation(server_ip, geoip_update, service)
    except Exception as e:
        return str(e)


@bp.route('/geoip/<service>/<server_ip>')
def check_geoip(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
    cmd = [f"ls {service_dir}geoip/"]
    return server_mod.ssh_command(server_ip, cmd)
