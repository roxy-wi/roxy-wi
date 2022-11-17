import os
import http.cookies

import modules.db.sql as sql


def check_login(user_uuid, token, **kwargs):
	if user_uuid is None:
		print('<meta http-equiv="refresh" content="0; url=/app/login.py">')

	ref = os.environ.get("REQUEST_URI")

	try:
		sql.delete_old_uuid()
	except Exception as e:
		raise Exception(f'error: cannot connect to DB {e}')

	if user_uuid is not None:
		if sql.get_user_name_by_uuid(user_uuid.value) is None:
			print(f'<meta http-equiv="refresh" content="0; url=login.py?ref={ref}">')
			return False
		if kwargs.get('service'):
			required_service = str(kwargs.get('service'))
			user_id = sql.get_user_id_by_uuid(user_uuid.value)
			user_services = sql.select_user_services(user_id)
			if required_service in user_services:
				return True
			else:
				print('<meta http-equiv="refresh" content="0; url=overview.py">')
				return False

		sql.update_last_act_user(user_uuid.value, token)
	else:
		print(f'<meta http-equiv="refresh" content="0; url=login.py?ref={ref}">')
		return False


def is_admin(level=1):
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	try:
		role = sql.get_user_role_by_uuid(user_id.value)
	except Exception:
		role = 4
		pass

	try:
		return True if role <= level else False
	except Exception:
		return False


def page_for_admin(level=1) -> None:
	if not is_admin(level=level):
		print('<meta http-equiv="refresh" content="0; url=/">')
		return
