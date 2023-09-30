import os

import pytz
import distro
from flask import render_template, request, redirect, url_for
from flask_login import login_required

from app.routes.admin import bp
import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.roxywi.roxy as roxy
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.tools.common as tools_common


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('')
def admin():
    roxywi_auth.page_for_admin()

    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    users = sql.select_users()
    settings = sql.get_setting('', all=1)
    ldap_enable = sql.get_setting('ldap_enable')
    services = sql.select_services()
    gits = sql.select_gits()
    masters = sql.select_servers(get_master_servers=1)
    is_needed_tool = common.is_tool('ansible')
    grafana = 0
    backups = sql.select_backups()
    s3_backups = sql.select_s3_backups()
    user_subscription = roxywi_common.return_user_subscription()

    if not roxy.is_docker():
        grafana, stderr = server_mod.subprocess_execute("systemctl is-active grafana-server")
        grafana = grafana[0]

    return render_template(
        'admin.html', h2=1, role=user_params['role'], user=user, users=users, groups=sql.select_groups(),
        servers=sql.select_servers(full=1), masters=masters, sshs=sql.select_ssh(), roles=sql.select_roles(),
        settings=settings, backups=backups, s3_backups=s3_backups, services=services, timezones=pytz.all_timezones,
        page="users.py", user_services=user_params['user_services'], ldap_enable=ldap_enable, gits=gits, guide_me=1,
        user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'],
        token=user_params['token'], is_needed_tool=is_needed_tool, lang=user_params['lang'], grafana=grafana
    )


@bp.route('/tools')
def show_tools():
    roxywi_auth.page_for_admin()
    lang = roxywi_common.get_user_lang_for_flask()
    try:
        services = tools_common.get_services_status()
    except Exception as e:
        return str(e)

    return render_template('ajax/load_services.html', services=services, lang=lang)


@bp.route('/tools/update/<service>')
def update_tools(service):
    roxywi_auth.page_for_admin()

    try:
        return tools_common.update_roxy_wi(service)
    except Exception as e:
        return f'error: {e}'


@bp.route('/tools/action/<service>/<action>')
def action_tools(service, action):
    roxywi_auth.page_for_admin()
    if action not in ('start', 'stop', 'restart'):
        return 'error: wrong action'

    return roxy.action_service(action, service)


@bp.route('/update')
def update_roxywi():
    roxywi_auth.page_for_admin()
    versions = roxy.versions()
    checker_ver = roxy.check_new_version('checker')
    smon_ver = roxy.check_new_version('smon')
    metrics_ver = roxy.check_new_version('metrics')
    keep_ver = roxy.check_new_version('keep_alive')
    portscanner_ver = roxy.check_new_version('portscanner')
    socket_ver = roxy.check_new_version('socket')
    prometheus_exp_ver = roxy.check_new_version('prometheus-exporter')
    services = tools_common.get_services_status()
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template(
        'ajax/load_updateroxywi.html', services=services, versions=versions, checker_ver=checker_ver, smon_ver=smon_ver,
        metrics_ver=metrics_ver, portscanner_ver=portscanner_ver, socket_ver=socket_ver, prometheus_exp_ver=prometheus_exp_ver,
        keep_ver=keep_ver, lang=lang
    )


@bp.route('/openvpn')
def load_openvpn():
    roxywi_auth.page_for_admin()
    openvpn_configs = ''
    openvpn_sess = ''
    openvpn = ''

    if distro.id() == 'ubuntu':
        stdout, stderr = server_mod.subprocess_execute("apt show openvpn3 2>&1|grep E:")
    elif distro.id() == 'centos' or distro.id() == 'rhel':
        stdout, stderr = server_mod.subprocess_execute("rpm --query openvpn3-client")

    if (
            (stdout[0] != 'package openvpn3-client is not installed' and stderr != '/bin/sh: rpm: command not found')
            and stdout[0] != 'E: No packages found'
    ):
        cmd = "sudo openvpn3 configs-list |grep -E 'ovpn|(^|[^0-9])[0-9]{4}($|[^0-9])' |grep -v net|awk -F\"    \" '{print $1}'|awk 'ORS=NR%2?\" \":\"\\n\"'"
        openvpn_configs, stderr = server_mod.subprocess_execute(cmd)
        cmd = "sudo openvpn3 sessions-list|grep -E 'Config|Status'|awk -F\":\" '{print $2}'|awk 'ORS=NR%2?\" \":\"\\n\"'| sed 's/^ //g'"
        openvpn_sess, stderr = server_mod.subprocess_execute(cmd)
        openvpn = stdout[0]

    return render_template('ajax/load_openvpn.html', openvpn=openvpn, openvpn_sess=openvpn_sess, openvpn_configs=openvpn_configs)


@bp.post('/openvpn/upload')
def upload_openvpn():
    roxywi_auth.page_for_admin()
    name = common.checkAjaxInput(request.form.get('ovpnname'))
    ovpn_file = f"{os.path.dirname('/tmp/')}/{name}.ovpn"

    try:
        with open(ovpn_file, "w") as conf:
            conf.write(request.form.get('uploadovpn'))
    except IOError as e:
        error = f'error: Cannot save ovpn file {e}'
        roxywi_common.logging('Roxy-WI server', error, roxywi=1)
        return error

    try:
        cmd = 'sudo openvpn3 config-import --config %s --persistent' % ovpn_file
        server_mod.subprocess_execute(cmd)
    except IOError as e:
        error = f'error: Cannot import OpenVPN file: {e}'
        roxywi_common.logging('Roxy-WI server', error, roxywi=1)
        return error

    try:
        cmd = 'sudo cp %s /etc/openvpn3/%s.conf' % (ovpn_file, name)
        server_mod.subprocess_execute(cmd)
    except IOError as e:
        error = f'error: Cannot save OpenVPN file: {e}'
        roxywi_common.logging('Roxy-WI server', error, roxywi=1)
        return error

    roxywi_common.logging("Roxy-WI server", f" has been uploaded a new ovpn file {ovpn_file}", roxywi=1, login=1)

    return 'success: ovpn file has been saved </div>'


@bp.post('/openvpn/delete')
def delete_openvpn():
    roxywi_auth.page_for_admin()
    openvpndel = common.checkAjaxInput(request.form.get('openvpndel'))

    cmd = f'sudo openvpn3 config-remove --config /tmp/{openvpndel}.ovpn --force'
    try:
        server_mod.subprocess_execute(cmd)
        roxywi_common.logging(openvpndel, ' has deleted the ovpn file ', roxywi=1, login=1)
    except IOError as e:
        error = f'error: Cannot delete OpenVPN file: {e}'
        roxywi_common.logging('Roxy-WI server', error, roxywi=1)
        return error
    else:
        return 'ok'


@bp.route('/openvpn/action/<action>/<openvpn>')
def action_openvpn(action, openvpn):
    roxywi_auth.page_for_admin()
    openvpn = common.checkAjaxInput(openvpn)

    if action == 'start':
        cmd = f'sudo openvpn3 session-start --config /tmp/{openvpn}.ovpn'
    elif action == 'restart':
        cmd = f'sudo openvpn3 session-manage --config /tmp/{openvpn}.ovpn --restart'
    elif action == 'disconnect':
        cmd = f'sudo openvpn3 session-manage --config /tmp/{openvpn}.ovpn --disconnect'
    else:
        return 'error: wrong action'
    try:
        server_mod.subprocess_execute(cmd)
        roxywi_common.logging(openvpn, f' The ovpn session has been {action}ed ', roxywi=1, login=1)
        return f"success: The {openvpn} has been {action}ed"
    except IOError as e:
        roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)
        return f'error: Cannot {action} OpenVPN: {e}'


@bp.post('/setting/<param>')
def update_settings(param):
    roxywi_auth.page_for_admin(level=2)
    val = request.form.get('val').replace('92', '/')
    user_group = roxywi_common.get_user_group(id=1)
    if sql.update_setting(param, val, user_group):
        roxywi_common.logging('Roxy-WI server', f'The {param} setting has been changed to: {val}', roxywi=1, login=1)

        return 'Ok'
