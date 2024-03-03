from app.modules.db.db_model import UserName, RoxyTool, Version
from app.modules.db.common import out_error


def insert_user_name(user_name):
	try:
		UserName.insert(UserName=user_name).execute()
	except Exception:
		pass


def select_user_name():
	try:
		query_res = UserName.get().UserName
	except Exception:
		return False
	else:
		return query_res



def update_user_name(user_name):
	user_update = UserName.update(UserName=user_name)
	try:
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_status(status, plan, method):
	user_update = UserName.update(Status=status, Method=method, Plan=plan)
	try:
		user_update.execute()
	except Exception:
		return False
	else:
		return True


def select_user_status():
	try:
		query_res = UserName.get().Status
	except Exception:
		return False
	else:
		return query_res


def select_user_plan():
	try:
		query_res = UserName.get().Plan
	except Exception:
		return False
	else:
		return query_res


def select_user_all():
	try:
		query_res = UserName.select()
	except Exception:
		return False
	else:
		return query_res


def get_roxy_tools():
	query = RoxyTool.select()
	try:
		query_res = query.where(RoxyTool.is_roxy == 1).execute()
	except Exception as e:
		out_error(e)
	else:
		tools = []
		for tool in query_res:
			tools.append(tool.name)
		return tools


def get_all_tools():
	try:
		query_res = RoxyTool.select().execute()
	except Exception as e:
		out_error(e)
	else:
		tools = {}
		for tool in query_res:
			tools.setdefault(tool.name, {'current_version': tool.current_version, 'new_version': tool.new_version, 'desc': tool.desc})

		return tools


def update_tool_cur_version(tool_name: str, version: str):
	try:
		RoxyTool.update(current_version=version).where(RoxyTool.name == tool_name).execute()
	except Exception as e:
		out_error(e)


def update_tool_new_version(tool_name: str, version: str):
	try:
		RoxyTool.update(new_version=version).where(RoxyTool.name == tool_name).execute()
	except Exception as e:
		out_error(e)


def get_tool_cur_version(tool_name: str):
	try:
		query = RoxyTool.get(RoxyTool.name == tool_name).current_version
	except Exception as e:
		out_error(e)
	else:
		return query


def get_ver():
	try:
		ver = Version.get()
	except Exception as e:
		out_error(e)
	else:
		return ver.version
