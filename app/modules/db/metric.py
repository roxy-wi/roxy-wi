from typing import Literal
from datetime import datetime, timedelta

from peewee import fn

from app.modules.db.db_model import mysql_enable, Metrics, MetricsHttpStatus, Server, NginxMetrics, ApacheMetrics, WafMetrics
from app.modules.db.common import out_error
import app.modules.roxy_wi_tools as roxy_wi_tools

MODELS = {
	'haproxy': Metrics,
	'nginx': NginxMetrics,
	'apache': ApacheMetrics,
	'http': MetricsHttpStatus,
	'waf': WafMetrics
}


def insert_service_metrics(service: Literal['haproxy', 'nginx', 'apache', 'waf', 'http'], **kwargs):
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular')
	kwargs['date'] = cur_date
	model = MODELS[service]
	try:
		model.insert(**kwargs).execute()
	except Exception as e:
		out_error(e)


def delete_service_metrics(service: Literal['haproxy', 'http', 'waf', 'nginx', 'apache']) -> None:
	get_date = roxy_wi_tools.GetDate()
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	model = MODELS[service]
	try:
		model.delete().where(model.date < cur_date).execute()
	except Exception as e:
		out_error(e)


def select_metrics(serv, service, **kwargs):
	try:
		# Map service to the appropriate model
		if service in ('nginx', 'apache', 'waf'):
			if service == 'nginx':
				model = NginxMetrics
			elif service == 'apache':
				model = ApacheMetrics
			else:  # waf
				model = WafMetrics
		elif service == 'http_metrics':
			model = MetricsHttpStatus
		else:
			model = Metrics

		# Get time range from kwargs
		time_range = kwargs.get('time_range', '30')  # Default to 30 minutes if not specified

		# Create a base query
		query = model.select().where(model.serv == serv)

		# Add time-based filtering
		now = datetime.utcnow()

		if time_range == '1':
			# Last 1 minute
			query = query.where(model.date >= now - timedelta(minutes=1))
		elif time_range == '60':
			# Last 60 minutes
			query = query.where(model.date >= now - timedelta(minutes=60))
		elif time_range == '180':
			# Last 180 minutes
			query = query.where(model.date >= now - timedelta(minutes=180))
		elif time_range == '360':
			# Last 360 minutes
			query = query.where(model.date >= now - timedelta(minutes=360))
		elif time_range == '720':
			# Last 720 minutes
			query = query.where(model.date >= now - timedelta(minutes=720))
		else:
			# Default: last 30 minutes
			query = query.where(model.date >= now - timedelta(minutes=30))

		# Order by date
		query = query.order_by(model.date.asc())
		# For longer time ranges, we can sample the data to reduce the number of points
		# This is similar to the original SQL's "group by `date` div X" or "rowid % X = 0"
		if mysql_enable == '1' and time_range not in ('1', '30'):
			# For MySQL, we can use the SQL function to sample data
			from peewee import fn
			sampling_rates = {
				'60': 100,
				'180': 200,
				'360': 300,
				'720': 500
			}
			if time_range in sampling_rates:
				# Group by date div X to reduce data points
				query = model.select().where(
					(model.serv == serv) & 
					(model.date >= now - timedelta(minutes=int(time_range)))
				).group_by(fn.DIV(model.date, sampling_rates[time_range])).order_by(model.date.asc())
		elif not mysql_enable == '1' and time_range not in ('1', '30'):
			# For SQLite, we need to fetch all data and then sample it in Python
			# This is less efficient but maintains compatibility
			results = list(query.dicts())
			sampling_rates = {
				'60': 2,
				'180': 5,
				'360': 7,
				'720': 9
			}
			if time_range in sampling_rates:
				# Sample data by taking every Nth row
				return [results[i] for i in range(len(results)) if i % sampling_rates[time_range] == 0]

		# Execute query and return results as dictionaries
		return list(query.dicts())

	except Exception as e:
		out_error(e)
		return []


def select_servers_metrics_for_master(group_id: int):
	query = Server.select(Server.ip).where(
		((Server.haproxy_metrics == 1) | (Server.nginx_metrics == 1) | (Server.apache_metrics == 1))
		& (Server.group_id == group_id)
	)

	try:
		return query.execute()
	except Exception as e:
		out_error(e)


def select_metrics_enabled(service: Literal['haproxy', 'nginx', 'apache']):
	query_where = {
		'haproxy': ((Server.haproxy_metrics == 1) & (Server.haproxy == 1)),
		'nginx': ((Server.nginx_metrics == 1) & (Server.nginx == 1)),
		'apache': ((Server.apache_metrics == 1) & (Server.apache == 1)),
	}
	try:
		return Server.select(Server.ip).where(query_where[service] & (Server.enabled == 1)).execute()
	except Exception as e:
		out_error(e)


def select_table_metrics(group_id):
	try:
		# Get current time
		now = datetime.now()

		# Define time ranges
		one_hour_ago = now - timedelta(hours=1)
		one_day_ago = now - timedelta(hours=24)
		three_days_ago = now - timedelta(days=3)

		# Get servers with haproxy metrics enabled
		server_query = Server.select(Server.ip, Server.hostname).where(
			(Server.haproxy_metrics == 1) & 
			(Server.enabled == 1)
		)

		# Apply group filter if not admin group
		if group_id != 1:
			server_query = server_query.where(Server.group_id == group_id)

		# Get list of server IPs
		servers = list(server_query.execute())
		if not servers:
			return []

		server_ips = [server.ip for server in servers]

		# Create a dictionary to store results
		results = {}
		for server in servers:
			results[server.ip] = {
				'ip': server.ip,
				'hostname': server.hostname,
				'avg_sess_1h': 0,
				'avg_sess_24h': 0,
				'avg_sess_3d': 0,
				'max_sess_1h': 0,
				'max_sess_24h': 0,
				'max_sess_3d': 0,
				'avg_cur_1h': 0,
				'avg_cur_24h': 0,
				'avg_cur_3d': 0,
				'max_con_1h': 0,
				'max_con_24h': 0,
				'max_con_3d': 0
			}

		# Calculate metrics for each time range
		# 1 hour metrics
		one_hour_metrics = (Metrics
			.select(
				Metrics.serv,
				fn.ROUND(fn.AVG(Metrics.sess_rate), 1).alias('avg_sess'),
				fn.MAX(Metrics.sess_rate).alias('max_sess'),
				fn.ROUND(fn.AVG(Metrics.curr_con + Metrics.cur_ssl_con), 1).alias('avg_cur'),
				fn.MAX(Metrics.curr_con).alias('max_con')
			)
			.where(
				(Metrics.serv.in_(server_ips)) &
				(Metrics.date >= one_hour_ago) &
				(Metrics.date <= now)
			)
			.group_by(Metrics.serv)
		)

		for metric in one_hour_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_sess_1h'] = metric.avg_sess or 0
				results[metric.serv]['max_sess_1h'] = metric.max_sess or 0
				results[metric.serv]['avg_cur_1h'] = metric.avg_cur or 0
				results[metric.serv]['max_con_1h'] = metric.max_con or 0

		# 24 hour metrics
		day_metrics = (Metrics
			.select(
				Metrics.serv,
				fn.ROUND(fn.AVG(Metrics.sess_rate), 1).alias('avg_sess'),
				fn.MAX(Metrics.sess_rate).alias('max_sess'),
				fn.ROUND(fn.AVG(Metrics.curr_con + Metrics.cur_ssl_con), 1).alias('avg_cur'),
				fn.MAX(Metrics.curr_con).alias('max_con')
			)
			.where(
				(Metrics.serv.in_(server_ips)) &
				(Metrics.date >= one_day_ago) &
				(Metrics.date <= now)
			)
			.group_by(Metrics.serv)
		)

		for metric in day_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_sess_24h'] = metric.avg_sess or 0
				results[metric.serv]['max_sess_24h'] = metric.max_sess or 0
				results[metric.serv]['avg_cur_24h'] = metric.avg_cur or 0
				results[metric.serv]['max_con_24h'] = metric.max_con or 0

		# 3 day metrics
		three_day_metrics = (Metrics
			.select(
				Metrics.serv,
				fn.ROUND(fn.AVG(Metrics.sess_rate), 1).alias('avg_sess'),
				fn.MAX(Metrics.sess_rate).alias('max_sess'),
				fn.ROUND(fn.AVG(Metrics.curr_con + Metrics.cur_ssl_con), 1).alias('avg_cur'),
				fn.MAX(Metrics.curr_con).alias('max_con')
			)
			.where(
				(Metrics.serv.in_(server_ips)) &
				(Metrics.date >= three_days_ago) &
				(Metrics.date <= now)
			)
			.group_by(Metrics.serv)
		)

		for metric in three_day_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_sess_3d'] = metric.avg_sess or 0
				results[metric.serv]['max_sess_3d'] = metric.max_sess or 0
				results[metric.serv]['avg_cur_3d'] = metric.avg_cur or 0
				results[metric.serv]['max_con_3d'] = metric.max_con or 0

		# Convert dictionary to list of dictionaries
		return list(results.values())

	except Exception as e:
		out_error(e)
		return []


def select_service_table_metrics(service: str, group_id: int):
	try:
		# Map service to the appropriate model
		if service == 'nginx':
			model = NginxMetrics
			metrics_field = Server.nginx_metrics
		elif service == 'apache':
			model = ApacheMetrics
			metrics_field = Server.apache_metrics
		else:
			return []  # Unsupported service

		# Get current time
		now = datetime.now()

		# Define time ranges
		one_hour_ago = now - timedelta(hours=1)
		one_day_ago = now - timedelta(hours=24)
		three_days_ago = now - timedelta(days=3)

		# Get servers with service metrics enabled
		server_query = Server.select(Server.ip, Server.hostname).where(
			(metrics_field == 1) & 
			(Server.enabled == 1)
		)

		# Apply group filter if not admin group
		if group_id != 1:
			server_query = server_query.where(Server.group_id == group_id)

		# Get list of server IPs
		servers = list(server_query.execute())
		if not servers:
			return []

		server_ips = [server.ip for server in servers]

		# Create a dictionary to store results
		results = {}
		for server in servers:
			results[server.ip] = {
				'ip': server.ip,
				'hostname': server.hostname,
				'avg_cur_1h': 0,
				'avg_cur_24h': 0,
				'avg_cur_3d': 0,
				'max_con_1h': 0,
				'max_con_24h': 0,
				'max_con_3d': 0
			}

		# Calculate metrics for each time range
		# 1 hour metrics
		one_hour_metrics = (model
			.select(
				model.serv,
				fn.ROUND(fn.AVG(model.conn), 1).alias('avg_cur'),
				fn.MAX(model.conn).alias('max_con')
			)
			.where(
				(model.serv.in_(server_ips)) &
				(model.date >= one_hour_ago) &
				(model.date <= now)
			)
			.group_by(model.serv)
		)

		for metric in one_hour_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_cur_1h'] = metric.avg_cur or 0
				results[metric.serv]['max_con_1h'] = metric.max_con or 0

		# 24 hour metrics
		day_metrics = (model
			.select(
				model.serv,
				fn.ROUND(fn.AVG(model.conn), 1).alias('avg_cur'),
				fn.MAX(model.conn).alias('max_con')
			)
			.where(
				(model.serv.in_(server_ips)) &
				(model.date >= one_day_ago) &
				(model.date <= now)
			)
			.group_by(model.serv)
		)

		for metric in day_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_cur_24h'] = metric.avg_cur or 0
				results[metric.serv]['max_con_24h'] = metric.max_con or 0

		# 3 day metrics
		three_day_metrics = (model
			.select(
				model.serv,
				fn.ROUND(fn.AVG(model.conn), 1).alias('avg_cur'),
				fn.MAX(model.conn).alias('max_con')
			)
			.where(
				(model.serv.in_(server_ips)) &
				(model.date >= three_days_ago) &
				(model.date <= now)
			)
			.group_by(model.serv)
		)

		for metric in three_day_metrics:
			if metric.serv in results:
				results[metric.serv]['avg_cur_3d'] = metric.avg_cur or 0
				results[metric.serv]['max_con_3d'] = metric.max_con or 0

		# Convert dictionary to list of dictionaries
		return list(results.values())

	except Exception as e:
		out_error(e)
		return []
