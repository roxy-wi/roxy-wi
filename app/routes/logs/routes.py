from flask import render_template, request, redirect, url_for, g, abort, jsonify
from flask_jwt_extended import jwt_required

from app.routes.logs import bp
from app.middleware import check_services, get_user_params
import app.modules.db.sql as sql
import app.modules.db.service as service_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
from app.modules.roxywi import log_query, log_snapshot, log_follow, logger
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/internal')
@get_user_params()
def logs_internal():
    log_type = request.args.get('type')
    log_file = request.args.get('log_file')
    selects = log_query.sources()

    if log_type == '2':
        roxywi_auth.page_for_admin(level=2)
    else:
        roxywi_auth.page_for_admin()

    if log_type is None and get_config.get_config_var('main', 'deployment_mode', 'package') == 'package':
        selects.append(['fail2ban.log', 'fail2ban.log'])
        selects.append(['roxy-wi.error.log', 'error.log'])
        selects.append(['roxy-wi.access.log', 'access.log'])

    kwargs = {
        'selects': selects,
        'serv': log_file or (selects[0][0] if selects else None),
        'process_roles': log_query.PROCESS_ROLES,
        'lang': g.user_params['lang']
    }
    return render_template('logs_internal.html', **kwargs)


@bp.route('/internal/query', methods=['GET', 'POST'])
@get_user_params()
def query_internal_logs():
    roxywi_auth.page_for_admin(level=2)
    if not roxywi_common.check_user_group_for_flask():
        abort(403)
    params = g.user_params
    group = None if roxywi_auth.is_admin() and int(params['group_id']) == 1 else params['group_id']
    try:
        query = log_query.LogQuery(request.values)
        source = request.values.get('source', 'runtime')
        if source in {'fail2ban.log', 'roxy-wi.error.log', 'roxy-wi.access.log'}:
            if group is not None or get_config.get_config_var('main', 'deployment_mode', 'package') != 'package':
                abort(403)
            result = log_snapshot.package_snapshot(source, query)
        else:
            result = log_query.read_logs(source, query, request.values.get('cursor'),
                                         scope=[params['user_id'], params['group_id'], params['role']], group_id=group)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except OSError:
        logger.exception('Cannot read internal logs')
        return jsonify(error='Cannot read the log journal; check storage permissions'), 503
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/query/<service>', methods=['GET', 'POST'])
@check_services
@get_user_params()
def query_service_logs(service):
    server = roxywi_common.require_server_access(request.values.get('server'))
    try:
        query = log_query.LogQuery(request.values)
        args = (service, str(server.ip), request.values.get('file'), request.values.get('waf') == '1', query)
        if request.values.get('follow') == '1':
            params = g.user_params
            result = log_follow.follow(*args, cursor=request.values.get('cursor'),
                                       scope=[params['user_id'], params['group_id'], params['role']])
        else:
            result = log_snapshot.remote_snapshot(*args)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        logger.exception('Cannot read remote service logs', server_ip=str(server.ip))
        message = log_follow.READ_ERROR if request.values.get('follow') == '1' else 'Cannot read the remote log; check the file and SSH/sudo permissions'
        return jsonify(error=message), 503
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.route('/<service>', defaults={'waf': None})
@bp.route('/<service>/<waf>')
@check_services
@get_user_params()
def logs(service, waf):
    serv = request.args.get('serv')
    rows = request.args.get('rows')
    grep = request.args.get('grep')
    log_file = request.args.get('file')
    service_desc = service_sql.select_service(service)
    service_name = service_desc.service

    if rows is None:
        rows = 10
    if grep is None:
        grep = ''

    if service in ('haproxy', 'nginx', 'keepalived', 'apache') and not waf:
        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    elif waf:
        service_name = 'WAF'
        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    else:
        return redirect(url_for('index'))

    kwargs = {
        'servers': servers,
        'serv': serv,
        'service': service,
        'service_name': service_name,
        'grep': grep,
        'rows': rows,
        'remote_file': log_file,
        'waf': waf,
        'lang': g.user_params['lang']
    }

    return render_template('logs.html', **kwargs)


@bp.route('/<service>/<serv>', methods=['GET', 'POST'])
@check_services
@get_user_params()
def show_remote_log_files(service, serv):
    serv = str(roxywi_common.require_server_access(serv).ip)
    service = common.checkAjaxInput(service)
    serv = common.checkAjaxInput(serv)
    try:
        if str(sql.get_setting('syslog_server_enable')) == '1':
            files = ['syslog.log']
        else:
            log_path = sql.get_setting(f'{service}_path_logs')
            result = server_mod.get_remote_files(serv, log_path, 'log')
            if 'error:' in result or 'ls: cannot access' in result:
                raise OSError('Cannot list remote log files')
            files = sorted({line.strip().rsplit('/', 1)[-1] for line in result.splitlines() if line.strip()})
    except Exception:
        logger.exception('Cannot list remote log files', server_ip=serv)
        return jsonify(error='Cannot list remote logs; check SSH/sudo permissions'), 503
    response = jsonify(files=files)
    response.headers['Cache-Control'] = 'no-store'
    return response
