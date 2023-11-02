from flask import render_template, g
from flask_login import login_required

from app.routes.overview import bp
from middleware import get_user_params
import app.modules.db.sql as sql
import app.modules.roxywi.logs as roxy_logs
import app.modules.roxywi.overview as roxy_overview


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.route('/')
@bp.route('/overview')
@get_user_params()
def index():
    user_params = g.user_params
    groups = sql.select_groups()
    return render_template(
        'ovw.html', autorefresh=1, role=user_params['role'], user=user_params['user'], roles=sql.select_roles(),
        servers=user_params['servers'], user_services=user_params['user_services'], groups=groups,
        token=user_params['token'], guide_me=1, lang=user_params['lang']
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
def overview_sub():
    return roxy_overview.show_sub_ovw()


@bp.route('/overview/logs')
@get_user_params()
def overview_logs():
    user_params = g.user_params
    return render_template('ajax/ovw_log.html', role=user_params['role'], lang=user_params['lang'], roxy_wi_log=roxy_logs.roxy_wi_log())
