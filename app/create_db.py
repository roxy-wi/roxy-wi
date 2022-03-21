#!/usr/bin/env python3
import distro
from sql import out_error
from db_model import *
from funct import check_ver


def default_values():
	if distro.id() == 'ubuntu':
		apache_dir = 'apache2'
	else:
		apache_dir = 'httpd'
	data_source = [
		{'param': 'time_zone', 'value': 'UTC', 'section': 'main', 'desc': 'Time Zone', 'group': '1'},
		{'param': 'proxy', 'value': '', 'section': 'main', 'desc': 'IP address and port of the proxy server. Use proto://ip:port', 'group': '1'},
		{'param': 'session_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user session (in days)',
		 'group': '1'},
		{'param': 'token_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user token (in days)',
		 'group': '1'},
		{'param': 'tmp_config_path', 'value': '/tmp/', 'section': 'main',
		 'desc': 'Path to the temporary directory. A valid path should be specified as the value of this parameter. The directory must be owned by the user specified in SSH settings',
		 'group': '1'},
		{'param': 'cert_path', 'value': '/etc/ssl/certs/', 'section': 'main',
		 'desc': 'Path to SSL dir. Folder owner must be a user which set in the SSH settings. Path must exist',
		 'group': '1'},
		{'param': 'ssl_local_path', 'value': 'certs', 'section': 'main',
		 'desc': 'Path to the directory with the saved local SSL certificates. The value of this parameter is specified as a relative path beginning with $HOME_ROXY_WI/app/',
		 'group': '1'},
		{'param': 'lists_path', 'value': 'lists', 'section': 'main',
		 'desc': 'Path to the black and the wild list. The value of this paramer should be specified as a relative path beginning with $HOME_ROXY-WI',
		 'group': '1'},
		{'param': 'haproxy_path_logs', 'value': '/var/log/haproxy/', 'section': 'haproxy',
		 'desc': 'The path for HAProxy logs', 'group': '1'},
		{'param': 'syslog_server_enable', 'value': '0', 'section': 'logs',
		 'desc': 'Enable getting logs from a syslog server; (0 - no, 1 - yes)', 'group': '1'},
		{'param': 'syslog_server', 'value': '', 'section': 'logs', 'desc': 'IP address of the syslog_server',
		 'group': '1'},
		{'param': 'log_time_storage', 'value': '14', 'section': 'logs',
		 'desc': 'Retention period for user activity logs (in days)', 'group': '1'},
		{'param': 'stats_user', 'value': 'admin', 'section': 'haproxy', 'desc': 'Username for accessing HAProxy stats page',
		 'group': '1'},
		{'param': 'stats_password', 'value': 'password', 'section': 'haproxy',
		 'desc': 'Password for accessing HAProxy stats page', 'group': '1'},
		{'param': 'stats_port', 'value': '8085', 'section': 'haproxy', 'desc': 'Port for HAProxy stats page',
		 'group': '1'},
		{'param': 'stats_page', 'value': 'stats', 'section': 'haproxy', 'desc': 'URI for HAProxy stats page',
		 'group': '1'},
		{'param': 'haproxy_dir', 'value': '/etc/haproxy', 'section': 'haproxy', 'desc': 'Path to the HAProxy directory',
		 'group': '1'},
		{'param': 'haproxy_config_path', 'value': '/etc/haproxy/haproxy.cfg', 'section': 'haproxy', 'desc': 'Path to the HAProxy configuration file',
		 'group': '1'},
		{'param': 'server_state_file', 'value': '/etc/haproxy/haproxy.state', 'section': 'haproxy', 'desc': 'Path to the HAProxy state file',
		 'group': '1'},
		{'param': 'haproxy_sock', 'value': '/var/run/haproxy.sock', 'section': 'haproxy',
		 'desc': 'Socket port for HAProxy', 'group': '1'},
		{'param': 'haproxy_sock_port', 'value': '1999', 'section': 'haproxy', 'desc': 'HAProxy sock port',
		 'group': '1'},
		{'param': 'apache_log_path', 'value': '/var/log/'+apache_dir+'/', 'section': 'logs', 'desc': 'Path to Apache logs',
		 'group': '1'},
		{'param': 'nginx_path_logs', 'value': '/var/log/nginx/', 'section': 'nginx',
		 'desc': 'The path for Nginx logs', 'group': '1'},
		{'param': 'nginx_stats_user', 'value': 'admin', 'section': 'nginx', 'desc': 'Username for accessing Nginx stats page',
		 'group': '1'},
		{'param': 'nginx_stats_password', 'value': 'password', 'section': 'nginx',
		 'desc': 'Password for Stats web page Ngin', 'group': '1'},
		{'param': 'nginx_stats_port', 'value': '8086', 'section': 'nginx', 'desc': 'Stats port for web page Nginx',
		 'group': '1'},
		{'param': 'nginx_stats_page', 'value': 'stats', 'section': 'nginx', 'desc': 'URI Stats for web page Nginx',
		 'group': '1'},
		{'param': 'nginx_dir', 'value': '/etc/nginx/conf.d/', 'section': 'nginx',
		 'desc': 'Path to the Nginx directory with config files', 'group': '1'},
		{'param': 'nginx_config_path', 'value': '/etc/nginx/nginx.conf', 'section': 'nginx',
		 'desc': 'Path to the main Nginx configuration file', 'group': '1'},
		{'param': 'ldap_enable', 'value': '0', 'section': 'ldap', 'desc': 'Enable LDAP (1 - yes, 0 - no)',
		 'group': '1'},
		{'param': 'ldap_server', 'value': '', 'section': 'ldap', 'desc': 'IP address of the LDAP server', 'group': '1'},
		{'param': 'ldap_port', 'value': '389', 'section': 'ldap', 'desc': 'LDAP port (port 389 or 636 is used by default)',
		 'group': '1'},
		{'param': 'ldap_user', 'value': '', 'section': 'ldap',
		 'desc': 'LDAP username. Format: user@domain.com', 'group': '1'},
		{'param': 'ldap_password', 'value': '', 'section': 'ldap', 'desc': 'LDAP password', 'group': '1'},
		{'param': 'ldap_base', 'value': '', 'section': 'ldap', 'desc': 'Base domain. Example: dc=domain, dc=com',
		 'group': '1'},
		{'param': 'ldap_domain', 'value': '', 'section': 'ldap', 'desc': 'LDAP domain for logging in', 'group': '1'},
		{'param': 'ldap_class_search', 'value': 'user', 'section': 'ldap', 'desc': 'Class for searching the user',
		 'group': '1'},
		{'param': 'ldap_user_attribute', 'value': 'sAMAccountName', 'section': 'ldap',
		 'desc': 'Attribute to search users by', 'group': '1'},
		{'param': 'ldap_search_field', 'value': 'mail', 'section': 'ldap', 'desc': 'User\'s email address', 'group': '1'},
		{'param': 'ldap_type', 'value': '0', 'section': 'ldap', 'desc': 'Use LDAPS (1 - yes, 0 - no)', 'group': '1'},
		{'param': 'rabbitmq_host', 'value': '127.0.0.1', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server host', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_vhost', 'value': '/', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server vhost', 'group': '1'},
		{'param': 'rabbitmq_queue', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server queue', 'group': '1'},
		{'param': 'rabbitmq_user', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user', 'group': '1'},
		{'param': 'rabbitmq_password', 'value': 'roxy-wi123', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user password', 'group': '1'},
	]
	try:
		Setting.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		out_error(e)

	data_source = [
		{'username': 'admin', 'email': 'admin@localhost', 'password': '21232f297a57a5a743894a0e4a801fc3', 'role': 'superAdmin', 'groups': '1'},
		{'username': 'editor', 'email': 'editor@localhost', 'password': '5aee9dbd2a188839105073571bee1b1f', 'role': 'admin', 'groups': '1'},
		{'username': 'guest', 'email': 'guest@localhost', 'password': '084e0343a0486ff05530df6c705c8bb4', 'role': 'guest', 'groups': '1'}
	]

	try:
		User.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		out_error(e)

	data_source = [
		{'name': 'superAdmin', 'description': 'Has the highest level of administrative permissions and controls the actions of all other users'},
		{'name': 'admin', 'description': 'Has access everywhere except the Admin area'},
		{'name': 'editor', 'description': 'Has the same rights as the admin but has no access to the Servers page'},
		{'name': 'guest', 'description': 'Read-only access'}
	]

	try:
		Role.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		out_error(e)

	try:
		Groups.insert(name='All', description='All servers are included in this group by default').on_conflict_ignore().execute()
	except Exception as e:
		out_error(e)


def update_db_v_3_4_5_22():
	try:
		Version.insert(version='3.4.5.2').execute()
	except Exception as e:
		print('Cannot insert version %s' % e)


def update_db_v_5_1_2(**kwargs):
	data_source = [
		{'param': 'smon_keep_history_range', 'value': '14', 'section': 'monitoring',
		 'desc': 'Retention period for SMON history', 'group': '1'},
		{'param': 'checker_keep_history_range', 'value': '14', 'section': 'monitoring',
		 'desc': 'Retention period for Checker history', 'group': '1'}
	]

	try:
		Setting.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'columns param, group are not unique':
				pass
			else:
				print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.1.2')


def update_db_v_5_1_3(**kwargs):
	cursor = conn.cursor()
	sql = """ALTER TABLE `servers` ADD COLUMN protected INTEGER NOT NULL DEFAULT 0;"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'duplicate column name: protected' or str(e) == '(1060, "Duplicate column name \'protected\'")':
				print('Updating... DB has been updated to version 5.1.3')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to version 5.1.3")



def update_db_v_5_2_0(**kwargs):
	try:
		Setting.insert(param='portscanner_keep_history_range', value=14, section='monitoring',
					   desc='Retention period for Port scanner history').execute()
	except Exception as e:
		if kwargs.get('silent') != 1:
			if (
					str(e) == 'columns param, group are not unique' or
					str(e) == '(1062, "Duplicate entry \'portscanner_keep_history_range-1\' for key \'param\'")' or
					str(e) == 'UNIQUE constraint failed: settings.param, settings.group'
			):
				pass
			else:
				print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.2.0')


def update_db_v_5_2_4(**kwargs):
	cursor = conn.cursor()
	sql = """ALTER TABLE `user` ADD COLUMN user_services varchar(20) DEFAULT '1 2 3 4';"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'duplicate column name: user_services' or str(e) == '(1060, "Duplicate column name \'user_services\'")':
				print('Updating... DB has been updated to version 5.2.4')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.2.4")


def update_db_v_5_2_4_1(**kwargs):
	cursor = conn.cursor()
	sql = """ALTER TABLE `servers` ADD COLUMN nginx_metrics integer DEFAULT 0;"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'duplicate column name: nginx_metrics' or str(e) == '(1060, "Duplicate column name \'nginx_metrics\'")':
				print('Updating... DB has been updated to version 5.2.4-1')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.2.4-1")


def update_db_v_5_2_5(**kwargs):
	query = Role.update(name='user').where(Role.name == 'editor')
	try:
		query.execute()
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'column name is not unique' or str(e) == '(1060, "column name is not unique")':
				print('Updating... DB has been updated to version 5.2.5-1')
			else:
				print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.2.5")


def update_db_v_5_2_5_1(**kwargs):
	query = User.update(role='user').where(User.role == 'editor')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.2.5-1")


def update_db_v_5_2_5_2(**kwargs):
	query = Role.delete().where(Role.name == 'editor')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.2.5-2")


def update_db_v_5_2_5_3(**kwargs):
	cursor = conn.cursor()
	sql = list()
	sql.append("alter table user add column last_login_date timestamp default '0000-00-00 00:00:00'")
	sql.append("alter table user add column last_login_ip VARCHAR ( 64 )")
	for i in sql:
		try:
			cursor.execute(i)
		except:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.2.5-3')


def update_db_v_5_2_6(**kwargs):
	query = Setting.delete().where(Setting.param == 'haproxy_enterprise')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.2.6")


def update_db_v_5_3_0(**kwargs):
	groups = ''
	query = Groups.select()

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		groups = query_res

	for g in groups:
		try:
			data_source = [
				{'param': 'nginx_container_name', 'value': 'nginx', 'section': 'nginx',
				 'desc': 'Docker container name for Nginx service',
				 'group': g.group_id},
				{'param': 'haproxy_container_name', 'value': 'haproxy', 'section': 'haproxy',
				 'desc': 'Docker container name for HAProxy service',
				 'group': g.group_id},
			]

			try:
				Setting.insert_many(data_source).on_conflict_ignore().execute()
			except Exception as e:
				if kwargs.get('silent') != 1:
					if str(e) == 'columns param, group are not unique':
						pass
					else:
						print("An error occurred:", e)
		except Exception as e:
			if kwargs.get('silent') != 1:
				if (
						str(e) == 'columns param, group are not unique' or
						str(e) == '(1062, "Duplicate entry \'nginx_container_name\' for key \'param\'")' or
						str(e) == 'UNIQUE constraint failed: settings.param, settings.group'
				):
					pass
				else:
					print("An error occurred:", e)


def update_db_v_5_3_1(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN keepalived_active INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: keepalived_active' or str(e) == '(1060, "Duplicate column name \'keepalived_active\'")':
				print('Updating... DB has been updated to version 5.3.1')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.3.1")



def update_db_v_5_3_2(**kwargs):
	try:
		Setting.insert(param='checker_maxconn_threshold', value=90, section='monitoring',
					   desc='Threshold value for alerting, in %').execute()
	except Exception as e:
		if kwargs.get('silent') != 1:
			if (
					str(e) == 'columns param, group are not unique' or
					str(e) == '(1062, "Duplicate entry \'checker_maxconn_threshold-1\' for key \'param\'")' or
					str(e) == 'UNIQUE constraint failed: settings.param, settings.group'
			):
				pass
			else:
				print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.3.2')



def update_db_v_5_3_2_2(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN keepalived_alert INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: keepalived_alert' or str(e) == '(1060, "Duplicate column name \'keepalived_alert\'")':
				print('Updating... DB has been updated to version 5.3.2')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.3.2")


def update_db_v_5_4_2(**kwargs):
	cursor = conn.cursor()
	sql = """ALTER TABLE `smon` ADD COLUMN slack_channel_id integer DEFAULT '0';"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if str(e) == 'duplicate column name: slack_channel_id' or str(e) == '(1060, "Duplicate column name \'slack_channel_id\'")':
				print('Updating... DB has been updated to version 5.4.2')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.4.2")


def update_db_v_5_4_3(**kwargs):
	query = Setting.update(param='nginx_path_logs', value='/var/log/nginx/').where(Setting.param == 'nginx_path_error_logs')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.4.3")


def update_db_v_5_4_3_1(**kwargs):
	query = Setting.update( value='/etc/nginx/').where(Setting.param == 'nginx_dir')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.4.3-1")


def update_ver():
	query = Version.update(version='5.5.0.0')
	try:
		query.execute()
	except:
		print('Cannot update version')


def update_all():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_5_1_2()
	update_db_v_5_1_3()
	update_db_v_5_2_0()
	update_db_v_5_2_4()
	update_db_v_5_2_4_1()
	update_db_v_5_2_5()
	update_db_v_5_2_5_1()
	update_db_v_5_2_5_2()
	update_db_v_5_2_5_3()
	update_db_v_5_2_6()
	update_db_v_5_3_0()
	update_db_v_5_3_1()
	update_db_v_5_3_2()
	update_db_v_5_3_2_2()
	update_db_v_5_4_2()
	update_db_v_5_4_3()
	update_db_v_5_4_3_1()
	update_ver()


def update_all_silent():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_5_1_2(silent=1)
	update_db_v_5_1_3(silent=1)
	update_db_v_5_2_0(silent=1)
	update_db_v_5_2_4(silent=1)
	update_db_v_5_2_4_1(silent=1)
	update_db_v_5_2_5(silent=1)
	update_db_v_5_2_5_1(silent=1)
	update_db_v_5_2_5_2(silent=1)
	update_db_v_5_2_5_3(silent=1)
	update_db_v_5_2_6(silent=1)
	update_db_v_5_3_0(silent=1)
	update_db_v_5_3_1(silent=1)
	update_db_v_5_3_2(silent=1)
	update_db_v_5_3_2_2(silent=1)
	update_db_v_5_4_2(silent=1)
	update_db_v_5_4_3(silent=1)
	update_db_v_5_4_3_1(silent=1)
	update_ver()


if __name__ == "__main__":
	create_tables()
	default_values()
	update_all()
