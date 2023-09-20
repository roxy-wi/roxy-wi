from flask import request, redirect, url_for, abort

import modules.db.sql as sql


def check_login(user_uuid, token, **kwargs) -> str:
	if user_uuid is None:
		return 'login_page'

	try:
		sql.delete_old_uuid()
	except Exception as e:
		raise Exception(f'error: cannot connect to DB {e}')

	if user_uuid is not None:
		if sql.get_user_name_by_uuid(user_uuid) is None:
			return 'login_page'
		if kwargs.get('service'):
			required_service = str(kwargs.get('service'))
			user_id = sql.get_user_id_by_uuid(user_uuid)
			user_services = sql.select_user_services(user_id)
			if required_service in user_services:
				return 'ok'
			else:
				return 'index'

		try:
			ip = request.remote_addr
		except Exception:
			ip = ''

		sql.update_last_act_user(user_uuid, token, ip)

	return 'login_page'


def is_admin(level=1, **kwargs):
	if kwargs.get('role_id'):
		role = kwargs.get('role_id')
	else:
		user_id = request.cookies.get('uuid')
		group_id = request.cookies.get('group')

		try:
			role = sql.get_user_role_by_uuid(user_id, group_id)
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
			raise Exception (f'error: {e}')
	else:
		return True
