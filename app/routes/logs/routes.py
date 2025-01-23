from flask import render_template, request, redirect, url_for, g
from flask_jwt_extended import jwt_required

from app.routes.logs import bp
from app.middleware import check_services, get_user_params
import app.modules.db.sql as sql
import app.modules.db.service as service_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.logs as roxy_logs
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
    log_path = get_config.get_config_var('main', 'log_path')
    selects = roxywi_common.get_files(log_path, file_format="log")

    if log_type == '2':
        roxywi_auth.page_for_admin(level=2)
    else:
        roxywi_auth.page_for_admin()

    if log_type is None:
        selects.append(['fail2ban.log', 'fail2ban.log'])
        selects.append(['roxy-wi.error.log', 'error.log'])
        selects.append(['roxy-wi.access.log', 'access.log'])

    kwargs = {
        'autorefresh': 1,
        'selects': selects,
        'serv': log_file,
        'lang': g.user_params['lang']
    }
    return render_template('logs_internal.html', **kwargs)


@bp.route('/<service>', defaults={'waf': None})
@bp.route('/<service>/<waf>')
@check_services
@get_user_params()
def logs(service, waf):
    serv = request.args.get('serv')
    rows = request.args.get('rows')
    grep = request.args.get('grep')
    # exgrep = request.args.get('exgrep')
    # hour = request.args.get('hour')
    # minute = request.args.get('minute')
    # hour1 = request.args.get('hour1')
    # minute1 = request.args.get('minute1')
    log_file = request.args.get('file')

    if rows is None:
        rows = 10
    if grep is None:
        grep = ''

    if service in ('haproxy', 'nginx', 'keepalived', 'apache', 'caddy') and not waf:
        service_desc = service_sql.select_service(service)
        service_name = service_desc.service
        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    elif waf:
        service_name = 'WAF'
        servers = roxywi_common.get_dick_permit(haproxy=1)
    else:
        return redirect(url_for('index'))

    kwargs = {
        'autorefresh': 1,
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
def show_remote_log_files(service, serv):
    service = common.checkAjaxInput(service)
    serv = common.checkAjaxInput(serv)
    log_path = sql.get_setting(f'{service}_path_logs')
    return_files = server_mod.get_remote_files(serv, log_path, 'log')
    lang = roxywi_common.get_user_lang_for_flask()

    if 'error: ' in return_files:
        return return_files

    return render_template(
        'ajax/show_log_files.html', serv=serv, return_files=return_files, path_dir=log_path, lang=lang
    )


@bp.route('/<service>/<serv>/<rows>', defaults={'waf': 0}, methods=['GET', 'POST'])
@bp.route('/<service>/waf/<serv>/<rows>', defaults={'waf': 1}, methods=['GET', 'POST'])
def show_logs(service, serv, rows, waf):
    grep = request.form.get('grep') or request.args.get('grep')
    exgrep = request.form.get('exgrep') or request.args.get('exgrep')
    hour = request.form.get('hour') or request.args.get('hour')
    minute = request.form.get('minute') or request.args.get('minute')
    hour1 = request.form.get('hour1') or request.args.get('hour1')
    minute1 = request.form.get('minute1') or request.args.get('minute1')
    log_file = request.form.get('file') or request.args.get('file')

    if roxywi_common.check_user_group_for_flask():
        try:
            out = roxy_logs.show_roxy_log(
                serv=serv, rows=rows, waf=waf, grep=grep, exgrep=exgrep, hour=hour, minute=minute,
                hour1=hour1, minute1=minute1, service=service, log_file=log_file
            )
        except Exception as e:
            return str(e)
        else:
            return out
