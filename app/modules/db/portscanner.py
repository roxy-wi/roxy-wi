from app.modules.db.db_model import connect, fn, PortScannerPorts, PortScannerSettings, PortScannerHistory
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def delete_port_scanner_settings(server_id):
	query = PortScannerSettings.delete().where(PortScannerSettings.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_port_scanner_settings(user_group):
	if user_group != 1:
		query = PortScannerSettings.select().where(PortScannerSettings.user_group_id == str(user_group))
	else:
		query = PortScannerSettings.select()

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_port_scanner_settings_for_service():
	query = PortScannerSettings.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_port_scanner_port(serv, user_group_id, port, service_name):
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular')
	try:
		PortScannerPorts.insert(
			serv=serv, port=port, user_group_id=user_group_id, service_name=service_name,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def select_ports(serv):
	conn = connect()
	cursor = conn.cursor()
	sql = """select port from port_scanner_ports where serv = '%s' """ % serv

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		conn.close()
		return cursor.fetchall()


def select_port_name(serv, port):
	query = PortScannerPorts.select(PortScannerPorts.service_name).where(
		(PortScannerPorts.serv == serv) & (PortScannerPorts.port == port))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for port in query_res:
			return port.service_name


def delete_ports(serv):
	query = PortScannerPorts.delete().where(PortScannerPorts.serv == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_port_scanner_history(serv, port, port_status, service_name):
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular')
	try:
		PortScannerHistory.insert(
			serv=serv, port=port, status=port_status, service_name=service_name, date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def insert_port_scanner_settings(server_id, user_group_id, enabled, notify, history):
	try:
		PortScannerSettings.insert(
			server_id=server_id, user_group_id=user_group_id, enabled=enabled, notify=notify, history=history
		).execute()
		return True
	except Exception:
		return False


def update_port_scanner_settings(server_id, user_group_id, enabled, notify, history):
	query = PortScannerSettings.update(
		user_group_id=user_group_id, enabled=enabled, notify=notify, history=history
	).where(PortScannerSettings.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)



def select_count_opened_ports(serv):
	query = PortScannerPorts.select(
		PortScannerPorts.date, fn.Count(PortScannerPorts.port).alias('count')
	).where(PortScannerPorts.serv == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		port = list()
		for ports in query_res:
			port.append([ports.count, ports.date])
		return port


def delete_portscanner_history(keep_interval: int):
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular', timedelta_minus=keep_interval)
	query = PortScannerHistory.delete().where(
		PortScannerHistory.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_port_scanner_history(serv):
	query = PortScannerHistory.select().where(PortScannerHistory.serv == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res
