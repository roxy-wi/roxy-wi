from app.modules.db.db_model import Cred, Server
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def select_ssh(**kwargs):
	if kwargs.get("group") and kwargs.get("cred_id") and kwargs.get("not_shared"):
		query = Cred.select().where(
			((Cred.id == kwargs.get('cred_id')) & (Cred.group_id == kwargs.get('group'))) |
			((Cred.id == kwargs.get('cred_id')) & (Cred.shared == 1))
		)
	elif kwargs.get("group") and kwargs.get("cred_id"):
		query = Cred.select().where(
			((Cred.id == kwargs.get('cred_id')) & (Cred.group_id == kwargs.get('group'))) |
			(Cred.shared == 1)
		)
	elif kwargs.get("name") is not None:
		query = Cred.select().where(Cred.name == kwargs.get('name'))
	elif kwargs.get("id") is not None:
		query = Cred.select().where(Cred.id == kwargs.get('id'))
	elif kwargs.get("serv") is not None:
		query = Cred.select().join(Server, on=(Cred.id == Server.cred_id)).where(Server.ip == kwargs.get('serv'))
	elif kwargs.get("group") is not None:
		query = Cred.select().where((Cred.group_id == kwargs.get("group")) | (Cred.shared == 1))
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


def insert_new_ssh(name, enable, group, username, password, shared):
	if password is None:
		password = 'None'
	try:
		return Cred.insert(name=name, key_enabled=enable, group_id=group, username=username, password=password, shared=shared).execute()
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


def update_ssh(cred_id: int, name: str, enable: int, group: int, username: str, password: bytes, shared: int):
	if password is None:
		password = 'None'

	cred_update = Cred.update(
		name=name, key_enabled=enable, group_id=group, username=username, password=password, shared=shared
	).where(Cred.id == cred_id)
	try:
		cred_update.execute()
	except Exception as e:
		out_error(e)


def update_ssh_passphrase(cred_id: int, passphrase: str):
	try:
		Cred.update(passphrase=passphrase).where(Cred.id == cred_id).execute()
	except Exception as e:
		out_error(e)


def get_ssh_by_id_and_group(cred_id: int, group_id: int) -> Cred:
	try:
		return Cred.select().where((Cred.group_id == group_id) & (Cred.id == cred_id)).execute()
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
