import os
import sys
import json

from flask import render_template, request
from flask_login import login_required

from app.routes.user import bp

sys.path.append(os.path.join(sys.path[0], '/var/www/haproxy-wi/app'))

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.user as roxywi_user
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common


@bp.before_request
@login_required
def before_request():
    """ Protect all of the admin endpoints. """
    pass


@bp.post('/create')
def create_user():
    roxywi_auth.page_for_admin(level=2)
    email = common.checkAjaxInput(request.form.get('newemail'))
    password = common.checkAjaxInput(request.form.get('newpassword'))
    role = common.checkAjaxInput(request.form.get('newrole'))
    new_user = common.checkAjaxInput(request.form.get('newusername'))
    page = common.checkAjaxInput(request.form.get('page'))
    activeuser = common.checkAjaxInput(request.form.get('activeuser'))
    group = common.checkAjaxInput(request.form.get('newgroupuser'))
    token = common.checkAjaxInput(request.form.get('token'))
    lang = roxywi_common.get_user_lang_for_flask()

    if not roxywi_common.check_user_group_for_flask(token=token):
        return 'error: Wrong group'
    if page == 'servers':
        if roxywi_auth.is_admin(level=2, role_id=role):
            roxywi_common.logging(new_user, ' tried to privilege escalation: user creation', roxywi=1, login=1)
            return 'error: Wrong role'
    if roxywi_user.create_user(new_user, email, password, role, activeuser, group):
        return render_template(
            'ajax/new_user.html', users=sql.select_users(user=new_user), groups=sql.select_groups(), page=page,
            roles=sql.select_roles(), adding=1, lang=lang
        )


@bp.post('/update')
def update_user():
    roxywi_auth.page_for_admin(level=2)
    email = request.form.get('email')
    new_user = request.form.get('updateuser')
    user_id = request.form.get('id')
    enabled = request.form.get('activeuser')
    group_id = int(request.form.get('usergroup'))

    if roxywi_common.check_user_group_for_flask():
        if request.form.get('role'):
            role_id = int(request.form.get('role'))
            if roxywi_auth.is_admin(level=role_id):
                roxywi_user.update_user(email, new_user, user_id, enabled, group_id, role_id)
            else:
                roxywi_common.logging(new_user, ' tried to privilege escalation', roxywi=1, login=1)
                return 'error: dalsd'
        else:
            try:
                sql.update_user_from_admin_area(new_user, email, user_id, enabled)
            except Exception as e:
                return f'error: Cannot update user: {e}'
            roxywi_common.logging(new_user, ' has been updated user ', roxywi=1, login=1)

        return 'ok'


@bp.route('/delete/<int:user_id>')
def delete_user(user_id):
    roxywi_auth.page_for_admin(level=2)
    try:
        return roxywi_user.delete_user(user_id)
    except Exception as e:
        return f'error: {e}'


@bp.route('/ldap/<username>')
def get_ldap_email(username):
    roxywi_auth.page_for_admin(level=2)

    return roxywi_user.get_ldap_email(username)


@bp.post('/password')
def update_password():
    password = request.form.get('updatepassowrd')
    uuid = request.form.get('uuid')
    user_id_from_get = request.form.get('id')

    return roxywi_user.update_user_password(password, uuid, user_id_from_get)


@bp.route('/services/<int:user_id>', methods=['GET', 'POST'])
def show_user_services(user_id):
    if request.method == 'GET':
        return roxywi_user.get_user_services(user_id)
    else:
        user = common.checkAjaxInput(request.form.get('changeUserServicesUser'))
        user_services = json.loads(request.form.get('jsonDatas'))

        return roxywi_user.change_user_services(user, user_id, user_services)


@bp.route('/group/current')
def get_current_group():
    uuid = request.cookies.get('uuid')
    group = request.cookies.get('group')

    return roxywi_user.get_user_active_group(uuid, group)


@bp.post('/group/change')
def change_current_group():
    group_id = common.checkAjaxInput(request.form.get('changeUserCurrentGroupId'))
    user_uuid = common.checkAjaxInput(request.form.get('changeUserGroupsUser'))

    return roxywi_user.change_user_active_group(group_id, user_uuid)


@bp.route('/groups/<int:user_id>')
def show_user_groups_and_roles(user_id):
    lang = roxywi_common.get_user_lang_for_flask()

    return roxywi_user.show_user_groups_and_roles(user_id, lang)


@bp.post('/groups/save')
def change_user_groups_and_roles():
    user = common.checkAjaxInput(request.form.get('changeUserGroupsUser'))
    groups_and_roles = json.loads(request.form.get('jsonDatas'))

    return roxywi_user.save_user_group_and_role(user, groups_and_roles)


@bp.route('/group/name/<int:group_id>')
def get_group_name_by_id(group_id):
    return sql.get_group_name_by_id(group_id)
