import json

from flask import render_template, request, g, jsonify, abort
from flask_login import login_required

from app.routes.server import bp
import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.backup as backup_sql
import app.modules.common.common as common
import app.modules.roxywi.group as group_mod
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.server.ssh as ssh_mod
import app.modules.server.server as server_mod
import app.modules.tools.smon as smon_mod
import app.modules.service.backup as backup_mod
from app.middleware import get_user_params

error_mess = roxywi_common.return_error_message()


@bp.before_request
@login_required
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/check/ssh/<server_ip>')
def check_ssh(server_ip):
    roxywi_auth.page_for_admin(level=2)
    server_ip = common.is_ip_or_dns(server_ip)

    try:
        return server_mod.ssh_command(server_ip, "ls -1t")
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
    command = "sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}' |awk -F':' '{print $1}'"

    return server_mod.ssh_command(server_ip, command)


@bp.route('/show/ip/<server_ip>')
def show_ip_by_id(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    if server_ip == '':
        raise Exception('error: Cannot find server ip')
    commands = 'sudo hostname -I | tr " " "\\n"|sed "/^$/d"'

    return server_mod.ssh_command(server_ip, commands, ip="1")


@bp.route('/show/ip/<int:server_id>')
def show_ip(server_id):
    server_ip = server_sql.get_server_by_id(server_id)
    commands = 'sudo hostname -I | tr " " "\\n"|sed "/^$/d"'

    return server_mod.ssh_command(server_ip.ip, commands, ip="1")


@bp.post('/create')
@get_user_params()
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
                try:
                    user_group = roxywi_common.get_user_group(id=1)
                    json_data = {
                        "name": hostname,
                        "ip": ip,
                        "port": "0",
                        "enabled": "1",
                        "url": "",
                        "body": "",
                        "group": hostname,
                        "desc": f"Ping {hostname}",
                        "tg": "0",
                        "slack": "0",
                        "pd": "0",
                        "resolver": "",
                        "record_type": "",
                        "packet_size": "56",
                        "http_method": "",
                        "check_type": "ping",
                        "agent_id": "1",
                        "interval": "120",
                    }
                    smon_mod.create_smon(json_data, user_group)
                except Exception as e:
                    roxywi_common.logging(ip, f'error: Cannot add server {hostname} to SMON: {e}', roxywi=1)

            roxywi_common.logging(ip, f'A new server {hostname} has been created', roxywi=1, login=1, keep_history=1, service='server')

            return render_template(
                'ajax/new_server.html', groups=group_sql.select_groups(), servers=server_sql.select_servers(server=ip), lang=lang,
                masters=server_sql.select_servers(get_master_servers=1), sshs=cred_sql.select_ssh(group=group), page=page,
                user_subscription=user_subscription, adding=1
            )
    except Exception as e:
        return f'{e}'


@bp.post('/create/after')
def after_add():
    hostname = common.checkAjaxInput(request.form.get('servername'))
    ip = common.is_ip_or_dns(request.form.get('newip'))
    scan_server = common.checkAjaxInput(request.form.get('scan_server'))

    try:
        return server_mod.update_server_after_creating(hostname, ip, scan_server)
    except Exception as e:
        return str(e)


@bp.post('/update')
def update_server():
    roxywi_auth.page_for_admin(level=2)
    name = request.form.get('updateserver')
    group = request.form.get('servergroup')
    typeip = request.form.get('typeip')
    firewall = request.form.get('firewall')
    enable = request.form.get('enable')
    master = int(request.form.get('slave'))
    serv_id = request.form.get('id')
    cred = request.form.get('cred')
    port = request.form.get('port')
    protected = request.form.get('protected')
    desc = request.form.get('desc')

    if name is None or port is None:
        return error_mess
    else:
        server_sql.update_server(name, group, typeip, enable, master, serv_id, cred, port, desc, firewall, protected)
        server_ip = server_sql.select_server_ip_by_id(serv_id)
        roxywi_common.logging(server_ip, f'The server {name} has been update', roxywi=1, login=1, keep_history=1, service='server')

    return 'ok'


@bp.route('/delete/<int:server_id>')
def delete_server(server_id):
    roxywi_auth.page_for_admin(level=2)
    return server_mod.delete_server(server_id)


@bp.route('/group', methods=['POST', 'PUT', 'DELETE'])
def create_group():
    roxywi_auth.page_for_admin()
    json_data = request.get_json()
    if request.method == 'POST':
        name = json_data.get('name')
        desc = json_data.get('desc')
        if name == '':
            return error_mess
        try:
            last_id = group_sql.add_group(name, desc)
            roxywi_common.logging('Roxy-WI server', f'A new group {name} has been created', roxywi=1, login=1)
            return jsonify({
                'status': 'created',
                'id': last_id,
                'data': render_template('ajax/new_group.html', groups=group_sql.select_groups(group=name))}
            )
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', 'Cannot create a new group')
    elif request.method == 'PUT':
        name = json_data.get('name')
        desc = json_data.get('desc')
        group_id = json_data.get('group_id')
        try:
            group_mod.update_group(group_id, name, desc)
            return jsonify({'status': 'updated'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot update group {name}')
    elif request.method == 'DELETE':
        group_id = json_data.get('group_id')
        try:
            group_mod.delete_group(group_id)
            return jsonify({'status': 'deleted'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot delete {group_id}')
    else:
        abort(405)


@bp.route('/ssh', methods=['POST', 'PUT', 'DELETE', 'PATCH'])
@get_user_params()
def create_ssh():
    roxywi_auth.page_for_admin(level=2)
    json_data = request.get_json()
    if request.method == 'POST':
        try:
            data = ssh_mod.create_ssh_cred(json_data)
            return jsonify({'status': 'created', 'id': data['id'], 'data': data['template']})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot create SSH')
    elif request.method == 'PUT':
        try:
            ssh_mod.update_ssh_key(json_data)
            return jsonify({'status': 'updated'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot update SSH')
    elif request.method == 'DELETE':
        ssh_id = int(json_data.get('id'))
        try:
            ssh_mod.delete_ssh_key(ssh_id)
            return jsonify({'status': 'deleted'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot delete SSH')
    elif request.method == 'PATCH':
        user_group = roxywi_common.get_user_group()
        name = common.checkAjaxInput(json_data['name'])
        passphrase = common.checkAjaxInput(json_data['pass'])
        key = json_data['ssh_cert']

        try:
            saved_path = ssh_mod.upload_ssh_key(name, user_group, key, passphrase)
            return jsonify({'status': 'uploaded', 'message': saved_path})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI server', f'Cannot upload ssh')


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


@bp.route('/backup')
@get_user_params()
def load_backup():
    user_group = g.user_params['group_id']
    kwargs = {
        'sshs': cred_sql.select_ssh(group=user_group),
        'servers': roxywi_common.get_dick_permit(virt=1, disable=0, only_group=1),
        'backups': backup_sql.select_backups(),
        's3_backups': backup_sql.select_s3_backups(),
        'gits': backup_sql.select_gits(),
        'lang': g.user_params['lang'],
        'is_needed_tool': common.is_tool('ansible'),
        'user_subscription': roxywi_common.return_user_subscription(),
    }
    return render_template('include/admin_backup.html', **kwargs)

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
