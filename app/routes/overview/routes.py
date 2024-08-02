from flask import render_template, g
from flask_jwt_extended import jwt_required

from app.routes.overview import bp
from app.middleware import get_user_params
import app.modules.db.sql as sql
import app.modules.db.group as group_sql
import app.modules.roxywi.logs as roxy_logs
import app.modules.roxywi.overview as roxy_overview


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/')
@bp.route('/overview')
@get_user_params()
def index():
    kwargs = {
        'autorefresh': 1,
        'roles': sql.select_roles(),
        'groups': group_sql.select_groups(),
        'guide_me': 1,
        'lang': g.user_params['lang']
    }
    return render_template('ovw.html', **kwargs)


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
    return render_template('ajax/ovw_log.html', role=g.user_params['role'], lang=g.user_params['lang'], roxy_wi_log=roxy_logs.roxy_wi_log())
