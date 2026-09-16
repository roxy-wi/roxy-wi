from app.modules.db.db_model import KeepaliveRestart, Server
from app.modules.db.common import out_error


def select_keep_alive():
	try:
		# Finish the read before callers await network checks. A partially consumed
		# cursor otherwise pins SQLite WAL for the whole check loop.
		return list(Server.select(Server.ip, Server.group_id, Server.server_id).where(Server.haproxy_active == 1))
	except Exception as e:
		out_error(e)


def select_nginx_keep_alive():
	try:
		return list(Server.select(Server.ip, Server.group_id, Server.server_id).where(Server.nginx_active == 1))
	except Exception as e:
		out_error(e)


def select_apache_keep_alive():
	try:
		return list(Server.select(Server.ip, Server.group_id, Server.server_id).where(Server.apache_active == 1))
	except Exception as e:
		out_error(e)


def select_keepalived_keep_alive():
	try:
		return list(Server.select(Server.ip, Server.port, Server.group_id, Server.server_id).where(Server.keepalived_active == 1))
	except Exception as e:
		out_error(e)


def select_update_keep_alive_restart(server_id: int, service: str) -> int:
	try:
		restarted = KeepaliveRestart.get(
			(KeepaliveRestart.server_id == server_id) &
			(KeepaliveRestart.service == service)
		).restarted
	except Exception as e:
		out_error(e)
	else:
		return restarted or 0


def update_keep_alive_restart(server_id: int, service: str, restarted: int) -> None:
	try:
		KeepaliveRestart.insert(server_id=server_id, service=service, restarted=restarted).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)
