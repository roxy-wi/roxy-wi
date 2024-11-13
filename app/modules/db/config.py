from app.modules.db.db_model import ConfigVersion
from app.modules.db.server import get_server_by_ip
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def insert_config_version(server_id: int, user_id: int, service: str, local_path: str, remote_path: str, diff: str):
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular')
	try:
		ConfigVersion.insert(
			server_id=server_id,
			user_id=user_id,
			service=service,
			local_path=local_path,
			remote_path=remote_path,
			diff=diff,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def select_config_version(server_ip: str, service: str) -> str:
	server_id = get_server_by_ip(server_ip).server_id
	query = ConfigVersion.select().where(
		(ConfigVersion.server_id == server_id)
		& (ConfigVersion.service == service)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_config_version(service: str, local_path: str):
	query_res = ConfigVersion.delete().where(
		(ConfigVersion.service == service)
		& (ConfigVersion.local_path == local_path)
	)
	try:
		query_res.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_remote_path_from_version(server_ip: str, service: str, local_path: str):
	server_id = get_server_by_ip(server_ip).server_id
	try:
		query_res = ConfigVersion.get(
			(ConfigVersion.server_id == server_id)
			& (ConfigVersion.service == service)
			& (ConfigVersion.local_path == local_path)
		).remote_path
	except Exception as e:
		out_error(e)
	else:
		return query_res
