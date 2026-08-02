from peewee import IntegrityError, DoesNotExist

from app.modules.db.db_model import Server, SystemInfo
from app.modules.db.common import out_error, not_unique_error
from app.modules.roxywi.exception import RoxywiResourceNotFound


def add_server(**kwargs):
	try:
		return Server.insert(**kwargs).execute()
	except IntegrityError as e:
		not_unique_error(e)
	except Exception as e:
		out_error(e)


def delete_server(server_id):
	try:
		server_for_delete = Server.delete().where(Server.server_id == server_id)
		deleted = server_for_delete.execute()
	except Exception as e:
		out_error(e)
	else:
		return deleted == 1


def update_server(hostname, ip, group, type_ip, enable, master, server_id, cred, port, desc, firewall, protected):
	try:
		server_update = Server.update(
			hostname=hostname, ip=ip, group_id=group, type_ip=type_ip, enabled=enable, master=master, cred_id=cred,
			port=port, description=desc, firewall_enable=firewall, protected=protected
		).where(Server.server_id == server_id)
		server_update.execute()
	except Exception as e:
		out_error(e)


def get_server(server_id: int) -> Server:
	try:
		return Server.get(Server.server_id == server_id)
	except DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		return out_error(e)


def get_server_by_ip(server_ip: str) -> Server:
	try:
		return Server.get(Server.ip == server_ip)
	except DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		return out_error(e)


def insert_system_info(
	server_id: int, os_info: str, sys_info: dict, cpu: dict, ram: dict, network: dict, disks: dict
):
	try:
		SystemInfo.insert(
			server_id=server_id, os_info=os_info, sys_info=sys_info, cpu=cpu, ram=ram, network=network, disks=disks
		).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)


def delete_system_info(server_id: int):
	try:
		SystemInfo.delete().where(SystemInfo.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def select_one_system_info(server_id: int):
	try:
		return SystemInfo.select().where(SystemInfo.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def is_system_info(server_id):
	try:
		query_res = SystemInfo.get(SystemInfo.server_id == server_id).server_id
	except Exception:
		return True
	else:
		if query_res:
			return True
		else:
			return False


def select_os_info(server_id):
	try:
		return SystemInfo.get(SystemInfo.server_id == server_id).os_info
	except DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def update_firewall(serv):
	try:
		Server.update(firewall_enable=1).where(Server.ip == serv).execute()
	except Exception as e:
		out_error(e)


def return_firewall(serv):
	try:
		query_res = Server.get(Server.ip == serv).firewall_enable
	except Exception:
		return False
	else:
		return True if query_res == 1 else False


def update_server_pos(pos, server_id) -> str:
	try:
		Server.update(pos=pos).where(Server.server_id == server_id).execute()
		return 'ok'
	except Exception as e:
		out_error(e)


def is_serv_protected(serv):
	try:
		query_res = Server.get(Server.ip == serv)
	except Exception:
		return ""
	else:
		return True if query_res.protected else False


def select_servers(**kwargs):
	query = Server.select()
	if kwargs.get('server') is not None:
		query = query.where(Server.ip == kwargs.get('server'))
	else:
		query = query.order_by(Server.hostname)
	try:
		return query.tuples().execute()
	except Exception as e:
		return out_error(e)


def get_dick_permit(group_id, **kwargs):
	query = Server.select().where(Server.group_id == int(group_id))
	if kwargs.get('disable') != 0:
		query = query.where(Server.enabled == 1)
	if not kwargs.get('virt'):
		query = query.where(Server.type_ip == 0)
	if kwargs.get('ip'):
		query = query.where(Server.ip == kwargs.get('ip'))
	for service_name in ('haproxy', 'nginx', 'keepalived', 'apache'):
		if kwargs.get(service_name) or kwargs.get('service') == service_name:
			query = query.where(getattr(Server, service_name) == 1)
	query = query.order_by(Server.pos.asc())
	try:
		return query.tuples().execute()
	except Exception as e:
		return out_error(e)


def is_master(ip, **kwargs):
	master = Server.alias('master')
	slave = Server.alias('slave')
	if kwargs.get('master_slave'):
		query = master.select(master.hostname, master.ip, slave.hostname, slave.ip).join(
			slave, on=(master.server_id == slave.master)
		).where(slave.master > 0)
	else:
		query = master.select(slave.ip, slave.hostname).join(
			slave, on=(master.server_id == slave.master)
		).where(master.ip == ip)
	try:
		return query.tuples().execute()
	except Exception as e:
		return out_error(e)


def get_server_with_group(server_id: int, group_id: int) -> Server:
	try:
		return Server.get((Server.server_id == server_id) & (Server.group_id == group_id))
	except DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def select_servers_with_group(group_id: int) -> Server:
	try:
		return Server.select().where(Server.group_id == group_id)
	except DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
