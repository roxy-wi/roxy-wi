from typing import Union

from flask import render_template, request, g
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress

from app.routes.runtime import bp
from app.middleware import get_user_params
import app.modules.common.common as common
import app.modules.config.runtime as runtime
import app.modules.db.server as server_sql
import app.modules.service.haproxy as service_haproxy
from app.modules.roxywi.class_models import DomainName, EscapedString


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def runtimeapi():
    return render_template('runtimeapi.html', lang=g.user_params['lang'])


@bp.route('/backends/<int:server_ip>')
@bp.route('/backends/<server_ip>')
@validate()
def show_backends(server_ip: Union[int, IPvAnyAddress, DomainName]):
    if isinstance(server_ip, int):
        server = server_sql.get_server(server_ip)
        server_ip = server.ip
    try:
        return runtime.show_backends(str(server_ip))
    except Exception as e:
        return f'{e}'


@bp.route('/backend/servers/<server_ip>/<backend>')
@validate()
def show_backend_servers(server_ip: Union[IPvAnyAddress, DomainName], backend: EscapedString):
    try:
        return runtime.show_frontend_backend(str(server_ip), backend)
    except Exception as e:
        return f'{e}'


@bp.route('/backend/server/<server_ip>/<backend>/<backend_server>')
@validate()
def show_backend_server(server_ip: Union[IPvAnyAddress, DomainName], backend: EscapedString, backend_server: EscapedString):
    try:
        return runtime.show_server(str(server_ip), backend, backend_server)
    except Exception as e:
        return f'{e}'


@bp.route('/server', methods=['POST', 'PUT', 'DELETE'])
def change_ip_port():
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    backend_backend = common.checkAjaxInput(request.form.get('backend_backend'))
    backend_server = common.checkAjaxInput(request.form.get('backend_server'))
    backend_ip = common.checkAjaxInput(request.form.get('backend_ip'))
    backend_port = common.checkAjaxInput(request.form.get('backend_port'))
    if request.method == 'PUT':
        try:
            return runtime.change_ip_and_port(server_ip, backend_backend, backend_server, backend_ip, backend_port)
        except Exception as e:
            return f'{e}'
    elif request.method == 'POST':
        check = common.checkAjaxInput(request.form.get('check'))
        port_check = common.checkAjaxInput(request.form.get('port_check'))
        try:
            return runtime.add_server(server_ip, backend_backend, backend_server, backend_ip, backend_port, check, port_check)
        except Exception as e:
            return f'{e}'
    elif request.method == 'DELETE':
        return runtime.delete_server(server_ip, backend_backend, backend_server)


@bp.route('/maxconn/<server_ip>')
@validate()
def maxconn_select(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.get_backends_from_config(str(server_ip), backends='frontend')
    except Exception as e:
        return f'{e}'


@bp.route('/maxconn/<type_maxconn>/<server_ip>', methods=['POST'])
@validate()
def change_maxconn(type_maxconn: str, server_ip: Union[IPvAnyAddress, DomainName]):
    server_ip = str(server_ip)
    maxconn = common.checkAjaxInput(request.form.get('maxconn'))

    if type_maxconn == 'global':
        try:
            return runtime.change_maxconn_global(server_ip, maxconn)
        except Exception as e:
            return f'{e}'
    elif type_maxconn == 'frontend':
        frontend = common.checkAjaxInput(request.form.get('maxconn_frontend'))

        try:
            return runtime.change_maxconn_frontend(server_ip, maxconn, frontend)
        except Exception as e:
            return f'{e}'
    elif type_maxconn == 'backend':
        backend = common.checkAjaxInput(request.form.get('maxconn_backend'))
        backend_server = common.checkAjaxInput(request.form.get('maxconn_backend_server'))

        try:
            return runtime.change_maxconn_backend(server_ip, backend, backend_server, maxconn)
        except Exception as e:
            return f'{e}'
    else:
        return 'error: Wrong backend'


@bp.route('/action/<server_ip>', methods=['POST'])
@get_user_params()
@validate()
def action(server_ip: Union[IPvAnyAddress, DomainName]):
    enable = common.checkAjaxInput(request.form.get('servaction'))
    backend = common.checkAjaxInput(request.form.get('servbackend'))
    save = request.form.get('save')

    try:
        return service_haproxy.runtime_command(str(server_ip), enable, backend, save)
    except Exception as e:
        return f'{e}'


@bp.post('/stats/action/<server_ip>')
@get_user_params()
@validate()
def stat_page_action(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return service_haproxy.stat_page_action(str(server_ip), g.user_params['group_id'])
    except Exception as e:
        return f'{e}'


@bp.route('/tables/<server_ip>')
@validate()
def get_all_tables(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.get_all_stick_table(str(server_ip))
    except Exception as e:
        return f'{e}'


@bp.route('/table/<server_ip>/<table>')
@validate()
def get_table(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString):
    try:
        return runtime.table_select(str(server_ip), table)
    except Exception as e:
        return f'{e}'


@bp.route('/table/delete/<server_ip>/<table>/<ip_for_delete>')
@validate()
def delete_ip(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString, ip_for_delete: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.delete_ip_from_stick_table(str(server_ip), str(ip_for_delete), table)
    except Exception as e:
        return f'{e}'


@bp.route('/table/clear/<server_ip>/<table>')
@validate()
def clear_table(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString):
    try:
        return runtime.clear_stick_table(str(server_ip), table)
    except Exception as e:
        return f'{e}'


@bp.route('/session/<server_ip>')
@validate()
def select_sessions(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.select_session(str(server_ip))
    except Exception as e:
        return f'{e}'


@bp.route('/session/<server_ip>/<sess_id>')
@validate()
def show_sessions(server_ip: Union[IPvAnyAddress, DomainName], sess_id: EscapedString):
    try:
        return runtime.show_session(str(server_ip), sess_id)
    except Exception as e:
        return f'{e}'


@bp.route('/session/delete/<server_ip>/<sess_id>')
@validate()
def delete_session(server_ip: Union[IPvAnyAddress, DomainName], sess_id: EscapedString):
    try:
        return runtime.delete_session(str(server_ip), sess_id)
    except Exception as e:
        return f'{e}'


@bp.route('/list/<server_ip>')
@validate()
def get_lists(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.list_of_lists(str(server_ip))
    except Exception as e:
        return f'{e}'


@bp.route('/list/<server_ip>/<int:list_id>/<color>/<list_name>')
@validate()
def get_list(server_ip: Union[IPvAnyAddress, DomainName], list_id: int, color: EscapedString, list_name: EscapedString):
    try:
        return runtime.show_lists(str(server_ip), list_id, color, list_name)
    except Exception as e:
        return f'{e}'


@bp.route('/list/delete', methods=['POST'])
def delete_ip_from_list():
    ip_id = common.checkAjaxInput(request.form.get('list_ip_id_for_delete'))
    ip = common.is_ip_or_dns(request.form.get('list_ip_for_delete'))
    serv = common.is_ip_or_dns(request.form.get('serv'))
    list_id = common.checkAjaxInput(request.form.get('list_id_for_delete'))
    list_name = common.checkAjaxInput(request.form.get('list_name'))

    try:
        return runtime.delete_ip_from_list(serv, ip_id, ip, list_id, list_name)
    except Exception as e:
        return f'{e}'


@bp.route('/list/add', methods=['POST'])
def add_ip_to_list():
    ip = request.form.get('list_ip_for_add')
    ip = common.is_ip_or_dns(ip.strip())
    serv = common.is_ip_or_dns(request.form.get('serv'))
    list_id = common.checkAjaxInput(request.form.get('list_id_for_add'))
    list_name = common.checkAjaxInput(request.form.get('list_name'))

    try:
        return runtime.add_ip_to_list(serv, ip, list_id, list_name)
    except Exception as e:
        return f'{e}'
