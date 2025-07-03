import os

from flask import render_template, request, g, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from app.routes.config import bp
import app.modules.db.sql as sql
import app.modules.db.config as config_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
from app.middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod
import app.modules.config.common as config_common
import app.modules.config.section as section_mod
import app.modules.service.haproxy as service_haproxy
import app.modules.server.server as server_mod
from app.views.service.views import ServiceConfigView, ServiceConfigVersionsView
from app.modules.roxywi.class_models import DataStrResponse

bp.add_url_rule('/<service>/<server_id>', view_func=ServiceConfigView.as_view('config_view_ip'), methods=['POST'])
bp.add_url_rule('/<service>/<server_id>/versions', view_func=ServiceConfigVersionsView.as_view('config_version'), methods=['DELETE'])


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/<service>/show', methods=['POST'])
@check_services
@get_user_params()
def show_config(service):
    config_file_name = request.json.get('config_file_name')
    configver = request.json.get('configver')
    server_ip = request.json.get('serv')
    claims = get_jwt()
    edit_section = request.json.get('edit_section')

    try:
        data = config_mod.show_config(server_ip, service, config_file_name, configver, claims, edit_section)
        return DataStrResponse(data=data).model_dump(mode='json'), 200
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, '')


@bp.route('/<service>/show-files', methods=['POST'])
@check_services
def show_config_files(service):
    server_ip = request.form.get('serv')
    config_file_name = request.form.get('config_file_name')

    try:
        return config_mod.show_config_files(server_ip, service, config_file_name)
    except Exception as e:
        return f'error: {e}'


@bp.route('/<service>/find-in-config', methods=['POST'])
@check_services
def find_in_config(service):
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    finding_words = request.form.get('words')
    log_path = sql.get_setting(service + '_dir')
    log_path = common.return_nice_path(log_path)
    commands = f'sudo grep "{finding_words}" {log_path}*/*.conf -C 2 -Rn'
    try:
        return_find = server_mod.ssh_command(server_ip, commands, raw=1)
        return_find = config_mod.show_finding_in_config(return_find, grep=finding_words)
    except Exception as e:
        return str(e)

    if 'error: ' in return_find:
        return return_find

    return return_find


@bp.route('/<service>/', defaults={'serv': None, 'edit': None, 'config_file_name': None, 'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/<edit>/', defaults={'config_file_name': None, 'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/show', defaults={'edit': None, 'config_file_name': None, 'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/show/<config_file_name>', defaults={'edit': None, 'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/show-files', defaults={'edit': None, 'config_file_name': None, 'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/<edit>/<config_file_name>', defaults={'new': None}, methods=['GET', 'POST'])
@bp.route('/<service>/<serv>/<edit>/<config_file_name>/<new>', methods=['GET', 'POST'])
@check_services
@get_user_params(0)
def config(service, serv, edit, config_file_name, new):
    config_read = ""
    cfg = ""
    error = ""
    is_restart = ''
    is_serv_protected = ''
    new_config = new

    if serv and edit and new_config is None:
        roxywi_common.check_is_server_in_group(serv)
        is_serv_protected = server_sql.is_serv_protected(serv)
        server_id = server_sql.get_server_by_ip(serv).server_id
        is_restart = service_sql.select_service_setting(server_id, service, 'restart')
        cfg = config_mod.return_cfg(service, serv, config_file_name)

        try:
            error = config_mod.get_config(serv, cfg, service=service, config_file_name=config_file_name)
        except Exception as e:
            return f'error: Cannot download config: {e}'

        try:
            roxywi_common.logging(serv, f" {service.title()} config has been opened")
        except Exception:
            pass

        try:
            conf = open(cfg, "rb")
            config_read = conf.read()
            config_read = config_read.decode('utf-8')
            conf.close()
        except IOError as e:
            return f'Cannot read imported config file {e}', 200

        os.system("/bin/mv %s %s.old" % (cfg, cfg))

    if new_config is not None:
        config_read = ' '

    kwargs = {
        'serv': serv,
        'aftersave': '',
        'config': config_read,
        'cfg': cfg,
        'stderr': '',
        'error': error,
        'service': service,
        'is_restart': is_restart,
        'config_file_name': config_file_name,
        'is_serv_protected': is_serv_protected,
        'service_desc': service_sql.select_service(service),
        'user_subscription': roxywi_common.return_user_subscription(),
        'lang': g.user_params['lang']
    }

    return render_template('config.html', **kwargs)


@bp.route('/versions/<service>', defaults={'server_ip': None}, methods=['GET'])
@bp.route('/versions/<service>/<server_ip>', methods=['GET'])
@check_services
@get_user_params(disable=1)
def versions(service, server_ip):
    roxywi_auth.page_for_admin(level=3)

    kwargs = {
        'serv': server_ip,
        'service': service,
        'lang': g.user_params['lang']
    }
    return render_template('delver.html', **kwargs)


@bp.route('/version/<service>/list', methods=['POST'])
@check_services
def list_of_version(service):
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    config_ver = common.checkAjaxInput(request.form.get('configver'))
    for_delver = common.checkAjaxInput(request.form.get('for_delver'))

    return config_mod.list_of_versions(server_ip, service, config_ver, for_delver)


@bp.route('/versions/<service>/<server_ip>/<configver>', methods=['GET'])
@check_services
@get_user_params(disable=1)
def show_version(service, server_ip, configver):
    roxywi_auth.page_for_admin(level=3)

    kwargs = {
        'serv': server_ip,
        'service': service,
        'lang': g.user_params['lang']
    }

    return render_template('configver.html', **kwargs)


@bp.route('/versions/<service>/<server_ip>/<configver>/save', methods=['POST'])
@check_services
@get_user_params()
def save_version(service, server_ip, configver):
    roxywi_auth.page_for_admin(level=3)
    config_dir = config_common.get_config_dir('haproxy')
    configver = config_dir + configver
    service_desc = service_sql.select_service(service)
    save_action = request.json.get('action')
    try:
        roxywi_common.logging(
            server_ip, f"Version of config has been uploaded {configver}", login=1, keep_history=1, service=service
        )
    except Exception:
        pass

    if service == 'keepalived':
        stderr = config_mod.upload_and_restart(server_ip, configver, save_action, service)
    elif service in ('nginx', 'apache'):
        config_file_name = config_sql.select_remote_path_from_version(server_ip=server_ip, service=service, local_path=configver)
        stderr = config_mod.master_slave_upload_and_restart(server_ip, configver, save_action, service_desc.slug, config_file_name=config_file_name)
    else:
        stderr = config_mod.master_slave_upload_and_restart(server_ip, configver, save_action, service)

    return DataStrResponse(data=stderr).model_dump(mode='json'), 201


@bp.route('/section/haproxy/<server_ip>')
@get_user_params()
def haproxy_section(server_ip):
    cfg = config_common.generate_config_path('haproxy', server_ip)
    error = config_mod.get_config(server_ip, cfg)
    kwargs = {
        'is_restart': 0,
        'config': '',
        'serv': server_ip,
        'sections': section_mod.get_sections(cfg),
        'error': error,
        'lang': g.user_params['lang']
    }

    return render_template('sections.html', **kwargs)


@bp.route('/section/haproxy/<server_ip>/<section>')
@get_user_params()
def haproxy_section_show(server_ip, section):
    cfg = config_common.generate_config_path('haproxy', server_ip)
    error = config_mod.get_config(server_ip, cfg)
    start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section)
    server_id = server_sql.get_server_by_ip(server_ip).server_id
    sections = section_mod.get_sections(cfg)

    os.system(f"/bin/mv {cfg} {cfg}.old")

    try:
        roxywi_common.logging(server_ip, f"A section {section} has been opened")
    except Exception:
        pass

    kwargs = {
        'is_restart': service_sql.select_service_setting(server_id, 'haproxy', 'restart'),
        'serv': server_ip,
        'sections': sections,
        'cfg': cfg,
        'config': config_read,
        'start_line': start_line,
        'end_line': end_line,
        'section': section,
        'error': error,
        'lang': g.user_params['lang']
    }

    return render_template('sections.html', **kwargs)


@bp.route('/section/haproxy/<server_ip>/save', methods=['POST'])
@get_user_params()
def haproxy_section_save(server_ip):
    hap_configs_dir = config_common.get_config_dir('haproxy')
    cfg = config_common.generate_config_path('haproxy', server_ip)
    config_file = request.json.get('config')
    oldcfg = request.json.get('oldconfig')
    save = request.json.get('action')
    start_line = request.json.get('start_line')
    end_line = request.json.get('end_line')

    if save == 'delete':
        config_file = ''
        save = 'reload'

    config_file = section_mod.rewrite_section(start_line, end_line, oldcfg, config_file)

    try:
        with open(cfg, "w") as conf:
            conf.write(config_file)
    except IOError as e:
        return f"error: Cannot read import config file: {e}"

    stderr = config_mod.master_slave_upload_and_restart(server_ip, cfg, save, 'haproxy', oldcfg=oldcfg)

    try:
        os.remove(f"{hap_configs_dir}*.old")
    except IOError:
        pass

    return DataStrResponse(data=stderr).model_dump(mode='json'), 201


@bp.route('/compare/<service>/<serv>')
@bp.route('/map/<service>/<serv>')
@get_user_params()
def show_compare_config(service, serv):
    kwargs = {
        'aftersave': '',
        'serv': serv,
        'cfg': '',
        'config': '',
        'config_file_name': '',
        'is_serv_protected': '',
        'is_restart': '',
        'service': service,
        'stderr': '',
        'error': '',
        'service_desc': service_sql.select_service(service),
        'lang': g.user_params['lang'],
        'user_subscription': roxywi_common.return_user_subscription(),
    }

    return render_template('config.html', **kwargs)


@bp.route('/compare/<service>/<server_ip>/files')
@check_services
def show_configs_for_compare(service, server_ip):
    return config_mod.show_compare_config(server_ip, service)


@bp.post('/compare/<service>/<server_ip>/show')
@check_services
def show_compare(service, server_ip):
    left = request.json.get('left')
    right = request.json.get('right')
    compare = config_mod.compare_config(service, left, right)
    return jsonify({'compare': compare})


@bp.route('/map/haproxy/<server_ip>/show')
@get_user_params()
def show_map(server_ip):
    return service_haproxy.show_map(server_ip, g.user_params['group_id'])
