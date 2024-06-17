from flask import request, render_template, jsonify
from flask_login import login_required

from app.routes.channel import bp
from app.middleware import get_user_params
import app.modules.common.common as common
import app.modules.tools.alerting as alerting
import app.modules.roxywi.common as roxywi_common


@bp.before_request
@login_required
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def channels():
    roxywi_common.check_user_group_for_flask()

    return render_template('channel.html')


@bp.route('/load')
@get_user_params()
def load_channels():
    try:
        return alerting.load_channels()
    except Exception as e:
        return f'{e}'


@bp.route('/check/<int:channel_id>/<receiver_name>')
def check_receiver(channel_id, receiver_name):
    receiver_name = common.checkAjaxInput(receiver_name)

    try:
        alerting.check_receiver(channel_id, receiver_name)
        return jsonify({'status': 'success'})
    except Exception as e:
        roxywi_common.handle_json_exceptions(e, 'Roxy-WI', f'Cannot send message via {receiver_name}')


@bp.route('/check/rabbit')
def check_rabbit():
    try:
        alerting.check_rabbit_alert()
        return jsonify({'status': 'success'})
    except Exception as e:
        roxywi_common.handle_json_exceptions(e, 'Roxy-WI', 'Cannot send message via Web panel')


@bp.route('/check/email')
def check_email():
    return alerting.check_email_alert()


@bp.route('/receiver/<receiver_name>', methods=['PUT', 'POST', 'DELETE'])
@get_user_params()
def receiver(receiver_name):
    json_data = request.get_json()
    if request.method == 'POST':
        token = common.checkAjaxInput(json_data['receiver'])
        channel = common.checkAjaxInput(json_data['channel'])
        group = int(json_data['group'])

        try:
            data = alerting.add_receiver_channel(receiver_name, token, channel, group)
            return jsonify({'status': 'updated', 'data': data})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI', f'Cannot create {receiver_name} channel')
    elif request.method == 'PUT':
        token = common.checkAjaxInput(json_data['receiver_token'])
        channel = common.checkAjaxInput(json_data['channel'])
        group = int(json_data['group'])
        user_id = int(json_data['id'])

        try:
            alerting.update_receiver_channel(receiver_name, token, channel, group, user_id)
            return jsonify({'status': 'updated'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI', f'Cannot update {receiver_name} channel')
    elif request.method == 'DELETE':
        channel_id = int(json_data['channel_id'])
        try:
            alerting.delete_receiver_channel(channel_id, receiver_name)
            return jsonify({'status': 'deleted'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Roxy-WI', f'Cannot delete {receiver_name} channel')
