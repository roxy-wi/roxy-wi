import os
from typing import Literal

from flask import render_template, request, jsonify, redirect, url_for, g
from flask_jwt_extended import jwt_required, get_jwt
from flask_pydantic import validate

from app.modules.roxywi.class_models import SSLCertUploadRequest, DataStrResponse, SavedServerRequest, BaseResponse, \
    EscapedString
from app.routes.add import bp
import app.modules.db.add as add_sql
import app.modules.db.server as server_sql
from app.middleware import check_services, get_user_params
import app.modules.config.add as add_mod
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.views.service.haproxy_section_views import (GlobalSectionView, DefaultsSectionView, ListenSectionView,
                                                     UserListSectionView, PeersSectionView)
from app.views.service.haproxy_lists_views import HaproxyListView

get_config = roxy_wi_tools.GetConfigVar()


def register_api_id_ip(view, endpoint, url: str = '', methods: list = ['GET', 'POST']):
    for point in ('_id', '_ip'):
        view_func = view.as_view(f'{endpoint}_{point}')
        pk = 'int:' if point == '_id' else ''
        bp.add_url_rule(f'/<any(haproxy, nginx, apache, keepalived):service>/<{pk}server_id>{url}', view_func=view_func, methods=methods)


register_api_id_ip(ListenSectionView, 'haproxy_section_post_a', '/section/<any(listen, frontend, backend):section_type>', methods=['POST'])
register_api_id_ip(ListenSectionView, 'haproxy_section_a', '/section/<any(listen, frontend, backend):section_type>/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(UserListSectionView, 'haproxy_userlist_post_a', '/section/userlist', methods=['POST'])
register_api_id_ip(UserListSectionView, 'haproxy_userlist_a', '/section/userlist/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(PeersSectionView, 'haproxy_peers_post_a', '/section/peers', methods=['POST'])
register_api_id_ip(PeersSectionView, 'haproxy_peers_a', '/section/peers/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(GlobalSectionView, 'haproxy_global_a', '/section/global', methods=['GET', 'PUT'])
register_api_id_ip(DefaultsSectionView, 'haproxy_defaults_a', '/section/defaults', methods=['GET', 'PUT'])
bp.add_url_rule('/<any(haproxy):service>/list/<list_name>/<color>', view_func=HaproxyListView.as_view('list_get'), methods=['GET'])
bp.add_url_rule('/<any(haproxy):service>/list', view_func=HaproxyListView.as_view('list_post'), methods=['POST', 'DELETE'])


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/<service>')
@check_services
@get_user_params()
def add(service):
    """
    Show page for Adding proxy and section for HAProxy and NGINX
    :param service: Service name for service in what will be add
    :return: Template with Add page or redirect to the index if no needed permission
    """
    roxywi_auth.page_for_admin(level=3)
    kwargs = {
        'h2': 1,
        'add': request.form.get('add'),
        'conf_add': request.form.get('conf'),
        'lang': g.user_params['lang'],
        'all_servers': roxywi_common.get_dick_permit()
    }

    if service == 'haproxy':
        claims = get_jwt()
        user_group = claims['group']
        lib_path = get_config.get_config_var('main', 'lib_path')
        list_dir = lib_path + "/lists"
        white_dir = lib_path + "/lists/" + user_group + "/white"
        black_dir = lib_path + "/lists/" + user_group + "/black"

        if not os.path.exists(list_dir):
            os.makedirs(list_dir)
        if not os.path.exists(list_dir + "/" + user_group):
            os.makedirs(list_dir + "/" + user_group)
        if not os.path.exists(white_dir):
            os.makedirs(white_dir)
        if not os.path.exists(black_dir):
            os.makedirs(black_dir)

        kwargs.setdefault('options', add_sql.select_options())
        kwargs.setdefault('saved_servers', add_sql.select_saved_servers())
        kwargs.setdefault('white_lists', roxywi_common.get_files(folder=white_dir, file_format="lst"))
        kwargs.setdefault('black_lists', roxywi_common.get_files(folder=black_dir, file_format="lst"))
        kwargs.setdefault('maps', roxywi_common.get_files(folder=f'{lib_path}/maps/{user_group}', file_format="map"))

        return render_template('add.html', **kwargs)
    elif service == 'nginx':
        return render_template('add_nginx.html', **kwargs)
    else:
        return redirect(url_for('index'))


@bp.route('/haproxy/get_section_html')
@get_user_params()
def get_section_html():
    lang = g.user_params['lang']
    return render_template('ajax/config_show_add_sections.html', lang=lang)


@bp.route('/haproxy/bwlists/<color>/<int:group>')
@validate()
def get_bwlists(color: Literal['black', 'white'], group):
    return add_mod.get_bwlists_for_autocomplete(color, group)


@bp.route('/option/get/<group>')
def get_option(group):
    term = request.args.get('term')

    return jsonify(add_mod.get_saved_option(group, term))


@bp.post('/option/save')
@get_user_params()
def save_option():
    option = common.checkAjaxInput(request.form.get('option'))
    group = g.user_params['group_id']

    return add_mod.create_saved_option(option, group)


@bp.post('/option/update')
def update_option():
    option = common.checkAjaxInput(request.form.get('option'))
    option_id = int(request.form.get('id'))

    try:
        add_sql.update_options(option, option_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/option/delete/<int:option_id>')
def delete_option(option_id):
    try:
        add_sql.delete_option(option_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/server/get/<int:group>')
def get_saved_server(group):
    term = common.checkAjaxInput(request.args.get('term'))

    return jsonify(add_mod.get_saved_servers(group, term))


@bp.post('/server')
@get_user_params()
@validate(body=SavedServerRequest)
def saved_server(body: SavedServerRequest):
    group = g.user_params['group_id']
    try:
        data = add_mod.create_saved_server(body.server, group, body.description)
        return DataStrResponse(data=data).model_dump(mode='json'), 201
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create server')


@bp.put('/server/<int:server_id>')
@validate(body=SavedServerRequest)
def update_saved_server(server_id: int, body: SavedServerRequest):
    try:
        add_sql.update_saved_server(body.server, body.description, server_id)
        return BaseResponse().model_dump(mode='json'), 201
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update server')


@bp.delete('/server/<int:server_id>')
def delete_saved_server(server_id):
    try:
        add_sql.delete_saved_server(server_id)
        return BaseResponse().model_dump(mode='json'), 204
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot delete server')


@bp.route('/certs/<int:server_id>')
def get_certs(server_id: int):
    server_ip = server_sql.get_server(server_id).ip
    return add_mod.get_ssl_certs(server_ip)


@bp.route('/cert/<int:server_id>/<cert_id>', methods=['DELETE', 'GET'])
@validate()
def get_cert(server_id: int, cert_id: EscapedString):
    server_ip = server_sql.get_server(server_id).ip
    if request.method == 'DELETE':
        return add_mod.del_ssl_cert(server_ip, cert_id)
    elif request.method == 'GET':
        return add_mod.get_ssl_cert(server_ip, cert_id)


@bp.post('/cert/add')
@validate(body=SSLCertUploadRequest)
def upload_cert(body: SSLCertUploadRequest):
    try:
        data = add_mod.upload_ssl_cert(body.server_ip, body.name, body.cert.replace("'", ""), body.cert_type)
        return jsonify(data), 201
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot upload SSL certificate')


@bp.route('/cert/get/raw/<server_id>/<cert_id>')
@validate()
def get_cert_raw(server_id: int, cert_id: EscapedString):
    server_ip = server_sql.get_server(server_id).ip
    return add_mod.get_ssl_raw_cert(server_ip, cert_id)


@bp.route('/map', methods=['POST', 'PUT', 'DELETE', 'GET'])
@get_user_params()
def create_map():
    server_ip = common.checkAjaxInput(request.form.get('serv'))
    map_name = common.checkAjaxInput(request.form.get('map_name')) or common.checkAjaxInput(request.args.get('map_name'))
    group = g.user_params['group_id']
    if request.method == 'POST':
        try:
            return add_mod.create_map(server_ip, map_name, group)
        except Exception as e:
            return str(e)
    elif request.method == 'PUT':
        content = request.form.get('content')
        action = common.checkAjaxInput(request.form.get('map_restart'))

        return add_mod.save_map(map_name, content, group, server_ip, action), 201
    elif request.method == 'DELETE':
        server_id = common.checkAjaxInput(request.form.get('serv'))
        return add_mod.delete_map(map_name, group, server_id)
    elif request.method == 'GET':
        return add_mod.edit_map(map_name, group)


@bp.post('/nginx/upstream')
@get_user_params()
def add_nginx_upstream():
    roxywi_auth.page_for_admin(level=3)

    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    new_upstream = request.form.get('upstream')
    balance = request.form.get("balance")
    config_add = ''
    servers_split = ''
    generate = request.form.get('generateconfig')

    if balance == 'round_robin' or balance is None:
        balance = ''
    else:
        balance = f'    {balance};\n'

    if new_upstream != '':
        config_add = f'upstream {new_upstream} {{\n'
        config_add += balance
        config_name = f'upstream_{new_upstream}'

    if request.form.get('keepalive') != '':
        config_add += f'    keepalive {request.form.get("keepalive")};\n'

    if request.form.get('servers') is not None:
        servers = request.form.getlist('servers')
        server_port = request.form.getlist('server_port')
        max_fails = request.form.getlist('max_fails')
        fail_timeout = request.form.getlist('fail_timeout')
        i = 0
        for server in servers:
            if server == '':
                continue
            try:
                max_fails_val = f'max_fails={max_fails[i]}'
            except Exception:
                max_fails_val = 'max_fails=1'

            try:
                fail_timeout_val = f'fail_timeout={fail_timeout[i]}'
            except Exception:
                fail_timeout_val = 'fail_timeout=1'

            servers_split += f"    server {server}:{server_port[i]} {max_fails_val} {fail_timeout_val}s; \n"
            i += 1
    config_add += f'{servers_split} }}\n'

    if generate:
        return config_add
    else:
        try:
            return add_mod.save_nginx_config(config_add, server_ip, config_name)
        except Exception as e:
            return str(e)
