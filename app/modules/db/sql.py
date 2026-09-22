import os
import re

from flask import g

from app.modules.common.execution_context import group_id as execution_group_id

from app.modules.db.db_model import GeoipCodes, Setting, Role
from app.modules.db.common import out_error
from app.modules.roxy_wi_tools import GetConfigVar


_INTEGER_SETTINGS = {
	'nginx_stats_port', 'session_ttl', 'token_ttl', 'haproxy_stats_port', 'haproxy_sock_port',
	'ldap_type', 'ldap_port', 'ldap_enable', 'log_time_storage', 'syslog_server_enable',
	'checker_check_interval', 'port_scan_interval', 'smon_keep_history_range',
	'checker_keep_history_range', 'portscanner_keep_history_range', 'checker_maxconn_threshold',
	'apache_stats_port', 'smon_ssl_expire_warning_alert', 'smon_ssl_expire_critical_alert',
	'action_keep_history_range',
}
_config = GetConfigVar()


def _setting_environment_name(param):
	name = re.sub(r'[^A-Za-z0-9]+', '_', str(param)).strip('_').upper()
	return f'ROXYWI_{name}'


def _coerce_setting(param, value):
	if value is not None and param in _INTEGER_SETTINGS:
		return int(value)
	return value


def get_setting(param, **kwargs):
	if kwargs.get('group_id'):
		user_group_id = kwargs.get('group_id')
	elif execution_group_id.get() is not None:
		user_group_id = execution_group_id.get()
	else:
		try:
			user_group_id = g.user_params['group_id']
		except Exception:
			user_group_id = 1

	if not kwargs.get('all') and not kwargs.get('section'):
		environment_name = _setting_environment_name(param)
		if environment_name in os.environ:
			return _coerce_setting(param, os.environ[environment_name])

	if kwargs.get('all') and not kwargs.get('section'):
		query = Setting.select().where(Setting.group_id == user_group_id).order_by(Setting.section.desc())
	elif kwargs.get('section'):
		query = Setting.select().where((Setting.group_id == user_group_id) & (Setting.section == kwargs.get('section')))
	else:
		query = Setting.select().where((Setting.param == param) & (Setting.group_id == user_group_id))

	fallback_section = None
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		if kwargs.get('all') or kwargs.get('section'):
			return query_res
		else:
			for setting in query_res:
				fallback_section = setting.section
				if setting.value is not None:
					return _coerce_setting(param, setting.value)

	if fallback_section:
		fallback = _config.get_config_var(fallback_section, param)
	else:
		fallback = _config.find_config_var(param)
	return _coerce_setting(param, fallback)


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
