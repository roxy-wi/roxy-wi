import os

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.alerting.alerting as alerting

form = common.form


def create_user():
    email = form.getvalue('newemail')
    password = form.getvalue('newpassword')
    role = form.getvalue('newrole')
    new_user = form.getvalue('newusername')
    page = form.getvalue('page')
    activeuser = form.getvalue('activeuser')
    group = form.getvalue('newgroupuser')
    role_id = sql.get_role_id_by_name(role)

    if roxywi_common.check_user_group():
        if roxywi_auth.is_admin(level=role_id):
            try:
                sql.add_user(new_user, email, password, role, activeuser, group)
                env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
                template = env.get_template('ajax/new_user.html')

                template = template.render(users=sql.select_users(user=new_user),
                                           groups=sql.select_groups(),
                                           page=page,
                                           roles=sql.select_roles(),
                                           adding=1)
                print(template)
                roxywi_common.logging(f'a new user {new_user}', ' has been created ', roxywi=1, login=1)
                try:
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
        else:
            print('error: dalsdm')
            roxywi_common.logging(new_user, ' tried to privilege escalation', roxywi=1, login=1)


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
    role = form.getvalue('role')
    new_user = form.getvalue('updateuser')
    user_id = form.getvalue('id')
    activeuser = form.getvalue('activeuser')
    role_id = sql.get_role_id_by_name(role)

    if roxywi_common.check_user_group():
        if roxywi_auth.is_admin(level=role_id):
            sql.update_user(new_user, email, role, user_id, activeuser)
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
    groups = []
    u_g = sql.select_user_groups(user_id)
    services = sql.select_services()
    for g in u_g:
        groups.append(g.user_group_id)

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_user_services.html')
    template = template.render(user_services=sql.select_user_services(user_id), id=user_id, services=services)
    print(template)


def change_user_services() -> None:
    user_id = common.checkAjaxInput(form.getvalue('changeUserServicesId'))
    services = common.checkAjaxInput(form.getvalue('changeUserServices'))
    user = common.checkAjaxInput(form.getvalue('changeUserServicesUser'))

    try:
        if sql.update_user_services(services=services, user_id=user_id):
            roxywi_common.logging('Roxy-WI server', f'Access to the services has been updated for user: {user}',
                                  roxywi=1, login=1)
    except Exception as e:
        print(e)


def get_user_groups() -> None:
    user_id = common.checkAjaxInput(form.getvalue('getusergroups'))
    groups = []
    u_g = sql.select_user_groups(user_id)
    for g in u_g:
        groups.append(g.user_group_id)

    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_user_groups.html')
    template = template.render(groups=sql.select_groups(), user_groups=groups, id=user_id)
    print(template)


def change_user_group() -> None:
    group_id = common.checkAjaxInput(form.getvalue('changeUserGroupId'))
    groups = common.checkAjaxInput(form.getvalue('changeUserGroups'))
    user = common.checkAjaxInput(form.getvalue('changeUserGroupsUser'))
    if sql.delete_user_groups(group_id):
        for group in groups:
            if group[0] == ',':
                continue
            try:
                sql.update_user_groups(groups=group[0], user_group_id=group_id)
            except Exception as e:
                print(e)

    roxywi_common.logging('Roxy-WI server', f'Groups has been updated for user: {user}', roxywi=1, login=1)


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
    env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
    template = env.get_template('/show_user_current_group.html')
    template = template.render(groups=groups, group=group.value, id=group_id)
    print(template)
