import os

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.alerting.alerting as alerting

form = common.form


def create_user(new_user: str, email: str, password: str, role: str, activeuser: int, group: int, **kwargs) -> bool:
    if roxywi_common.check_user_group(token=kwargs.get('token')):

        if roxywi_auth.is_admin(level=2, role_id=kwargs.get('role_id')):
            try:
                user_id = sql.add_user(new_user, email, password, role, activeuser, group)
                sql.update_user_role(user_id, group, role)
                roxywi_common.logging(f'a new user {new_user}', ' has been created ', roxywi=1, login=1)
                try:
                    sql.update_user_role(user_id, group, role)
                except Exception as e:
                    print(f'error: cannot update user role {e}')
                try:
                    if password == 'aduser':
                        password = 'your domain password'
                    message = f"A user has been created for you on Roxy-WI portal!\n\n" \
                              f"Now you can login to https://{os.environ.get('HTTP_HOST', '')}\n\n" \
                              f"Your credentials are:\n" \
                              f"Login: {new_user}\n" \
                              f"Password: {password}"
                    alerting.send_email(email, 'A user has been created for you', message)
                except Exception as e:
                    roxywi_common.logging('error: Cannot send email for a new user', e, roxywi=1, login=1)
            except Exception as e:
                print(f'error: Cannot create a new user: {e}')
                roxywi_common.logging('error: Cannot create a new user', e, roxywi=1, login=1)
                return False
        else:
            print('error: dalsdm')
            roxywi_common.logging(new_user, ' tried to privilege escalation', roxywi=1, login=1)
            return False

    return True


def delete_user():
    userdel = form.getvalue('userdel')
    user = sql.select_users(id=userdel)
    username = ''
    for u in user:
        username = u.username
    if sql.delete_user(userdel):
        sql.delete_user_groups(userdel)
        roxywi_common.logging(username, ' has been deleted user ', roxywi=1, login=1)
        print("Ok")


def update_user():
    email = form.getvalue('email')
    role_id = int(form.getvalue('role'))
    new_user = form.getvalue('updateuser')
    user_id = form.getvalue('id')
    activeuser = form.getvalue('activeuser')
    group_id = int(form.getvalue('usergroup'))

    if roxywi_common.check_user_group():
        if roxywi_auth.is_admin(level=role_id):
            sql.update_user(new_user, email, role_id, user_id, activeuser)
            sql.update_user_role(user_id, group_id, role_id)
            roxywi_common.logging(new_user, ' has been updated user ', roxywi=1, login=1)
        else:
            roxywi_common.logging(new_user, ' tried to privilege escalation', roxywi=1, login=1)


def update_user_password():
    password = form.getvalue('updatepassowrd')
    username = ''

    if form.getvalue('uuid'):
        user_id = sql.get_user_id_by_uuid(form.getvalue('uuid'))
    else:
        user_id = form.getvalue('id')
    user = sql.select_users(id=user_id)
    for u in user:
        username = u.username
    sql.update_user_password(password, user_id)
    roxywi_common.logging('user ' + username, ' has changed password ', roxywi=1, login=1)
    print("Ok")


def get_user_services() -> None:
    user_id = common.checkAjaxInput(form.getvalue('getuserservices'))
    lang = roxywi_common.get_user_lang()
    services = sql.select_services()

    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_user_services.html')
    template = template.render(user_services=sql.select_user_services(user_id), id=user_id, services=services, lang=lang)
    print(template)


def change_user_services() -> None:
    import json

    user_id = common.checkAjaxInput(form.getvalue('changeUserServicesId'))
    user = common.checkAjaxInput(form.getvalue('changeUserServicesUser'))
    services = ''
    user_services = json.loads(form.getvalue('jsonDatas'))

    for k, v in user_services.items():
        for k2, v2 in v.items():
            services += ' ' + k2

    try:
        if sql.update_user_services(services=services, user_id=user_id):
            roxywi_common.logging('Roxy-WI server', f'Access to the services has been updated for user: {user}', roxywi=1, login=1)
    except Exception as e:
        print(e)


def change_user_active_group() -> None:
    group_id = common.checkAjaxInput(form.getvalue('changeUserCurrentGroupId'))
    user_uuid = common.checkAjaxInput(form.getvalue('changeUserGroupsUser'))

    try:
        if sql.update_user_current_groups(group_id, user_uuid):
            print('Ok')
        else:
            print('error: Cannot change group')
    except Exception as e:
        print(e)


def get_user_active_group(user_id: str, group: str) -> None:
    group_id = sql.get_user_id_by_uuid(user_id.value)
    groups = sql.select_user_groups_with_names(group_id)
    lang = roxywi_common.get_user_lang()
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_user_current_group.html')
    template = template.render(groups=groups, group=group.value, id=group_id, lang=lang)
    print(template)


def show_user_groups_and_roles() -> None:
    user_id = common.checkAjaxInput(form.getvalue('user_id'))
    groups = sql.select_user_groups_with_names(user_id, user_not_in_group=1)
    roles = sql.select_roles()
    lang = roxywi_common.get_user_lang()
    user_groups = sql.select_user_groups_with_names(user_id)
    env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
    template = env.get_template('ajax/show_user_groups_and_roles.html')
    template = template.render(groups=groups, user_groups=user_groups, roles=roles, lang=lang)
    print(template)


def save_user_group_and_role() -> None:
    import json

    user = common.checkAjaxInput(form.getvalue('changeUserGroupsUser'))
    groups_and_roles = json.loads(form.getvalue('jsonDatas'))

    for k, v in groups_and_roles.items():
        user_id = int(k)
        if not sql.delete_user_groups(user_id):
            print('error: cannot delete old groups')
        for k2, v2 in v.items():
            group_id = int(k2)
            role_id = int(v2['role_id'])
            try:
                sql.update_user_role(user_id, group_id, role_id)
            except Exception as e:
                print(e)
                break
        else:
            roxywi_common.logging('Roxy-WI server', f'Groups and roles have been updated for user: {user}', roxywi=1, login=1)
            print('ok')
