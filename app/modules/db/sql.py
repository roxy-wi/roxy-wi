from flask import g

from app.modules.db.db_model import GeoipCodes, Setting, Role
from app.modules.db.common import out_error


def get_setting(param, **kwargs):
	if kwargs.get('group_id'):
		user_group_id = kwargs.get('group_id')
	else:
		try:
			user_group_id = g.user_params['group_id']
		except Exception:
			user_group_id = 1

	if kwargs.get('all') and not kwargs.get('section'):
		query = Setting.select().where(Setting.group_id == user_group_id).order_by(Setting.section.desc())
	elif kwargs.get('section'):
		query = Setting.select().where((Setting.group_id == user_group_id) & (Setting.section == kwargs.get('section')))
	else:
		query = Setting.select().where((Setting.param == param) & (Setting.group_id == user_group_id))

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		if kwargs.get('all') or kwargs.get('section'):
			return query_res
		else:
			for setting in query_res:
				if param in (
					'nginx_stats_port', 'session_ttl', 'token_ttl', 'haproxy_stats_port', 'haproxy_sock_port', 'ldap_type',
					'ldap_port', 'ldap_enable', 'log_time_storage', 'syslog_server_enable', 'checker_check_interval', 'port_scan_interval',
					'smon_keep_history_range', 'checker_keep_history_range', 'portscanner_keep_history_range', 'checker_maxconn_threshold',
					'apache_stats_port', 'smon_ssl_expire_warning_alert', 'smon_ssl_expire_critical_alert', 'action_keep_history_range'
				):
					return int(setting.value)
				else:
					return setting.value


def update_setting(param: str, val: str, user_group: int) -> None:
	query = Setting.update(value=val).where((Setting.param == param) & (Setting.group_id == user_group))
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_roles():
	query = Role.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_geoip_country_codes():
	query = GeoipCodes.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res
