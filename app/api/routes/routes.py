from flask_swagger import swagger
from flask import jsonify, render_template, abort
from flask_pydantic import validate

from app import app
from app.api.routes import bp
from app.views.install.views import InstallView, InstallGetStatus
from app.views.server.views import ServerView, ServerGroupView, ServerGroupsView, ServersView, ServerIPView
from app.views.server.cred_views import CredView, CredsView
from app.views.server.backup_vews import BackupView, S3BackupView, GitBackupView
from app.views.service.views import (ServiceView, ServiceActionView, ServiceBackendView, ServiceConfigView,
                                     ServiceConfigVersionsView, ServiceConfigList)
from app.views.service.haproxy_section_views import ListenSectionView, UserListSectionView, PeersSectionView, \
    GlobalSectionView, DefaultsSectionView
from app.views.ha.views import HAView, HAVIPView, HAVIPsView
from app.views.user.views import UserView, UserGroupView, UserRoles
from app.views.udp.views import UDPListener, UDPListeners, UDPListenerActionView
from app.views.channel.views import ChannelView, ChannelsView
from app.views.tools.views import CheckerView
from app.views.tools.port_scanner_views import PortScannerView, PortScannerPortsView
from app.views.admin.views import SettingsView
from app.modules.roxywi.class_models import LoginRequest
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common


@bp.before_request
def before_request():
    """ Protect all the API endpoints. """
    user_subscription = roxywi_common.return_user_subscription()
    if user_subscription['user_status'] == 0 or user_subscription['user_plan'] == 'user':
        abort(401, 'Your subscription is not active or you are on a Home plan.')
    pass


def register_api(view, endpoint, url, pk='listener_id', pk_type='int'):
    view_func = view.as_view(endpoint)
    bp.add_url_rule(url, view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'{url}/<{pk_type}:{pk}>', view_func=view_func, methods=['GET', 'PUT', 'PATCH', 'DELETE'])


def register_api_for_not_api(view, endpoint, url, pk='listener_id', pk_type='int'):
    view_func = view.as_view(endpoint, True)
    bp.add_url_rule(url, view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'{url}/<{pk_type}:{pk}>', view_func=view_func, methods=['GET', 'PUT', 'PATCH', 'DELETE'])


def register_api_id_ip(view, endpoint, url: str = '', methods: list = ['GET', 'POST']):
    for point in ('_id', '_ip'):
        view_func = view.as_view(f'{endpoint}_{point}')
        pk = 'int:' if point == '_id' else ''
        bp.add_url_rule(f'/service/<any(haproxy, nginx, apache, keepalived):service>/<{pk}server_id>{url}', view_func=view_func, methods=methods)


register_api(HAView, 'ha_cluster', '/ha/<service>', 'cluster_id')
register_api(HAVIPView, 'ha_vip', '/ha/<service>/<int:cluster_id>/vip', 'vip_id')
bp.add_url_rule('/ha/<service>/<int:cluster_id>/vips', view_func=HAVIPsView.as_view('ha_vips'), methods=['GET'])
register_api(UDPListener, 'udp_listener', '/<service>/listener', 'listener_id')
bp.add_url_rule('/<service>/listener/<int:listener_id>/<any(start, stop, reload, restart):action>', view_func=UDPListenerActionView.as_view('listener_action'), methods=['GET'])
bp.add_url_rule('/<service>/listeners', view_func=UDPListeners.as_view('listeners'), methods=['GET'])
bp.add_url_rule('/service/<service>/<int:server_id>/install', view_func=InstallGetStatus.as_view('install_status'), methods=['GET'])
bp.add_url_rule('/service/<service>/<server_id>/install', view_func=InstallGetStatus.as_view('install_status_ip'), methods=['GET'])


register_api_id_ip(ServiceView, 'service', '/status', ['GET'])
register_api_id_ip(ServiceBackendView, 'service_backend', '/backend', ['GET'])
register_api_id_ip(ServiceConfigView, 'config_view', '/config')
register_api_id_ip(ServiceConfigVersionsView, 'config_version', '/versions', methods=['GET', 'DELETE'])
register_api_id_ip(ListenSectionView, 'haproxy_section_post', '/section/<any(listen, frontend, backend):section_type>', methods=['POST'])
register_api_id_ip(ListenSectionView, 'haproxy_section', '/section/<any(listen, frontend, backend):section_type>/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(UserListSectionView, 'haproxy_userlist_post', '/section/userlist', methods=['POST'])
register_api_id_ip(UserListSectionView, 'haproxy_userlist', '/section/userlist/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(PeersSectionView, 'haproxy_peers_post', '/section/peers', methods=['POST'])
register_api_id_ip(PeersSectionView, 'haproxy_peers', '/section/peers/<section_name>', methods=['GET', 'PUT', 'DELETE'])
register_api_id_ip(GlobalSectionView, 'haproxy_global', '/section/global', methods=['GET', 'PUT'])
register_api_id_ip(DefaultsSectionView, 'haproxy_defaults', '/section/defaults', methods=['GET', 'PUT'])
bp.add_url_rule('/service/<any(nginx, apache):service>/<server_id>/config/list', view_func=ServiceConfigList.as_view('config_list_ip'), methods=['GET'])
bp.add_url_rule('/service/<any(nginx, apache):service>/<int:server_id>/config/list', view_func=ServiceConfigList.as_view('config_list'), methods=['GET'])
register_api_id_ip(CheckerView, 'checker', '/tools')
register_api_id_ip(InstallView, 'install', '/install', methods=['POST'])
register_api_id_ip(ServiceActionView, 'service_action', '/<any(start, stop, reload, restart):action>', methods=['GET'])

register_api(ServerView, 'server', '/server', 'server_id')
register_api(BackupView, 'backup_fs', '/server/backup/fs', 'backup_id')
register_api(S3BackupView, 'backup_s3', '/server/backup/s3', 'backup_id')
register_api(GitBackupView, 'backup_git', '/server/backup/git', 'backup_id')
bp.add_url_rule('/server/<server_id>/ip', view_func=ServerIPView.as_view('server_ip_ip'), methods=['GET'])
bp.add_url_rule('/server/<int:server_id>/ip', view_func=ServerIPView.as_view('server_ip'), methods=['GET'])
register_api_for_not_api(CredView, 'cred', '/server/cred', 'cred_id')
bp.add_url_rule('/server/creds', view_func=CredsView.as_view('creds'), methods=['GET'])
bp.add_url_rule('/server/portscanner/<server_id>', view_func=PortScannerView.as_view('port_scanner_ip'), methods=['GET', 'POST'])
bp.add_url_rule('/server/portscanner/<int:server_id>', view_func=PortScannerView.as_view('port_scanner'), methods=['GET', 'POST'])
bp.add_url_rule('/server/portscanner/<server_id>/ports', view_func=PortScannerPortsView.as_view('port_scanner_ports_ip'), methods=['GET'])
bp.add_url_rule('/server/portscanner/<int:server_id>/ports', view_func=PortScannerPortsView.as_view('port_scanner_ports'), methods=['GET'])
bp.add_url_rule('/servers', view_func=ServersView.as_view('servers'), methods=['GET'])

register_api(ServerGroupView, 'group', '/group', 'group_id')
bp.add_url_rule('/groups', view_func=ServerGroupsView.as_view('groups'), methods=['GET'])


def register_api_with_group(view, endpoint, url_beg, url_end, pk='user_id', pk_type='int', pk_end='group_id', pk_type_end='int'):
    view_func = view.as_view(endpoint)
    bp.add_url_rule(f'/{url_beg}/<{pk_type}:{pk}>/{url_end}', view_func=view_func, methods=['GET'])
    bp.add_url_rule(f'/{url_beg}/<{pk_type}:{pk}>/{url_end}/<{pk_type_end}:{pk_end}>', view_func=view_func, methods=['PUT', 'DELETE', 'POST', 'PATCH'])


register_api(UserView, 'user', '/user', 'user_id')
register_api_with_group(UserGroupView, 'user_group', 'user', 'groups')
bp.add_url_rule('/user/roles', view_func=UserRoles.as_view('roles'))

def register_api_channel(view, endpoint, url_beg, pk='receiver', pk_type='int', pk_end='channel_id', pk_type_end='int'):
    view_func = view.as_view(endpoint, True)
    bp.add_url_rule(f'/{url_beg}/<any(telegram, slack, pd, mm):{pk}>', view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'/{url_beg}/<any(telegram, slack, pd, mm):{pk}>/<{pk_type_end}:{pk_end}>', view_func=view_func, methods=['PUT', 'DELETE', 'GET', 'PATCH'])


register_api_channel(ChannelView, 'channel', '/channel')
bp.add_url_rule('/channels/<any(telegram, slack, pd, mm):receiver>', view_func=ChannelsView.as_view('channels'), methods=['GET'])


bp.add_url_rule(
    '/settings',
    view_func=SettingsView.as_view('settings'),
    methods=['GET'],
    defaults={'section': None}
)

bp.add_url_rule(
    '/settings/<any(smon, main, haproxy, nginx, apache, keepalived, rabbitmq, ldap, monitoring, mail, logs):section>',
    view_func=SettingsView.as_view('settings_section'),
    methods=['GET', 'POST']
)


@bp.route("/spec")
def spec():
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "Roxy-WI API"
    return jsonify(swag)


@bp.route("/swagger")
def swagger_ui():
    return render_template('swagger.html')


@bp.post('/login')
@validate(body=LoginRequest)
def do_login(body: LoginRequest):
    """
    Do log in
    ---
    tags:
      - Authentication
    description: This route is used to log into the system
    parameters:
      - name: body
        in: body
        schema:
          type: object
          properties:
            login:
              type: string
              required: true
              description: The user's login name
            password:
              type: string
              required: true
              description: The user's password
    responses:
      200:
        description: Login successfully, return a JWT token
        schema:
          type: object
          properties:
            access_token:
              type: string
              description: JWT token for user authentication
      401:
        description: Authentication Error
    """
    try:
        login = body.login
        password = body.password
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'There is no login or password')
    try:
        user_params = roxywi_auth.check_user_password(login, password)
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, ''), 401
    access_token = roxywi_auth.create_jwt_token(user_params)
    return jsonify(access_token=access_token)
