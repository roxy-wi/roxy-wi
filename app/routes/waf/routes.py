from flask import render_template, request
from flask_login import login_required

from app.routes.waf import bp
import app.modules.db.sql as sql
import app.modules.common.common as common
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.roxywi.waf as roxy_waf
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.config.config as config_mod

get_config = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/<service>')
def waf(service):
    roxywi_auth.page_for_admin(level=2)

    manage_rules = ''
    waf_rule_id = ''
    config_file_name = ''
    waf_rule_file = ''
    config_read = ''
    rules = ''
    serv = ''
    cfg = ''
    user_params = roxywi_common.get_users_params()

    if service == 'nginx':
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2)
        servers = roxywi_common.get_dick_permit(nginx=1)
    else:
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)
        servers = user_params['servers']

    title = "Web application firewall"
    servers_waf = sql.select_waf_servers_metrics(user_params['user_uuid'])
    autorefresh = 1

    return render_template(
        'waf.html',
        h2=1, title=title, autorefresh=autorefresh, role=user_params['role'], user=user_params['user'], serv=serv,
        servers=servers_waf,
        servers_all=servers, manage_rules=manage_rules, rules=rules, user_services=user_params['user_services'],
        waf_rule_file=waf_rule_file, waf_rule_id=waf_rule_id, config=config_read, cfg=cfg, token=user_params['token'],
        config_file_name=config_file_name, service=service, lang=user_params['lang']
    )


@bp.route('/<service>/<server_ip>/rules')
def waf_rules(service, server_ip):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)

    manage_rules = '1'
    waf_rule_id = ''
    config_file_name = ''
    waf_rule_file = ''
    servers_waf = ''
    config_read = ''
    servers = ''
    cfg = ''
    user_params = roxywi_common.get_users_params()
    title = "Manage rules - Web application firewall"
    rules = sql.select_waf_rules(server_ip, service)

    if service == 'nginx':
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2)
    else:
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)

    return render_template(
        'waf.html',
        h2=1, title=title, autorefresh=0, role=user_params['role'], user=user_params['user'], serv=server_ip,
        servers=servers_waf,
        servers_all=servers, manage_rules=manage_rules, rules=rules, user_services=user_params['user_services'],
        waf_rule_file=waf_rule_file, waf_rule_id=waf_rule_id, config=config_read, cfg=cfg, token=user_params['token'],
        config_file_name=config_file_name, service=service, lang=user_params['lang']
    )


@bp.route('/<service>/<server_ip>/rule/<rule_id>')
def waf_rule_edit(service, server_ip, rule_id):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)

    manage_rules = ''
    servers_waf = ''
    config_read = ''
    servers = ''
    user_params = roxywi_common.get_users_params()
    rules = sql.select_waf_rules(server_ip, service)

    if service == 'nginx':
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2)
        config_path = sql.get_setting('nginx_dir')
    else:
        roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)
        config_path = sql.get_setting('haproxy_dir')

    title = 'Edit a WAF rule'
    waf_rule_file = sql.select_waf_rule_by_id(rule_id)
    configs_dir = sql.get_setting('tmp_config_path')
    cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}-{waf_rule_file}"
    error = config_mod.get_config(server_ip, cfg, waf=service, waf_rule_file=waf_rule_file)
    config_file_name = common.return_nice_path(config_path) + 'waf/rules/' + waf_rule_file

    try:
        conf = open(cfg, "r")
        config_read = conf.read()
        conf.close()
    except IOError:
        print('Cannot read imported config file')

    return render_template(
        'waf.html',
        h2=1, title=title, autorefresh=0, role=user_params['role'], user=user_params['user'], serv=server_ip,
        servers=servers_waf,
        servers_all=servers, manage_rules=manage_rules, rules=rules, user_services=user_params['user_services'],
        waf_rule_file=waf_rule_file, waf_rule_id=rule_id, config=config_read, cfg=cfg, token=user_params['token'],
        config_file_name=config_file_name, service=service, lang=user_params['lang']
    )


@bp.route('/<service>/<server_ip>/rule/<rule_id>/save', methods=['POST'])
def waf_save_config(service, server_ip, rule_id):
    roxywi_auth.page_for_admin(level=2)
    roxywi_common.check_is_server_in_group(server_ip)

    configs_dir = sql.get_setting('tmp_config_path')
    cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}"
    config_file_name = request.form.get('config_file_name')
    config = request.form.get('config')
    oldcfg = request.form.get('oldconfig')
    save = request.form.get('save')

    try:
        with open(cfg, "a") as conf:
            conf.write(config)
    except IOError:
        print("error: Cannot read imported config file")

    stderr = config_mod.master_slave_upload_and_restart(server_ip, cfg, save, 'waf', oldcfg=oldcfg, config_file_name=config_file_name)

    config_mod.diff_config(oldcfg, cfg)

    try:
        os.system(f"/bin/rm -f {configs_dir}*.old")
    except Exception as e:
        return f'error: {e}'

    if stderr:
        return stderr

    return


@bp.route('/<server_ip>/rule/<int:rule_id>/<int:enable>')
def enable_rule(server_ip, rule_id, enable):
    server_ip = common.is_ip_or_dns(server_ip)

    return roxy_waf.switch_waf_rule(server_ip, enable, rule_id)


@bp.route('/<service>/<server_ip>/rule/create', methods=['POST'])
def create_rule(service, server_ip):
    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    server_ip = common.is_ip_or_dns(server_ip)

    return roxy_waf.create_waf_rule(server_ip, service)


@bp.route('/<service>/mode/<server_name>/<waf_mode>')
def change_waf_mode(service, server_name, waf_mode):
    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    server_name = common.checkAjaxInput(server_name)
    waf_mode = common.checkAjaxInput(waf_mode)

    return roxy_waf.change_waf_mode(waf_mode, server_name, service)


@bp.route('/overview/<service>/<server_ip>')
def overview_waf(service, server_ip):
    server_ip = common.is_ip_or_dns(server_ip)

    if service not in ('haproxy', 'nginx'):
        return 'error: Wrong service'

    return roxy_waf.waf_overview(server_ip, service)


@bp.route('/metric/enable/<int:enable>/<server_name>')
def enable_metric(enable, server_name):
    server_name = common.checkAjaxInput(server_name)
    return sql.update_waf_metrics_enable(server_name, enable)
