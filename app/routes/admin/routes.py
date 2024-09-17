import pytz
from flask import render_template, g
from flask_jwt_extended import jwt_required

from app import scheduler
from app.routes.admin import bp
import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
from app.middleware import get_user_params
import app.modules.roxywi.roxy as roxy
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.tools.common as tools_common
import app.modules.server.ssh as ssh_mod
from app.views.admin.views import SettingsView

bp.add_url_rule(
    '/settings/<any(smon, main, haproxy, nginx, apache, keepalived, rabbitmq, ldap, monitoring, mail, logs):section>',
    view_func=SettingsView.as_view('settings'),
    methods=['GET', 'POST']
)


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def admin():
    roxywi_auth.page_for_admin(level=2)
    user_group = roxywi_common.get_user_group(id=1)
    if g.user_params['role'] == 1:
        users = user_sql.select_users()
        servers = server_sql.select_servers(full=1)
        masters = server_sql.select_servers(get_master_servers=1)
        sshs = ssh_mod.get_creds()
    else:
        users = user_sql.select_users(group=user_group)
        servers = roxywi_common.get_dick_permit(virt=1, disable=0, only_group=1)
        masters = server_sql.select_servers(get_master_servers=1, uuid=g.user_params['user_id'])
        sshs = ssh_mod.get_creds(group_id=user_group)

    kwargs = {
        'lang': g.user_params['lang'],
        'users': users,
        'groups': group_sql.select_groups(),
        'group': roxywi_common.get_user_group(id=1),
        'sshs': sshs,
        'servers': servers,
        'roles': sql.select_roles(),
        'ldap_enable': sql.get_setting('ldap_enable'),
        'services': service_sql.select_services(),
        'masters': masters,
        'guide_me': 1,
        'user_subscription': roxywi_common.return_user_subscription(),
        'users_roles': user_sql.select_users_roles(),
        'user_roles': user_sql.select_user_roles_by_group(user_group),
    }

    return render_template('admin.html', **kwargs)


@bp.route('/tools')
def show_tools():
    roxywi_auth.page_for_admin()
    lang = roxywi_common.get_user_lang_for_flask()
    try:
        services = tools_common.get_services_status(update_cur_ver=1)
    except Exception as e:
        return str(e)

    return render_template('ajax/load_services.html', services=services, lang=lang)


@bp.route('/tools/update/<service>')
def update_tools(service):
    roxywi_auth.page_for_admin()

    try:
        return tools_common.update_roxy_wi(service)
    except Exception as e:
        return f'error: {e}'


@bp.route('/tools/action/<service>/<action>')
def action_tools(service, action):
    roxywi_auth.page_for_admin()
    if action not in ('start', 'stop', 'restart'):
        return 'error: wrong action'

    return roxy.action_service(action, service)


@bp.route('/update')
def update_roxywi():
    roxywi_auth.page_for_admin()
    versions = roxy.versions()
    services = tools_common.get_services_status()
    lang = roxywi_common.get_user_lang_for_flask()

    return render_template(
        'ajax/load_updateroxywi.html', services=services, versions=versions, lang=lang
    )


@bp.route('/update/check')
def check_update():
    roxywi_auth.page_for_admin()
    scheduler.run_job('check_new_version')
    return 'ok'


@bp.get('/settings')
@get_user_params()
def get_settings():
    kwargs = {
        'settings': sql.get_setting('', all=1, group_id=g.user_params['group_id']),
        'timezones': pytz.all_timezones,
    }
    return render_template('include/admin_settings.html', **kwargs)
