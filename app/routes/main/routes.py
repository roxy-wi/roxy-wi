import os
from datetime import timedelta
from typing import Union, Literal

from flask import render_template, g, abort, jsonify, send_from_directory, request
from flask_jwt_extended import create_access_token, jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress, ValidationError
import requests
from werkzeug.exceptions import HTTPException

from app import app, jwt
from app.routes.main import bp
import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.db.history as history_sql
from app.middleware import check_services, get_user_params, page_for_admin
import app.modules.common.common as common
import app.modules.roxywi.roxy as roxy
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.nettools as nettools_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.service.common as service_common
from app.modules.service.stats import (
    haproxy_stats, haproxy_stats_actions, haproxy_stats_config, haproxy_stats_maxconn, haproxy_stats_servers,
    haproxy_stats_sessions, haproxy_stats_tables,
)
from app.modules.roxywi.class_models import (
    ErrorResponse, NettoolsRequest, DomainName, HaproxyStatsMaxconnRequest,
    HaproxyStatsServerQuery, HaproxyStatsServerRequest, HaproxyStatsSessionQuery, HaproxyStatsSessionDelete,
    HaproxyStatsTableQuery, HaproxyStatsTableChange,
)
from app.modules.roxywi.exception import RoxywiPermissionError
from app.modules.subscription.access import MANAGED_SERVICES, require_feature
from app.modules.roxywi.error_handler import safe_error_message


@bp.get('/socket-ticket')
@jwt_required()
def socket_ticket():
    """Issue a short-lived, subscription-gated identity for the Socket service."""
    try:
        require_feature(MANAGED_SERVICES)
    except RoxywiPermissionError as exc:
        return jsonify({'status': 'failed', 'error': exc.public_message}), 403
    claims = roxywi_common.get_jwt_token_claims()
    expires_in = app.config['SOCKET_TICKET_SECONDS']
    token = create_access_token(
        identity=str(claims['user_id']),
        additional_claims={
            'aud': 'roxy-socket',
            'group': str(claims['group']),
            'socket_ticket': True,
        },
        expires_delta=timedelta(seconds=expires_in),
    )
    response = jsonify({'status': 'success', 'token': token, 'expires_in': expires_in})
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    return common.get_time_zoned_date(date, fmt)


@jwt.expired_token_loader
def my_expired_token_callback(jwt_header, jwt_payload):
    return jsonify(error="Token is expired"), 401


@jwt.unauthorized_loader
def custom_unauthorized_response(_err):
    return jsonify(error="Authorize first"), 401


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
    template = 'haproxy_stats.html' if service == 'haproxy' else 'statsview.html'
    return render_template(template, **kwargs)


@bp.route('/stats/view/<service>/<server_ip>')
@jwt_required()
@check_services
@get_user_params()
@validate()
def show_stats(service: Literal['haproxy', 'apache', 'nginx'], server_ip: Union[IPvAnyAddress, DomainName]):
    server = roxywi_common.require_server_access(server_ip)
    if service in ('nginx', 'apache'):
        try:
            return service_common.get_stat_page(server_ip, service, g.user_params['group_id'])
        except Exception as e:
            return 'error: ' + safe_error_message(e)
    else:
        if not server.haproxy:
            abort(404)
        try:
            data = haproxy_stats.collect_stats(
                str(server.ip), sql.get_setting('haproxy_sock_port', group_id=server.group_id)
            )
            response = jsonify(data)
        except haproxy_stats.StatsError as e:
            safe_error_message(e)
            response = jsonify({'status': 'error', 'code': e.code})
            response.status_code = e.status
        except Exception as e:
            safe_error_message(e)
            response = jsonify({'status': 'error', 'code': 'operation_failed'})
            response.status_code = 500
        response.headers['Cache-Control'] = 'no-store'
        return response


@bp.post('/stats/server/<any(haproxy):service>/<server_ip>')
@jwt_required()
@check_services
@get_user_params()
@page_for_admin(level=3)
@validate()
def stats_server_action(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    server = roxywi_common.require_server_access(server_ip)
    if not server.haproxy:
        abort(404)
    try:
        command = haproxy_stats_actions.change_server(
            str(server.ip), sql.get_setting('haproxy_sock_port', group_id=server.group_id),
            request.get_json(silent=True),
        )
        roxywi_common.logging(server.ip, f'HAProxy Stats: {command}', keep_history=1, service='haproxy')
        response = jsonify({'status': 'ok'})
    except haproxy_stats.StatsError as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': exc.code})
        response.status_code = exc.status
    except Exception as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': 'action_unknown'})
        response.status_code = 500
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/stats/maxconn/<any(haproxy):service>/<server_ip>', methods=['GET', 'POST'])
@jwt_required()
@check_services
@get_user_params()
@page_for_admin(level=3)
@validate()
def stats_maxconn(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    server = roxywi_common.require_server_access(server_ip)
    if not server.haproxy:
        abort(404)
    try:
        if request.method == 'GET':
            data = {'status': 'ok', 'targets': [
                {'ip': node.ip, 'hostname': node.hostname} for node in haproxy_stats_config.targets(server)
            ]}
        else:
            body = HaproxyStatsMaxconnRequest.model_validate(request.get_json(silent=True))
            data = {'status': 'ok', 'nodes': haproxy_stats_maxconn.change(server, body.model_dump(mode='json'))}
        response = jsonify(data)
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_context=False)
        # Preserve the existing error codes and precedence for malformed requests.
        malformed = any(error['type'] in ('missing', 'extra_forbidden') for error in errors)
        invalid_value = any(error['loc'][-1:] == ('value',) for error in errors)
        code = 'invalid_maxconn' if invalid_value and not malformed else 'invalid_action'
        response = jsonify({'status': 'error', 'code': code})
        response.status_code = 400
    except haproxy_stats.StatsError as exc:
        safe_error_message(exc)
        data = {'status': 'error', 'code': exc.code}
        if isinstance(exc, haproxy_stats_maxconn.MaxconnError):
            data['nodes'] = exc.nodes
        response = jsonify(data)
        response.status_code = exc.status
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': 'maxconn_unknown'})
        response.status_code = 500
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/stats/servers/<any(haproxy):service>/<server_ip>', methods=['GET', 'POST'])
@jwt_required()
@check_services
@get_user_params()
@page_for_admin(level=3)
@validate()
def stats_manage_servers(service: str, server_ip: Union[IPvAnyAddress, DomainName]):
    server = roxywi_common.require_server_access(server_ip)
    if not server.haproxy:
        abort(404)
    try:
        if request.method == 'GET':
            query = HaproxyStatsServerQuery.model_validate(request.args.to_dict())
            data = {'status': 'ok', **haproxy_stats_servers.describe(server, query.model_dump())}
        else:
            body = HaproxyStatsServerRequest.model_validate(request.get_json(silent=True))
            data = {'status': 'ok', 'nodes': haproxy_stats_servers.change(server, body.model_dump(mode='json'))}
        response = jsonify(data)
    except ValidationError as exc:
        # Keep the localized Stats error contract without returning rejected input values.
        error = exc.errors(include_input=False, include_context=False)[0]
        location = error['loc']
        code = 'invalid_action'
        if 'value' in location and error['type'] not in ('missing', 'extra_forbidden'):
            code = {'address': 'server_invalid_address', 'port': 'server_invalid_port',
                    'name': 'server_invalid_fields', 'check': 'server_invalid_fields',
                    'check_port': 'server_invalid_fields'}.get(location[-1], code)
        response = jsonify({'status': 'error', 'code': code})
        response.status_code = 400
    except haproxy_stats.StatsError as exc:
        safe_error_message(exc)
        data = {'status': 'error', 'code': exc.code}
        if isinstance(exc, haproxy_stats_servers.ServerEditError):
            data['nodes'] = exc.nodes
        response = jsonify(data)
        response.status_code = exc.status
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': 'server_incomplete'})
        response.status_code = 500
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/stats/sessions/<any(haproxy):service>/<server_ip>', defaults={'resource': 'sessions', 'details': False})
@bp.route('/stats/session/<any(haproxy):service>/<server_ip>', methods=['GET', 'POST'],
          defaults={'resource': 'sessions', 'details': True})
@bp.route('/stats/tables/<any(haproxy):service>/<server_ip>', methods=['GET', 'POST'],
          defaults={'resource': 'tables', 'details': False})
@jwt_required()
@check_services
@get_user_params()
@validate()
def stats_runtime_data(service: str, server_ip: Union[IPvAnyAddress, DomainName], resource: str, details: bool):
    server = roxywi_common.require_server_access(server_ip)
    if not server.haproxy:
        abort(404)
    writing = request.method == 'POST'
    if writing and not roxywi_auth.is_admin(level=3):
        abort(403)
    try:
        port = sql.get_setting('haproxy_sock_port', group_id=server.group_id)
        if resource == 'tables':
            if writing:
                body = HaproxyStatsTableChange.model_validate(request.get_json(silent=True))
                data = haproxy_stats_tables.change(str(server.ip), port, body.model_dump())
                # Keys can contain personal data; record the operation and table only.
                message = f'HAProxy Stats: {body.action} stick table {body.table}'
                roxywi_common.logging(server.ip, message, keep_history=1, service='haproxy')
            else:
                query = HaproxyStatsTableQuery.model_validate(request.args.to_dict())
                data = haproxy_stats_tables.collect_tables(str(server.ip), port, query.table)
        elif writing:
            body = HaproxyStatsSessionDelete.model_validate(request.get_json(silent=True))
            command = haproxy_stats_sessions.terminate(str(server.ip), port, body.model_dump())
            roxywi_common.logging(server.ip, f'HAProxy Stats: {command}', keep_history=1, service='haproxy')
            data = {'status': 'ok'}
        elif details:
            query = HaproxyStatsSessionQuery.model_validate(request.args.to_dict())
            data = haproxy_stats_sessions.describe(str(server.ip), port, query.model_dump())
        else:
            data = haproxy_stats_sessions.collect_sessions(str(server.ip), port)
        response = jsonify(data)
    except ValidationError:
        response = jsonify({'status': 'error', 'code': 'invalid_action'})
        response.status_code = 400
    except haproxy_stats.StatsError as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': exc.code})
        response.status_code = exc.status
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_message(exc)
        response = jsonify({'status': 'error', 'code': 'action_unknown' if writing else 'operation_failed'})
        response.status_code = 500
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/nettools')
@jwt_required()
@get_user_params(1)
def nettools():
    return render_template('nettools.html', lang=g.user_params['lang'])


@bp.post('/nettools/<check>')
@validate(body=NettoolsRequest)
@jwt_required()
@get_user_params()
def nettools_check(check, body: NettoolsRequest):
    if check in ('icmp', 'tcp', 'dns'):
        # Authorize the selected execution host before Nettools can resolve
        # stored SSH credentials or open a connection to it.
        roxywi_common.require_request_server_access()

    if check == 'icmp':
        try:
            return nettools_mod.ping_from_server(body.server_from, str(body.server_to), body.action)
        except Exception as e:
            return ErrorResponse(error=f'Cannot ping: {safe_error_message(e)}').model_dump(mode='json'), 500
    elif check == 'tcp':
        try:
            return nettools_mod.telnet_from_server(body.server_from, str(body.server_to), body.port)
        except Exception as e:
            return ErrorResponse(error=f'Cannot check port: {safe_error_message(e)}').model_dump(mode='json'), 500
    elif check == 'dns':
        try:
            return nettools_mod.nslookup_from_server(body.server_from, body.dns_name, body.record_type)
        except Exception as e:
            return ErrorResponse(error=f'Cannot lookup: {safe_error_message(e)}').model_dump(mode='json'), 500
    elif check == 'whois':
        try:
            return jsonify(nettools_mod.whois_check(body.dns_name))
        except Exception as e:
            return ErrorResponse(error=f'Cannot make whois: {safe_error_message(e)}').model_dump(mode='json'), 500
    elif check == 'ipcalc':
        try:
            ip_add = str(body.ip)
            netmask = int(body.netmask)
        except Exception as e:
            return ErrorResponse(error=f'Cannot calc: {safe_error_message(e)}').model_dump(mode='json'), 500

        try:
            return jsonify(nettools_mod.ip_calc(ip_add, netmask))
        except Exception as e:
            return ErrorResponse(error=f'Cannot calc: {safe_error_message(e)}').model_dump(mode='json'), 500
    else:
        return 'error: Wrong check'


@bp.route('/history/<service>/<server_ip>')
@jwt_required()
@get_user_params()
@validate()
def service_history(service: str, server_ip: Union[IPvAnyAddress, DomainName, int]):
    history = ''
    server_ip = str(server_ip)

    if service in ('haproxy', 'nginx', 'keepalived', 'apache', 'cluster', 'udp'):
        service_desc = service_sql.select_service(service)
        if not roxywi_auth.is_access_permit_to_service(service_desc.slug):
            abort(403, f'You do not have needed permissions to access to {service_desc.slug.title()} service')
        if service in ('cluster', 'udp'):
            server_id = server_ip
        else:
            server_id = server_sql.get_server_by_ip(server_ip).server_id
        history = history_sql.select_action_history_by_server_id_and_service(server_id, service_desc.service)
    elif service == 'server':
        if roxywi_common.check_is_server_in_group(server_ip):
            server_id = server_sql.get_server_by_ip(server_ip).server_id
            history = history_sql.select_action_history_by_server_id(server_id)
    elif service == 'user':
        roxywi_common.is_user_has_access_to_its_group(int(server_ip))
        history = history_sql.select_action_history_by_user_id(int(server_ip))
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


@bp.get('/api/version')
def get_version():
    version_status = roxy.versions()
    return jsonify(
        service_version=version_status['current_ver'],
        latest_version=version_status['new_ver'],
        update_available=bool(version_status['need_update']),
    )


@app.route("/api/gpt", methods=["POST"])
@jwt_required()
def ask_gpt():
    data = request.get_json()
    prompt = data.get("prompt", "")
    try:
        proxies = common.return_proxy_dict()
        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "prompt": prompt,
            "license": sql.get_setting('license')
        }

        response = requests.post(
            "https://roxy-wi.org/api/gpt",
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=20
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            return jsonify({"error": result["error"]}), 500
        content = result["response"]
        return jsonify({"response": content})
    except Exception as e:
        return jsonify({"error": safe_error_message(e)}), 500
