from typing import Union

from flask import render_template, request, g
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress

from app.routes.runtime import bp
from app.middleware import get_user_params, page_for_admin
import app.modules.common.common as common
import app.modules.config.runtime as runtime
import app.modules.db.server as server_sql
import app.modules.service.haproxy as service_haproxy
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi.class_models import DomainName, EscapedString
from app.modules.roxywi.error_handler import safe_error_message


@bp.before_request
@jwt_required()
@get_user_params()
@page_for_admin(level=3)
def before_request():
    """ Protect all the admin endpoints. """
    roxywi_common.require_request_server_access()


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
        return 'error: ' + safe_error_message(e)


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
        return 'error: ' + safe_error_message(e)


@bp.route('/tables/<server_ip>')
@validate()
def get_all_tables(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.get_all_stick_table(str(server_ip))
    except Exception as e:
        return 'error: ' + safe_error_message(e)


@bp.route('/table/<server_ip>/<table>')
@validate()
def get_table(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString):
    try:
        return runtime.table_select(str(server_ip), table)
    except Exception as e:
        return 'error: ' + safe_error_message(e)


@bp.route('/table/delete/<server_ip>/<table>/<ip_for_delete>', methods=['POST'])
@validate()
def delete_ip(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString, ip_for_delete: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.delete_ip_from_stick_table(str(server_ip), str(ip_for_delete), table)
    except Exception as e:
        return 'error: ' + safe_error_message(e)


@bp.route('/table/clear/<server_ip>/<table>', methods=['POST'])
@validate()
def clear_table(server_ip: Union[IPvAnyAddress, DomainName], table: EscapedString):
    try:
        return runtime.clear_stick_table(str(server_ip), table)
    except Exception as e:
        return 'error: ' + safe_error_message(e)


@bp.route('/list/<server_ip>')
@validate()
def get_lists(server_ip: Union[IPvAnyAddress, DomainName]):
    try:
        return runtime.list_of_lists(str(server_ip))
    except Exception as e:
        return 'error: ' + safe_error_message(e)


@bp.route('/list/<server_ip>/<int:list_id>/<color>/<list_name>')
@validate()
def get_list(server_ip: Union[IPvAnyAddress, DomainName], list_id: int, color: EscapedString, list_name: EscapedString):
    try:
        return runtime.show_lists(str(server_ip), list_id, color, list_name)
    except Exception as e:
        return 'error: ' + safe_error_message(e)


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
        return 'error: ' + safe_error_message(e)


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
        return 'error: ' + safe_error_message(e)
