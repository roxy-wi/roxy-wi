from flask import render_template, request, redirect, url_for, g
from flask_login import login_required

from app.routes.runtime import bp
from middleware import get_user_params
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
import app.modules.config.runtime as runtime
import app.modules.service.haproxy as service_haproxy


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def runtimeapi():
    user_params = g.user_params
    servbackend = ""

    return render_template(
        'runtimeapi.html', title="RunTime API", role=user_params['role'], user=user_params['user'], select_id="serv",
        selects=user_params['servers'], token=user_params['token'], user_services=user_params['user_services'],
        servbackend=servbackend, lang=user_params['lang']
    )


@bp.route('/backends/<server_ip>')
def show_backends(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return runtime.show_backends(server_ip)


@bp.route('/backend/servers/<server_ip>/<backend>')
def show_backend_servers(server_ip, backend):
    server_ip = common.is_ip_or_dns(server_ip)
    backend = common.checkAjaxInput(backend)

    return runtime.show_frontend_backend(server_ip, backend)


@bp.route('/backend/server/<server_ip>/<backend>/<backend_server>')
def show_backend_server(server_ip, backend, backend_server):
    server_ip = common.is_ip_or_dns(server_ip)
    backend = common.checkAjaxInput(backend)
    backend_server = common.checkAjaxInput(backend_server)

    return runtime.show_server(server_ip, backend, backend_server)


@bp.route('/change/ip', methods=['POST'])
def change_ip_port():
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    backend_backend = common.checkAjaxInput(request.form.get('backend_backend'))
    backend_server = common.checkAjaxInput(request.form.get('backend_server'))
    backend_ip = common.checkAjaxInput(request.form.get('backend_ip'))
    backend_port = common.checkAjaxInput(request.form.get('backend_port'))

    return runtime.change_ip_and_port(server_ip, backend_backend, backend_server, backend_ip, backend_port)


@bp.route('/maxconn/<server_ip>')
def maxconn_select(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return runtime.get_backends_from_config(server_ip, backends='frontend')


@bp.route('/maxconn/<type_maxconn>/<server_ip>', methods=['POST'])
def change_maxconn(type_maxconn, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    maxconn = common.checkAjaxInput(request.form.get('maxconn'))

    if type_maxconn == 'global':

        return runtime.change_maxconn_global(server_ip, maxconn)
    elif type_maxconn == 'frontend':
        frontend = common.checkAjaxInput(request.form.get('maxconn_frontend'))

        return runtime.change_maxconn_frontend(server_ip, maxconn, frontend)
    elif type_maxconn == 'backend':
        backend = common.checkAjaxInput(request.form.get('maxconn_backend'))
        backend_server = common.checkAjaxInput(request.form.get('maxconn_backend_server'))

        return runtime.change_maxconn_backend(server_ip, backend, backend_server, maxconn)
    else:
        return 'error: Wrong backend'


@bp.route('/action/<server_ip>', methods=['POST'])
def action(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    enable = common.checkAjaxInput(request.form.get('servaction'))
    backend = common.checkAjaxInput(request.form.get('servbackend'))
    save = request.form.get('save')

    return service_haproxy.runtime_command(server_ip, enable, backend, save)


@bp.route('/tables/<server_ip>')
def get_all_tables(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return runtime.get_all_stick_table(server_ip)


@bp.route('/table/<server_ip>/<table>')
def get_table(server_ip, table):
    server_ip = common.is_ip_or_dns(server_ip)
    table = common.checkAjaxInput(table)

    return runtime.table_select(server_ip, table)


@bp.route('/table/delete/<server_ip>/<table>/<ip_for_delete>')
def delete_ip(server_ip, table, ip_for_delete):
    server_ip = common.is_ip_or_dns(server_ip)
    table = common.checkAjaxInput(table)
    ip_for_delete = common.is_ip_or_dns(ip_for_delete)

    return runtime.delete_ip_from_stick_table(server_ip, ip_for_delete, table)


@bp.route('/table/clear/<server_ip>/<table>')
def clear_table(server_ip, table):
    server_ip = common.is_ip_or_dns(server_ip)
    table = common.checkAjaxInput(table)

    return runtime.clear_stick_table(server_ip, table)


@bp.route('/session/<server_ip>')
def select_sessions(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return runtime.select_session(server_ip)


@bp.route('/session/<server_ip>/<sess_id>')
def show_sessions(server_ip, sess_id):
    server_ip = common.is_ip_or_dns(server_ip)
    sess_id = common.checkAjaxInput(sess_id)

    return runtime.show_session(server_ip, sess_id)


@bp.route('/session/delete/<server_ip>/<sess_id>')
def delete_session(server_ip, sess_id):
    server_ip = common.is_ip_or_dns(server_ip)
    sess_id = common.checkAjaxInput(sess_id)

    return runtime.delete_session(server_ip, sess_id)


@bp.route('/list/<server_ip>')
def get_lists(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    return runtime.list_of_lists(server_ip)


@bp.route('/list/<server_ip>/<int:list_id>/<list_name>')
def get_list(server_ip, list_id, list_name):
    server_ip = common.is_ip_or_dns(server_ip)
    list_name = common.checkAjaxInput(list_name)

    return runtime.show_lists(server_ip, list_id, list_name)


@bp.route('/list/delete', methods=['POST'])
def delete_ip_from_list():
    ip_id = common.checkAjaxInput(request.form.get('list_ip_id_for_delete'))
    ip = common.is_ip_or_dns(request.form.get('list_ip_for_delete'))
    list_id = common.checkAjaxInput(request.form.get('list_id_for_delete'))
    list_name = common.checkAjaxInput(request.form.get('list_name'))

    return runtime.delete_ip_from_list(serv, ip_id, ip, list_id, list_name)


@bp.route('/list/add', methods=['POST'])
def add_ip_to_list():
    ip = request.form.get('list_ip_for_add')
    ip = ip.strip()
    ip = common.is_ip_or_dns(ip)
    list_id = common.checkAjaxInput(request.form.get('list_id_for_add'))
    list_name = common.checkAjaxInput(request.form.get('list_name'))

    return runtime.add_ip_to_list(serv, ip, list_id, list_name)
