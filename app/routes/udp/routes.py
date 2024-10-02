from flask_jwt_extended import jwt_required

from app.routes.udp import bp
from app.views.udp.views import UDPListener


@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


bp.add_url_rule('/<service>/listener', view_func=UDPListener.as_view('udp_listener', False), methods=['GET'], defaults={'listener_id': None})
bp.add_url_rule('/<service>/listener/<int:listener_id>', view_func=UDPListener.as_view('udp_listener_id', False), methods=['GET'])
