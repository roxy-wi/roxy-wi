from app.modules.db.db_model import SavedServer, Option
from app.modules.db.common import out_error


def update_saved_server(server, description, saved_id):
	query_update = SavedServer.update(server=server, description=description).where(SavedServer.id == saved_id)
	try:
		query_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_saved_server(saved_id):
	query = SavedServer.delete().where(SavedServer.id == saved_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_option(option_id):
	try:
		Option.delete().where(Option.id == option_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_saved_server(server, description, group):
	try:
		SavedServer.insert(server=server, description=description, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_option(saved_option, group):
	try:
		Option.insert(options=saved_option, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_options(**kwargs):
	if kwargs.get('option'):
		query = Option.select().where(Option.options == kwargs.get('option'))
	elif kwargs.get('group'):
		query = Option.select(Option.options).where(
			(Option.groups == kwargs.get('group')) & (Option.options.startswith(kwargs.get('term'))))
	else:
		query = Option.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_options(option, option_id):
	try:
		Option.update(options=option).where(Option.id == option_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_saved_servers(**kwargs):
	if kwargs.get('server'):
		query = SavedServer.select().where(SavedServer.server == kwargs.get('server'))
	elif kwargs.get('group'):
		query = SavedServer.select(SavedServer.server, SavedServer.description).where(
			(SavedServer.groups == kwargs.get('group')) & (SavedServer.server.startswith(kwargs.get('term'))))
	else:
		query = SavedServer.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res
