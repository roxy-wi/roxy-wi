import os

from flask import render_template, request, g, abort, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.routes.waf import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.roxywi.waf as roxy_waf
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod

get_config = roxy_wi_tools.GetConfigVar()


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/<service>')
@check_services
@get_user_params()
def waf(service):
    roxywi_auth.page_for_admin(level=2)

    if not roxywi_auth.is_access_permit_to_service(service):
        abort(403, f'You do not have needed permissions to access to {service.title()} service')

    if service == 'nginx':
        servers = roxywi_common.get_dick_permit(nginx=1)
    else:
        servers = g.user_params['servers']

    kwargs = {
        'title': 'Web application firewall',
        'autorefresh': 1,
        'serv': '',
        'servers': waf_sql.select_waf_servers_metrics(g.user_params['group_id']),
        'servers_all': servers,
        'manage_rules': '',
        'rules': '',
        'waf_rule_file': '',
        'waf_rule_id': '',
        'config': '',
        'cfg': '',
        'config_file_name': '',
        'service': service,
        'lang': g.user_params['lang']
    }
    return render_template('waf.html', **kwargs)


@bp.route('/<service>/<server_ip>/rules')
@get_user_params()
def waf_rules(service, server_ip):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)
    if not roxywi_auth.is_access_permit_to_service(service):
        abort(403, f'You do not have needed permissions to access to {service.title()} service')

    kwargs = {
        'title': 'Manage rules - Web application firewall',
        'serv': server_ip,
        'servers': waf_sql.select_waf_servers_metrics(g.user_params['group_id']),
        'servers_all': '',
        'manage_rules': '1',
        'rules': waf_sql.select_waf_rules(server_ip, service),
        'waf_rule_file': '',
        'waf_rule_id': '',
        'config': '',
        'cfg': '',
        'config_file_name': '',
        'service': service,
        'lang': g.user_params['lang']
    }

    return render_template('waf.html', **kwargs)


@bp.route('/<service>/<server_ip>/rule/<int:rule_id>')
@get_user_params()
def waf_rule_edit(service, server_ip, rule_id):
    if service not in ('haproxy', 'nginx'):
        abort(404)
    roxywi_auth.page_for_admin(level=2)
    if not roxywi_auth.is_access_permit_to_service(service):
        abort(403, f'You do not have needed permissions to access to {service.title()} service')
    roxywi_common.check_is_server_in_group(server_ip)

    if service == 'nginx':
        config_path = sql.get_setting('nginx_dir')
    else:
        config_path = sql.get_setting('haproxy_dir')

    get_date = roxy_wi_tools.GetDate(sql.get_setting('time_zone'))
    waf_rule_file = waf_sql.select_waf_rule_by_id(rule_id)
    configs_dir = sql.get_setting('tmp_config_path')
    try:
        cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}-{waf_rule_file}"
        config_mod.get_config(server_ip, cfg, waf=service, waf_rule_file=waf_rule_file)
    except Exception:
        pass
    config_file_name = common.return_nice_path(config_path) + 'waf/rules/' + waf_rule_file

    try:
        conf = open(cfg, "r")
        config_read = conf.read()
        conf.close()
    except IOError as e:
        return f'error: Cannot read imported config file: {e}'

    kwargs = {
        'title': 'Edit a WAF rule',
        'serv': server_ip,
        'servers': waf_sql.select_waf_servers_metrics(g.user_params['group_id']),
        'servers_all': '',
        'manage_rules': '',
        'rules': waf_sql.select_waf_rules(server_ip, service),
        'waf_rule_file': waf_sql.select_waf_rule_by_id(rule_id),
        'waf_rule_id': rule_id,
        'config': config_read,
        'cfg': cfg,
        'config_file_name': config_file_name,
        'service': service,
        'lang': g.user_params['lang']
    }

    return render_template('waf.html', **kwargs)


@bp.route('/<service>/<server_ip>/rule/<rule_id>/save', methods=['POST'])
def waf_save_config(service, server_ip, rule_id):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)

    get_date = roxy_wi_tools.GetDate(sql.get_setting('time_zone'))
    configs_dir = sql.get_setting('tmp_config_path')
    cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}"
    config_file_name = request.form.get('config_file_name')
    config = request.form.get('config')
    oldcfg = request.form.get('oldconfig')
    save = request.form.get('save')

    try:
        with open(cfg, "a") as conf:
            conf.write(config)
    except IOError as e:
        return f"error: Cannot read imported config file: {e}"

    stderr = config_mod.master_slave_upload_and_restart(server_ip, cfg, save, 'waf', oldcfg=oldcfg, config_file_name=config_file_name)

    config_mod.diff_config(oldcfg, cfg)

    try:
        os.system(f"/bin/rm -f {configs_dir}*.old")
    except Exception as e:
        return f'error: {e}'

    if stderr:
        return stderr

    return


@bp.route('/<server_ip>/rule/<int:rule_id>/<int:enable>')
def enable_rule(server_ip, rule_id, enable):
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        roxy_waf.switch_waf_rule(server_ip, enable, rule_id)
        return jsonify({'status': 'updated'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, f'Cannot enable WAF rule {rule_id}', server_ip)


@bp.route('/<service>/<server_ip>/rule/create', methods=['POST'])
def create_rule(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    json_data = request.get_json()
    if service not in ('haproxy', 'nginx'):
        return roxywi_common.handle_json_exceptions('Wrong service', '', server_ip)

    try:
        last_id = roxy_waf.create_waf_rule(server_ip, service, json_data)
        return jsonify({'status': 'created', 'id': last_id})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot create WAF rule', server_ip,)


@bp.route('/<service>/mode/<server_name>/<waf_mode>')
def change_waf_mode(service, server_name, waf_mode):
    if service not in ('haproxy', 'nginx'):
        return roxywi_common.handle_json_exceptions('Wrong service', '', server_name)

    server_name = common.checkAjaxInput(server_name)
    waf_mode = common.checkAjaxInput(waf_mode)

    try:
        roxy_waf.change_waf_mode(waf_mode, server_name, service)
        return jsonify({'status': 'updated'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot change WAF mode', server_name)


@bp.route('/overview/<service>/<server_ip>')
def overview_waf(service, server_ip):
    if service not in ('haproxy', 'nginx'):
        abort(404)
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    claims = get_jwt()

    return roxy_waf.waf_overview(server_ip, service, claims)


@bp.route('/metric/enable/<int:enable>/<server_name>')
def enable_metric(enable, server_name):
    server_name = common.checkAjaxInput(server_name)
    try:
        waf_sql.update_waf_metrics_enable(server_name, enable)
        return jsonify({'status': 'updated'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot enable WAF metrics', server_name)
