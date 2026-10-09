import tempfile
from pathlib import Path

from flask import render_template, request, g, abort, jsonify, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt

from app.routes.waf import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
from app.middleware import check_services, get_user_params, page_for_admin
import app.modules.common.common as common
import app.modules.roxywi.waf as roxy_waf
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiPermissionError, RoxywiPublicError, RoxywiValidationError
from app.modules.roxywi import logger
from app.modules.subscription.access import MANAGED_SERVICES, require_feature


def _waf_error_response(error_key: str, exc: Exception, server_ip: str, *, section='waf_editor', status=500):
    if status == 500:
        logger.exception(f'WAF: {error_key}', exc=exc, server_ip=server_ip)
    language = g.user_params['lang']
    languages = current_app.jinja_env.get_template('languages/languages.html').module.languages
    if language not in languages:
        language = 'en'
    messages = getattr(current_app.jinja_env.get_template(f'languages/{language}.html').module, section)
    message = messages[error_key]
    if request.is_json or request.accept_mimetypes.best == 'application/json':
        return jsonify({'status': 'failed', 'error': message}), status
    return render_template('error.html', title='WAF', e=message, lang=language), status


@bp.before_request
@jwt_required()
@get_user_params()
@page_for_admin(level=2)
def before_request():
    """ Protect all the admin endpoints. """
    roxywi_common.require_request_server_access()


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


@bp.route('/<any(haproxy, nginx):service>/<server_ip>/rule/<int:rule_id>')
@get_user_params()
def waf_rule_edit(service, server_ip, rule_id):
    roxywi_auth.page_for_admin(level=2)
    if not roxywi_auth.is_access_permit_to_service(service):
        abort(403, f'You do not have needed permissions to access to {service.title()} service')
    roxywi_common.check_is_server_in_group(server_ip)

    rule = roxy_waf.get_waf_rule(server_ip, rule_id, service)
    waf_rule_file = rule.rule_file
    config_file_name = common.resolve_waf_config_path(rule.service, waf_rule_file)
    configs_dir = sql.get_setting('tmp_config_path')
    try:
        with tempfile.TemporaryDirectory(prefix='waf-read-', dir=configs_dir) as workdir:
            cfg = Path(workdir) / waf_rule_file
            config_mod.get_config(server_ip, str(cfg), waf=service, waf_rule_file=waf_rule_file)
            config_read = cfg.read_text(encoding='utf-8')
    except Exception as exc:
        return _waf_error_response('read_failed', exc, server_ip)

    kwargs = {
        'title': 'Edit a WAF rule',
        'serv': server_ip,
        'servers': waf_sql.select_waf_servers_metrics(g.user_params['group_id']),
        'servers_all': '',
        'manage_rules': '',
        'rules': waf_sql.select_waf_rules(server_ip, service),
        'waf_rule_file': waf_rule_file,
        'waf_rule_id': rule_id,
        'config': config_read,
        'config_file_name': config_file_name,
        'service': service,
        'lang': g.user_params['lang']
    }

    return render_template('waf.html', **kwargs)


@bp.route('/<any(haproxy, nginx):service>/<server_ip>/rule/<int:rule_id>/save', methods=['POST'])
@check_services
def waf_save_config(service, server_ip, rule_id):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)

    data = request.get_json() if request.is_json else request.form
    if not hasattr(data, 'get'):
        abort(400, 'Invalid configuration request')
    save = data.get('action') if request.is_json else data.get('save')
    config_mod.validate_config_action(save)
    if save == 'test':
        abort(400, 'WAF rule validation is not available')
    config = data.get('config')
    if not isinstance(config, str):
        abort(400, 'Configuration content is required')
    rule = roxy_waf.get_waf_rule(server_ip, rule_id, service)
    config_file_name = common.resolve_waf_config_path(rule.service, rule.rule_file)
    if data.get('config_file_name') not in (None, rule.rule_file, config_file_name):
        abort(400, 'Configuration path does not match the WAF rule')
    configs_dir = sql.get_setting('tmp_config_path')
    try:
        with tempfile.TemporaryDirectory(prefix='waf-save-', dir=configs_dir) as workdir:
            cfg = Path(workdir) / rule.rule_file
            cfg.write_text(config, encoding='utf-8', newline='')
            stderr = config_mod.master_slave_upload_and_restart(
                server_ip, str(cfg), save, 'waf', waf=rule.service, config_file_name=config_file_name)
    except Exception as exc:
        return _waf_error_response('save_failed', exc, server_ip)

    if request.is_json:
        return jsonify({'status': 'ok', 'data': stderr or ''})
    if stderr:
        return stderr

    return ''


@bp.route('/<server_ip>/rule/<int:rule_id>/<int:enable>', methods=['POST'])
def enable_rule(server_ip, rule_id, enable):
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        roxy_waf.switch_waf_rule(server_ip, enable, rule_id)
        return jsonify({'status': 'updated'})
    except RoxywiPublicError:
        raise
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, f'Cannot enable WAF rule {rule_id}', server_ip)


@bp.route('/<any(haproxy, nginx):service>/<server_ip>/rule/create', methods=['POST'])
def create_rule(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    json_data = request.get_json()

    try:
        last_id = roxy_waf.create_waf_rule(server_ip, service, json_data)
        return jsonify({'status': 'Ok', 'id': last_id,
                        'edit_url': url_for('waf.waf_rule_edit', service=service, server_ip=server_ip, rule_id=last_id)})
    except RoxywiPermissionError as exc:
        return _waf_error_response('forbidden', exc, server_ip, section='waf_create', status=403)
    except RoxywiValidationError as exc:
        return _waf_error_response('invalid', exc, server_ip, section='waf_create', status=400)
    except RoxywiConflictError as exc:
        return _waf_error_response('conflict', exc, server_ip, section='waf_create', status=409)
    except Exception as exc:
        return _waf_error_response('failed', exc, server_ip, section='waf_create')


@bp.route('/<any(haproxy, nginx):service>/mode/<int:server_id>/<any(On, Off, DetectionOnly):waf_mode>', methods=['POST'])
def change_waf_mode(service, server_id, waf_mode):
    try:
        roxy_waf.change_waf_mode(waf_mode, server_id, service)
        return jsonify({'status': 'Ok'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot change WAF mode', server_id)


@bp.route('/overview/<any(haproxy, nginx):service>/<server_ip>')
def overview_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    claims = get_jwt()

    return roxy_waf.waf_overview(server_ip, service, claims)


@bp.route('/metric/enable/<int:enable>/<int:server_id>', methods=['POST'])
def enable_metric(enable, server_id):
    try:
        if enable:
            require_feature(MANAGED_SERVICES)
        waf_sql.update_waf_metrics_enable(server_id, enable)
        from app.modules.db.service_command import queue_metrics_assignment
        queue_metrics_assignment(server_id, 'waf', bool(enable))
        return jsonify({'status': 'Ok'})
    except RoxywiPermissionError as exc:
        return jsonify({'status': 'failed', 'error': str(exc)}), 403
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot enable WAF metrics', server_id)
