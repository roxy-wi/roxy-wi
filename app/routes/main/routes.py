import os

from flask import render_template, request, g, abort, jsonify, redirect, url_for, send_from_directory
from flask_jwt_extended import jwt_required
from flask_pydantic.exceptions import ValidationError

from app import app, cache, jwt
from app.routes.main import bp
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.history as history_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.roxywi.roxy as roxy
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.nettools as nettools_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.common as service_common
import app.modules.service.haproxy as service_haproxy
from app.modules.roxywi.class_models import ErrorResponse


@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    return common.get_time_zoned_date(date, fmt)


@jwt.expired_token_loader
def my_expired_token_callback(jwt_header, jwt_payload):
    return jsonify(error="Token is expired"), 401


@jwt.unauthorized_loader
def custom_unauthorized_response(_err):
    return jsonify(error="Authorize first"), 401


@app.errorhandler(ValidationError)
def handle_pydantic_validation_errors1(e):
    errors = []
    if e.body_params:
        req_type = e.body_params
    elif e.form_params:
        req_type = e.form_params
    elif e.path_params:
        req_type = e.path_params
    else:
        req_type = e.query_params
    for er in req_type:
        if len(er["loc"]) > 0:
            errors.append(f'{er["loc"][0]}: {er["msg"]}')
        else:
            errors.append(er["msg"])
    return ErrorResponse(error=errors).model_dump(mode='json'), 400


@app.errorhandler(401)
def no_auth(e):
    if 'api' in request.url:
        return jsonify({'error': str(e)}), 401
    return redirect(url_for('login_page'))


@app.errorhandler(403)
@get_user_params()
def page_is_forbidden(e):
    if 'api' in request.url:
        return jsonify({'error': str(e)}), 403
    kwargs = {
        'user_params': g.user_params,
        'title': e,
        'e': e
    }
    return render_template('error.html', **kwargs), 403


@app.errorhandler(404)
@get_user_params()
def page_not_found(e):
    if 'api' in request.url:
        return jsonify({'error': str(e)}), 404
    get_user_params()
    kwargs = {
        'user_params': g.user_params,
        'title': e,
        'e': e
    }
    return render_template('error.html', **kwargs), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'error': str(e)}), 405


@app.errorhandler(500)
def internal_error(e):
    if 'api' in request.url:
        return jsonify({'error': str(e)}), 500
    get_user_params()
    kwargs = {
        'user_params': g.user_params,
        'title': e,
        'e': e
    }
    return render_template('error.html', **kwargs), 500


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'images/favicon/favicon.ico', mimetype='image/vnd.microsoft.icon')


@bp.route('/stats/<service>/', defaults={'serv': None})
@bp.route('/stats/<service>/<serv>')
@jwt_required()
@check_services
@get_user_params()
def stats(service, serv):
    kwargs = {
        'serv': serv,
        'service': service,
        'service_desc': service_sql.select_service(service),
        'lang': g.user_params['lang']
    }
    return render_template('statsview.html', **kwargs)


@bp.route('/stats/view/<service>/<server_ip>')
@jwt_required()
@check_services
def show_stats(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service in ('nginx', 'apache'):
        try:
            return service_common.get_stat_page(server_ip, service)
        except Exception as e:
            return f'error: {e}'
    else:
        try:
            return service_haproxy.stat_page_action(server_ip)
        except Exception as e:
            return f'error: {e}'


@bp.route('/nettools')
@jwt_required()
@get_user_params(1)
def nettools():
    return render_template('nettools.html', lang=g.user_params['lang'])


@bp.post('/nettools/<check>')
@jwt_required()
def nettools_check(check):
    server_from = common.checkAjaxInput(request.form.get('server_from'))
    server_to = common.is_ip_or_dns(request.form.get('server_to'))
    action = common.checkAjaxInput(request.form.get('nettools_action'))
    port_to = common.checkAjaxInput(request.form.get('nettools_telnet_port_to'))
    dns_name = common.checkAjaxInput(request.form.get('nettools_nslookup_name'))
    dns_name = common.is_ip_or_dns(dns_name)
    record_type = common.checkAjaxInput(request.form.get('nettools_nslookup_record_type'))
    domain_name = common.is_ip_or_dns(request.form.get('nettools_whois_name'))

    if check == 'icmp':
        try:
            return nettools_mod.ping_from_server(server_from, server_to, action)
        except Exception as e:
            return str(e)
    elif check == 'tcp':
        try:
            return nettools_mod.telnet_from_server(server_from, server_to, port_to)
        except Exception as e:
            return str(e)
    elif check == 'dns':
        try:
            return nettools_mod.nslookup_from_server(server_from, dns_name, record_type)
        except Exception as e:
            return str(e)
    elif check == 'whois':
        try:
            return jsonify(nettools_mod.whois_check(domain_name))
        except Exception as e:
            return str(e)
    else:
        return 'error: Wrong check'


@bp.route('/history/<service>/<server_ip>')
@jwt_required()
@get_user_params()
def service_history(service, server_ip):
    history = ''
    server_ip = common.checkAjaxInput(server_ip)

    if service in ('haproxy', 'nginx', 'keepalived', 'apache', 'cluster', 'udp'):
        service_desc = service_sql.select_service(service)
        if not roxywi_auth.is_access_permit_to_service(service_desc.slug):
            abort(403, f'You do not have needed permissions to access to {service_desc.slug.title()} service')
        if service in ('cluster', 'udp'):
            server_id = server_ip
        else:
            server_id = server_sql.select_server_id_by_ip(server_ip)
        history = history_sql.select_action_history_by_server_id_and_service(server_id, service_desc.service)
    elif service == 'server':
        if roxywi_common.check_is_server_in_group(server_ip):
            server_id = server_sql.select_server_id_by_ip(server_ip)
            history = history_sql.select_action_history_by_server_id(server_id)
    elif service == 'user':
        history = history_sql.select_action_history_by_user_id(server_ip)
    else:
        abort(404, 'History not found')

    kwargs = {
        'user_subscription': roxywi_common.return_user_subscription(),
        'users': user_sql.select_users(),
        'serv': server_ip,
        'service': service,
        'history': history
    }

    return render_template('history.html', **kwargs)

@bp.route('/internal/show_version')
@cache.cached()
def show_roxywi_version():
    return jsonify(roxy.versions())
