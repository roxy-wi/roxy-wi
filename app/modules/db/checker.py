from app.modules.db.db_model import CheckerSetting, Server, ServiceStatus, UDPBalancer
from app.modules.db.common import out_error


def select_checker_settings(service_id: int):
	query = CheckerSetting.select().where(CheckerSetting.service_id == service_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_checker_settings_for_server(service_id: int, server_id: int):
	query = CheckerSetting.select().where(
		(CheckerSetting.service_id == service_id)
		& (CheckerSetting.server_id == server_id)
	)
	try:
		return query.execute()
	except Exception as e:
		out_error(e)


def insert_new_checker_setting_for_server(server_ip: str) -> None:
	server_id = ()
	try:
		server_id = Server.get(Server.ip == server_ip).server_id
	except Exception as e:
		out_error(e)

	for service_id in range(1, 5):
		CheckerSetting.insert(
			server_id=server_id, service_id=service_id
		).on_conflict_ignore().execute()


def update_checker_setting_for_server(service_id: int, server_id: int, **kwargs) -> None:
	try:
		query = (CheckerSetting.update(**kwargs).where(
			(CheckerSetting.service_id == service_id) & (CheckerSetting.server_id == server_id)
		))
		query.execute()
	except Exception as e:
		out_error(e)


def update_haproxy_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, mm_id: int, service_alert: int, backend_alert: int,
	maxconn_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, mm_id=mm_id, service_alert=service_alert,
		backend_alert=backend_alert, maxconn_alert=maxconn_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_keepalived_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, mm_id: int, service_alert: int, backend_alert: int,
	setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, mm_id=mm_id,
		service_alert=service_alert, backend_alert=backend_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_service_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, mm_id: int, service_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, mm_id=mm_id, service_alert=service_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def select_checker_service_status(server_id: int, service_id: int, service_check: str) -> int:
	try:
		service_check_status = ServiceStatus.get(
			(ServiceStatus.server_id == server_id)
			& (ServiceStatus.service_id == service_id)
			& (ServiceStatus.service_check == service_check)
		).status
	except Exception as e:
		return out_error(e)
	else:
		return service_check_status


def select_checker_services_status() -> tuple:
	try:
		return ServiceStatus.select().execute()
	except Exception as e:
		return out_error(e)


def inset_or_update_service_status(server_id: int, service_id: int, service_check: str, status: int) -> None:
	query = ServiceStatus.insert(
		server_id=server_id, service_id=service_id, service_check=service_check, status=status
	).on_conflict('replace')
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_checker_enabled(service: str) -> Server:
	services = {
		'haproxy': (Server.haproxy_alert == 1),
		'nginx': (Server.nginx_alert == 1),
		'apache': (Server.apache_alert == 1),
		'keepalived': (Server.keepalived_alert == 1),
	}
	service_req = services.get(service)
	try:
		return Server.select(Server.ip).where(service_req & (Server.enabled == 1)).execute()
	except Exception as e:
		out_error(e)


def select_all_alerts(group_id: int):
	query = Server.select(Server.ip).where(
		((Server.haproxy_alert == 1) | (Server.nginx_alert == 1)) & (Server.enabled == 1) & (Server.group_id == group_id)
	)
	try:
		return query.execute()
	except Exception as e:
		out_error(e)


def select_checker_udp_enabled():
	try:
		return UDPBalancer.select().where(UDPBalancer.is_checker == 1)
	except Exception as e:
		out_error(e)
