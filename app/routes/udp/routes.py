from flask import render_template, request, g, jsonify
from flask_login import login_required

from app.routes.udp import bp
import app.modules.db.udp as udp_sql
import app.modules.db.server as server_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
import app.modules.service.udp as udp_mod
import app.modules.service.installation as service_mod
from app.middleware import get_user_params, check_services


@bp.before_request
@login_required
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/<service>/listener', methods=['GET', 'POST', 'PUT', 'DELETE'])
@check_services
@get_user_params()
def listener_funct(service):
    if request.method != 'GET':
        roxywi_auth.page_for_admin(level=2)
    if request.method == 'GET':
        kwargs = {
            'listeners': udp_sql.select_listeners(g.user_params['group_id']),
            'lang': g.user_params['lang'],
            'clusters': ha_sql.select_clusters(g.user_params['group_id']),
            'is_needed_tool': common.is_tool('ansible'),
            'user_subscription': roxywi_common.return_user_subscription()
        }
        return render_template('udp/listeners.html', **kwargs)
    elif request.method == 'POST':
        json_data = request.get_json()
        json_data['group_id'] = g.user_params['group_id']
        listener_name = json_data['new-listener-name']
        try:
            listener_id = udp_mod.create_listener(json_data)
            roxywi_common.logging(listener_id, f'UDP listener {listener_name} has been created', roxywi=1, keep_history=1, login=1, service='UDP listener')
            return jsonify({'status': 'created', 'listener_id': listener_id})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e,'Cannot create UDP listener')
    elif request.method == 'PUT':
        json_data = request.get_json()
        json_data['group_id'] = g.user_params['group_id']
        listener_name = json_data['new-listener-name']
        listener_id = json_data['listener_id']
        try:
            udp_mod.update_listener(json_data)
            roxywi_common.logging(listener_id, f'UDP listener {listener_name} has been updated', roxywi=1, keep_history=1, login=1, service='UDP listener')
            return jsonify({'status': 'updated'}), 201
        except Exception as e:
            return jsonify({'status': 'failed', 'error': str(e)})
    elif request.method == 'DELETE':
        kwargs = request.get_json()
        listener_id = int(kwargs['listener_id'])
        try:
            inv, server_ips = service_mod.generate_udp_inv(listener_id, 'uninstall')
            service_mod.run_ansible(inv, server_ips, 'udp'), 201
            roxywi_common.logging(listener_id, f'UDP listener has been deleted {listener_id}', roxywi=1, keep_history=1, login=1, service='UDP listener')
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e,f'Cannot create inventory for UDP listener deleting {listener_id}')
        try:
            udp_sql.delete_listener(listener_id)
            return jsonify({'status': 'deleted'}), 201
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e,f'Cannot delete UDP listener {listener_id}')


@bp.get('/<service>/listener/<int:listener_id>')
@check_services
@get_user_params()
def get_listener(service, listener_id):
    listener = udp_sql.get_listener(listener_id)
    cluster = dict()
    server = dict()
    if listener.cluster_id:
        cluster = ha_sql.select_cluster(listener.cluster_id)
    elif listener.server_id:
        server = server_sql.get_server_by_id(listener.server_id)
    kwargs = {
        'clusters': cluster,
        'listener': listener,
        'server': server,
        'lang': g.user_params['lang'],
    }
    return render_template('udp/listener.html', **kwargs)


@bp.get('/<service>/listener/<int:listener_id>/settings')
@check_services
@get_user_params()
def get_listener_settings(service, listener_id):
    listener_config = udp_mod.get_listener_config(listener_id)
    return jsonify(listener_config)


@bp.get('/<service>/listener/<int:listener_id>/<action>')
@check_services
@get_user_params()
def action_with_listener(service, listener_id, action):
    try:
        udp_mod.listener_actions(listener_id, action, g.user_params['group_id'])
        roxywi_common.logging(listener_id, f'UDP listener {listener_id} has been {action}ed', roxywi=1, keep_history=1, login=1, service='UDP listener')
        return jsonify({'status': 'done'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e,f'Cannot {action} listener')


@bp.get('/<service>/listener/<int:listener_id>/check')
@check_services
def check_listener(service, listener_id):
    try:
        status = udp_mod.check_is_listener_active(listener_id)
        return jsonify({'status': status})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e,f'Cannot get status')
