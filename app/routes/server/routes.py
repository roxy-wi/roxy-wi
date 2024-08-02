import json
import time

from flask import render_template, request, g, jsonify, Response
from flask_jwt_extended import jwt_required

from app.routes.server import bp
import app.modules.db.cred as cred_sql
import app.modules.db.server as server_sql
import app.modules.db.backup as backup_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod
import app.modules.service.backup as backup_mod
from app.middleware import get_user_params
from app.views.server.views import ServerView, CredView, CredsView, ServerGroupView, ServerGroupsView, ServerIPView
from app.views.server.backup_vews import BackupView, S3BackupView


def register_api(view, endpoint, url, pk='listener_id', pk_type='int'):
    view_func = view.as_view(endpoint)
    bp.add_url_rule(url, view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'{url}/<{pk_type}:{pk}>', view_func=view_func, methods=['GET', 'PUT', 'PATCH', 'DELETE'])


register_api(ServerView, 'server', '', 'server_id')
register_api(ServerGroupView, 'group', '/group', 'group_id')
register_api(CredView, 'cred', '/cred', 'creds_id')
bp.add_url_rule('/groups', view_func=ServerGroupsView.as_view('groups'), methods=['GET'])
bp.add_url_rule('/creds', view_func=CredsView.as_view('creds'), methods=['GET'])

bp.add_url_rule('/<server_id>/ip', view_func=ServerIPView.as_view('server_ip_ip'), methods=['GET'])
bp.add_url_rule('/<int:server_id>/ip', view_func=ServerIPView.as_view('server_ip'), methods=['GET'])
bp.add_url_rule('/backup', view_func=BackupView.as_view('backup', False), methods=['POST'])
bp.add_url_rule('/backup/s3', view_func=S3BackupView.as_view('backup_s3', False), methods=['POST'])

error_mess = roxywi_common.return_error_message()


@bp.before_request
@jwt_required()
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


@bp.route('/check/server/<int:server_id>')
def check_server(server_id):
    def get_check():
        while True:
            try:
                server = server_sql.get_server_by_id(server_id)
            except Exception as e:
                raise e
            result = server_mod.server_is_up(server.ip)
            status = {
                "status": result,
                'name': server.hostname,
                'ip': server.ip,
                'port': server.port,
                'enabled': server.enabled,
                'creds_id': server.cred_id,
                'group_id': server.group_id,
                'firewall': server.firewall_enable,
                'slave': server.master,
                'type_ip': server.type_ip,
                'description': server.description,
                'protected': server.protected,
            }
            yield f'data:{json.dumps(status)}\n\n'
            time.sleep(10)

    response = Response(get_check(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@bp.route('/show/if/<server_ip>')
def show_if(server_ip):
    roxywi_auth.page_for_admin(level=2)
    server_ip = common.is_ip_or_dns(server_ip)
    command = "sudo ip link|grep 'UP' |grep -v 'lo'| awk '{print $2}' |awk -F':' '{print $1}'"

    return server_mod.ssh_command(server_ip, command)


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


@bp.route('/backup', methods=['GET'])
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


@bp.route('/git', methods=['DELETE', 'POST'])
def create_git_backup():
    json_data = request.get_json()
    server_id = int(json_data['server'])
    service_id = int(json_data['service'])
    git_init = int(json_data['init'])
    repo = common.checkAjaxInput(json_data['repo'])
    branch = common.checkAjaxInput(json_data['branch'])
    period = common.checkAjaxInput(json_data['time'])
    cred = int(json_data['cred'])
    del_job = int(json_data['del_job'])
    description = common.checkAjaxInput(json_data['desc'])
    backup_id = ''
    if request.method == 'DELETE':
        backup_id = json_data['backup_id']

    try:
        data = backup_mod.git_backup(server_id, service_id, git_init, repo, branch, period, cred, del_job, description, backup_id)
        return jsonify({'status': 'ok', 'data': data})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, f'Cannot {request.method} git backup')
