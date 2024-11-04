import os
from typing import Union

from flask import render_template, make_response

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.service as service_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.tools.alerting as alerting


def create_user(new_user: str, email: str, password: str, role: int, enabled: int, group: int) -> Union[int, tuple]:
    try:
        user_id = user_sql.add_user(new_user, email, password, role, enabled, group)
        roxywi_common.logging(f'a new user {new_user}', 'has been created', roxywi=1, login=1)
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot create a new user')
    try:
        user_sql.update_user_role(user_id, group, role)
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e, 'Cannot update user role')
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
        roxywi_common.logging('error: Cannot send email for a new user', str(e), roxywi=1, login=1)

    return user_id


def delete_user(user_id: int):
    if user_sql.is_user_super_admin(user_id):
        count_super_admin_users = user_sql.get_super_admin_count()
        if count_super_admin_users < 2:
            raise Exception('error: you cannot delete a last user with superAdmin role')
    try:
        user = user_sql.get_user_id(user_id)
        user_sql.delete_user(user_id)
        user_sql.delete_user_groups(user_id)
        roxywi_common.logging(user.username, 'has been deleted user', roxywi=1, login=1)
    except Exception as e:
        return roxywi_common.handler_exceptions_for_json_data(e)


def update_user_password(password, user_id):
    user = user_sql.get_user_id(user_id)
    user_sql.update_user_password(password, user_id)
    roxywi_common.logging(f'user {user.username}', 'has changed password', roxywi=1, login=1)


def get_user_services(user_id: int) -> str:
    lang = roxywi_common.get_user_lang_for_flask()
    services = service_sql.select_services()

    return render_template(
        'ajax/user_services.html', user_services=user_sql.select_user_services(user_id), id=user_id, services=services, lang=lang
    )


def change_user_services(user: str, user_id: int, user_services: dict):
    services = ''

    for _k, v in user_services.items():
        for k2, _v2 in v.items():
            services += ' ' + k2

    try:
        user_sql.update_user_services(services=services, user_id=user_id)
    except Exception as e:
        raise Exception(f'error: Cannot save: {e}')
    roxywi_common.logging('Roxy-WI server', f'Access to the services has been updated for user: {user}', roxywi=1, login=1)


def change_user_active_group(group_id: int, user_id: int) -> str:
    try:
        user_sql.update_user_current_groups(group_id, user_id)
        return 'Ok'
    except Exception as e:
        roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot change the group', roxywi=1, login=1)


def get_user_active_group(group_id: int, user_id: int) -> str:
    groups = user_sql.select_user_groups_with_names(user_id)
    lang = roxywi_common.get_user_lang_for_flask()
    return render_template('ajax/user_current_group.html', groups=groups, group=group_id, lang=lang)


def save_user_group_and_role(user: str, groups_and_roles: dict):
    resp = make_response('ok')
    for k, v in groups_and_roles.items():
        user_id = int(k)
        if not user_sql.delete_user_groups(user_id):
            return 'error: Cannot delete old groups'
        for k2, v2 in v.items():
            group_id = int(k2)
            role_id = int(v2['role_id'])
            if len(v) == 1:
                user_sql.update_user_current_groups_by_id(group_id, user_id)
                resp.set_cookie('group', str(group_id), secure=True)
            try:
                user_sql.update_user_role(user_id, group_id, role_id)
            except Exception as e:
                raise Exception(f'error: Cannot update groups: {e}')
        else:
            roxywi_common.logging('Roxy-WI server', f'Groups and roles have been updated for user: {user}', roxywi=1, login=1)
            return resp


def get_ldap_email(username) -> str:
    import ldap

    server = sql.get_setting('ldap_server')
    port = sql.get_setting('ldap_port')
    user = sql.get_setting('ldap_user')
    password = sql.get_setting('ldap_password')
    ldap_base = sql.get_setting('ldap_base')
    domain = sql.get_setting('ldap_domain')
    ldap_search_field = sql.get_setting('ldap_search_field')
    ldap_class_search = sql.get_setting('ldap_class_search')
    ldap_user_attribute = sql.get_setting('ldap_user_attribute')
    ldap_type = sql.get_setting('ldap_type')

    ldap_proto = 'ldap' if ldap_type == "0" else 'ldaps'

    try:
        ldap_bind = ldap.initialize(f'{ldap_proto}://{server}:{port}/')
    except Exception as e:
        raise Exception(f'Cannot initialize connect to LDAP: {e}')

    try:
        ldap_bind.protocol_version = ldap.VERSION3
        ldap_bind.set_option(ldap.OPT_REFERRALS, 0)

        _ = ldap_bind.simple_bind_s(user, password)

        criteria = f"(&(objectClass={ldap_class_search})({ldap_user_attribute}={username}))"
        attributes = [ldap_search_field]
        result = ldap_bind.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

        results = [entry for dn, entry in result if isinstance(entry, dict)]
        try:
            return f'["{results[0][ldap_search_field][0].decode("utf-8")}","{domain}"]'
        except Exception:
            raise Exception('user not found')
    except Exception as e:
        raise Exception(e)
    finally:
        ldap_bind.unbind()
