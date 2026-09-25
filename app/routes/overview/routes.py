from typing import Union

from flask import render_template, g, request, jsonify, abort
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from pydantic import IPvAnyAddress

from app.routes.overview import bp
from app.middleware import get_user_params
import app.modules.db.sql as sql
import app.modules.db.group as group_sql
from app.modules.roxywi import auth, common, log_query, logger
import app.modules.roxywi.overview as roxy_overview
from app.modules.roxywi.class_models import DomainName


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
        'roles': sql.select_roles(),
        'groups': group_sql.select_groups(),
        'lang': g.user_params['lang']
    }
    return render_template('ovw.html', **kwargs)


@bp.route('/overview/services')
def show_services_overview():
    return roxy_overview.show_services_overview()


@bp.route('/overview/server/<server_ip>')
@validate()
def overview_server(server_ip: Union[IPvAnyAddress, DomainName]):
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
    auth.page_for_admin(level=2)
    if not common.check_user_group_for_flask():
        abort(403)
    params = g.user_params
    group = None if auth.is_admin() and int(params['group_id']) == 1 else params['group_id']
    try:
        # The Overview is a small snapshot; the full viewer handles time ranges and Live.
        query = log_query.LogQuery({'relative': 7 * 86400, 'limit': 10, 'search': request.args.get('search', '')})
        available = dict(log_query.sources())
        source = 'runtime' if 'runtime' in available else 'roxy-wi.log'
        result = log_query.read_logs(source, query, group_id=group) if source in available else {'entries': []}
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except OSError:
        logger.exception('Cannot read Overview logs')
        return jsonify(error='Cannot read the log journal; check storage permissions'), 503
    # Latest first, with the same bounded reader and group isolation as Internal logs.
    result['entries'].reverse()
    result.pop('cursor', None)
    result['source'] = source
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response
