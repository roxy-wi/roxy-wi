from peewee import Case, JOIN

from app.modules.db.db_model import User, UserGroups, Groups, UUID, Token, ApiToken
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def add_user(user, email, password, role, activeuser, group):
	if password != 'aduser':
		try:
			hashed_pass = roxy_wi_tools.Tools.get_hash(password)
			last_id = User.insert(
				username=user, email=email, password=hashed_pass, role=role, activeuser=activeuser, groups=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id
	else:
		try:
			last_id = User.insert(
				username=user, email=email, role=role, ldap_user=1, activeuser=activeuser, groups=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id


def update_user(user, email, role, user_id, active_user):
	try:
		User.update(username=user, email=email, role=role, activeuser=active_user).where(User.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def update_user_from_admin_area(user, email, user_id, active_user):
	try:
		User.update(username=user, email=email, activeuser=active_user).where(User.user_id == user_id).execute()
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


def update_user_current_groups(groups, user_uuid):
	user_id = get_user_id_by_uuid(user_uuid)
	try:
		user_update = User.update(groups=groups).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_current_groups_by_id(groups, user_id):
	try:
		user_update = User.update(groups=groups).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)


def update_user_password(password, user_id):
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
	elif kwargs.get("id") is not None:
		query = User.select().where(User.user_id == kwargs.get("id"))
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
		query = User.select().where(User.groups == kwargs.get("by_group_id"))
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
		query = User.get(User.user_id == user_id).activeuser
	except Exception as e:
		out_error(e)
	else:
		return int(query)


def check_user_group(user_id, group_id):
	try:
		query_res = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
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


def update_last_act_user(uuid: str, token: str, ip: str) -> None:
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	session_ttl = get_setting('session_ttl')
	token_ttl = get_setting('token_ttl')
	cur_date_session = get_date.return_date('regular', timedelta=session_ttl)
	cur_date_token = get_date.return_date('regular', timedelta=token_ttl)
	cur_date = get_date.return_date('regular')
	user_id = get_user_id_by_uuid(uuid)
	query = UUID.update(exp=cur_date_session).where(UUID.uuid == uuid)
	query1 = Token.update(exp=cur_date_token).where(Token.token == token)
	query2 = User.update(last_login_date=cur_date, last_login_ip=ip).where(User.user_id == user_id)
	try:
		query.execute()
		query1.execute()
		query2.execute()
	except Exception as e:
		out_error(e)


def get_user_name_by_uuid(uuid):
	try:
		query = User.select(User.username).join(UUID, on=(User.user_id == UUID.user_id)).where(UUID.uuid == uuid)
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user in query_res:
			return user.username


def get_user_id_by_uuid(uuid):
	try:
		query = User.select(User.user_id).join(UUID, on=(User.user_id == UUID.user_id)).where(UUID.uuid == uuid)
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user in query_res:
			return user.user_id


def get_user_id_by_username(username: str):
	try:
		query = User.get(User.username == username).user_id
	except Exception as e:
		out_error(e)
	else:
		return query


def get_user_role_by_uuid(uuid, group_id):
	query = (
		UserGroups.select(UserGroups.user_role_id).join(UUID, on=(UserGroups.user_id == UUID.user_id)
		).where(
			(UUID.uuid == uuid) &
			(UserGroups.user_group_id == group_id)
		)
	)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user_id in query_res:
			return int(user_id.user_role_id)


def write_user_uuid(login, user_uuid):
	session_ttl = get_setting('session_ttl')
	user_id = get_user_id_by_username(login)
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular', timedelta=session_ttl)

	try:
		UUID.insert(user_id=user_id, uuid=user_uuid, exp=cur_date).execute()
	except Exception as e:
		out_error(e)


def write_user_token(login, user_token):
	token_ttl = get_setting('token_ttl')
	user_id = get_user_id_by_username(login)
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular', timedelta=token_ttl)

	try:
		Token.insert(user_id=user_id, token=user_token, exp=cur_date).execute()
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
	query = User.select(User.email).where((User.groups == group_id) & (User.role != 'guest'))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_user_email_by_uuid(uuid: str) -> str:
	user_id = get_user_id_by_uuid(uuid)
	try:
		query_res = User.get(User.user_id == user_id).email
	except Exception as e:
		out_error(e)
		return ""
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


def get_api_token(token):
	try:
		user_token = ApiToken.get(ApiToken.token == token)
	except Exception as e:
		return str(e)
	else:
		return True if token == user_token.token else False


def get_user_id_by_api_token(token):
	query = (User.select(User.user_id).join(ApiToken, on=(
		ApiToken.user_name == User.username
	)).where(ApiToken.token == token))
	try:
		query_res = query.execute()
	except Exception as e:
		return str(e)
	for i in query_res:
		return i.user_id


def write_api_token(user_token, group_id, user_role, user_name):
	token_ttl = int(get_setting('token_ttl'))
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular', timedelta=token_ttl)
	cur_date_token_ttl = get_date.return_date('regular', timedelta=token_ttl)

	try:
		ApiToken.insert(
			token=user_token, user_name=user_name, user_group_id=group_id, user_role=user_role,
			create_date=cur_date, expire_date=cur_date_token_ttl).execute()
	except Exception as e:
		out_error(e)


def get_username_group_id_from_api_token(token):
	try:
		user_name = ApiToken.get(ApiToken.token == token)
	except Exception as e:
		return str(e)
	else:
		return user_name.user_name, user_name.user_group_id, user_name.user_role


def get_token(uuid):
	query = Token.select().join(UUID, on=(Token.user_id == UUID.user_id)).where(UUID.uuid == uuid).limit(1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				return i.token
		except Exception:
			return ''


def delete_old_uuid():
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular')
	query = UUID.delete().where((UUID.exp < cur_date) | (UUID.exp.is_null(True)))
	query1 = Token.delete().where((Token.exp < cur_date) | (Token.exp.is_null(True)))
	try:
		query.execute()
		query1.execute()
	except Exception as e:
		out_error(e)


def get_role_id(user_id: int, group_id: int) -> int:
	try:
		role_id = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
	except Exception as e:
		out_error(e)
	else:
		return int(role_id.user_role_id)


def get_user_id(user_id: int) -> int:
	try:
		return User.get(User.user_id == user_id)
	except Exception as e:
		out_error(e)
