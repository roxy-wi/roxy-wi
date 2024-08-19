from flask import request, render_template, g, jsonify
from flask_jwt_extended import jwt_required

from app.routes.channel import bp
from app.middleware import get_user_params
import app.modules.tools.alerting as alerting
import app.modules.roxywi.common as roxywi_common
from app.views.channel.views import ChannelView

def register_api_channel(view, endpoint, url_beg, pk='receiver', pk_type='int', pk_end='channel_id', pk_type_end='int'):
    view_func = view.as_view(endpoint, False)
    bp.add_url_rule(f'/{url_beg}/<any(telegram, slack, pd, mm):{pk}>', view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'/{url_beg}/<any(telegram, slack, pd, mm):{pk}>/<{pk_type_end}:{pk_end}>', view_func=view_func, methods=['PUT', 'DELETE', 'GET', 'PATCH'])


register_api_channel(ChannelView, 'channel', '')


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('')
@get_user_params()
def channels():
    roxywi_common.check_user_group_for_flask()
    lang = g.user_params['lang']

    return render_template('channel.html', lang=lang)


@bp.route('/load')
@get_user_params()
def load_channels():
    try:
        return alerting.load_channels()
    except Exception as e:
        return f'{e}'


@bp.post('/check')
@get_user_params()
def check_sender():
    json_data = request.get_json()
    sender = json_data.get('sender')
    send_function = {
        'email': alerting.check_email_alert,
        'web': alerting.check_rabbit_alert
    }
    try:
        send_function[sender]()
        return jsonify({'status': 'success'})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, f'Cannot send message via {sender.title()}')
