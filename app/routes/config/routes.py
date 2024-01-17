import os

from flask import render_template, request, g
from flask_login import login_required

from app.routes.config import bp
import app.modules.db.sql as sql
from middleware import check_services, get_user_params
import app.modules.common.common as common
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod
import app.modules.config.section as section_mod
import app.modules.service.haproxy as service_haproxy
import app.modules.server.server as server_mod

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>/show', methods=['POST'])
@check_services
def show_config(service):
    config_file_name = request.form.get('config_file_name')
    configver = request.form.get('configver')
    server_ip = request.form.get('serv')

    return config_mod.show_config(server_ip, service, config_file_name, configver)


@bp.route('/<service>/show-files', methods=['POST'])
@check_services
def show_config_files(service):
    server_ip = request.form.get('serv')
    config_file_name = request.form.get('config_file_name')

    return config_mod.show_config_files(server_ip, service, config_file_name)


@bp.route('/<service>/find-in-config', methods=['POST'])
@check_services
def find_in_config(service):
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    finding_words = request.form.get('words')
    log_path = sql.get_setting(service + '_dir')
    log_path = common.return_nice_path(log_path)
    commands = [f'sudo grep "{finding_words}" {log_path}*/*.conf -C 2 -Rn']
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

    if serv and config_file_name:
        cfg = config_mod.return_cfg(service, serv, config_file_name)

    if serv and edit and new_config is None:
        roxywi_common.check_is_server_in_group(serv)
        is_serv_protected = sql.is_serv_protected(serv)
        server_id = sql.select_server_id_by_ip(serv)
        is_restart = sql.select_service_setting(server_id, service, 'restart')

        try:
            error = config_mod.get_config(serv, cfg, service=service, config_file_name=config_file_name)
        except Exception as e:
            return f'error: Cannot download config: {e}'

        try:
            roxywi_common.logging(serv, f" {service.title()} config has been opened")
        except Exception:
            pass

        try:
            conf = open(cfg, "r")
            config_read = conf.read()
            conf.close()
        except IOError as e:
            return f'Cannot read imported config file {e}', 200

        os.system("/bin/mv %s %s.old" % (cfg, cfg))

    if new_config is not None:
        config_read = ' '

    kwargs = {
        'user_params': g.user_params,
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
        'service_desc': sql.select_service(service),
        'lang': g.user_params['lang']
    }

    return render_template('config.html', **kwargs)


@bp.route('/<service>/<server_ip>/save', methods=['POST'])
@check_services
def save_config(service, server_ip):
    roxywi_common.check_is_server_in_group(server_ip)
    config_file = request.form.get('config')
    oldcfg = request.form.get('oldconfig')
    save = request.form.get('save')
    config_file_name = request.form.get('config_file_name')

    try:
        cfg = config_mod.return_cfg(service, server_ip, config_file_name)
    except Exception as e:
        return f'error: Cannot get config {e}'

    try:
        with open(cfg, "a") as conf:
            conf.write(config_file)
    except IOError as e:
        return f"error: Cannot read imported config file: {e}", 200

    try:
        if service == 'keepalived':
            stderr = config_mod.upload_and_restart(server_ip, cfg, save, service, oldcfg=oldcfg)
        else:
            stderr = config_mod.master_slave_upload_and_restart(server_ip, cfg, save, service, oldcfg=oldcfg,
                                                                config_file_name=config_file_name)
    except Exception as e:
        return f'error: {e}', 200

    if save != 'test':
        config_mod.diff_config(oldcfg, cfg)

    if stderr:
        return stderr, 200

    return


@bp.route('/versions/<service>', defaults={'server_ip': None}, methods=['GET', 'POST'])
@bp.route('/versions/<service>/<server_ip>', methods=['GET', 'POST'])
@check_services
@get_user_params(disable=1)
def versions(service, server_ip):
    roxywi_auth.page_for_admin(level=3)
    aftersave = ''
    file = set()
    stderr = ''

    if service in ('haproxy', 'keepalived'):
        conf_format = 'cfg'
    else:
        conf_format = 'conf'

    if request.form.get('del'):
        aftersave = 1
        for get in request.form.getlist('do_delete'):
            if conf_format in get and server_ip in get:
                try:
                    if sql.delete_config_version(service, get):
                        try:
                            os.remove(get)
                        except OSError as e:
                            if 'No such file or directory' in str(e):
                                pass
                    else:
                        configs_dir = get_config.get_config_var('configs', f'{service}_save_configs_dir')
                        os.remove(os.path.join(configs_dir, get))
                    try:
                        file.add(get + "\n")
                        roxywi_common.logging(
                            server_ip, f"Version of config has been deleted: {get}", login=1, keep_history=1,
                            service=service
                        )
                    except Exception:
                        pass
                except OSError as e:
                    stderr = "Error: %s - %s." % (e.filename, e.strerror)

    kwargs = {
        'user_params': g.user_params,
        'serv': server_ip,
        'aftersave': aftersave,
        'file': file,
        'service': service,
        'stderr': stderr,
        'lang': g.user_params['lang']
    }
    return render_template('delver.html', **kwargs)


@bp.route('/version/<service>/list', methods=['POST'])
@check_services
def list_of_version(service):
    server_ip = common.is_ip_or_dns(request.form.get('serv'))
    configver = common.checkAjaxInput(request.form.get('configver'))
    for_delver = common.checkAjaxInput(request.form.get('for_delver'))

    return config_mod.list_of_versions(server_ip, service, configver, for_delver)


@bp.route('/versions/<service>/<server_ip>/<configver>', defaults={'save': None}, methods=['GET', 'POST'])
@bp.route('/versions/<service>/<server_ip>/<configver>/save', defaults={'save': 1}, methods=['GET', 'POST'])
@check_services
@get_user_params(disable=1)
def show_version(service, server_ip, configver, save):
    roxywi_auth.page_for_admin(level=3)
    service_desc = sql.select_service(service)
    configs_dir = get_config.get_config_var('configs', f'{service_desc.service}_save_configs_dir')
    configver = configs_dir + configver
    aftersave = 0
    stderr = ''

    if save:
        aftersave = 1
        save_action = request.form.get('save')
        try:
            roxywi_common.logging(
                server_ip, f"Version of config has been uploaded {configver}", login=1, keep_history=1, service=service
            )
        except Exception:
            pass

        if service == 'keepalived':
            stderr = config_mod.upload_and_restart(server_ip, configver, save_action, service)
        elif service in ('nginx', 'apache'):
            config_file_name = sql.select_remote_path_from_version(server_ip=server_ip, service=service,
                                                                   local_path=configver)
            stderr = config_mod.master_slave_upload_and_restart(server_ip, configver, save_action, service_desc.slug,
                                                                config_file_name=config_file_name)
        else:
            stderr = config_mod.master_slave_upload_and_restart(server_ip, configver, save_action, service)

    kwargs = {
        'user_params': g.user_params,
        'serv': server_ip,
        'aftersave': aftersave,
        'configver': configver,
        'service': service,
        'stderr': stderr,
        'lang': g.user_params['lang']
    }

    return render_template('configver.html', **kwargs)


@bp.route('/section/haproxy/<server_ip>')
@get_user_params()
def haproxy_section(server_ip):
    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    cfg = f"{hap_configs_dir}{server_ip}-{get_date.return_date('config')}.cfg"
    error = config_mod.get_config(server_ip, cfg)
    kwargs = {
        'user_params': g.user_params,
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
    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    cfg = f"{hap_configs_dir}{server_ip}-{get_date.return_date('config')}.cfg"
    error = config_mod.get_config(server_ip, cfg)
    start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section)
    server_id = sql.select_server_id_by_ip(server_ip)
    sections = section_mod.get_sections(cfg)

    os.system(f"/bin/mv {cfg} {cfg}.old")

    try:
        roxywi_common.logging(server_ip, f"A section {section} has been opened")
    except Exception:
        pass

    kwargs = {
        'user_params': g.user_params,
        'is_restart': sql.select_service_setting(server_id, 'haproxy', 'restart'),
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
def haproxy_section_save(server_ip):
    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    cfg = f"{hap_configs_dir}{server_ip}-{get_date.return_date('config')}.cfg"
    config_file = request.form.get('config')
    oldcfg = request.form.get('oldconfig')
    save = request.form.get('save')
    start_line = request.form.get('start_line')
    end_line = request.form.get('end_line')

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

    config_mod.diff_config(oldcfg, cfg)

    os.system(f"/bin/rm -f {hap_configs_dir}*.old")

    return stderr


@bp.route('/compare/<service>/<serv>')
@bp.route('/map/<service>/<serv>')
@get_user_params()
def show_compare_config(service, serv):
    kwargs = {
        'user_params': g.user_params,
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
        'service_desc': sql.select_service(service),
        'lang': g.user_params['lang']
    }

    return render_template('config.html', **kwargs)


@bp.route('/compare/<service>/<server_ip>/files')
@check_services
def show_configs_for_compare(service, server_ip):
    return config_mod.show_compare_config(server_ip, service)


@bp.post('/compare/<service>/<server_ip>/show')
@check_services
def show_compare(service, server_ip):
    left = common.checkAjaxInput(request.form.get('left'))
    right = common.checkAjaxInput(request.form.get('right'))

    return config_mod.compare_config(service, left, right)


@bp.route('/map/haproxy/<server_ip>/show')
def show_map(server_ip):
    return service_haproxy.show_map(server_ip)
