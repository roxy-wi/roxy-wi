from app.modules.db.db_model import UserName, RoxyTool, Version
from app.modules.db.common import out_error


def insert_user_name(user_name):
	try:
		UserName.insert(UserName=user_name).execute()
	except Exception:
		pass


def update_user_name(user_name):
	try:
		UserName.update(UserName=user_name).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_status(status, plan, method):
	try:
		UserName.update(Status=status, Method=method, Plan=plan).execute()
	except Exception as e:
		out_error(e)


def get_user() -> UserName:
	try:
		return UserName.get()
	except Exception as e:
		print(str(e))


def select_user_status() -> int:
	try:
		return UserName.get().Status
	except Exception:
		return 0


def get_roxy_tools():
	try:
		query_res = RoxyTool.select().where(RoxyTool.is_roxy == 1).execute()
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
