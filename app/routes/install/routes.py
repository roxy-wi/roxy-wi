from flask import render_template, request, g
from flask_login import login_required

from app.routes.install import bp
from app.middleware import get_user_params, check_services
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.service.installation as service_mod
import app.modules.service.exporter_installation as exp_installation


@bp.before_request
@login_required
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def install_monitoring():
    roxywi_auth.page_for_admin(level=2)
    kwargs = {
        'is_needed_tool': common.is_tool('ansible'),
        'geoip_country_codes': sql.select_geoip_country_codes(),
        'lang': g.user_params['lang']
    }
    return render_template('install.html', **kwargs)


@bp.post('/<service>')
@check_services
def install_service(service):
    json_data = request.form.get('jsonData')
    try:
        return service_mod.install_service(service, json_data)
    except Exception as e:
        return f'{e}'


@bp.route('/<service>/version/<server_ip>')
def get_service_version(service, server_ip):
    if service in ('haproxy', 'nginx', 'apache'):
        return service_common.show_service_version(server_ip, service)
    elif service == 'keepalived':
        cmd = "sudo /usr/sbin/keepalived -v 2>&1|head -1|awk '{print $2}'"
        return server_mod.ssh_command(server_ip, cmd)
    else:
        return 'error: Wrong service'


@bp.post('/exporter/<exporter>')
def install_exporter(exporter):
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    ver = common.checkAjaxInput(request.form.get('exporter_v'))
    ext_prom = common.checkAjaxInput(request.form.get('ext_prom'))

    if exporter not in ('haproxy', 'nginx', 'apache', 'keepalived', 'node'):
        return 'error: Wrong exporter'

    try:
        return exp_installation.install_exporter(server_ip, ver, ext_prom, exporter)
    except Exception as e:
        return f'{e}'


@bp.route('/exporter/<exporter>/version/<server_ip>')
def get_exporter_version(exporter, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return service_common.get_exp_version(server_ip, exporter)


@bp.route('/grafana')
def install_grafana():
    try:
        inv, server_ips = service_mod.generate_grafana_inv()
        return service_mod.run_ansible(inv, server_ips, 'grafana'), 201
    except Exception as e:
        return f'{e}'


@bp.post('/waf/<service>/<server_ip>')
def install_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        inv, server_ips = service_mod.generate_waf_inv(server_ip, service)
    except Exception as e:
        return f'error: Cannot create inventory: {e}'
    try:
        ansible_status = service_mod.run_ansible(inv, server_ips, f'waf_{service}'), 201
    except Exception as e:
        return f'error: Cannot install WAF: {e}'

    if service == 'haproxy':
        try:
            waf_sql.insert_waf_metrics_enable(server_ip, "0")
            waf_sql.insert_waf_rules(server_ip)
        except Exception as e:
            return str(e)
    elif service == 'nginx':
        try:
            waf_sql.insert_nginx_waf_rules(server_ip)
            waf_sql.insert_waf_nginx_server(server_ip)
        except Exception as e:
            return str(e)
    else:
        return 'error: Wrong service'

    return ansible_status


@bp.post('/geoip')
def install_geoip():
    server_ip = common.is_ip_or_dns(request.form.get('server_ip'))
    geoip_update = common.checkAjaxInput(request.form.get('update'))
    service = request.form.get('service')

    try:
        inv, server_ips = service_mod.generate_geoip_inv(server_ip, service, geoip_update)
        return service_mod.run_ansible(inv, server_ips, f'{service}_geoip'), 201
    except Exception as e:
        return f'{e}'


@bp.route('/geoip/<service>/<server_ip>')
def check_geoip(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
    cmd = f"ls {service_dir}geoip/"
    return server_mod.ssh_command(server_ip, cmd)
