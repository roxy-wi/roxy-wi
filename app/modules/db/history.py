from app.modules.db.db_model import ActionHistory, Alerts
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def alerts_history(service, user_group, **kwargs):
	query = Alerts.select(Alerts.message, Alerts.level, Alerts.ip, Alerts.port, Alerts.date).where(
		Alerts.service == service
	)
	if kwargs.get('host'):
		query = query.where(Alerts.ip == kwargs['host'])
	if user_group != 1:
		query = query.where(Alerts.user_group == user_group)
	try:
		return list(query.order_by(Alerts.date.desc()).tuples())
	except Exception as e:
		out_error(e)


def insert_alerts(user_group, level, ip, port, message, service):
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular')
	try:
		Alerts.insert(
			user_group=user_group, message=message, level=level, ip=ip, port=port, service=service,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def delete_alert_history(keep_interval: int, service: str):
	if service == 'Checker':
		from app.modules.db.service_event_storage import prune_history
		return prune_history('checker', keep_interval)
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular', timedelta_minus=keep_interval)
	query = Alerts.delete().where(
		(Alerts.date < cur_date) & (Alerts.service == service)
	)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_action_history(service: str, action: str, server_id: int, user_id: int, user_ip: str, server_ip: str, hostname: str):
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular')
	try:
		ActionHistory.insert(
			service=service,
			action=action,
			server_id=server_id,
			user_id=user_id,
			ip=user_ip,
			date=cur_date,
			server_ip=server_ip,
			hostname=hostname
		).execute()
	except Exception as e:
		out_error(e)


def delete_action_history(server_id: int):
	query = ActionHistory.delete().where(ActionHistory.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_action_history_for_period():
	time_period = get_setting('action_keep_history_range')
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular', timedelta_minus=time_period)
	query = ActionHistory.delete().where(ActionHistory.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_action_history_by_server_id(server_id: int):
	try:
		return ActionHistory.select().where(ActionHistory.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def select_action_history_by_user_id(user_id: int):
	try:
		return ActionHistory.select().where(ActionHistory.user_id == user_id).execute()
	except Exception as e:
		out_error(e)


def select_action_history_by_server_id_and_service(server_id: int, service: str):
	query = ActionHistory.select().where(
		(ActionHistory.server_id == server_id)
		& (ActionHistory.service == service)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res
