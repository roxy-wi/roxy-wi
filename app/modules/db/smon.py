import uuid

from peewee import fn

from app.modules.db.db_model import SmonAgent, Server, SMON, SmonTcpCheck, SmonHttpCheck, SmonDnsCheck, SmonPingCheck, SmonHistory, SmonStatusPageCheck, SmonStatusPage
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def get_agents(group_id: int):
	try:
		return SmonAgent.select(SmonAgent, Server).join(Server).where(Server.groups == group_id).objects().execute()
	except Exception as e:
		out_error(e)


def get_free_servers_for_agent(group_id: int):
	try:
		query = Server.select().where(
			(Server.type_ip == 0) &
			(Server.server_id.not_in(SmonAgent.select(SmonAgent.server_id))) &
			(Server.groups == group_id)
		)
		return query.execute()
	except Exception as e:
		out_error(e)


def get_agent(agent_id: int):
	try:
		return SmonAgent.select(SmonAgent, Server).join(Server).where(SmonAgent.id == agent_id).objects().execute()
	except Exception as e:
		out_error(e)


def get_agent_id_by_check_id(check_id: int):
	check_type = SMON.get(SMON.id == check_id).check_type
	if check_type == 'tcp':
		query = SmonTcpCheck.get(SmonTcpCheck.smon_id == check_id).agent_id
	elif check_type == 'http':
		query = SmonHttpCheck.get(SmonHttpCheck.smon_id == check_id).agent_id
	elif check_type == 'dns':
		query = SmonDnsCheck.get(SmonDnsCheck.smon_id == check_id).agent_id
	else:
		query = SmonPingCheck.get(SmonPingCheck.smon_id == check_id).agent_id
	return query


def add_agent(name: str, server_id: int, desc: str, enabled: int, agent_uuid: str) -> int:
	try:
		last_id = SmonAgent.insert(name=name, server_id=server_id, desc=desc, enabled=enabled, uuid=agent_uuid).execute()
		return last_id
	except Exception as e:
		out_error(e)


def delete_agent(agent_id: int):
	try:
		SmonAgent.delete().where(SmonAgent.id == agent_id).execute()
	except Exception as e:
		out_error(e)


def update_agent(agent_id: int, name: str, desc: str, enabled: int):
	try:
		SmonAgent.update(name=name, desc=desc, enabled=enabled).where(SmonAgent.id == agent_id).execute()
	except Exception as e:
		out_error(e)


def get_agent_uuid(agent_id: int) -> uuid:
	try:
		return SmonAgent.get(SmonAgent.id == agent_id).uuid
	except SmonAgent.DoesNotExist:
		raise Exception('agent not found')
	except Exception as e:
		out_error(e)


def get_agent_ip_by_id(agent_id: int):
	try:
		query = SmonAgent.select(SmonAgent, Server).join(Server).where(SmonAgent.id == agent_id)
		query_res = query.objects().execute()
	except Exception as e:
		out_error(e)
	else:
		for r in query_res:
			return r.ip


def get_agent_id_by_uuid(agent_uuid: int) -> int:
	try:
		return SmonAgent.get(SmonAgent.uuid == agent_uuid).id
	except Exception as e:
		out_error(e)


def get_agent_id_by_ip(agent_ip) -> int:
	try:
		return SmonAgent.get(SmonAgent.server_id == Server.get(Server.ip == agent_ip).server_id).id
	except Exception as e:
		out_error(e)


def select_server_ip_by_agent_id(agent_id: int) -> str:
	try:
		return Server.get(Server.server_id == SmonAgent.get(SmonAgent.id == agent_id).server_id).ip
	except Exception as e:
		out_error(e)


def select_en_smon_tcp(agent_id) -> object:
	try:
		return SmonTcpCheck.select(SmonTcpCheck, SMON).join_from(SmonTcpCheck, SMON).where((SMON.en == '1') & (SmonTcpCheck.agent_id == agent_id)).execute()
	except Exception as e:
		out_error(e)


def select_en_smon_ping(agent_id) -> object:
	query = SmonPingCheck.select(SmonPingCheck, SMON).join_from(SmonPingCheck, SMON).where((SMON.en == '1') & (SmonPingCheck.agent_id == agent_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_dns(agent_id) -> object:
	query = SmonDnsCheck.select(SmonDnsCheck, SMON).join_from(SmonDnsCheck, SMON).where((SMON.en == '1') & (SmonDnsCheck.agent_id == agent_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_http(agent_id) -> object:
	query = SmonHttpCheck.select(SmonHttpCheck, SMON).join_from(SmonHttpCheck, SMON).where((SMON.en == '1') & (SmonHttpCheck.agent_id == agent_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_status(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).status
	except Exception as e:
		out_error(e)
	else:
		return int(query_res)


def change_status(status, smon_id):
	query = SMON.update(status=status).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def response_time(time, smon_id):
	query = SMON.update(response_time=time).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def add_sec_to_state_time(time, smon_id):
	query = SMON.update(time_state=time).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_smon_history(smon_id: int, resp_time: float, status: int, check_id: int, mes='') -> None:
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular')
	try:
		SmonHistory.insert(smon_id=smon_id, response_time=resp_time, status=status, date=cur_date, check_id=check_id, mes=mes).execute()
	except Exception as e:
		out_error(e)


def select_one_smon(smon_id: int, check_id: int) -> tuple:
	if check_id == 1:
		query = SmonTcpCheck.select(SmonTcpCheck, SMON).join_from(SmonTcpCheck, SMON).where(SMON.id == smon_id)
	elif check_id == 2:
		query = SmonHttpCheck.select(SmonHttpCheck, SMON).join_from(SmonHttpCheck, SMON).where(SMON.id == smon_id)
	elif check_id == 5:
		query = SmonDnsCheck.select(SmonDnsCheck, SMON).join_from(SmonDnsCheck, SMON).where(SMON.id == smon_id)
	else:
		query = SmonPingCheck.select(SmonPingCheck, SMON).join_from(SmonPingCheck, SMON).where(SMON.id == smon_id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_smon(name, enable, group, desc, telegram, slack, pd, user_group, check_type):
	try:
		last_id = SMON.insert(
			name=name, en=enable, desc=desc, group=group, telegram_channel_id=telegram, slack_channel_id=slack,
			pd_channel_id=pd, user_group=user_group, status='3', check_type=check_type
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return last_id


def insert_smon_ping(smon_id, hostname, packet_size, interval, agent_id):
	try:
		SmonPingCheck.insert(smon_id=smon_id, ip=hostname, packet_size=packet_size, interval=interval, agent_id=agent_id).execute()
	except Exception as e:
		out_error(e)


def insert_smon_tcp(smon_id, hostname, port, interval, agent_id):
	try:
		SmonTcpCheck.insert(smon_id=smon_id, ip=hostname, port=port, interval=interval, agent_id=agent_id).execute()
	except Exception as e:
		out_error(e)


def insert_smon_dns(smon_id: int, hostname: str, port: int, resolver: str, record_type: str, interval: int, agent_id: int) -> None:
	try:
		SmonDnsCheck.insert(smon_id=smon_id, ip=hostname, port=port, resolver=resolver, record_type=record_type, interval=interval, agent_id=agent_id).execute()
	except Exception as e:
		out_error(e)


def insert_smon_http(smon_id, url, body, http_method, interval, agent_id):
	try:
		SmonHttpCheck.insert(smon_id=smon_id, url=url, body=body, method=http_method, interval=interval, agent_id=agent_id).execute()
	except Exception as e:
		out_error(e)


def select_smon_ping():
	try:
		query_res = SmonPingCheck.select().execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_tcp():
	try:
		query_res = SmonTcpCheck.select().execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_http():
	try:
		query_res = SmonHttpCheck.select().execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_dns():
	try:
		query_res = SmonDnsCheck.select().execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_by_id(last_id):
	query = SMON.select().where(SMON.id == last_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_check_by_id(last_id, check_type):
	if check_type == 'ping':
		query = SmonPingCheck.select().where(SmonPingCheck.smon_id == last_id)
	elif check_type == 'tcp':
		query = SmonTcpCheck.select().where(SmonTcpCheck.smon_id == last_id)
	elif check_type == 'dns':
		query = SmonDnsCheck.select().where(SmonDnsCheck.smon_id == last_id)
	else:
		query = SmonHttpCheck.select().where(SmonHttpCheck.smon_id == last_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_smon(smon_id, user_group):
	query = SMON.delete().where((SMON.id == smon_id) & (SMON.user_group == user_group))
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def smon_list(user_group):
	if user_group == 1:
		query = (SMON.select().order_by(SMON.group))
	else:
		query = (SMON.select().where(SMON.user_group == user_group).order_by(SMON.group))

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def add_status_page(name: str, slug: str, desc: str, group_id: int, checks: list) -> int:
	try:
		last_id = SmonStatusPage.insert(name=name, slug=slug, group_id=group_id, desc=desc).execute()
	except Exception as e:
		if 'Duplicate entry' in str(e):
			raise Exception('error: The Slug is already taken, please enter another one')
		else:
			out_error(e)
	else:
		add_status_page_checks(last_id, checks)
		return last_id


def edit_status_page(page_id: int, name: str, slug: str, desc: str) -> None:
	try:
		SmonStatusPage.update(name=name, slug=slug, desc=desc).where(SmonStatusPage.id == page_id).execute()
	except Exception as e:
		out_error(e)


def add_status_page_checks(page_id: int, checks: list) -> None:
	for check in checks:
		try:
			SmonStatusPageCheck.insert(page_id=page_id, check_id=int(check)).execute()
		except Exception as e:
			out_error(e)


def delete_status_page_checks(page_id: int) -> None:
	try:
		SmonStatusPageCheck.delete().where(SmonStatusPageCheck.page_id == page_id).execute()
	except Exception as e:
		out_error(e)


def select_status_pages(group_id: int):
	try:
		query_res = SmonStatusPage.select().where(SmonStatusPage.group_id == group_id).execute()
	except Exception as e:
		return out_error(e)
	else:
		return query_res


def select_status_page_by_id(page_id: int):
	try:
		query_res = SmonStatusPage.select().where(SmonStatusPage.id == page_id).execute()
	except Exception as e:
		return out_error(e)
	else:
		return query_res


def select_status_page(slug: str):
	try:
		query_res = SmonStatusPage.select().where(SmonStatusPage.slug == slug).execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_status_page_checks(page_id: int):
	try:
		query_res = SmonStatusPageCheck.select().where(SmonStatusPageCheck.page_id == page_id).execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_status_page(page_id):
	try:
		SmonStatusPage.delete().where(SmonStatusPage.id == page_id).execute()
	except Exception as e:
		out_error(e)


def get_last_smon_status_by_check(smon_id: int) -> object:
	query = SmonHistory.select().where(
		SmonHistory.smon_id == smon_id
	).limit(1).order_by(SmonHistory.date.desc())
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				return i.status
		except Exception:
			return ''


def get_last_smon_res_time_by_check(smon_id: int, check_id: int) -> int:
	query = SmonHistory.select().where(
		(SmonHistory.smon_id == smon_id) &
		(SmonHistory.check_id == check_id)
	).limit(1).order_by(SmonHistory.date.desc())
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				return i.response_time
		except Exception:
			return ''


def get_smon_history_count_checks(smon_id: int) -> dict:
	count_checks = {}
	query = SmonHistory.select(fn.Count(SmonHistory.status)).where(
		SmonHistory.smon_id == smon_id
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				count_checks['total'] = i.status
		except Exception as e:
			raise Exception(f'error: {e}')

	query = SmonHistory.select(fn.Count(SmonHistory.status)).where(
		(SmonHistory.smon_id == smon_id) &
		(SmonHistory.status == 1)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				count_checks['up'] = i.status
		except Exception as e:
			raise Exception(f'error: {e}')

	return count_checks


def get_smon_service_name_by_id(smon_id: int) -> str:
	query = SMON.select().join(SmonHistory, on=(SmonHistory.smon_id == SMON.id)).where(SmonHistory.smon_id == smon_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				return f'{i.name}'
		except Exception:
			return ''


def select_smon_history(smon_id: int) -> object:
	query = SmonHistory.select().where(
		SmonHistory.smon_id == smon_id
	).limit(40).order_by(SmonHistory.date.desc())
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_smon(smon_id, name, telegram, slack, pd, group, desc, en):
	query = (SMON.update(
		name=name, telegram_channel_id=telegram, slack_channel_id=slack, pd_channel_id=pd, group=group, desc=desc, en=en
	).where(SMON.id == smon_id))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonHttp(smon_id, url, body, method, interval, agent_id):
	try:
		SmonHttpCheck.update(url=url, body=body, method=method, interval=interval, agent_id=agent_id).where(SmonHttpCheck.smon_id == smon_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonTcp(smon_id, ip, port, interval, agent_id):
	try:
		SmonTcpCheck.update(ip=ip, port=port, interval=interval, agent_id=agent_id).where(SmonTcpCheck.smon_id == smon_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonPing(smon_id, ip, packet_size, interval, agent_id):
	try:
		SmonPingCheck.update(ip=ip, packet_size=packet_size, interval=interval, agent_id=agent_id).where(SmonPingCheck.smon_id == smon_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonDns(smon_id: int, ip: str, port: int, resolver: str, record_type: str, interval: int, agent_id: int):
	try:
		SmonDnsCheck.update(ip=ip, port=port, resolver=resolver, record_type=record_type, interval=interval,
							agent_id=agent_id).where(SmonDnsCheck.smon_id == smon_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def select_smon(user_group):
	if user_group == 1:
		query = SMON.select()
	else:
		query = SMON.select().where(SMON.user_group == user_group)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_avg_resp_time(smon_id: int, check_id: int) -> int:
	try:
		query_res = SmonHistory.select(fn.AVG(SmonHistory.response_time)).where(
			(SmonHistory.smon_id == smon_id) &
			(SmonHistory.check_id == check_id)
		).scalar()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_smon_ssl_expire_date(smon_id: str, expire_date: str) -> None:
	try:
		SMON.update(ssl_expire_date=expire_date).where(SMON.id == smon_id).execute()
	except Exception as e:
		out_error(e)


def update_smon_alert_status(smon_id: str, alert_value: int, alert: str) -> None:
	if alert == 'ssl_expire_warning_alert':
		query = SMON.update(ssl_expire_warning_alert=alert_value).where(SMON.id == smon_id)
	else:
		query = SMON.update(ssl_expire_critical_alert=alert_value).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def get_smon_alert_status(smon_id: str, alert: str) -> int:
	try:
		if alert == 'ssl_expire_warning_alert':
			alert_value = SMON.get(SMON.id == smon_id).ssl_expire_warning_alert
		else:
			alert_value = SMON.get(SMON.id == smon_id).ssl_expire_critical_alert
	except Exception as e:
		out_error(e)
	else:
		return alert_value


def change_body_status(status, smon_id):
	query = SMON.update(body_status=status).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_body_status(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).body_status
	except Exception as e:
		out_error(e)
	else:
		return query_res


def count_agents() -> int:
	try:
		return SmonAgent.select().count()
	except Exception as e:
		out_error(e)


def delete_smon_history():
	cur_date = get_date.return_date('regular', timedelta_minus=1)
	query = SmonHistory.delete().where(SmonHistory.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
