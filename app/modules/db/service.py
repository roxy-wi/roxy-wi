from app.modules.db.db_model import Server, Services, ServiceSetting
from app.modules.db.common import out_error


def update_hapwi_server(server_id, alert, metrics, active, service_name):
	try:
		if service_name == 'nginx':
			update_hapwi = Server.update(
				nginx_alert=alert, nginx_active=active, nginx_metrics=metrics
			).where(Server.server_id == server_id)
		elif service_name == 'keepalived':
			update_hapwi = Server.update(keepalived_alert=alert, keepalived_active=active).where(
				Server.server_id == server_id)
		elif service_name == 'apache':
			update_hapwi = Server.update(apache_alert=alert, apache_active=active, apache_metrics=metrics).where(
				Server.server_id == server_id)
		else:
			update_hapwi = Server.update(haproxy_alert=alert, haproxy_metrics=metrics, haproxy_active=active).where(
				Server.server_id == server_id)
		update_hapwi.execute()
	except Exception as e:
		out_error(e)


def update_server_services(server_id: int, haproxy: int, nginx: int, apache: int, keepalived: int) -> bool:
	try:
		server_update = Server.update(
			haproxy=haproxy, nginx=nginx, apache=apache, keepalived=keepalived
		).where(Server.server_id == server_id)
		server_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_or_update_service_setting(server_id, service, setting, value):
	try:
		ServiceSetting.insert(server_id=server_id, service=service, setting=setting, value=value).on_conflict(
			'replace').execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_service_settings(server_id: int, service: str) -> str:
	query = ServiceSetting.select().where((ServiceSetting.server_id == server_id) & (ServiceSetting.service == service))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_docker_service_settings(server_id: int, service: str) -> str:
	query = ServiceSetting.select().where(
		(ServiceSetting.server_id == server_id)
		& (ServiceSetting.service == service)
		& (ServiceSetting.setting == 'dockerized')
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_docker_services_settings(service: str) -> str:
	query = ServiceSetting.select().where(
		(ServiceSetting.service == service)
		& (ServiceSetting.setting == 'dockerized')
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_restart_service_settings(server_id: int, service: str) -> str:
	query = ServiceSetting.select().where(
		(ServiceSetting.server_id == server_id)
		& (ServiceSetting.service == service)
		& (ServiceSetting.setting == 'restart')
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_restart_services_settings(service: str) -> str:
	query = ServiceSetting.select().where(
		(ServiceSetting.service == service)
		& (ServiceSetting.setting == 'restart')
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_service_setting(server_id: int, service: str, setting: str) -> str:
	try:
		result = ServiceSetting.get(
			(ServiceSetting.server_id == server_id)
			& (ServiceSetting.service == service)
			& (ServiceSetting.setting == setting)
		).value
	except Exception:
		return '0'
	else:
		return result


def delete_service_settings(server_id: int):
	query = ServiceSetting.delete().where(ServiceSetting.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_service_name_by_id(service_id: int) -> str:
	try:
		service = Services.get(Services.service_id == service_id).service
	except Exception as e:
		return out_error(e)
	else:
		return service


def select_service_id_by_slug(service_slug: str) -> int:
	try:
		service = Services.get(Services.slug == service_slug).service_id
	except Exception as e:
		return out_error(e)
	else:
		return service


def select_services():
	query = Services.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_service(slug: str) -> object:
	try:
		query_res = Services.get(Services.slug == slug)
	except Exception as e:
		out_error(e)
		return 'there is no service'
	else:
		return query_res


def update_keepalived(serv):
	try:
		Server.update(keepalived='1').where(Server.ip == serv).execute()
	except Exception as e:
		out_error(e)


def select_apache(serv):
	try:
		apache = Server.get(Server.ip == serv).apache
	except Exception as e:
		out_error(e)
	else:
		return apache


def update_apache(serv: str) -> None:
	try:
		Server.update(apache='1').where(Server.ip == serv).execute()
	except Exception as e:
		out_error(e)


def select_nginx(serv):
	try:
		query_res = Server.get(Server.ip == serv).nginx
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_nginx(serv: str) -> None:
	try:
		Server.update(nginx=1).where(Server.ip == serv).execute()
	except Exception as e:
		out_error(e)


def select_haproxy(serv):
	try:
		query_res = Server.get(Server.ip == serv).haproxy
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_haproxy(serv):
	try:
		Server.update(haproxy=1).where(Server.ip == serv).execute()
	except Exception as e:
		out_error(e)


def select_keepalived(serv):
	try:
		keepalived = Server.get(Server.ip == serv).keepalived
	except Exception as e:
		out_error(e)
	else:
		return keepalived


def select_count_services(service: str) -> int:
	try:
		if service == 'haproxy':
			query_res = Server.select().where(Server.haproxy == 1).count()
		elif service == 'nginx':
			query_res = Server.select().where(Server.nginx == 1).count()
		elif service == 'keepalived':
			query_res = Server.select().where(Server.keepalived == 1).count()
		elif service == 'apache':
			query_res = Server.select().where(Server.apache == 1).count()
		else:
			query_res = Server.select().where().count()
	except Exception as e:
		out_error(e)
	else:
		return query_res
