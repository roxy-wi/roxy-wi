import os
import sys
import json

import distro
from flask import render_template, request
from flask_login import login_required

from app.routes.server import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.roxy as roxy
import modules.roxywi.group as group_mod
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.server.ssh as ssh_mod
import modules.server.server as server_mod
import modules.tools.smon as smon_mod
import modules.service.backup as backup_mod

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
error_mess = roxywi_common.return_error_message()


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/check/ssh/<server_ip>')
def check_ssh(server_ip):
    roxywi_auth.page_for_admin(level=2)
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        return server_mod.ssh_command(server_ip, ["ls -1t"])
    except Exception as e:
        return str(e)


@bp.route('/check/server/<server_ip>')
def check_server(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return server_mod.server_is_up(server_ip)


@bp.route('/show/if/<server_ip>')
def show_if(server_ip):
    roxywi_auth.page_for_admin(level=2)
    server_ip = common.is_ip_or_dns(server_ip)
    commands = ["sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}' |awk -F':' '{print $1}'"]

    return server_mod.ssh_command(server_ip, commands)


@bp.route('/create', methods=['POST'])
def create_server():
    roxywi_auth.page_for_admin(level=2)
    hostname = common.checkAjaxInput(request.form.get('servername'))
    ip = common.is_ip_or_dns(request.form.get('newip'))
    group = common.checkAjaxInput(request.form.get('newservergroup'))
    typeip = common.checkAjaxInput(request.form.get('typeip'))
    haproxy = common.checkAjaxInput(request.form.get('haproxy'))
    nginx = common.checkAjaxInput(request.form.get('nginx'))
    apache = common.checkAjaxInput(request.form.get('apache'))
    firewall = common.checkAjaxInput(request.form.get('firewall'))
    enable = common.checkAjaxInput(request.form.get('enable'))
    master = common.checkAjaxInput(request.form.get('slave'))
    cred = common.checkAjaxInput(request.form.get('cred'))
    page = common.checkAjaxInput(request.form.get('page'))
    page = page.split("#")[0]
    port = common.checkAjaxInput(request.form.get('newport'))
    desc = common.checkAjaxInput(request.form.get('desc'))
    add_to_smon = common.checkAjaxInput(request.form.get('add_to_smon'))
    lang = roxywi_common.get_user_lang_for_flask()

    if ip == '':
        return 'error: IP or DNS name is not valid'
    try:
        if server_mod.create_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx,
                                    apache, firewall):
            try:
                user_subscription = roxywi_common.return_user_status()
            except Exception as e:
                user_subscription = roxywi_common.return_unsubscribed_user_status()
                roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

            if add_to_smon:
                user_group = roxywi_common.get_user_group(id=1)
                smon_mod.create_smon(hostname, ip, 0, 1, 0, 0, hostname, desc, 0, 0, 0, 56, 'ping', 0, 0, user_group, 0)

            roxywi_common.logging(ip, f'A new server {hostname} has been created', roxywi=1, login=1, keep_history=1, service='server')

            return render_template(
                'ajax/new_server.html', groups=sql.select_groups(), servers=sql.select_servers(server=ip), lang=lang,
                masters=sql.select_servers(get_master_servers=1), sshs=sql.select_ssh(group=group), page=page,
                user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], adding=1
            )
    except Exception as e:
        return f'error: {e}'


@bp.route('/create/after', methods=['POST'])
def after_add():
    hostname = common.checkAjaxInput(request.form.get('servername'))
    ip = common.is_ip_or_dns(request.form.get('newip'))
    scan_server = common.checkAjaxInput(request.form.get('scan_server'))

    try:
        return server_mod.update_server_after_creating(hostname, ip, scan_server)
    except Exception as e:
        return str(e)


@bp.route('/update', methods=['POST'])
def update_server():
    roxywi_auth.page_for_admin(level=2)
    name = request.form.get('updateserver')
    group = request.form.get('servergroup')
    typeip = request.form.get('typeip')
    firewall = request.form.get('firewall')
    enable = request.form.get('enable')
    master = request.form.get('slave')
    serv_id = request.form.get('id')
    cred = request.form.get('cred')
    port = request.form.get('port')
    protected = request.form.get('protected')
    desc = request.form.get('desc')

    if name is None or port is None:
        return error_mess
    else:
        sql.update_server(name, group, typeip, enable, master, serv_id, cred, port, desc, firewall, protected)
        roxywi_common.logging(f'The server {name}', ' has been updated ', roxywi=1, login=1)
        server_ip = sql.select_server_ip_by_id(serv_id)
        roxywi_common.logging(server_ip, f'The server {name} has been update', roxywi=1, login=1, keep_history=1, service='server')

        return 'ok'


@bp.route('/delete/<int:server_id>')
def delete_server(server_id):
    roxywi_auth.page_for_admin(level=2)
    return server_mod.delete_server(server_id)


@bp.route('/group/create', methods=['POST'])
def create_group():
    roxywi_auth.page_for_admin()
    newgroup = common.checkAjaxInput(request.form.get('groupname'))
    desc = common.checkAjaxInput(request.form.get('newdesc'))
    if newgroup == '':
        return error_mess
    else:
        try:
            if sql.add_group(newgroup, desc):
                roxywi_common.logging('Roxy-WI server', f'A new group {newgroup} has been created', roxywi=1, login=1)
                return render_template('ajax/new_group.html', groups=sql.select_groups(group=newgroup))
        except Exception as e:
            return str(e)


@bp.route('/group/update', methods=['POST'])
def update_group():
    roxywi_auth.page_for_admin()
    name = common.checkAjaxInput(request.form.get('updategroup'))
    desc = common.checkAjaxInput(request.form.get('descript'))
    group_id = common.checkAjaxInput(request.form.get('id'))

    return group_mod.update_group(group_id, name, desc)


@bp.route('/group/delete/<int:group_id>')
def delete_group(group_id):
    roxywi_auth.page_for_admin()
    return group_mod.delete_group(group_id)


@bp.route('/ssh/create', methods=['POST'])
def create_ssh():
    roxywi_auth.page_for_admin(level=2)
    return ssh_mod.create_ssh_cred()


@bp.route('/ssh/delete/<int:ssh_id>')
def delete_ssh(ssh_id):
    roxywi_auth.page_for_admin(level=2)
    return ssh_mod.delete_ssh_key(ssh_id)


@bp.route('/ssh/update', methods=['POST'])
def update_ssh():
    roxywi_auth.page_for_admin(level=2)
    return ssh_mod.update_ssh_key()


@bp.route('/ssh/upload', methods=['POST'])
def upload_ssh_key():
    user_group = roxywi_common.get_user_group()
    name = common.checkAjaxInput(request.form.get('name'))
    key = request.form.get('ssh_cert')

    try:
        return ssh_mod.upload_ssh_key(name, user_group, key)
    except Exception as e:
        return str(e)


@bp.app_template_filter('string_to_dict')
def string_to_dict(dict_string) -> dict:
    from ast import literal_eval
    return literal_eval(dict_string)


@bp.route('/system_info/get/<server_ip>/<int:server_id>')
def get_system_info(server_ip, server_id):
    server_ip = common.is_ip_or_dns(server_ip)

    return server_mod.show_system_info(server_ip, server_id)


@bp.route('/system_info/update/<server_ip>/<int:server_id>')
def update_system_info(server_ip, server_id):
    server_ip = common.is_ip_or_dns(server_ip)

    return server_mod.update_system_info(server_ip, server_id)


@bp.route('/tools')
def show_tools():
    roxywi_auth.page_for_admin()
    lang = roxywi_common.get_user_lang_for_flask()
    try:
        services = roxy.get_services_status()
    except Exception as e:
        return str(e)

    return render_template('ajax/load_services.html', services=services, lang=lang)


@bp.route('/tools/update/<service>')
def update_tools(service):
    roxywi_auth.page_for_admin()

    try:
        return roxy.update_roxy_wi(service)
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
    services = roxy.get_services_status()
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


@bp.route('/services/<int:server_id>', methods=['GET', 'POST'])
def show_server_services(server_id):
    roxywi_auth.page_for_admin(level=2)

    if request.method == 'GET':
        return server_mod.show_server_services(server_id)
    else:
        server_name = common.checkAjaxInput(request.form.get('changeServerServicesServer'))
        server_services = json.loads(request.form.get('jsonDatas'))

        return server_mod.change_server_services(server_id, server_name, server_services)


@bp.route('/firewall/<server_ip>')
def show_firewall(server_ip):
    roxywi_auth.page_for_admin(level=2)

    server_ip = common.is_ip_or_dns(server_ip)

    return server_mod.show_firewalld_rules(server_ip)


@bp.post('/backup/create')
@bp.post('/backup/delete')
@bp.post('/backup/update')
def create_backup():
    server = common.is_ip_or_dns(request.form.get('server'))
    rpath = common.checkAjaxInput(request.form.get('rpath'))
    time = common.checkAjaxInput(request.form.get('time'))
    backup_type = common.checkAjaxInput(request.form.get('type'))
    rserver = common.checkAjaxInput(request.form.get('rserver'))
    cred = int(request.form.get('cred'))
    deljob = common.checkAjaxInput(request.form.get('deljob'))
    update = common.checkAjaxInput(request.form.get('backupupdate'))
    description = common.checkAjaxInput(request.form.get('description'))

    try:
        return backup_mod.backup(server, rpath, time, backup_type, rserver, cred, deljob, update, description)
    except Exception as e:
        return str(e)


@bp.post('/s3backup/create')
@bp.post('/s3backup/delete')
def create_s3_backup():
    server = common.is_ip_or_dns(request.form.get('s3_backup_server'))
    s3_server = common.checkAjaxInput(request.form.get('s3_server'))
    bucket = common.checkAjaxInput(request.form.get('s3_bucket'))
    secret_key = common.checkAjaxInput(request.form.get('s3_secret_key'))
    access_key = common.checkAjaxInput(request.form.get('s3_access_key'))
    time = common.checkAjaxInput(request.form.get('time'))
    deljob = common.checkAjaxInput(request.form.get('dels3job'))
    description = common.checkAjaxInput(request.form.get('description'))

    try:
        return backup_mod.s3_backup(server, s3_server, bucket, secret_key, access_key, time, deljob, description)
    except Exception as e:
        return str(e)


@bp.post('/git/create')
@bp.post('/git/delete')
def create_git_backup():
    server_id = request.form.get('server')
    service_id = request.form.get('git_service')
    git_init = request.form.get('git_init')
    repo = request.form.get('git_repo')
    branch = request.form.get('git_branch')
    period = request.form.get('time')
    cred = request.form.get('cred')
    deljob = request.form.get('git_deljob')
    description = request.form.get('description')
    backup_id = request.form.get('git_backup')

    return backup_mod.git_backup(server_id, service_id, git_init, repo, branch, period, cred, deljob, description, backup_id)
