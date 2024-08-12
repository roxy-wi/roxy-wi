from app.modules.db.db_model import Cred, Server
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def select_ssh(**kwargs):
	if kwargs.get("group") and kwargs.get("cred_id"):
		query = Cred.select().where((Cred.id == kwargs.get('cred_id')) & (Cred.group_id == kwargs.get('group')))
	elif kwargs.get("name") is not None:
		query = Cred.select().where(Cred.name == kwargs.get('name'))
	elif kwargs.get("id") is not None:
		query = Cred.select().where(Cred.id == kwargs.get('id'))
	elif kwargs.get("serv") is not None:
		query = Cred.select().join(Server, on=(Cred.id == Server.cred_id)).where(Server.ip == kwargs.get('serv'))
	elif kwargs.get("group") is not None:
		query = Cred.select().where(Cred.group_id == kwargs.get("group"))
	else:
		query = Cred.select()
	try:
		query_res = query.execute()
	except Cred.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_ssh(name, enable, group, username, password):
	if password is None:
		password = 'None'
	try:
		return Cred.insert(name=name, key_enabled=enable, group_id=group, username=username, password=password).execute()
	except Exception as e:
		out_error(e)


def delete_ssh(ssh_id):
	query = Cred.delete().where(Cred.id == ssh_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def update_ssh(cred_id, name, enable, group, username, password):
	if password is None:
		password = 'None'

	cred_update = Cred.update(name=name, key_enabled=enable, group_id=group, username=username, password=password).where(
		Cred.id == cred_id)
	try:
		cred_update.execute()
	except Exception as e:
		out_error(e)


def update_ssh_passphrase(name: str, passphrase: str):
	try:
		Cred.update(passphrase=passphrase).where(Cred.name == name).execute()
	except Exception as e:
		out_error(e)


def get_ssh_by_id_and_group(creds_id: int, group_id: int) -> Cred:
	try:
		return Cred.select().where((Cred.group_id == group_id) & (Cred.id == creds_id)).execute()
	except Cred.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def get_ssh(ssh_id: int) -> Cred:
	try:
		return Cred.get(Cred.id == ssh_id)
	except Cred.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
