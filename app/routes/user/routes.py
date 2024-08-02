import json

from flask import request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt

from app.routes.user import bp
import app.modules.common.common as common
import app.modules.roxywi.user as roxywi_user
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common
from app.middleware import get_user_params
from app.modules.roxywi.class_models import BaseResponse, ErrorResponse
from app.views.user.views import UserView, UserGroupView

def register_api_with_group(view, endpoint, url_beg, url_end, pk='user_id', pk_type='int', pk_end='group_id', pk_type_end='int'):
    view_func = view.as_view(endpoint)
    bp.add_url_rule(f'/<{pk_type}:{pk}>/{url_end}', view_func=view_func, methods=['GET'])
    bp.add_url_rule(f'/<{pk_type}:{pk}>/{url_end}/<{pk_type_end}:{pk_end}>', view_func=view_func, methods=['PUT', 'DELETE', 'POST', 'PATCH'])


def register_api(view, endpoint, url, pk='listener_id', pk_type='int'):
    view_func = view.as_view(endpoint)
    bp.add_url_rule(url, view_func=view_func, methods=['POST'])
    bp.add_url_rule(f'{url}/<{pk_type}:{pk}>', view_func=view_func, methods=['GET', 'PUT', 'DELETE'])


register_api(UserView, 'user', '', 'user_id')
register_api_with_group(UserGroupView, 'user_group', '', 'groups')

@bp.before_request
@jwt_required()
def before_request():
    """ Protect all the admin endpoints. """
    pass


@bp.route('/ldap/<username>')
def get_ldap_email(username):
    roxywi_auth.page_for_admin(level=2)

    try:
        user = roxywi_user.get_ldap_email(username)
        return jsonify({'status': 'ldap', 'user': user})
    except Exception as e:
        return roxywi_common.handle_json_exceptions(e, 'Cannot get LDAP email')


@bp.post('/password')
@get_user_params()
def update_user_its_password():
    password = request.json.get('pass')

    try:
        roxywi_user.update_user_password(password, g.user_params['user_id'])
        return BaseResponse().model_dump(mode='json')
    except Exception as e:
        return ErrorResponse(error=str(e)).model_dump(mode='json'), 501


@bp.post('/password/<int:user_id>')
def update_user_password(user_id):
    password = request.json.get('pass')

    try:
        roxywi_user.update_user_password(password, user_id)
        return BaseResponse().model_dump(mode='json')
    except Exception as e:
        return ErrorResponse(error=str(e)).model_dump(mode='json'), 501



@bp.route('/services/<int:user_id>', methods=['GET', 'POST'])
def show_user_services(user_id):
    if request.method == 'GET':
        return roxywi_user.get_user_services(user_id)
    else:
        json_data = request.get_json()
        user = json_data['username']
        user_services = json_data['services']
        try:
            roxywi_user.change_user_services(user, user_id, user_services)
            return jsonify({'status': 'updated'})
        except Exception as e:
            return roxywi_common.handle_json_exceptions(e, 'Cannot change user services')


@bp.route('/group', methods=['GET', 'PUT'])
def get_current_group():
    claims = get_jwt()
    group_id = claims['group']
    user_id = claims['user_id']
    if request.method == 'GET':
        return roxywi_user.get_user_active_group(group_id, user_id)
    elif request.method == 'PUT':
        return roxywi_user.change_user_active_group(group_id, user_id)


@bp.post('/groups/save')
def change_user_groups_and_roles():
    user = common.checkAjaxInput(request.form.get('changeUserGroupsUser'))
    groups_and_roles = json.loads(request.form.get('jsonDatas'))

    return roxywi_user.save_user_group_and_role(user, groups_and_roles)
