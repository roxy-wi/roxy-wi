from flask import render_template, request
from flask_login import login_required

from app.routes.portscanner import bp
import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('')
def portscanner():
    try:
        user_params = roxywi_common.get_users_params(virt=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    user_group = roxywi_common.get_user_group(id=1)
    port_scanner_settings = sql.select_port_scanner_settings(user_group)

    if not port_scanner_settings:
        port_scanner_settings = ''
        count_ports = ''
    else:
        count_ports = list()
        for s in user_params['servers']:
            count_ports_from_sql = sql.select_count_opened_ports(s[2])
            i = (s[2], count_ports_from_sql)
            count_ports.append(i)

    cmd = "systemctl is-active roxy-wi-portscanner"
    port_scanner, port_scanner_stderr = server_mod.subprocess_execute(cmd)
    user_subscription = roxywi_common.return_user_subscription()

    return render_template(
        'portscanner.html', h2=1, autorefresh=0, role=user_params['role'], user=user, servers=user_params['servers'],
        port_scanner_settings=port_scanner_settings, count_ports=count_ports, port_scanner=''.join(port_scanner),
        port_scanner_stderr=port_scanner_stderr, user_services=user_params['user_services'], user_status=user_subscription['user_status'],
        user_plan=user_subscription['user_plan'], token=user_params['token'], lang=user_params['lang']
    )


@bp.route('/history/<server_ip>')
def portscanner_history(server_ip):
    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    history = sql.select_port_scanner_history(server_ip)
    user_subscription = roxywi_common.return_user_subscription()

    return render_template(
        'include/port_scan_history.html', h2=1, autorefresh=0, role=user_params['role'], user=user, history=history,
        servers=user_params['servers'], user_services=user_params['user_services'], token=user_params['token'],
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], lang=user_params['lang']
    )


@bp.post('/settings')
def change_settings_portscanner():
    server_id = common.checkAjaxInput(request.form.get('server_id'))
    enabled = common.checkAjaxInput(request.form.get('enabled'))
    notify = common.checkAjaxInput(request.form.get('notify'))
    history = common.checkAjaxInput(request.form.get('history'))
    user_group_id = [server[3] for server in sql.select_servers(id=server_id)]

    try:
        if sql.insert_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
            return 'ok'
        else:
            if sql.update_port_scanner_settings(server_id, user_group_id[0], enabled, notify, history):
                return 'ok'
    except Exception as e:
        return f'error: Cannot save settings: {e}'
    else:
        return 'ok'


@bp.route('/scan/<int:server_id>')
def scan_port(server_id):
    server = sql.select_servers(id=server_id)
    ip = ''

    for s in server:
        ip = s[2]

    cmd = f"sudo nmap -sS {ip} |grep -E '^[[:digit:]]'|sed 's/  */ /g'"
    cmd1 = f"sudo nmap -sS {ip} |head -5|tail -2"

    stdout, stderr = server_mod.subprocess_execute(cmd)
    stdout1, stderr1 = server_mod.subprocess_execute(cmd1)

    if stderr != '':
        return f'error: {stderr}'
    else:
        lang = roxywi_common.get_user_lang_for_flask()
        return render_template('ajax/scan_ports.html', ports=stdout, info=stdout1, lang=lang)

