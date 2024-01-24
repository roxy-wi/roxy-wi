import os

from flask import render_template, request, jsonify, redirect, url_for, g
from flask_login import login_required

from app.routes.add import bp
import app.modules.db.sql as sql
from middleware import check_services, get_user_params
import app.modules.config.add as add_mod
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.server.server as server_mod

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
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
        'user_params': g.user_params,
        'add': request.form.get('add'),
        'conf_add': request.form.get('conf'),
        'lang': g.user_params['lang']
    }

    if service == 'haproxy':
        user_group = request.cookies.get('group')
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

        kwargs.setdefault('options', sql.select_options())
        kwargs.setdefault('saved_servers', sql.select_saved_servers())
        kwargs.setdefault('white_lists', roxywi_common.get_files(folder=white_dir, file_format="lst"))
        kwargs.setdefault('black_lists', roxywi_common.get_files(folder=black_dir, file_format="lst"))
        kwargs.setdefault('maps', roxywi_common.get_files(folder=f'{lib_path}/maps/{user_group}', file_format="map"))

        return render_template('add.html', **kwargs)
    elif service == 'nginx':
        return render_template('add_nginx.html', **kwargs)
    else:
        return redirect(url_for('index'))


@bp.route('/haproxy/add', methods=['POST'])
def add_haproxy():
    """
    Add HAProxy sections
    :return: Generated section or output of adding status
    """
    roxywi_auth.page_for_admin(level=3)

    haproxy_dir = sql.get_setting('haproxy_dir')
    generate = request.form.get('generateconfig')
    server_ip = request.form.get('serv')
    port = request.form.getlist('port')
    bind = ""
    ip = ""
    force_close = request.form.get('force_close')
    balance = ""
    mode = f"    mode {request.form.get('mode')}\n"
    maxconn = ""
    options_split = ""
    ssl = ""
    ssl_check = ""
    backend = ""
    headers = ""
    acl = ""
    servers_split = ""
    new_listener = request.form.get('listener')
    new_frontend = request.form.get('frontend')
    new_backend = request.form.get('new_backend')

    if request.form.get('balance') is not None:
        balance = "    balance " + request.form.get('balance') + "\n"

    if request.form.get('health_check') is not None:
        health_check = request.form.get('health_check')
        if health_check == 'option httpchk' and request.form.get('checks_http_domain') is not None:
            health_check = health_check + ' GET ' + request.form.get(
                'checks_http_path') + ' "HTTP/1.0\\r\\nHost: ' + request.form.get('checks_http_domain') + '"'
        balance += f"    {health_check}\n"

    if request.form.get('ip') is not None:
        ip = request.form.getlist('ip')

    if new_listener is not None:
        name = f"listen {new_listener}"
        end_name = new_listener
    elif new_frontend is not None:
        name = f"frontend {new_frontend}"
        end_name = new_frontend
    elif new_backend is not None:
        name = f"backend {new_backend}"
        end_name = new_backend
    else:
        return 'error: The name cannot be empty'

    if request.form.get('backends') is not None:
        backend = f"    default_backend {request.form.get('backends')}\n"

    if request.form.get('maxconn'):
        maxconn = f"    maxconn {request.form.get('maxconn')}\n"

    if request.form.get('ssl') == "https" and request.form.get('mode') != "tcp":
        cert_path = sql.get_setting('cert_path')
        if request.form.get('cert') is not None:
            ssl = f"ssl crt {cert_path}{request.form.get('cert')}"
        if request.form.get('ssl-dis-check') is None:
            if request.form.get('ssl-check') == "ssl-check":
                ssl_check = " ssl verify none"
            else:
                ssl_check = " ssl verify"

    if ip or port:
        if type(port) is list:
            i = 0
            for _p in port:
                if ip[i] == 'IsEmptY':
                    if ip[i] == 'IsEmptY' and port[i] == 'IsEmptY':
                        i += 1
                        continue
                    else:
                        port_value = port[i]
                    bind += f"    bind *:{port_value} {ssl}\n"
                else:
                    if port[i] == 'IsEmptY':
                        return 'error: IP cannot be bind without a port'
                    else:
                        port_value = port[i]
                    bind += f"    bind {ip[i]}:{port_value} {ssl}\n"
                i += 1

    if request.form.get('default-check') == "1":
        if request.form.get('check-servers') == "1":
            check = f" check inter {request.form.get('inter')} rise {request.form.get('rise')} fall {request.form.get('fall')}{ssl_check}"
        else:
            check = ""
    else:
        if request.form.get('check-servers') != "1":
            check = ""
        else:
            check = f" check{ssl_check}"

    if request.form.get('option') is not None:
        options = request.form.get('option')
        i = options.split("\n")
        for j in i:
            options_split += f"    {j}\n"

    if force_close == "1":
        options_split += "    option http-server-close\n"
    elif force_close == "2":
        options_split += "    option forceclose\n"
    elif force_close == "3":
        options_split += "    option http-pretend-keepalive\n"

    if request.form.get('whitelist'):
        options_split += "    tcp-request connection accept if { src -f " + haproxy_dir + "/white/" + request.form.get(
            'whitelist') + " }\n"

    if request.form.get('blacklist'):
        options_split += "    tcp-request connection reject if { src -f " + haproxy_dir + "/black/" + request.form.get(
            'blacklist') + " }\n"

    if request.form.get('cookie'):
        cookie = f"    cookie {request.form.get('cookie_name')}"
        if request.form.get('cookie_domain'):
            cookie += f" domain {request.form.get('cookie_domain')}"
        if request.form.get('rewrite'):
            rewrite = request.form.get('rewrite')
        else:
            rewrite = ""
        if request.form.get('prefix'):
            prefix = request.form.get('prefix')
        else:
            prefix = ""
        if request.form.get('nocache'):
            nocache = request.form.get('nocache')
        else:
            nocache = ""
        if request.form.get('postonly'):
            postonly = request.form.get('postonly')
        else:
            postonly = ""
        if request.form.get('dynamic'):
            dynamic = request.form.get('dynamic')
        else:
            dynamic = ""
        cookie += f" {rewrite} {prefix} {nocache} {postonly} {dynamic}\n"
        options_split += cookie
        if request.form.get('dynamic'):
            options_split += f"    dynamic-cookie-key {request.form.get('dynamic-cookie-key')}\n"

    if request.form.get('headers_res'):
        headers_res = request.form.getlist('headers_res')
        headers_method = request.form.getlist('headers_method')
        header_name = request.form.getlist('header_name')
        header_value = request.form.getlist('header_value')
        i = 0

        for _h in headers_method:
            if headers_method[i] != 'del-header':
                headers += f'    {headers_res[i]} {headers_method[i]} {header_name[i]} {header_value[i]}\n'
            else:
                headers += f'    {headers_res[i]} {headers_method[i]} {header_name[i]}\n'
            i += 1

    if request.form.get('acl_if'):
        acl_if = request.form.getlist('acl_if')
        acl_value = request.form.getlist('acl_value')
        acl_then = request.form.getlist('acl_then')
        acl_then_values = request.form.getlist('acl_then_value')
        i = 0

        for a in acl_if:
            acl_then_value = '' if acl_then_values[i] == 'IsEmptY' else acl_then_values[i]

            try:
                if a == '1':
                    acl_if_word = 'hdr_beg(host) -i '
                    if request.form.get('ssl') == "https" and request.form.get('mode') != "tcp":
                        acl_if_word = 'ssl_fc_sni -i '
                    if request.form.get('mode') == "tcp":
                        acl_if_word = 'req.ssl_sni -i '
                elif a == '2':
                    acl_if_word = 'hdr_end(host) -i '
                    if request.form.get('ssl') == "https" and request.form.get('mode') != "tcp":
                        acl_if_word = 'ssl_fc_sni -i '
                    if request.form.get('mode') == "tcp":
                        acl_if_word = 'req.ssl_sni -i '
                elif a == '3':
                    acl_if_word = 'path_beg -i '
                elif a == '4':
                    acl_if_word = 'path_end -i '
                elif a == '6':
                    acl_if_word = 'src ip '
                else:
                    acl_if_word = ''

                if acl_then[i] == '5':
                    acl += '    use_backend '
                elif acl_then[i] == '2':
                    acl += '    http-request redirect location '
                elif acl_then[i] == '3':
                    acl += '    http-request allow'
                    acl_then_value = ''
                elif acl_then[i] == '4':
                    acl += '    http-request deny'
                    acl_then_value = ''
                elif acl_then[i] == '6':
                    acl += f'    acl return_{acl_value[i]} {acl_if_word} {acl_value[i]}\n'
                    acl += f'    http-request return if return_{acl_value[i]}\n'
                elif acl_then[i] == '7':
                    acl += f'    acl set_header_{acl_value[i]} {acl_if_word} {acl_value[i]}\n'
                    acl += f'    http-request set-header if set_header_{acl_value[i]}\n'

                if acl_then[i] in ('2', '3', '4', '5'):
                    acl += acl_then_value + ' if { ' + acl_if_word + acl_value[i] + ' } \n'
            except Exception:
                acl = ''

            i += 1

    if request.form.get('circuit_breaking') == "1":
        observe = 'observe ' + request.form.get('circuit_breaking_observe')
        error_limit = ' error-limit ' + request.form.get('circuit_breaking_error_limit')
        circuit_breaking_on_error = ' on-error ' + request.form.get('circuit_breaking_on_error')
        default_server = '    default-server ' + observe + error_limit + circuit_breaking_on_error + '\n'
        servers_split += default_server

    if request.form.get('servers'):
        servers = request.form.getlist('servers')
        server_port = request.form.getlist('server_port')
        send_proxy = request.form.getlist('send_proxy')
        backup = request.form.getlist('backup')
        server_maxconn = request.form.getlist('server_maxconn')
        port_check = request.form.getlist('port_check')
        i = 0
        for server in servers:
            if server == '':
                continue
            if request.form.get('template') is None:
                try:
                    if send_proxy[i] == '1':
                        send_proxy_param = 'send-proxy'
                    else:
                        send_proxy_param = ''
                except Exception:
                    send_proxy_param = ''

                try:
                    if backup[i] == '1':
                        backup_param = 'backup'
                    else:
                        backup_param = ''
                except Exception:
                    backup_param = ''

                try:
                    maxconn_val = server_maxconn[i]
                except Exception:
                    maxconn_val = '200'

                try:
                    port_check_val = port_check[i]
                except Exception:
                    port_check_val = server_port[i]

                servers_split += "    server {0} {0}:{1}{2} port {6} maxconn {5} {3} {4} \n".format(
                    server, server_port[i], check, send_proxy_param, backup_param, maxconn_val, port_check_val
                )
            else:
                servers_split += "    server-template {0} {1} {2}:{3} {4} \n".format(
                    request.form.get('prefix'), request.form.get('template-number'), server, server_port[i], check
                )
            i += 1

    compression = request.form.get("compression")
    cache = request.form.get("cache")
    compression_s = ""
    cache_s = ""
    cache_set = ""
    filter_com = ""
    if compression == "1" or cache == "2":
        filter_com = "    filter compression\n"
        if cache == "2":
            cache_s = f"    http-request cache-use {end_name}\n    http-response cache-store {end_name}\n"
            cache_set = f"cache {end_name}\n    total-max-size 4\n    max-age 240\n"
        if compression == "1":
            compression_s = "    compression algo gzip\n    compression type text/html text/plain text/css\n"

    waf = ""
    if request.form.get('waf'):
        waf = f"    filter spoe engine modsecurity config {haproxy_dir}/waf.conf\n"
        waf += "    http-request deny if { var(txn.modsec.code) -m int gt 0 }\n"

    config_add = f"\n{name}\n{bind}{mode}{maxconn}{balance}{options_split}{cache_s}{filter_com}{compression_s}" \
                 f"{waf}{headers}{acl}{backend}{servers_split}\n{cache_set}\n"

    if generate:
        return config_add
    else:
        try:
            return add_mod.save_to_haproxy_config(config_add, server_ip, name)
        except Exception as e:
            return f'error: Cannot add to config: {e}'


@bp.post('/haproxy/userlist')
def add_userlist():
    """
    Add HAProxy section userlist
    :return: Output of adding status
    """
    roxywi_auth.page_for_admin(level=3)
    return add_mod.add_userlist()


@bp.post('/haproxy/bwlist/create')
@get_user_params()
def create_bwlist():
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    color = common.checkAjaxInput(request.form.get('color'))
    group = g.user_params['group_id']
    list_name = common.checkAjaxInput(request.form.get('bwlists_create'))

    return add_mod.create_bwlist(server_ip, list_name, color, group)


@bp.post('/haproxy/bwlist/save')
@get_user_params()
def save_bwlist():
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    color = common.checkAjaxInput(request.form.get('color'))
    group = g.user_params['group_id']
    bwlists_save = common.checkAjaxInput(request.form.get('bwlists_save'))
    list_con = request.form.get('bwlists_content')
    action = common.checkAjaxInput(request.form.get('bwlists_restart'))

    return add_mod.save_bwlist(bwlists_save, list_con, color, group, server_ip, action)


@bp.route('/haproxy/bwlist/delete/<server_ip>/<color>/<name>/<int:group>')
def delete_bwlist(server_ip, color, name, group):
    server_ip = common.is_ip_or_dns(server_ip)
    color = common.checkAjaxInput(color)
    list_name = common.checkAjaxInput(name)

    return add_mod.delete_bwlist(list_name, color, group, server_ip)


@bp.route('/haproxy/bwlist/<bwlists>/<color>/<int:group>')
def get_bwlist(bwlists, color, group):
    color = common.checkAjaxInput(color)
    bwlists = common.checkAjaxInput(bwlists)

    return add_mod.get_bwlist(color, group, bwlists)


@bp.route('/haproxy/bwlists/<color>/<int:group>')
def get_bwlists(color, group):
    color = common.checkAjaxInput(color)

    return add_mod.get_bwlists_for_autocomplete(color, group)


@bp.route('/haproxy/userlist/<server_ip>')
def show_userlist(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return add_mod.show_userlist(server_ip)


@bp.post('/haproxy/peers')
def add_peers():
    roxywi_auth.page_for_admin(level=3)

    generate = request.form.get('generateconfig')
    server_ip = request.form.get('serv')
    servers_split = ''
    name = "peers " + request.form.get('peers-name') + "\n"
    servers = request.form.getlist('servers')
    server_port = request.form.getlist('server_port')
    servers_name = request.form.getlist('servers_name')
    i = 0

    for server in servers:
        if server == '':
            continue
        servers_split += "    peer {0} {1}:{2} \n".format(servers_name[i], server, server_port[i])
        i += 1

    config_add = "\n" + name + servers_split

    if generate:
        return config_add, 200
    else:
        try:
            return add_mod.save_to_haproxy_config(config_add, server_ip, name)
        except Exception as e:
            return f'error: Cannot add to config: {e}'


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
        sql.update_options(option, option_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/option/delete/<int:option_id>')
def delete_option(option_id):
    try:
        sql.delete_option(option_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/server/get/<int:group>')
def get_saved_server(group):
    term = request.args.get('term')

    return jsonify(add_mod.get_saved_servers(group, term))


@bp.post('/server/save')
@get_user_params()
def save_saved_server():
    server = common.checkAjaxInput(request.form.get('server'))
    group = g.user_params['group_id']
    desc = common.checkAjaxInput(request.form.get('desc'))

    return add_mod.create_saved_server(server, group, desc)


@bp.post('/server/update')
def update_saved_server():
    server = common.checkAjaxInput(request.form.get('server'))
    server_id = int(request.form.get('id'))
    desc = common.checkAjaxInput(request.form.get('desc'))

    try:
        sql.update_savedserver(server, desc, server_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/server/delete/<int:server_id>')
def delete_saved_server(server_id):
    try:
        sql.delete_savedserver(server_id)
    except Exception as e:
        return str(e)
    else:
        return 'ok'


@bp.route('/certs/<server_ip>')
def get_certs(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    return add_mod.get_ssl_certs(server_ip)


@bp.route('/cert/<server_ip>/<cert_id>', methods=['DELETE', 'GET'])
def get_cert(server_ip, cert_id):
    server_ip = common.is_ip_or_dns(server_ip)
    cert_id = common.checkAjaxInput(cert_id)
    if request.method == 'DELETE':
        return add_mod.del_ssl_cert(server_ip, cert_id)
    elif request.method == 'GET':
        return add_mod.get_ssl_cert(server_ip, cert_id)


@bp.post('/cert/add')
def upload_cert():
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    ssl_name = request.form.get('ssl_name')
    ssl_cont = request.form.get('ssl_cert')

    return add_mod.upload_ssl_cert(server_ip, ssl_name, ssl_cont)


@bp.route('/cert/get/raw/<server_ip>/<int:cert_id>')
def get_cert_raw(server_ip, cert_id):
    server_ip = common.is_ip_or_dns(server_ip)
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


@bp.post('lets')
def lets():
    server_ip = common.checkAjaxInput(request.form.get('serv'))
    lets_domain = common.checkAjaxInput(request.form.get('lets_domain'))
    lets_email = common.checkAjaxInput(request.form.get('lets_email'))

    return add_mod.get_le_cert(server_ip, lets_domain, lets_email)


@bp.post('/nginx/upstream')
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


@bp.route('/show/ip/<server_ip>')
def show_ip(server_ip):
    server_ip = common.is_ip_or_dns(server_ip)
    commands = ['sudo hostname -I | tr " " "\\n"|sed "/^$/d"']

    return server_mod.ssh_command(server_ip, commands, ip="1")
