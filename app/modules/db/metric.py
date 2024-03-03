from app.modules.db.db_model import connect, mysql_enable, Metrics, MetricsHttpStatus, Server, NginxMetrics, ApacheMetrics, WafMetrics
from app.modules.db.sql import get_setting
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools


def insert_metrics(serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate):
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular')
	try:
		Metrics.insert(
			serv=serv, curr_con=curr_con, cur_ssl_con=cur_ssl_con, sess_rate=sess_rate, max_sess_rate=max_sess_rate,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)
	else:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def insert_metrics_http(serv, http_2xx, http_3xx, http_4xx, http_5xx):
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular')
	try:
		MetricsHttpStatus.insert(
			serv=serv, ok_ans=http_2xx, redir_ans=http_3xx, not_found_ans=http_4xx, err_ans=http_5xx,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)
	else:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def insert_nginx_metrics(serv, connection):
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular')
	try:
		NginxMetrics.insert(serv=serv, conn=connection, date=cur_date).execute()
	except Exception as e:
		out_error(e)
	else:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def insert_apache_metrics(serv, connection):
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular')
	try:
		ApacheMetrics.insert(serv=serv, conn=connection, date=cur_date).execute()
	except Exception as e:
		out_error(e)
	else:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def insert_waf_metrics(serv, connection):
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular')
	try:
		WafMetrics.insert(serv=serv, conn=connection, date=cur_date).execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def delete_waf_metrics():
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = WafMetrics.delete().where(WafMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def delete_metrics():
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = Metrics.delete().where(Metrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def delete_http_metrics():
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = MetricsHttpStatus.delete().where(MetricsHttpStatus.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def delete_nginx_metrics():
	time_zone = get_setting('time_zone')
	get_date = roxy_wi_tools.GetDate(time_zone)
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = NginxMetrics.delete().where(NginxMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def delete_apache_metrics():
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = ApacheMetrics.delete().where(ApacheMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	finally:
		conn = connect()
		if type(conn) is not str:
			if not conn.is_closed():
				conn.close()


def select_metrics(serv, service, **kwargs):
	conn = connect()
	cursor = conn.cursor()

	if service in ('nginx', 'apache', 'waf'):
		metrics_table = '{}_metrics'.format(service)
	elif service == 'http_metrics':
		metrics_table = 'metrics_http_status'
	else:
		metrics_table = 'metrics'

	if mysql_enable == '1':
		if kwargs.get('time_range') == '60':
			date_from = "and date > now() - INTERVAL 60 minute group by `date` div 100"
		elif kwargs.get('time_range') == '180':
			date_from = "and date > now() - INTERVAL 180 minute group by `date` div 200"
		elif kwargs.get('time_range') == '360':
			date_from = "and date > now() - INTERVAL 360 minute group by `date` div 300"
		elif kwargs.get('time_range') == '720':
			date_from = "and date > now() - INTERVAL 720 minute group by `date` div 500"
		else:
			date_from = "and date > now() - INTERVAL 30 minute"
		sql = """ select * from {metrics_table} where serv = '{serv}' {date_from} order by `date` asc """.format(
			metrics_table=metrics_table, serv=serv, date_from=date_from
		)
	else:
		if kwargs.get('time_range') == '60':
			date_from = "and date > datetime('now', '-60 minutes', 'localtime') and rowid % 2 = 0"
		elif kwargs.get('time_range') == '180':
			date_from = "and date > datetime('now', '-180 minutes', 'localtime') and rowid % 5 = 0"
		elif kwargs.get('time_range') == '360':
			date_from = "and date > datetime('now', '-360 minutes', 'localtime') and rowid % 7 = 0"
		elif kwargs.get('time_range') == '720':
			date_from = "and date > datetime('now', '-720 minutes', 'localtime') and rowid % 9 = 0"
		else:
			date_from = "and date > datetime('now', '-30 minutes', 'localtime')"

		sql = """ select * from (select * from {metrics_table} where serv = '{serv}' {date_from} order by `date`) order by `date` """.format(
			metrics_table=metrics_table, serv=serv, date_from=date_from)

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_servers_metrics_for_master(**kwargs):
	if kwargs.get('group') != 1:
		query = Server.select(Server.ip).where(
			((Server.metrics == 1) | (Server.nginx_metrics == 1) | (Server.apache_metrics == 1))
			& (Server.groups == kwargs.get('group'))
		)
	else:
		query = Server.select(Server.ip).where(
			(Server.metrics == 1)
			| (Server.nginx_metrics == 1)
			| (Server.apache_metrics == 1)
		)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_haproxy_servers_metrics_for_master():
	query = Server.select(Server.ip).where(Server.metrics == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_nginx_servers_metrics_for_master():
	query = Server.select(Server.ip).where((Server.nginx_metrics == 1) & (Server.nginx == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_apache_servers_metrics_for_master():
	query = Server.select(Server.ip).where(
		(Server.apache_metrics == 1)
		& (Server.apache == 1)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_servers_metrics(group_id):
	if group_id == 1:
		query = Server.select(Server.ip).where((Server.enable == 1) & (Server.metrics == 1))
	else:
		query = Server.select(Server.ip).where(
			(Server.enable == 1) & (Server.groups == group_id) & (Server.metrics == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_table_metrics(group_id):
	conn = connect()
	cursor = conn.cursor()

	if group_id == 1:
		groups = ""
	else:
		groups = "and servers.groups = '{group}' ".format(group=group_id)
	if mysql_enable == '1':
		sql = """
				select ip.ip, hostname, avg_sess_1h, avg_sess_24h, avg_sess_3d, max_sess_1h, max_sess_24h, max_sess_3d,
				avg_cur_1h, avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
				(select servers.ip from servers where metrics = 1 ) as ip,

				(select servers.ip, servers.hostname as hostname from servers left join metrics as metr on servers.ip = metr.serv where servers.metrics = 1 %s) as hostname,

				(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_1h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(), INTERVAL -1 HOUR)
				group by servers.ip)   as avg_sess_1h,

				(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_24h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as avg_sess_24h,

				(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_3d from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(), INTERVAL -3 DAY)
				group by servers.ip ) as avg_sess_3d,

		(select servers.ip,max(metr.sess_rate) as max_sess_1h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -1 HOUR)
				group by servers.ip)   as max_sess_1h,

				(select servers.ip,max(metr.sess_rate) as max_sess_24h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as max_sess_24h,

				(select servers.ip,max(metr.sess_rate) as max_sess_3d from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <=  now() and metr.date >= DATE_ADD(NOW(),INTERVAL -3 DAY)
				group by servers.ip ) as max_sess_3d,

				(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_1h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -1 HOUR)
				group by servers.ip)   as avg_cur_1h,

				(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_24h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as avg_cur_24h,

		(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_3d from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <=  now() and metr.date >= DATE_ADD(NOW(),INTERVAL -3 DAY)
		group by servers.ip ) as avg_cur_3d,

		(select servers.ip,max(metr.curr_con) as max_con_1h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -1 HOUR)
				group by servers.ip)   as max_con_1h,

				(select servers.ip,max(metr.curr_con) as max_con_24h from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as max_con_24h,

				(select servers.ip,max(metr.curr_con) as max_con_3d from servers
				left join metrics as metr on metr.serv = servers.ip
				where servers.metrics = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -3 DAY)
				group by servers.ip ) as max_con_3d

		where ip.ip=hostname.ip
				and ip.ip=avg_sess_1h.ip
				and ip.ip=avg_sess_24h.ip
				and ip.ip=avg_sess_3d.ip
				and ip.ip=max_sess_1h.ip
				and ip.ip=max_sess_24h.ip
				and ip.ip=max_sess_3d.ip
				and ip.ip=avg_cur_1h.ip
				and ip.ip=avg_cur_24h.ip
				and ip.ip=avg_cur_3d.ip
				and ip.ip=max_con_1h.ip
				and ip.ip=max_con_24h.ip
				and ip.ip=max_con_3d.ip

				group by hostname.ip """ % groups
	else:
		sql = """
		select ip.ip, hostname, avg_sess_1h, avg_sess_24h, avg_sess_3d, max_sess_1h, max_sess_24h, max_sess_3d, avg_cur_1h,
			avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
		(select servers.ip from servers where metrics = 1 ) as ip,

		(select servers.ip, servers.hostname as hostname from servers left join metrics as metr on servers.ip = metr.serv where servers.metrics = 1 %s) as hostname,

		(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_1h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as avg_sess_1h,

		(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_24h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as avg_sess_24h,

		(select servers.ip,round(avg(metr.sess_rate), 1) as avg_sess_3d from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as avg_sess_3d,

		(select servers.ip,max(metr.sess_rate) as max_sess_1h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as max_sess_1h,

		(select servers.ip,max(metr.sess_rate) as max_sess_24h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as max_sess_24h,

		(select servers.ip,max(metr.sess_rate) as max_sess_3d from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as max_sess_3d,

		(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_1h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as avg_cur_1h,

		(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_24h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as avg_cur_24h,

		(select servers.ip,round(avg(metr.curr_con+metr.cur_ssl_con), 1) as avg_cur_3d from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as avg_cur_3d,

		(select servers.ip,max(metr.curr_con) as max_con_1h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as max_con_1h,

		(select servers.ip,max(metr.curr_con) as max_con_24h from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as max_con_24h,

		(select servers.ip,max(metr.curr_con) as max_con_3d from servers
		left join metrics as metr on metr.serv = servers.ip
		where servers.metrics = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as max_con_3d

		where ip.ip=hostname.ip
		and ip.ip=avg_sess_1h.ip
		and ip.ip=avg_sess_24h.ip
		and ip.ip=avg_sess_3d.ip
		and ip.ip=max_sess_1h.ip
		and ip.ip=max_sess_24h.ip
		and ip.ip=max_sess_3d.ip
		and ip.ip=avg_cur_1h.ip
		and ip.ip=avg_cur_24h.ip
		and ip.ip=avg_cur_3d.ip
		and ip.ip=max_con_1h.ip
		and ip.ip=max_con_24h.ip
		and ip.ip=max_con_3d.ip

		group by hostname.ip """ % groups

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_service_table_metrics(service: str, group_id: int):
	conn = connect()
	cursor = conn.cursor()

	if service in ('nginx', 'apache'):
		metrics_table = f'{service}_metrics'

	if group_id == 1:
		groups = ""
	else:
		groups = f"and servers.groups = '{group_id}' "

	if mysql_enable == '1':
		sql = """
				select ip.ip, hostname, avg_cur_1h, avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
				(select servers.ip from servers where {metrics} = 1 ) as ip,

				(select servers.ip, servers.hostname as hostname from servers left join {metrics} as metr on servers.ip = metr.serv where servers.{metrics} = 1 {groups}) as hostname,

				(select servers.ip,round(avg(metr.conn), 1) as avg_cur_1h from servers
				left join {metrics} as metr on metr.serv = servers.ip
				where servers.{metrics} = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -1 HOUR)
				group by servers.ip)   as avg_cur_1h,

				(select servers.ip,round(avg(metr.conn), 1) as avg_cur_24h from servers
				left join {metrics} as metr on metr.serv = servers.ip
				where servers.{metrics} = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as avg_cur_24h,

		(select servers.ip,round(avg(metr.conn), 1) as avg_cur_3d from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <=  now() and metr.date >= DATE_ADD(NOW(),INTERVAL -3 DAY)
		group by servers.ip ) as avg_cur_3d,

		(select servers.ip,max(metr.conn) as max_con_1h from servers
				left join {metrics} as metr on metr.serv = servers.ip
				where servers.{metrics} = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -1 HOUR)
				group by servers.ip)   as max_con_1h,

				(select servers.ip,max(metr.conn) as max_con_24h from servers
				left join {metrics} as metr on metr.serv = servers.ip
				where servers.{metrics} = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -24 HOUR)
				group by servers.ip) as max_con_24h,

				(select servers.ip,max(metr.conn) as max_con_3d from servers
				left join {metrics} as metr on metr.serv = servers.ip
				where servers.{metrics} = 1 and
				metr.date <= now() and metr.date >= DATE_ADD(NOW(),INTERVAL -3 DAY)
				group by servers.ip ) as max_con_3d

		where ip.ip=hostname.ip
				and ip.ip=avg_cur_1h.ip
				and ip.ip=avg_cur_24h.ip
				and ip.ip=avg_cur_3d.ip
				and ip.ip=max_con_1h.ip
				and ip.ip=max_con_24h.ip
				and ip.ip=max_con_3d.ip

				group by hostname.ip """.format(metrics=metrics_table, groups=groups)
	else:
		sql = """
		select ip.ip, hostname, avg_cur_1h, avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
		(select servers.ip from servers where {metrics} = 1 ) as ip,

		(select servers.ip, servers.hostname as hostname from servers left join {metrics} as metr on servers.ip = metr.serv where servers.{metrics} = 1 {groups}) as hostname,

		(select servers.ip,round(avg(metr.conn), 1) as avg_cur_1h from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as avg_cur_1h,

		(select servers.ip,round(avg(metr.conn), 1) as avg_cur_24h from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as avg_cur_24h,

		(select servers.ip,round(avg(metr.conn), 1) as avg_cur_3d from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as avg_cur_3d,

		(select servers.ip,max(metr.conn) as max_con_1h from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-1 hours', 'localtime')
		group by servers.ip)   as max_con_1h,

		(select servers.ip,max(metr.conn) as max_con_24h from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-24 hours', 'localtime')
		group by servers.ip) as max_con_24h,

		(select servers.ip,max(metr.conn) as max_con_3d from servers
		left join {metrics} as metr on metr.serv = servers.ip
		where servers.{metrics} = 1 and
		metr.date <= datetime('now', 'localtime') and metr.date >= datetime('now', '-3 days', 'localtime')
		group by servers.ip ) as max_con_3d

		where ip.ip=hostname.ip
		and ip.ip=avg_cur_1h.ip
		and ip.ip=avg_cur_24h.ip
		and ip.ip=avg_cur_3d.ip
		and ip.ip=max_con_1h.ip
		and ip.ip=max_con_24h.ip
		and ip.ip=max_con_3d.ip

		group by hostname.ip """.format(metrics=metrics_table, groups=groups)

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()
