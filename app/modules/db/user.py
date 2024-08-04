from peewee import Case, JOIN

from app.modules.db.db_model import User, UserGroups, Groups, ApiToken
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.exception import RoxywiResourceNotFound


def add_user(user, email, password, role, enabled, group):
	if password != 'aduser':
		try:
			hashed_pass = roxy_wi_tools.Tools.get_hash(password)
			last_id = User.insert(
				username=user, email=email, password=hashed_pass, role_id=role, enabled=enabled, group_id=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id
	else:
		try:
			last_id = User.insert(
				username=user, email=email, role=role, ldap_user=1, enabled=enabled, group_id=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id


def update_user(user, email, role, user_id, enabled):
	try:
		User.update(username=user, email=email, role_id=role, enabled=enabled).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def update_user_from_admin_area(user_id, **kwargs):
	try:
		User.update(**kwargs).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def delete_user_groups(user_id):
	group_for_delete = UserGroups.delete().where(UserGroups.user_id == user_id)
	try:
		group_for_delete.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_current_groups(group_id: int, user_id: int) -> None:
	try:
		User.update(group_id=group_id).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def update_user_current_groups_by_id(groups, user_id):
	try:
		user_update = User.update(group_id=groups).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)


def update_user_password(password, user_id):
	if password == '':
		return
	try:
		hashed_pass = roxy_wi_tools.Tools.get_hash(password)
		user_update = User.update(password=hashed_pass).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)


def delete_user(user_id):
	try:
		user_for_delete = User.delete().where(User.user_id == user_id)
		user_for_delete.execute()
		delete_user_groups(user_id)
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_role(user_id: int, group_id: int, role_id: int) -> None:
	try:
		UserGroups.insert(user_id=user_id, user_group_id=group_id, user_role_id=role_id).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)


def select_users(**kwargs):
	if kwargs.get("user") is not None:
		query = User.select().where(User.username == kwargs.get("user"))
	elif kwargs.get("group") is not None:
		get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
		cur_date = get_date.return_date('regular', timedelta_minutes_minus=15)
		query = (User.select(
			User, UserGroups, Case(
				0, [((User.last_login_date >= cur_date), 0)], 1
			).alias('last_login')
		).join(UserGroups, on=(User.user_id == UserGroups.user_id)).where(
			UserGroups.user_group_id == kwargs.get("group")
		))
	elif kwargs.get('by_group_id'):
		query = User.select().where(User.group_id == kwargs.get("by_group_id"))
	else:
		get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
		cur_date = get_date.return_date('regular', timedelta_minutes_minus=15)
		query = User.select(User, Case(0, [(
			(User.last_login_date >= cur_date), 0)], 1).alias('last_login')).order_by(User.user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def is_user_active(user_id: int) -> int:
	try:
		query = User.get(User.user_id == user_id).enabled
	except Exception as e:
		out_error(e)
	else:
		return int(query)


def check_user_group(user_id, group_id):
	try:
		query_res = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
	except UserGroups.DoesNotExist:
		return False
	except Exception:
		return False
	else:
		if query_res.user_id != '':
			return True
		else:
			return False


def select_user_groups_with_names(user_id, **kwargs):
	if kwargs.get("all") is not None:
		query = (UserGroups.select(
			UserGroups.user_group_id, UserGroups.user_id, Groups.name, Groups.description
		).join(Groups, on=(UserGroups.user_group_id == Groups.group_id)))
	elif kwargs.get("user_not_in_group") is not None:
		query = (Groups.select(
			Groups.group_id, Groups.name
		).join(UserGroups, on=(
			(UserGroups.user_group_id == Groups.group_id) &
			(UserGroups.user_id == user_id)
		), join_type=JOIN.LEFT_OUTER).group_by(Groups.name).where(UserGroups.user_id.is_null(True)))
	else:
		query = (UserGroups.select(
			UserGroups.user_group_id, UserGroups.user_role_id, Groups.name, Groups.group_id
		).join(Groups, on=(UserGroups.user_group_id == Groups.group_id)).where(UserGroups.user_id == user_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_user_roles_by_group(group_id: int):
	try:
		query_res = UserGroups.select().where(UserGroups.user_group_id == group_id).execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_users_roles():
	try:
		query_res = UserGroups.select().execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_last_act_user(user_id: int, ip: str) -> None:
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular')
	try:
		User.update(last_login_date=cur_date, last_login_ip=ip).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def get_user_by_username(username: str) -> User:
	try:
		return User.get(User.username == username)
	except Exception as e:
		out_error(e)


def get_user_role_in_group(user_id, group_id):
	try:
		query_res = UserGroups.select().where(
			(UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id)
		).execute()
	except Exception as e:
		out_error(e)
	else:
		for user_id in query_res:
			return int(user_id.user_role_id)


def get_user_id_by_username(username: str) -> User:
	try:
		return User.get(User.username == username)
	except Exception as e:
		out_error(e)


def select_user_services(user_id):
	try:
		query_res = User.get(User.user_id == user_id).user_services
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_user_services(services, user_id):
	try:
		User.update(user_services=services).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def get_super_admin_count() -> int:
	query = UserGroups.select(UserGroups.user_id, UserGroups.user_role_id).distinct().where(UserGroups.user_role_id == 1).group_by(UserGroups.user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			return len(list(query_res))
		except Exception as e:
			raise Exception(f'error: {e}')


def select_users_emails_by_group_id(group_id: int):
	query = User.select(User.email).where((User.group_id == group_id) & (User.role_id != 'guest'))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def is_user_super_admin(user_id: int) -> bool:
	query = UserGroups.select().where(UserGroups.user_id == user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for i in query_res:
			if i.user_role_id == 1:
				return True
		else:
			return False


def get_role_id(user_id: int, group_id: int) -> int:
	try:
		role_id = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
	except Exception as e:
		out_error(e)
	else:
		return int(role_id.user_role_id)


def get_user_id(user_id: int) -> User:
	try:
		return User.get(User.user_id == user_id)
	except User.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_user_from_group(group_id: int, user_id):
	try:
		UserGroups.delete().where((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id)).execute()
	except UserGroups.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
