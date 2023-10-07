import os
from functools import wraps

from flask import render_template, request, redirect, url_for, abort
from flask_login import login_required

from app.routes.config import bp
import app.modules.db.sql as sql
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


def check_services(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        service = kwargs['service']
        if service not in ('haproxy', 'nginx', 'apache', 'keepalived'):
            abort(400, 'bad service')
        return fn(*args, **kwargs)
    return decorated_view


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
def config(service, serv, edit, config_file_name, new):
    config_read = ""
    cfg = ""
    stderr = ""
    error = ""
    aftersave = ""
    is_restart = ''
    is_serv_protected = ''
    new_config = new

    try:
        user_params = roxywi_common.get_users_params(service=service)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
        service_desc = sql.select_service(service)
        is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

        if is_redirect != 'ok':
            return redirect(url_for(f'{is_redirect}'))
    else:
        return redirect(url_for('index'))

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
            return str(e), 200

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

    return render_template(
        'config.html', role=user_params['role'], user=user, select_id="serv", serv=serv, aftersave=aftersave,
        config=config_read, cfg=cfg, selects=user_params['servers'], stderr=stderr, error=error, service=service,
        is_restart=is_restart, user_services=user_params['user_services'], config_file_name=config_file_name,
        is_serv_protected=is_serv_protected, token=user_params['token'], lang=user_params['lang'], service_desc=service_desc
    )


@bp.route('/<service>/<server_ip>/save', methods=['POST'])
@check_services
def save_config(service, server_ip):
    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    roxywi_common.check_is_server_in_group(server_ip)
    service_desc = sql.select_service(service)
    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    config_file = request.form.get('config')
    oldcfg = request.form.get('oldconfig')
    save = request.form.get('save')
    config_file_name = request.form.get('config_file_name')

    try:
        cfg = config_mod.return_cfg(service, server_ip, config_file_name)
    except Exception as e:
        return f'error: {e}', 200

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
def versions(service, server_ip):
    roxywi_auth.page_for_admin(level=3)
    aftersave = ''
    file = set()
    stderr = ''

    try:
        user_params = roxywi_common.get_users_params(disable=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service not in ('haproxy', 'nginx', 'keepalived', 'apache'):
        return redirect(url_for('index'))

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

    return render_template(
        'delver.html', role=user_params['role'], user=user, select_id="serv", serv=server_ip, aftersave=aftersave,
        selects=user_params['servers'], file=file, service=service, user_services=user_params['user_services'],
        token=user_params['token'], lang=user_params['lang'], stderr=stderr
    )


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
def show_version(service, server_ip, configver, save):
    roxywi_auth.page_for_admin(level=3)

    try:
        user_params = roxywi_common.get_users_params(disable=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service not in ('haproxy', 'nginx', 'keepalived', 'apache'):
        return redirect(url_for('index'))

    service_desc = sql.select_service(service)

    if not roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
        return redirect(url_for('index'))

    configs_dir = get_config.get_config_var('configs', f'{service_desc.service}_save_configs_dir')
    configver = configs_dir + configver
    servers = roxywi_common.get_dick_permit(service=service_desc.slug)
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

    return render_template(
        'configver.html', role=user_params['role'], user=user, select_id="serv", serv=server_ip, aftersave=aftersave,
        selects=servers, stderr=stderr, save=save, configver=configver, service=service,
        user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang']
    )


@bp.route('/section/haproxy/<server_ip>')
def haproxy_section(server_ip):
    try:
        user_params = roxywi_common.get_users_params(service=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    is_restart = 0
    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    cfg = f"{hap_configs_dir}{server_ip}-{get_date.return_date('config')}.cfg"
    error = config_mod.get_config(server_ip, cfg)
    sections = section_mod.get_sections(cfg)

    return render_template(
        'sections.html', role=user_params['role'], user=user, serv=server_ip, selects=user_params['servers'],
        sections=sections, error=error, token=user_params['token'], lang=user_params['lang'], is_restart=is_restart, config='',
        user_services=user_params['user_services']
    )


@bp.route('/section/haproxy/<server_ip>/<section>')
def haproxy_section_show(server_ip, section):
    try:
        user_params = roxywi_common.get_users_params(service=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

    try:
        roxywi_common.logging(server_ip, f"A section {section} has been opened")
    except Exception:
        pass

    hap_configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
    cfg = f"{hap_configs_dir}{server_ip}-{get_date.return_date('config')}.cfg"
    error = config_mod.get_config(server_ip, cfg)
    sections = section_mod.get_sections(cfg)
    start_line, end_line, config_read = section_mod.get_section_from_config(cfg, section)
    server_id = sql.select_server_id_by_ip(server_ip)
    is_restart = sql.select_service_setting(server_id, 'haproxy', 'restart')

    os.system(f"/bin/mv {cfg} {cfg}.old")

    return render_template(
        'sections.html', role=user_params['role'], user=user, serv=server_ip, selects=user_params['servers'],
        error=error, sections=sections, cfg=cfg, token=user_params['token'], lang=user_params['lang'],
        is_restart=is_restart, config=config_read, start_line=start_line, end_line=end_line, section=section,
        user_services=user_params['user_services']
    )


@bp.route('/section/haproxy/<server_ip>/save', methods=['POST'])
def haproxy_section_save(server_ip):
    try:
        user_params = roxywi_common.get_users_params(service=1)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

    if is_redirect != 'ok':
        return redirect(url_for(f'{is_redirect}'))

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
def show_compare_config(service, serv):
    config_read = ""
    cfg = ""
    stderr = ""
    error = ""
    aftersave = ""
    is_restart = ''
    is_serv_protected = ''
    config_file_name = ''

    try:
        user_params = roxywi_common.get_users_params(service=service)
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
        service_desc = sql.select_service(service)
        is_redirect = roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id)

        if is_redirect != 'ok':
            return redirect(url_for(f'{is_redirect}'))
    else:
        return redirect(url_for('index'))

    return render_template(
        'config.html', role=user_params['role'], user=user, select_id="serv", serv=serv, aftersave=aftersave,
        config=config_read, cfg=cfg, selects=user_params['servers'], stderr=stderr, error=error, service=service,
        is_restart=is_restart, user_services=user_params['user_services'], config_file_name=config_file_name,
        is_serv_protected=is_serv_protected, token=user_params['token'], lang=user_params['lang'],
        service_desc=service_desc
    )


@bp.route('/compare/<service>/<server_ip>/files')
@check_services
def show_configs_for_compare(service, server_ip):
    return config_mod.show_compare_config(server_ip, service)


@bp.route('/compare/<service>/<server_ip>/show', methods=['POST'])
@check_services
def show_compare(service, server_ip):
    left = common.checkAjaxInput(request.form.get('left'))
    right = common.checkAjaxInput(request.form.get('right'))

    return config_mod.compare_config(service, left, right)


@bp.route('/map/haproxy/<server_ip>/show')
def show_map(server_ip):
    return service_haproxy.show_map(server_ip)
