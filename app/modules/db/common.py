import os
import sys
import traceback

from flask import request

from app.modules.db.db_model import Setting


def out_error(error):
	error = str(error)
	exc_type, exc_obj, exc_tb = sys.exc_info()
	file_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	stk = traceback.extract_tb(exc_tb, 1)
	function_name = stk[0][2]
	error = f'{error} in function: {function_name} in file: {file_name}'
	raise Exception(f'error: {error}')


def get_setting(param, **kwargs):
	user_group_id = ''
	try:
		user_group_id = request.cookies.get('group')
	except Exception:
		pass
	if user_group_id == '' or user_group_id is None or param == 'proxy':
		user_group_id = 1

	if kwargs.get('all'):
		query = Setting.select().where(Setting.group == user_group_id).order_by(Setting.section.desc())
	else:
		query = Setting.select().where((Setting.param == param) & (Setting.group == user_group_id))

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		if kwargs.get('all'):
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
