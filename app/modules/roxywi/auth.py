import uuid

from flask import request, abort, make_response, url_for
from flask_login import login_user
from datetime import datetime, timedelta

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.service as service_sql
import app.modules.roxywi.common as roxywi_common


def check_login(user_uuid, token) -> str:
    if user_uuid is None:
        return 'login_page'

    if user_uuid is not None:
        if user_sql.get_user_name_by_uuid(user_uuid) is None:
            return 'login_page'
        else:
            try:
                ip = request.remote_addr
            except Exception:
                ip = ''

            user_sql.update_last_act_user(user_uuid, token, ip)

            return 'ok'
    return 'login_page'


def is_access_permit_to_service(service: str) -> bool:
    service_id = service_sql.select_service_id_by_slug(service)
    user_uuid = request.cookies.get('uuid')
    user_id = user_sql.get_user_id_by_uuid(user_uuid)
    user_services = user_sql.select_user_services(user_id)
    if str(service_id) in user_services:
        return True
    else:
        return False


def is_admin(level=1, **kwargs):
    if kwargs.get('role_id'):
        role = kwargs.get('role_id')
    else:
        user_id = request.cookies.get('uuid')
        group_id = request.cookies.get('group')

        try:
            role = user_sql.get_user_role_by_uuid(user_id, group_id)
        except Exception:
            role = 4
            pass
    try:
        return True if int(role) <= int(level) else False
    except Exception:
        return False


def page_for_admin(level=1) -> None:
    if not is_admin(level=level):
        return abort(400, 'bad permission')


def check_in_ldap(user, password):
    import ldap

    server = sql.get_setting('ldap_server')
    port = sql.get_setting('ldap_port')
    ldap_class_search = sql.get_setting('ldap_class_search')
    root_user = sql.get_setting('ldap_user')
    root_password = sql.get_setting('ldap_password')
    ldap_base = sql.get_setting('ldap_base')
    ldap_search_field = sql.get_setting('ldap_search_field')
    ldap_user_attribute = sql.get_setting('ldap_user_attribute')
    ldap_type = sql.get_setting('ldap_type')

    ldap_proto = 'ldap' if ldap_type == "0" else 'ldaps'

    ldap_bind = ldap.initialize('{}://{}:{}/'.format(ldap_proto, server, port))
    try:
        ldap_bind.protocol_version = ldap.VERSION3
        ldap_bind.set_option(ldap.OPT_REFERRALS, 0)

        bind = ldap_bind.simple_bind_s(root_user, root_password)

        criteria = "(&(objectClass=" + ldap_class_search + ")(" + ldap_user_attribute + "=" + user + "))"
        attributes = [ldap_search_field]
        result = ldap_bind.search_s(ldap_base, ldap.SCOPE_SUBTREE, criteria, attributes)

        bind = ldap_bind.simple_bind_s(result[0][0], password)
    except ldap.INVALID_CREDENTIALS:
        return False
    except ldap.SERVER_DOWN:
        raise Exception('error: LDAP server is down')
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            raise Exception(f'error: {e.message["desc"]}')
        else:
            raise Exception(f'error: {e}')
    else:
        return True


def create_uuid_and_token(login: str):
    user_uuid = str(uuid.uuid4())
    user_token = str(uuid.uuid4())
    user_sql.write_user_uuid(login, user_uuid)
    user_sql.write_user_token(login, user_token)

    return user_uuid, user_token


def do_login(user_uuid: str, user_group: str, user: str, next_url: str):
    try:
        session_ttl = sql.get_setting('session_ttl')
    except Exception:
        session_ttl = 5

    if next_url:
        redirect_to = f'https://{request.host}{next_url}'
    else:
        redirect_to = f"https://{request.host}{url_for('overview.index')}"

    expires = datetime.utcnow() + timedelta(days=session_ttl)

    login_user(user)
    resp = make_response(redirect_to)
    resp.set_cookie('uuid', user_uuid, secure=True, expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"), samesite='Strict')
    resp.set_cookie('group', str(user_group), expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"), samesite='Strict')

    try:
        user_group_name = group_sql.get_group_name_by_id(user_group)
    except Exception:
        user_group_name = ''

    try:
        user_name = user_sql.get_user_name_by_uuid(user_uuid)
        roxywi_common.logging('Roxy-WI server', f' user: {user_name}, group: {user_group_name} login', roxywi=1)
    except Exception as e:
        print(f'error: {e}')

    return resp
