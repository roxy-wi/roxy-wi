import os

from flask import render_template, request, redirect, url_for
from flask_login import login_required

from app.routes.logs import bp
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
def logs_internal():
    log_type = request.args.get('type')

    if log_type == '2':
        roxywi_auth.page_for_admin(level=2)
    else:
        roxywi_auth.page_for_admin()

    try:
        user_params = roxywi_common.get_users_params(virt=1, haproxy=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    time_storage = sql.get_setting('log_time_storage')
    log_path = get_config.get_config_var('main', 'log_path')
    selects = roxywi_common.get_files(log_path, file_format="log")

    try:
        time_storage_hours = time_storage * 24
        for dirpath, dirnames, filenames in os.walk(log_path):
            for file in filenames:
                curpath = os.path.join(dirpath, file)
                file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
                if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
                    os.remove(curpath)
    except Exception:
        pass

    if log_type is None:
        selects.append(['fail2ban.log', 'fail2ban.log'])
        selects.append(['roxy-wi.error.log', 'error.log'])
        selects.append(['roxy-wi.access.log', 'access.log'])

    return render_template(
        'logs_internal.html', h2=1, autorefresh=1, role=user_params['role'], user=user,
        user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang'],
        selects=selects, serv='viewlogs'
    )


@bp.route('/<service>', defaults={'waf': None})
@bp.route('/<service>/<waf>')
def logs(service, waf):
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

    try:
        user_params = roxywi_common.get_users_params(virt=1, haproxy=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service in ('haproxy', 'nginx', 'keepalived', 'apache') and not waf:
        service_desc = sql.select_service(service)
        service_name = service_desc.service
        is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

        if is_redirect != 'ok':
            return redirect(url_for(f'{is_redirect}'))

        servers = roxywi_common.get_dick_permit(service=service_desc.slug)
    elif waf:
        service_name = 'WAF'
        is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

        if is_redirect != 'ok':
            return redirect(url_for(f'{is_redirect}'))

        servers = roxywi_common.get_dick_permit(haproxy=1)
    else:
        return redirect(url_for('index'))

    return render_template(
        'logs.html', autorefresh=1, role=user_params['role'], user=user, select_id='serv', rows=rows,
        remote_file=log_file, selects=servers, waf=waf, service=service, user_services=user_params['user_services'],
        token=user_params['token'], lang=user_params['lang'], service_name=service_name, grep=grep, serv=serv
    )


@bp.route('/<service>/<serv>', methods=['GET', 'POST'])
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
