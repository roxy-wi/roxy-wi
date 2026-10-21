import tempfile
from pathlib import Path

from flask import render_template, request, g, abort, jsonify, current_app, url_for, redirect
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.exceptions import HTTPException

from app.routes.waf import bp
import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.server as server_sql
from app.middleware import check_services, get_user_params, page_for_admin
import app.modules.common.common as common
import app.modules.roxywi.waf as roxy_waf
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod
from app.modules.config.candidate import CandidateApplyError
from app.modules.config import waf_wizard
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiPermissionError, RoxywiPublicError, RoxywiValidationError
from app.modules.roxywi import logger
from app.modules.roxywi.error_handler import error_response
from app.modules.subscription.access import MANAGED_SERVICES, WAF_WIZARD, require_feature, is_feature_available


def _waf_error_response(error_key: str, exc: Exception, server_ip: str, *, section='waf_editor', status=500):
    if status == 500:
        if isinstance(exc, roxy_waf.WafSyncError):
            logger.warning('WAF synchronization failed', server_ip=exc.server_ip, reason=exc.reason,
                           cause=type(exc.__cause__).__name__)
        else:
            logger.exception(f'WAF: {error_key}', exc=exc, server_ip=server_ip)
    language = g.user_params['lang']
    languages = current_app.jinja_env.get_template('languages/languages.html').module.languages
    if language not in languages:
        language = 'en'
    messages = current_app.jinja_env.get_template(f'languages/{language}.html').module
    if isinstance(exc, roxy_waf.WafSyncError):
        message = messages.waf_sync[exc.reason].format(server=exc.server_ip)
        exc = exc.__cause__
    else:
        message = getattr(messages, section)[error_key]
    if isinstance(exc, CandidateApplyError):
        detail = {
            'Service action failed': 'action_failed',
            'The restarted WAF agent did not become ready': 'agent_unready',
        }.get(exc.reason) or {
            'TimeoutExpired': 'timeout', 'PermissionError': 'permission', 'FileNotFoundError': 'missing',
        }.get(exc.cause)
        if detail:
            details = current_app.jinja_env.get_template(f'languages/{language}.html').module.waf_error_details
            message += ' ' + details[detail]
    return error_response(message, status, public_message=message, language=language)


@bp.before_request
@jwt_required()
@get_user_params()
@page_for_admin(level=2)
def before_request():
    """ Protect all the admin endpoints. """
    roxywi_common.require_request_server_access()


def _waf_apply_context(service: str, server_ip: str, *, button=True) -> dict:
    if service not in ('haproxy', 'nginx') or not roxywi_auth.is_access_permit_to_service(service):
        abort(403)
    roxywi_common.check_is_server_in_group(server_ip)
    return dict(waf_apply_status=roxy_waf.waf_apply_status(server_ip, service), waf_apply_ip=server_ip,
                waf_apply_service=service, waf_apply_button=button,
                waf_sync_enabled=bool(list(server_sql.is_master(server_ip))))


@bp.get('/<any(haproxy, nginx):service>/<server_ip>/state')
def waf_apply_state(service, server_ip):
    return render_template('ajax/wafApplyState.html', lang=g.user_params['lang'],
                           **_waf_apply_context(service, server_ip, button=request.args.get('button') != '0'))


@bp.post('/<any(haproxy, nginx):service>/<server_ip>/apply')
def apply_waf(service, server_ip):
    _waf_apply_context(service, server_ip)
    try:
        roxy_waf.apply_waf_rules(server_ip, service)
        return jsonify({'status': 'ok'})
    except (RoxywiPermissionError, HTTPException):
        raise
    except CandidateApplyError as exc:
        error_key = service + '_apply_failed' if exc.code == 'apply_failed' else exc.code
        return _waf_error_response(error_key, exc, server_ip, section='waf_apply')
    except Exception as exc:
        return _waf_error_response('failed', exc, server_ip, section='waf_apply')


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
        'waf_wizard_available': is_feature_available(WAF_WIZARD),
        'lang': g.user_params['lang'],
        **_waf_apply_context(service, server_ip)
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
    if rule.wizard:
        return redirect(url_for('waf.waf_config_wizard', service=service, server_ip=server_ip, rule_id=rule_id))
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
        'lang': g.user_params['lang'],
        **_waf_apply_context(service, server_ip, button=False)
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
    if rule.wizard or waf_wizard.START in config or waf_wizard.METADATA in config:
        return _waf_error_response('managed', ValueError('Managed rule'), server_ip, section='waf_wizard', status=409)
    config_file_name = common.resolve_waf_config_path(rule.service, rule.rule_file)
    if service == 'haproxy' and save == 'reload':
        return _waf_error_response('haproxy_reload_unsupported', ValueError('Unsupported WAF action'), server_ip, status=400)
    if data.get('config_file_name') not in (None, rule.rule_file, config_file_name):
        abort(400, 'Configuration path does not match the WAF rule')
    configs_dir = sql.get_setting('tmp_config_path')
    try:
        with tempfile.TemporaryDirectory(prefix='waf-save-', dir=configs_dir) as workdir:
            cfg = Path(workdir) / rule.rule_file
            cfg.write_text(config, encoding='utf-8', newline='')
            stderr = roxy_waf.save_waf_rule(server_ip, rule.id, str(cfg), save, rule.service)
    except CandidateApplyError as exc:
        return _waf_error_response(rule.service + '_' + exc.code, exc, server_ip)
    except Exception as exc:
        return _waf_error_response('save_failed', exc, server_ip)

    if request.is_json:
        return jsonify({'status': 'ok', 'data': stderr or ''})
    if stderr:
        return stderr

    return ''


@bp.route('/<any(haproxy, nginx):service>/<server_ip>/wizard', methods=['GET', 'POST'])
@bp.route('/<any(haproxy, nginx):service>/<server_ip>/rule/<int:rule_id>/wizard', methods=['GET', 'POST'])
def waf_config_wizard(service, server_ip, rule_id=None):
    context = _waf_apply_context(service, server_ip, button=False)
    rule = roxy_waf.get_waf_rule(server_ip, rule_id, service) if rule_id is not None else None
    try:
        require_feature(WAF_WIZARD)
    except RoxywiPermissionError as exc:
        return _waf_error_response('enterprise', exc, server_ip, section='waf_wizard', status=403)
    try:
        if request.method == 'POST':
            result = waf_wizard.preview_or_save(server_ip, service, request.get_json(), rule_id)
            if 'id' in result:
                result['edit_url'] = url_for('waf.waf_config_wizard', service=service, server_ip=server_ip, rule_id=result['id'])
            return jsonify(result)
        spec = waf_wizard.DEFAULT.copy()
        if rule:
            if not rule.wizard:
                raise waf_wizard.WizardError('not_managed')
            content = waf_wizard.read_rule(server_ip, rule)
            if not content.startswith('# Roxy-WI rule creation:'):
                spec = waf_wizard.read_spec(content)
        registered = waf_sql.select_registered_waf_servers(service)
        servers = [row for row in roxywi_common.get_dick_permit(service=service)
                   if row[2] in registered or row[2] == server_ip]
        masters = {row[1] for row in server_sql.is_master(server_ip, master_slave=True)}
        targets = {row[2]: {
            'wizard': url_for('waf.waf_config_wizard', service=service, server_ip=row[2]),
            'rules': url_for('waf.waf_rules', service=service, server_ip=row[2]),
            'state': url_for('waf.waf_apply_state', service=service, server_ip=row[2], button=0),
            'sync': row[2] in masters,
        } for row in servers}
        return render_template('waf_wizard.html', service=service, serv=server_ip, rule=rule,
                               wizard_servers=servers, wizard_targets=targets,
                               spec=waf_wizard.form_spec(spec),
                               lang=g.user_params['lang'], **context)
    except waf_wizard.WizardError as exc:
        return _waf_error_response(exc.code, exc, server_ip, section='waf_wizard', status=400)
    except RoxywiConflictError as exc:
        return _waf_error_response('conflict', exc, server_ip, section='waf_wizard', status=409)
    except RoxywiPermissionError as exc:
        return _waf_error_response('enterprise', exc, server_ip, section='waf_wizard', status=403)
    except CandidateApplyError as exc:
        return _waf_error_response(service + '_' + exc.code, exc, server_ip)
    except (RoxywiPublicError, HTTPException):
        raise
    except Exception as exc:
        return _waf_error_response('failed', exc, server_ip, section='waf_wizard')


@bp.route('/<server_ip>/rule/<int:rule_id>/<int:enable>', methods=['POST'])
@bp.route('/<any(haproxy, nginx):service>/<server_ip>/rule/<int:rule_id>/<int:enable>', methods=['POST'])
def enable_rule(server_ip, rule_id, enable, service=None):
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        roxy_waf.switch_waf_rule(server_ip, enable, rule_id, service)
        return jsonify({'status': 'updated', 'enabled': enable})
    except RoxywiValidationError as exc:
        return _waf_error_response('invalid', exc, server_ip, section='waf_toggle', status=400)
    except RoxywiPermissionError as exc:
        return _waf_error_response('forbidden', exc, server_ip, section='waf_toggle', status=403)
    except RoxywiConflictError as exc:
        return _waf_error_response('conflict', exc, server_ip, section='waf_toggle', status=409)
    except RoxywiPublicError:
        raise
    except Exception as exc:
        return _waf_error_response('failed', exc, server_ip, section='waf_toggle')


@bp.delete('/<any(haproxy, nginx):service>/<server_ip>/rule/<int:rule_id>')
def delete_rule(service, server_ip, rule_id):
    server_ip = common.is_ip_or_dns(server_ip)
    try:
        roxy_waf.delete_waf_rule(server_ip, service, rule_id)
        return jsonify({'status': 'deleted', 'id': rule_id})
    except RoxywiPermissionError as exc:
        return _waf_error_response('forbidden', exc, server_ip, section='waf_delete', status=403)
    except RoxywiConflictError as exc:
        return _waf_error_response('conflict', exc, server_ip, section='waf_delete', status=409)
    except RoxywiValidationError as exc:
        return _waf_error_response('invalid', exc, server_ip, section='waf_delete', status=400)
    except (RoxywiPublicError, HTTPException):
        raise
    except Exception as exc:
        return _waf_error_response('failed', exc, server_ip, section='waf_delete')


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
        return jsonify({'status': 'Ok', 'mode': waf_mode})
    except RoxywiValidationError as exc:
        return _waf_error_response('invalid', exc, server_id, section='waf_mode', status=400)
    except RoxywiPermissionError as exc:
        return _waf_error_response('forbidden', exc, server_id, section='waf_mode', status=403)
    except RoxywiConflictError as exc:
        return _waf_error_response('conflict', exc, server_id, section='waf_mode', status=409)
    except (RoxywiPublicError, HTTPException):
        raise
    except Exception as exc:
        return _waf_error_response('failed', exc, server_id, section='waf_mode')


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
        return jsonify({'status': 'failed', 'error': exc.public_message}), 403
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot enable WAF metrics', server_id)
