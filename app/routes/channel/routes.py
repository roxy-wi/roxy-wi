from flask import request, render_template
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


@bp.route('/check/<channel_id>/<receiver_name>')
def check_receiver(channel_id, receiver_name):
    channel_id = common.checkAjaxInput(channel_id)
    receiver_name = common.checkAjaxInput(receiver_name)

    return alerting.check_receiver(channel_id, receiver_name)


@bp.route('/check/rabbit')
def check_rabbit():
    return alerting.check_rabbit_alert()


@bp.route('/check/email')
def check_email():
    return alerting.check_email_alert()


@bp.route('/receiver/<receiver_name>', methods=['PUT', 'POST', 'DELETE'])
def receiver(receiver_name):
    if request.method == 'POST':
        token = common.checkAjaxInput(request.form.get('receiver'))
        channel = common.checkAjaxInput(request.form.get('channel'))
        group = common.checkAjaxInput(request.form.get('group'))
        page = common.checkAjaxInput(request.form.get('page'))
        page = page.split("#")[0]

        return alerting.add_receiver_channel(receiver_name, token, channel, group, page)
    elif request.method == 'PUT':
        token = common.checkAjaxInput(request.form.get('receiver_token'))
        channel = common.checkAjaxInput(request.form.get('channel'))
        group = common.checkAjaxInput(request.form.get('group'))
        user_id = common.checkAjaxInput(request.form.get('id'))

        return alerting.update_receiver_channel(receiver_name, token, channel, group, user_id)
    elif request.method == 'DELETE':
        channel_id = common.checkAjaxInput(request.form.get('channel_id'))

        return alerting.delete_receiver_channel(channel_id, receiver_name)
