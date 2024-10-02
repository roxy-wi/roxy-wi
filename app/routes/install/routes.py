from flask import render_template, request, g, jsonify
from flask_jwt_extended import jwt_required

from app.routes.install import bp
from app.middleware import get_user_params
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.server.server as server_mod
import app.modules.service.common as service_common
import app.modules.service.installation as service_mod
import app.modules.service.exporter_installation as exp_installation
from app.views.install.views import InstallView


bp.add_url_rule(
    '/<any(haproxy, nginx, apache, keepalived):service>',
    view_func=InstallView.as_view('install'),
    methods=['POST'],
    defaults={'server_id': None}
)
bp.add_url_rule(
    '/<any(haproxy, nginx, apache, keepalived):service>/<server_id>',
    view_func=InstallView.as_view('install_ip'),
    methods=['POST'],
)


@bp.before_request
@jwt_required()
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


@bp.post('/exporter/<exporter>')
def install_exporter(exporter):
    json_data = request.get_json()
    server_ip = common.is_ip_or_dns(json_data['server_ip'])
    ver = common.checkAjaxInput(json_data['exporter_v'])

    if exporter not in ('haproxy', 'nginx', 'apache', 'keepalived', 'node'):
        return jsonify({'status': 'failed', 'error': 'Wrong exporter'})

    try:
        return exp_installation.install_exporter(server_ip, ver, exporter)
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot install {exporter.title()} exporter: {e}'})


@bp.route('/exporter/<exporter>/version/<server_ip>')
def get_exporter_version(exporter, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return service_common.get_exp_version(server_ip, exporter)


@bp.post('/waf/<service>/<server_ip>')
def install_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        inv, server_ips = service_mod.generate_waf_inv(server_ip, service)
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot create inventory: {e}'})
    try:
        ansible_status = service_mod.run_ansible(inv, server_ips, f'waf_{service}'), 201
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot install WAF: {e}'})

    if service == 'haproxy':
        try:
            waf_sql.insert_waf_metrics_enable(server_ip, "0")
            waf_sql.insert_waf_rules(server_ip)
        except Exception as e:
            return jsonify({'status': 'failed', 'error': f'Cannot enable WAF: {e}'})
    elif service == 'nginx':
        try:
            waf_sql.insert_nginx_waf_rules(server_ip)
            waf_sql.insert_waf_nginx_server(server_ip)
        except Exception as e:
            return jsonify({'status': 'failed', 'error': f'Cannot enable WAF: {e}'})
    else:
        return jsonify({'status': 'failed', 'error': 'Wrong service'})

    return ansible_status


@bp.post('/geoip')
def install_geoip():
    json_data = request.get_json()
    server_ip = common.is_ip_or_dns(json_data['server_ip'])
    geoip_update = common.checkAjaxInput(json_data['update'])
    service = common.checkAjaxInput(json_data['service'])

    try:
        inv, server_ips = service_mod.generate_geoip_inv(server_ip, service, geoip_update)
        return service_mod.run_ansible(inv, server_ips, f'{service}_geoip'), 201
    except Exception as e:
        return jsonify({'status': 'failed', 'error': f'Cannot install GeoIP: {e}'})


@bp.route('/geoip/<service>/<server_ip>')
def check_geoip(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
    cmd = f"ls {service_dir}geoip/"
    return server_mod.ssh_command(server_ip, cmd)
