from flask import render_template, redirect, url_for
from flask_login import login_required

from app import cache
from app.routes.overview import bp
import app.modules.db.sql as sql
import app.modules.roxywi.logs as roxy_logs
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.overview as roxy_overview


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/')
@bp.route('/overview')
def index():
    try:
        user_params = roxywi_common.get_users_params()
        user = user_params['user']
    except Exception:
        return redirect(url_for('login_page'))

    groups = sql.select_groups()
    return render_template(
        'ovw.html', h2=1, autorefresh=1, role=user_params['role'], user=user, groups=groups,
        roles=sql.select_roles(), servers=user_params['servers'], user_services=user_params['user_services'],
        roxy_wi_log=roxy_logs.roxy_wi_log(), token=user_params['token'], guide_me=1, lang=user_params['lang']
    )


@bp.route('/overview/services')
def show_services_overview():
    return roxy_overview.show_services_overview()


@bp.route('/overview/server/<server_ip>')
def overview_server(server_ip):
    return roxy_overview.show_overview(server_ip)


@bp.route('/overview/users')
def overview_users():
    return roxy_overview.user_owv()


@bp.route('/overview/sub')
@cache.cached()
def overview_sub():
    return roxy_overview.show_sub_ovw()
