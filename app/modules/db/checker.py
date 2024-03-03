from app.modules.db.db_model import CheckerSetting, Server, ServiceStatus
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
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


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


def update_haproxy_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, backend_alert: int,
	maxconn_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, service_alert=service_alert,
		backend_alert=backend_alert, maxconn_alert=maxconn_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_keepalived_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, backend_alert: int,
	setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id,
		service_alert=service_alert, backend_alert=backend_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_service_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, service_alert=service_alert
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
		services_check_status = ServiceStatus.select().execute()
	except Exception as e:
		return out_error(e)
	else:
		return services_check_status


def inset_or_update_service_status(server_id: int, service_id: int, service_check: str, status: int) -> None:
	query = ServiceStatus.insert(
		server_id=server_id, service_id=service_id, service_check=service_check, status=status
	).on_conflict('replace')
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.alert == 1) & (Server.enable == 1) & (Server.groups == kwargs.get('group'))
		)
	else:
		query = Server.select(Server.ip).where((Server.alert == 1) & (Server.enable == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_all_alerts(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			((Server.alert == 1) | (Server.nginx_alert == 1)) & (Server.enable == 1) & (Server.groups == kwargs.get('group'))
		)
	else:
		query = Server.select(Server.ip).where(((Server.alert == 1) | (Server.nginx_alert == 1)) & (Server.enable == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_nginx_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.nginx_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.nginx == 1)
		)
	else:
		query = Server.select(Server.ip).where(
			(Server.nginx_alert == 1)
			& (Server.enable == 1)
			& (Server.nginx == 1)
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_apache_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.apache_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.apache == 1)
		)
	else:
		query = Server.select(Server.ip).where((Server.apache_alert == 1) & (Server.enable == 1) & (Server.apache == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_keepalived_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.keepalived_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.keepalived == 1)
		)
	else:
		query = Server.select(Server.ip).where(
			(Server.keepalived_alert == 1)
			& (Server.enable == 1)
			& (Server.keepalived == 1)
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res
