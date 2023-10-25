from flask import render_template, request, redirect, url_for, g
from flask_login import login_required

from app.routes.logs import bp
from middleware import check_services, get_user_params
import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.logs as roxy_logs
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.roxy_wi_tools as roxy_wi_tools

get_config = roxy_wi_tools.GetConfigVar()


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/internal')
@get_user_params()
def logs_internal():
    log_type = request.args.get('type')

    if log_type == '2':
        roxywi_auth.page_for_admin(level=2)
    else:
        roxywi_auth.page_for_admin()

    user_params = g.user_params
    log_path = get_config.get_config_var('main', 'log_path')
    selects = roxywi_common.get_files(log_path, file_format="log")

    if log_type is None:
        selects.append(['fail2ban.log', 'fail2ban.log'])
        selects.append(['roxy-wi.error.log', 'error.log'])
        selects.append(['roxy-wi.access.log', 'access.log'])

    return render_template(
        'logs_internal.html', autorefresh=1, role=user_params['role'], user=user_params['user'],
        user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang'],
        selects=selects, serv='viewlogs'
    )


@bp.route('/<service>', defaults={'waf': None})
@bp.route('/<service>/<waf>')
@check_services
@get_user_params()
def logs(service, waf):
    user_params = g.user_params
    serv = request.args.get('serv')
    rows = request.args.get('rows')
    grep = request.args.get('grep')
    exgrep = request.args.get('exgrep')
    hour = request.args.get('hour')
    minute = request.args.get('minute')
    hour1 = request.args.get('hour1')
    minute1 = request.args.get('minute1')
    log_file = request.args.get('file')

    if rows is None:
        rows = 10
    if grep is None:
        grep = ''

    if service in ('haproxy', 'nginx', 'keepalived', 'apache') and not waf:
        service_desc = sql.select_service(service)
        service_name = service_desc.service
        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    elif waf:
        service_name = 'WAF'
        servers = roxywi_common.get_dick_permit(haproxy=1)
    else:
        return redirect(url_for('index'))

    return render_template(
        'logs.html', autorefresh=1, role=user_params['role'], user=user_params['user'], select_id='serv', rows=rows,
        remote_file=log_file, selects=servers, waf=waf, service=service, user_services=user_params['user_services'],
        token=user_params['token'], lang=user_params['lang'], service_name=service_name, grep=grep, serv=serv
    )


@bp.route('/<service>/<serv>', methods=['GET', 'POST'])
@check_services
def show_remote_log_files(service, serv):
    service = common.checkAjaxInput(service)
    serv = common.checkAjaxInput(serv)
    log_path = sql.get_setting(f'{service}_path_logs')
    return_files = server_mod.get_remote_files(serv, log_path, 'log')

    if 'error: ' in return_files:
        return return_files

    lang = roxywi_common.get_user_lang_for_flask()

    return render_template(
        'ajax/show_log_files.html', serv=serv, return_files=return_files, path_dir=log_path, lang=lang
    )


@bp.route('/<service>/<serv>/<rows>', defaults={'waf': '0'}, methods=['GET', 'POST'])
@bp.route('/<service>/waf/<serv>/<rows>', defaults={'waf': '1'}, methods=['GET', 'POST'])
def show_logs(service, serv, rows, waf):
    if request.method == 'GET':
        grep = request.args.get('grep')
        exgrep = request.args.get('exgrep')
        hour = request.args.get('hour')
        minute = request.args.get('minute')
        hour1 = request.args.get('hour1')
        minute1 = request.args.get('minute1')
        log_file = request.args.get('file')
    else:
        grep = request.form.get('grep')
        exgrep = request.form.get('exgrep')
        hour = request.form.get('hour')
        minute = request.form.get('minute')
        hour1 = request.form.get('hour1')
        minute1 = request.form.get('minute1')
        log_file = request.form.get('file')

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
