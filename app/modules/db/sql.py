#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import traceback
import sys
import os

from modules.db.db_model import *
import modules.roxy_wi_tools as roxy_wi_tools


def get_setting(param, **kwargs):
	import http.cookies

	user_group = ''
	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_group_id = cookie.get('group')
		user_group_id1 = user_group_id.value
		groups = sql.select_groups(id=user_group_id1)
		for g in groups:
			if g.group_id == int(user_group_id1):
				if kwargs.get('id'):
					user_group = g.group_id
				else:
					user_group = g.name
	except Exception:
		pass

	if user_group == '' or param in ('proxy'):
		user_group = 1

	if kwargs.get('all'):
		query = Setting.select().where(Setting.group == user_group).order_by(Setting.section.desc())
	else:
		query = Setting.select().where((Setting.param == param) & (Setting.group == user_group))

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
					'nginx_stats_port', 'session_ttl', 'token_ttl', 'stats_port', 'haproxy_sock_port', 'ldap_type',
					'ldap_port', 'ldap_enable', 'log_time_storage', 'syslog_server_enable', 'smon_check_interval',
					'checker_check_interval', 'port_scan_interval', 'smon_keep_history_range', 'checker_keep_history_range',
					'portscanner_keep_history_range', 'checker_maxconn_threshold', 'apache_stats_port', 'smon_ssl_expire_warning_alert',
					'smon_ssl_expire_critical_alert', 'action_keep_history_range'
				):
					return int(setting.value)
				else:
					return setting.value


time_zone = get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


def out_error(error):
	error = str(error)
	exc_type, exc_obj, exc_tb = sys.exc_info()
	file_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	stk = traceback.extract_tb(exc_tb, 1)
	function_name = stk[0][2]
	error = f'{error} in function: {function_name} in file: {file_name}'
	raise Exception(f'error: {error}')


def add_user(user, email, password, role, activeuser, group):
	if password != 'aduser':
		try:
			hashed_pass = roxy_wi_tools.Tools.get_hash(password)
			last_id = User.insert(
				username=user, email=email, password=hashed_pass, role=role, activeuser=activeuser, groups=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id
	else:
		try:
			last_id = User.insert(
				username=user, email=email, role=role, ldap_user=1, activeuser=activeuser, groups=group
			).execute()
		except Exception as e:
			out_error(e)
		else:
			return last_id


def update_user(user, email, role, user_id, activeuser):
	user_update = User.update(username=user, email=email, role=role, activeuser=activeuser).where(User.user_id == user_id)
	try:
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_from_admin_area(user, email, user_id, activeuser):
	user_update = User.update(username=user, email=email, activeuser=activeuser).where(User.user_id == user_id)
	try:
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_user_groups(user_id):
	group_for_delete = UserGroups.delete().where(UserGroups.user_id == user_id)
	try:
		group_for_delete.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_current_groups(groups, user_uuid):
	user_id = get_user_id_by_uuid(user_uuid)
	try:
		user_update = User.update(groups=groups).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_password(password, user_id):
	try:
		hashed_pass = roxy_wi_tools.Tools.get_hash(password)
		user_update = User.update(password=hashed_pass).where(User.user_id == user_id)
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_user(user_id):
	try:
		user_for_delete = User.delete().where(User.user_id == user_id)
		user_for_delete.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def add_group(name, description):
	try:
		last_insert = Groups.insert(name=name, description=description)
		last_insert_id = last_insert.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		add_setting_for_new_group(last_insert_id)
		return True


def add_setting_for_new_group(group_id):
	group_id = str(group_id)
	data_source = [
		{'param': 'time_zone', 'value': 'UTC', 'section': 'main', 'desc': 'Time Zone', 'group': group_id},
		{'param': 'proxy', 'value': '', 'section': 'main',
			'desc': 'IP address and port of the proxy server . Use proto://ip:port', 'group': group_id},
		{'param': 'session_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user session (in days)', 'group': group_id},
		{'param': 'token_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user token (in days)', 'group': group_id},
		{'param': 'tmp_config_path', 'value': '/tmp/', 'section': 'main',
			'desc': 'Path to the temporary directory. A valid path should be specified as the value of this parameter. '
					'The directory must be owned by the user specified in SSH settings', 'group': group_id},
		{'param': 'cert_path', 'value': '/etc/ssl/certs/', 'section': 'main',
			'desc': 'Path to SSL dir. Folder owner must be a user which set in the SSH settings. The path must be valid', 'group': group_id},
		{'param': 'haproxy_path_logs', 'value': '/var/log/haproxy/', 'section': 'haproxy',
			'desc': 'The default local path for saving logs', 'group': group_id},
		{'param': 'syslog_server_enable', 'value': '0', 'section': 'logs',
			'desc': 'Enable getting logs from a syslog server; (0 - no, 1 - yes)', 'group': group_id},
		{'param': 'syslog_server', 'value': '', 'section': 'logs', 'desc': 'IP address of the syslog_server', 'group': group_id},
		{'param': 'stats_user', 'value': 'admin', 'section': 'haproxy',
			'desc': 'Username for accessing HAProxy stats page', 'group': group_id},
		{'param': 'stats_password', 'value': 'password', 'section': 'haproxy',
			'desc': 'Password for accessing HAProxy stats page', 'group': group_id},
		{'param': 'stats_port', 'value': '8085', 'section': 'haproxy', 'desc': 'Port for HAProxy stats page', 'group': group_id},
		{'param': 'stats_page', 'value': 'stats', 'section': 'haproxy', 'desc': 'URI for HAProxy stats page', 'group': group_id},
		{'param': 'haproxy_dir', 'value': '/etc/haproxy', 'section': 'haproxy', 'desc': 'Path to the HAProxy directory', 'group': group_id},
		{'param': 'haproxy_config_path', 'value': '/etc/haproxy/haproxy.cfg', 'section': 'haproxy', 'desc': 'Path to the HAProxy configuration file', 'group': group_id},
		{'param': 'server_state_file', 'value': '/etc/haproxy/haproxy.state', 'section': 'haproxy', 'desc': 'Path to the HAProxy state file', 'group': group_id},
		{'param': 'haproxy_sock', 'value': '/var/run/haproxy.sock', 'section': 'haproxy', 'desc': 'Path to the HAProxy sock file', 'group': group_id},
		{'param': 'haproxy_sock_port', 'value': '1999', 'section': 'haproxy', 'desc': 'Socket port for HAProxy', 'group': group_id},
		{'param': 'haproxy_container_name', 'value': 'haproxy', 'section': 'haproxy', 'desc': 'Docker container name for HAProxy service', 'group': group_id},
		{'param': 'maxmind_key', 'value': '', 'section': 'main',
			'desc': 'License key for downloading GeoIP DB. You can create it on maxmind.com', 'group': group_id},
		{'param': 'nginx_path_logs', 'value': '/var/log/nginx/', 'section': 'nginx', 'desc': 'NGINX error log', 'group': group_id},
		{'param': 'nginx_stats_user', 'value': 'admin', 'section': 'nginx', 'desc': 'Username for accessing NGINX stats page', 'group': group_id},
		{'param': 'nginx_stats_password', 'value': 'password', 'section': 'nginx', 'desc': 'Password for accessing NGINX stats page', 'group': group_id},
		{'param': 'nginx_stats_port', 'value': '8086', 'section': 'nginx', 'desc': 'Stats port for web page NGINX', 'group': group_id},
		{'param': 'nginx_stats_page', 'value': 'stats', 'section': 'nginx', 'desc': 'URI Stats for web page NGINX', 'group': group_id},
		{'param': 'nginx_dir', 'value': '/etc/nginx/', 'section': 'nginx', 'desc': 'Path to the NGINX directory with config files', 'group': group_id},
		{'param': 'nginx_config_path', 'value': '/etc/nginx/nginx.conf', 'section': 'nginx', 'desc': 'Path to the main NGINX configuration file', 'group': group_id},
		{'param': 'nginx_container_name', 'value': 'nginx', 'section': 'nginx', 'desc': 'Docker container name for NGINX service', 'group': group_id},
		{'param': 'ldap_enable', 'value': '0', 'section': 'ldap', 'desc': 'Enable LDAP', 'group': group_id},
		{'param': 'ldap_server', 'value': '', 'section': 'ldap', 'desc': 'IP address of the LDAP server', 'group': group_id},
		{'param': 'ldap_port', 'value': '389', 'section': 'ldap', 'desc': 'LDAP port (port 389 or 636 is used by default)', 'group': group_id},
		{'param': 'ldap_user', 'value': '', 'section': 'ldap', 'desc': 'LDAP username. Format: user@domain.com', 'group': group_id},
		{'param': 'ldap_password', 'value': '', 'section': 'ldap', 'desc': 'LDAP password', 'group': group_id},
		{'param': 'ldap_base', 'value': '', 'section': 'ldap', 'desc': 'Base domain. Example: dc=domain, dc=com', 'group': group_id},
		{'param': 'ldap_domain', 'value': '', 'section': 'ldap', 'desc': 'LDAP domain for logging in', 'group': group_id},
		{'param': 'ldap_class_search', 'value': 'user', 'section': 'ldap', 'desc': 'Class for searching the user', 'group': group_id},
		{'param': 'ldap_user_attribute', 'value': 'sAMAccountName', 'section': 'ldap', 'desc': 'Attribute to search users by', 'group': group_id},
		{'param': 'ldap_search_field', 'value': 'mail', 'section': 'ldap', 'desc': 'User\'s email address', 'group': group_id},
		{'param': 'ldap_type', 'value': '0', 'section': 'ldap', 'desc': 'Use LDAPS', 'group': group_id},
		{'param': 'apache_path_logs', 'value': '/var/log/httpd/', 'section': 'apache', 'desc': 'The path for Apache logs', 'group': group_id},
		{'param': 'apache_stats_user', 'value': 'admin', 'section': 'apache', 'desc': 'Username for accessing Apache stats page', 'group': group_id},
		{'param': 'apache_stats_password', 'value': 'password', 'section': 'apache', 'desc': 'Password for Apache stats webpage', 'group': group_id},
		{'param': 'apache_stats_port', 'value': '8087', 'section': 'apache', 'desc': 'Stats port for webpage Apache', 'group': group_id},
		{'param': 'apache_stats_page', 'value': 'stats', 'section': 'apache', 'desc': 'URI Stats for webpage Apache', 'group': group_id},
		{'param': 'apache_dir', 'value': '/etc/httpd/', 'section': 'apache', 'desc': 'Path to the Apache directory with config files', 'group': group_id},
		{'param': 'apache_config_path', 'value': '/etc/httpd/conf/httpd.conf', 'section': 'apache', 'desc': 'Path to the main Apache configuration file', 'group': group_id},
		{'param': 'apache_container_name', 'value': 'apache', 'section': 'apache', 'desc': 'Docker container name for Apache service', 'group': group_id},
		{'param': 'keepalived_config_path', 'value': '/etc/keepalived/keepalived.conf', 'section': 'keepalived',
			'desc': 'Path to the main Keepalived configuration file', 'group': group_id},
		{'param': 'keepalived_path_logs', 'value': '/var/log/keepalived/', 'section': 'keepalived', 'desc': 'The path for Keepalived logs', 'group': group_id},
	]

	try:
		Setting.insert_many(data_source).execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def delete_group_settings(group_id):
	try:
		group_for_delete = Setting.delete().where(Setting.group == group_id)
		group_for_delete.execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def delete_group(group_id):
	try:
		group_for_delete = Groups.delete().where(Groups.group_id == group_id)
		group_for_delete.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		delete_group_settings(group_id)
		return True


def update_group(name, descript, group_id):
	try:
		group_update = Groups.update(name=name, description=descript).where(Groups.group_id == group_id)
		group_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def add_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx, apache, firewall):
	try:
		Server.insert(
			hostname=hostname, ip=ip, groups=group, type_ip=typeip, enable=enable, master=master, cred=cred,
			port=port, desc=desc, haproxy=haproxy, nginx=nginx, apache=apache, firewall_enable=firewall
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def delete_server(server_id):
	try:
		server_for_delete = Server.delete().where(Server.server_id == server_id)
		server_for_delete.execute()
	except Exception as e:
		out_error(e)
	else:
		return True


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
			update_hapwi = Server.update(alert=alert, metrics=metrics, active=active).where(
				Server.server_id == server_id)
		update_hapwi.execute()
	except Exception as e:
		out_error(e)


def update_server(hostname, group, typeip, enable, master, server_id, cred, port, desc, firewall, protected):
	try:
		server_update = Server.update(
			hostname=hostname, groups=group, type_ip=typeip, enable=enable, master=master, cred=cred,
			port=port, desc=desc, firewall_enable=firewall, protected=protected
		).where(Server.server_id == server_id)
		server_update.execute()
	except Exception as e:
		out_error(e)


def update_server_services(server_id: str, haproxy: int, nginx: int, apache: int, keepalived: int) -> bool:
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


def update_server_master(master, slave):
	try:
		master_id = Server.get(Server.ip == master).server_id
	except Exception as e:
		out_error(e)

	try:
		Server.update(master=master_id).where(Server.ip == slave).execute()
	except Exception as e:
		out_error(e)


def select_users(**kwargs):
	if kwargs.get("user") is not None:
		query = User.select().where(User.username == kwargs.get("user"))
	elif kwargs.get("id") is not None:
		query = User.select().where(User.user_id == kwargs.get("id"))
	elif kwargs.get("group") is not None:
		cur_date = get_date.return_date('regular', timedelta_minutes_minus=15)
		query = (User.select(
			User, UserGroups, Case(
				0, [((User.last_login_date >= cur_date), 0)], 1
			).alias('last_login')
		).join(UserGroups, on=(User.user_id == UserGroups.user_id)).where(
			UserGroups.user_group_id == kwargs.get("group")
		))
	elif kwargs.get('by_group_id'):
		query = User.select().where(User.groups == kwargs.get("by_group_id"))
	else:
		cur_date = get_date.return_date('regular', timedelta_minutes_minus=15)
		query = User.select(User, Case(0, [(
			(User.last_login_date >= cur_date), 0)], 1).alias('last_login')).order_by(User.user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_user_groups(user_id, **kwargs):
	if kwargs.get("limit") is not None:
		query = UserGroups.select().where(UserGroups.user_id == user_id).limit(1)
	else:
		query = UserGroups.select().where(UserGroups.user_id == user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		if kwargs.get("limit") is not None:
			for i in query_res:
				return i.user_group_id
		else:
			return query_res


def check_user_group(user_id, group_id):
	try:
		query_res = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
	except Exception:
		return False
	else:
		if query_res.user_id != '':
			return True
		else:
			return False


def select_user_groups_with_names(user_id, **kwargs):
	if kwargs.get("all") is not None:
		query = (UserGroups.select(
			UserGroups.user_group_id, UserGroups.user_id, Groups.name
		).join(Groups, on=(UserGroups.user_group_id == Groups.group_id)))
	elif kwargs.get("user_not_in_group") is not None:
		query = (Groups.select(
			Groups.group_id, Groups.name
		).join(UserGroups, on=(
			(UserGroups.user_group_id == Groups.group_id) &
			(UserGroups.user_id == user_id)
		), join_type=JOIN.LEFT_OUTER).group_by(Groups.name).where(UserGroups.user_id.is_null(True)))
	else:
		query = (UserGroups.select(
			UserGroups.user_group_id, UserGroups.user_role_id, Groups.name, Groups.group_id
		).join(Groups, on=(UserGroups.user_group_id == Groups.group_id)).where(UserGroups.user_id == user_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_user_roles_by_group(group_id: int):
	try:
		query_res = UserGroups.select().where(UserGroups.user_group_id == group_id).execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_groups(**kwargs):
	if kwargs.get("group") is not None:
		query = Groups.select().where(Groups.name == kwargs.get('group'))
	elif kwargs.get("id") is not None:
		query = Groups.select().where(Groups.group_id == kwargs.get('id'))
	else:
		query = Groups.select().order_by(Groups.group_id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_group_name_by_id(group_id):
	try:
		group_name = Groups.get(Groups.group_id == group_id)
	except Exception as e:
		out_error(e)
	else:
		return group_name.name


def get_group_id_by_name(group_name):
	try:
		group_id = Groups.get(Groups.name == group_name)
	except Exception as e:
		out_error(e)
	else:
		return group_id.group_id


def get_group_id_by_server_ip(server_ip):
	try:
		group_id = Server.get(Server.ip == server_ip)
	except Exception as e:
		out_error(e)
	else:
		return group_id.groups


def get_cred_id_by_server_ip(server_ip):
	try:
		cred = Server.get(Server.ip == server_ip)
	except Exception as e:
		return out_error(e)
	else:
		return cred.cred


def get_hostname_by_server_ip(server_ip):
	try:
		hostname = Server.get(Server.ip == server_ip)
	except Exception as e:
		return out_error(e)
		# pass
	else:
		return hostname.hostname


def select_server_by_name(name):
	try:
		ip = Server.get(Server.hostname == name)
	except Exception as e:
		return out_error(e)
	else:
		return ip.ip


def select_server_id_by_ip(server_ip):
	try:
		server_id = Server.get(Server.ip == server_ip).server_id
	except Exception:
		return None
	else:
		return server_id


def select_server_group_by_ip(server_ip):
	try:
		groups = Server.get(Server.ip == server_ip).groups
	except Exception as e:
		return out_error(e)
	else:
		return groups


def select_server_ip_by_id(server_id):
	try:
		server_ip = Server.get(Server.server_id == server_id).ip
	except Exception as e:
		return out_error(e)
	else:
		return server_ip


def select_servers(**kwargs):
	cursor = conn.cursor()

	if mysql_enable == '1':

		sql = """select * from `servers` where `enable` = 1 ORDER BY servers.groups """

		if kwargs.get("server") is not None:
			sql = """select * from `servers` where `ip` = '{}' """.format(kwargs.get("server"))
		if kwargs.get("full") is not None:
			sql = """select * from `servers` ORDER BY hostname """
		if kwargs.get("get_master_servers") is not None:
			sql = """select id,hostname from `servers` where `master` = 0 and type_ip = 0 and enable = 1 ORDER BY servers.groups """
		if kwargs.get("get_master_servers") is not None and kwargs.get('uuid') is not None:
			sql = """ select servers.id, servers.hostname from `servers`
				left join user as user on servers.groups = user.groups
				left join uuid as uuid on user.id = uuid.user_id
				where uuid.uuid = '{}' and servers.master = 0 and servers.type_ip = 0 and servers.enable = 1 ORDER BY servers.groups
				""".format(kwargs.get('uuid'))
		if kwargs.get("id"):
			sql = """select * from `servers` where `id` = '{}' """.format(kwargs.get("id"))
		if kwargs.get("hostname"):
			sql = """select * from `servers` where `hostname` = '{}' """.format(kwargs.get("hostname"))
		if kwargs.get("id_hostname"):
			sql = """select * from `servers` where `hostname` ='{}' or id = '{}' or ip = '{}'""".format(
				kwargs.get("id_hostname"), kwargs.get("id_hostname"), kwargs.get("id_hostname"))
		if kwargs.get("server") and kwargs.get("keep_alive"):
			sql = """select active from `servers` where `ip` = '{}' """.format(kwargs.get("server"))
	else:
		sql = """select * from servers where enable = '1' ORDER BY servers.groups """

		if kwargs.get("server") is not None:
			sql = """select * from servers where ip = '{}' """.format(kwargs.get("server"))
		if kwargs.get("full") is not None:
			sql = """select * from servers ORDER BY hostname """
		if kwargs.get("get_master_servers") is not None:
			sql = """select id,hostname from servers where master = 0 and type_ip = 0 and enable = 1 ORDER BY servers.groups """
		if kwargs.get("get_master_servers") is not None and kwargs.get('uuid') is not None:
			sql = """ select servers.id, servers.hostname from servers
				left join user as user on servers.groups = user.groups
				left join uuid as uuid on user.id = uuid.user_id
				where uuid.uuid = '{}' and servers.master = 0 and servers.type_ip = 0 and servers.enable = 1 ORDER BY servers.groups
				""".format(kwargs.get('uuid'))
		if kwargs.get("id"):
			sql = """select * from servers where id = '{}' """.format(kwargs.get("id"))
		if kwargs.get("hostname"):
			sql = """select * from servers where hostname = '{}' """.format(kwargs.get("hostname"))
		if kwargs.get("id_hostname"):
			sql = """select * from servers where hostname = '{}' or id = '{}' or ip = '{}'""".format(
				kwargs.get("id_hostname"), kwargs.get("id_hostname"), kwargs.get("id_hostname"))
		if kwargs.get("server") and kwargs.get("keep_alive"):
			sql = """select active from servers where ip = '{}' """.format(kwargs.get("server"))

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def write_user_uuid(login, user_uuid):
	session_ttl = get_setting('session_ttl')
	session_ttl = int(session_ttl)
	user_id = get_user_id_by_username(login)
	cur_date = get_date.return_date('regular', timedelta=session_ttl)

	try:
		UUID.insert(user_id=user_id, uuid=user_uuid, exp=cur_date).execute()
	except Exception as e:
		out_error(e)


def write_user_token(login, user_token):
	token_ttl = int(get_setting('token_ttl'))
	user_id = get_user_id_by_username(login)
	cur_date = get_date.return_date('regular', timedelta=token_ttl)

	try:
		Token.insert(user_id=user_id, token=user_token, exp=cur_date).execute()
	except Exception as e:
		out_error(e)


def write_api_token(user_token, group_id, user_role, user_name):
	token_ttl = int(get_setting('token_ttl'))
	cur_date = get_date.return_date('regular', timedelta=token_ttl)
	cur_date_token_ttl = get_date.return_date('regular', timedelta=token_ttl)

	try:
		ApiToken.insert(
			token=user_token, user_name=user_name, user_group_id=group_id, user_role=user_role,
			create_date=cur_date, expire_date=cur_date_token_ttl).execute()
	except Exception as e:
		out_error(e)


def get_api_token(token):
	try:
		user_token = ApiToken.get(ApiToken.token == token)
	except Exception as e:
		return str(e)
	else:
		return True if token == user_token.token else False


def get_user_id_by_api_token(token):
	query = (User.select(User.user_id).join(ApiToken, on=(
		ApiToken.user_name == User.username
	)).where(ApiToken.token == token))
	try:
		query_res = query.execute()
	except Exception as e:
		return str(e)
	for i in query_res:
		return i.user_id


def get_username_groupid_from_api_token(token):
	try:
		user_name = ApiToken.get(ApiToken.token == token)
	except Exception as e:
		return str(e)
	else:
		return user_name.user_name, user_name.user_group_id, user_name.user_role


def get_token(uuid):
	query = Token.select().join(UUID, on=(Token.user_id == UUID.user_id)).where(UUID.uuid == uuid).limit(1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			for i in query_res:
				return i.token
		except Exception:
			return ''


def delete_uuid(uuid):
	try:
		query = UUID.delete().where(UUID.uuid == uuid)
		query.execute()
	except Exception:
		pass


def delete_old_uuid():
	cur_date = get_date.return_date('regular')
	query = UUID.delete().where((UUID.exp < cur_date) | (UUID.exp.is_null(True)))
	query1 = Token.delete().where((Token.exp < cur_date) | (Token.exp.is_null(True)))
	try:
		query.execute()
		query1.execute()
	except Exception as e:
		out_error(e)


def update_last_act_user(uuid, token):
	session_ttl = int(get_setting('session_ttl'))
	token_ttl = int(get_setting('token_ttl'))
	cur_date_session = get_date.return_date('regular', timedelta=session_ttl)
	cur_date_token = get_date.return_date('regular', timedelta=token_ttl)
	cur_date = get_date.return_date('regular')
	user_id = get_user_id_by_uuid(uuid)

	try:
		import cgi
		import os
		ip = cgi.escape(os.environ["REMOTE_ADDR"])
	except Exception:
		ip = ''

	query = UUID.update(exp=cur_date_session).where(UUID.uuid == uuid)
	query1 = Token.update(exp=cur_date_token).where(Token.token == token)
	query2 = User.update(last_login_date=cur_date, last_login_ip=ip).where(User.user_id == user_id)
	try:
		query.execute()
		query1.execute()
		query2.execute()
	except Exception as e:
		out_error(e)


def get_user_name_by_uuid(uuid):
	try:
		query = User.select(User.username).join(UUID, on=(User.user_id == UUID.user_id)).where(UUID.uuid == uuid)
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user in query_res:
			return user.username


def get_user_id_by_uuid(uuid):
	try:
		query = User.select(User.user_id).join(UUID, on=(User.user_id == UUID.user_id)).where(UUID.uuid == uuid)
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user in query_res:
			return user.user_id


def get_user_id_by_username(username: str):
	try:
		query = User.get(User.username == username).user_id
	except Exception as e:
		out_error(e)
	else:
		return query


def get_user_role_by_uuid(uuid, group_id):
	query = (
		UserGroups.select(UserGroups.user_role_id).join(UUID, on=(UserGroups.user_id == UUID.user_id)
		).where(
			(UUID.uuid == uuid) &
			(UserGroups.user_group_id == group_id)
		)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for user_id in query_res:
			return int(user_id.user_role_id)


def get_user_telegram_by_group(group):
	query = Telegram.select().where(Telegram.groups == group)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_telegram_by_ip(ip):
	query = Telegram.select().join(Server, on=(Server.groups == Telegram.groups)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_telegram_by_id(telegram_id):
	query = Telegram.select().where(Telegram.id == telegram_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_user_slack_by_group(group):
	query = Slack.select().where(Slack.groups == group)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_slack_by_ip(ip):
	query = Slack.select().join(Server, on=(Server.groups == Slack.groups)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_slack_by_id(slack_id):
	query = Slack.select().where(Slack.id == slack_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_user_pd_by_group(group):
	query = PD.select().where(PD.groups == group)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_pd_by_ip(ip):
	query = PD.select().join(Server, on=(Server.groups == PD.groups)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_pd_by_id(pd_id):
	query = PD.select().where(PD.id == pd_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_dick_permit(**kwargs):
	if kwargs.get('username'):
		grp = kwargs.get('group_id')
	else:
		try:
			import http.cookies
			cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
			group = cookie.get('group')
			grp = group.value
		except Exception:
			print('<meta http-equiv="refresh" content="0; url=/app/login.py">')
			return

	only_group = kwargs.get('only_group')
	disable = 'enable = 1'
	haproxy = ''
	nginx = ''
	keepalived = ''
	apache = ''
	ip = ''

	if kwargs.get('virt'):
		type_ip = ""
	else:
		type_ip = "and type_ip = 0"
	if kwargs.get('disable') == 0:
		disable = '(enable = 1 or enable = 0)'
	if kwargs.get('ip'):
		ip = "and ip = '%s'" % kwargs.get('ip')
	if kwargs.get('haproxy') or kwargs.get('service') == 'haproxy':
		haproxy = "and haproxy = 1"
	if kwargs.get('nginx') or kwargs.get('service') == 'nginx':
		nginx = "and nginx = 1"
	if kwargs.get('keepalived') or kwargs.get('service') == 'keepalived':
		keepalived = "and keepalived = 1"
	if kwargs.get('apache') or kwargs.get('service') == 'apache':
		apache = "and apache = 1"

	cursor = conn.cursor()
	try:
		if mysql_enable == '1':
			if grp == '1' and not only_group:
				sql = """ select * from `servers` where {} {} {} {} {} {} {} order by `pos` asc""".format(
					disable, type_ip, nginx, haproxy, keepalived, apache, ip
				)
			else:
				sql = """ select * from `servers` where `groups` = {group} and ({disable}) {type_ip} {ip} {haproxy} {nginx} {keepalived} {apache} order by `pos` asc
				""".format(
					group=grp, disable=disable, type_ip=type_ip, ip=ip, haproxy=haproxy, nginx=nginx, keepalived=keepalived, apache=apache
				)
		else:
			if grp == '1' and not only_group:
				sql = """ select * from servers where {} {} {} {} {} {} {} order by pos""".format(disable, type_ip, nginx, haproxy, keepalived, apache, ip)
			else:
				sql = """ select * from servers where groups = '{group}' and ({disable}) {type_ip} {ip} {haproxy} {nginx} {keepalived} {apache} order by pos
				""".format(group=grp, disable=disable, type_ip=type_ip, ip=ip, haproxy=haproxy, nginx=nginx, keepalived=keepalived, apache=apache)

	except Exception as e:
		raise Exception(f'error: {e}')

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def is_master(ip, **kwargs):
	cursor = conn.cursor()
	if kwargs.get('master_slave'):
		sql = """ select master.hostname, master.ip, slave.hostname, slave.ip
		from servers as master
		left join servers as slave on master.id = slave.master
		where slave.master > 0 """
	else:
		sql = """ select slave.ip, slave.hostname from servers as master
		left join servers as slave on master.id = slave.master
		where master.ip = '%s' """ % ip
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_ssh(**kwargs):
	if kwargs.get("name") is not None:
		query = Cred.select().where(Cred.name == kwargs.get('name'))
	elif kwargs.get("id") is not None:
		query = Cred.select().where(Cred.id == kwargs.get('id'))
	elif kwargs.get("serv") is not None:
		query = Cred.select().join(Server, on=(Cred.id == Server.cred)).where(Server.ip == kwargs.get('serv'))
	elif kwargs.get("group") is not None:
		query = Cred.select().where(Cred.groups == kwargs.get("group"))
	else:
		query = Cred.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_ssh(name, enable, group, username, password):
	if password is None:
		password = 'None'
	try:
		Cred.insert(name=name, enable=enable, groups=group, username=username, password=password).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_ssh(ssh_id):
	query = Cred.delete().where(Cred.id == ssh_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def update_ssh(cred_id, name, enable, group, username, password):
	if password is None:
		password = 'None'

	cred_update = Cred.update(name=name, enable=enable, groups=group, username=username, password=password).where(
		Cred.id == cred_id)
	try:
		cred_update.execute()
	except Exception as e:
		out_error(e)


def insert_backup_job(server, rserver, rpath, backup_type, time, cred, description):
	try:
		Backup.insert(
			server=server, rhost=rserver, rpath=rpath, backup_type=backup_type, time=time,
			cred=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_s3_backup_job(server, s3_server, bucket, secret_key, access_key, time, description):
	try:
		S3Backup.insert(
			server=server, s3_server=s3_server, bucket=bucket, secret_key=secret_key, access_key=access_key, time=time,
			description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_backups(**kwargs):
	if kwargs.get("server") is not None and kwargs.get("rserver") is not None:
		query = Backup.select().where((Backup.server == kwargs.get("server")) & (Backup.rhost == kwargs.get("rserver")))
	else:
		query = Backup.select().order_by(Backup.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_s3_backups(**kwargs):
	if kwargs.get("server") is not None and kwargs.get("bucket") is not None:
		query = S3Backup.select().where(
			(S3Backup.server == kwargs.get("server")) &
			(S3Backup.s3_server == kwargs.get("s3_server")) &
			(S3Backup.bucket == kwargs.get("bucket"))
		)
	else:
		query = S3Backup.select().order_by(S3Backup.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_backup(server, rserver, rpath, backup_type, time, cred, description, backup_id):
	backup_update = Backup.update(
		server=server, rhost=rserver, rpath=rpath, backup_type=backup_type, time=time,
		cred=cred, description=description
	).where(Backup.id == backup_id)
	try:
		backup_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_backups(backup_id: int) -> bool:
	query = Backup.delete().where(Backup.id == backup_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_s3_backups(backup_id: int) -> bool:
	query = S3Backup.delete().where(S3Backup.id == backup_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def check_exists_backup(server: str) -> bool:
	try:
		backup = Backup.get(Backup.server == server)
	except Exception:
		pass
	else:
		if backup.id is not None:
			return True
		else:
			return False


def check_exists_s3_backup(server: str) -> bool:
	try:
		backup = S3Backup.get(S3Backup.server == server)
	except Exception:
		pass
	else:
		if backup.id is not None:
			return True
		else:
			return False


def delete_telegram(telegram_id):
	query = Telegram.delete().where(Telegram.id == telegram_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_telegram(**kwargs):
	if kwargs.get('token'):
		query = Telegram.select().where(Telegram.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = Telegram.select().where(Telegram.id == kwargs.get('id'))
	else:
		query = Telegram.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_telegram(token, channel, group):
	try:
		Telegram.insert(token=token, chanel_name=channel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_telegram(token, channel, group, telegram_id):
	telegram_update = Telegram.update(token=token, chanel_name=channel, groups=group).where(Telegram.id == telegram_id)
	try:
		telegram_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_slack(slack_id):
	query = Slack.delete().where(Slack.id == slack_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_slack(**kwargs):
	if kwargs.get('token'):
		query = Slack.select().where(Slack.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = Slack.select().where(Slack.id == kwargs.get('id'))
	else:
		query = Slack.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_slack(token, chanel, group):
	try:
		Slack.insert(token=token, chanel_name=chanel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_slack(token, chanel, group, slack_id):
	query_update = Slack.update(token=token, chanel_name=chanel, groups=group).where(Slack.id == slack_id)
	try:
		query_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_pd(pd_id):
	query = PD.delete().where(PD.id == pd_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_pd(**kwargs):
	if kwargs.get('token'):
		query = PD.select().where(PD.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = PD.select().where(PD.id == kwargs.get('id'))
	else:
		query = PD.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_pd(token, chanel, group):
	try:
		PD.insert(token=token, chanel_name=chanel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_pd(token, chanel, group, pd_id):
	query_update = PD.update(token=token, chanel_name=chanel, groups=group).where(PD.id == pd_id)
	try:
		query_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_option(saved_option, group):
	try:
		Option.insert(options=saved_option, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_options(**kwargs):
	if kwargs.get('option'):
		query = Option.select().where(Option.options == kwargs.get('option'))
	elif kwargs.get('group'):
		query = Option.select(Option.options).where(
			(Option.groups == kwargs.get('group')) & (Option.options.startswith(kwargs.get('term'))))
	else:
		query = Option.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_options(option, option_id):
	query_update = Option.update(options=option).where(Option.id == option_id)
	try:
		query_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_option(option_id):
	query = Option.delete().where(Option.id == option_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_savedserver(server, description, group):
	try:
		SavedServer.insert(server=server, description=description, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_saved_servers(**kwargs):
	if kwargs.get('server'):
		query = SavedServer.select().where(SavedServer.server == kwargs.get('server'))
	elif kwargs.get('group'):
		query = SavedServer.select(SavedServer.server, SavedServer.description).where(
			(SavedServer.groups == kwargs.get('group')) & (SavedServer.server.startswith(kwargs.get('term'))))
	else:
		query = SavedServer.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_savedserver(server, description, saved_id):
	query_update = SavedServer.update(server=server, description=description).where(SavedServer.id == saved_id)
	try:
		query_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_savedserver(saved_id):
	query = SavedServer.delete().where(SavedServer.id == saved_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_metrics(serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate):
	cur_date = get_date.return_date('regular')
	try:
		Metrics.insert(
			serv=serv, curr_con=curr_con, cur_ssl_con=cur_ssl_con, sess_rate=sess_rate, max_sess_rate=max_sess_rate,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def insert_metrics_http(serv, http_2xx, http_3xx, http_4xx, http_5xx):
	cur_date = get_date.return_date('regular')
	try:
		MetricsHttpStatus.insert(
			serv=serv, ok_ans=http_2xx, redir_ans=http_3xx, not_found_ans=http_4xx, err_ans=http_5xx,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def insert_nginx_metrics(serv, conn):
	cur_date = get_date.return_date('regular')
	try:
		NginxMetrics.insert(serv=serv, conn=conn, date=cur_date).execute()
	except Exception as e:
		out_error(e)


def insert_apache_metrics(serv, conn):
	cur_date = get_date.return_date('regular')
	try:
		ApacheMetrics.insert(serv=serv, conn=conn, date=cur_date).execute()
	except Exception as e:
		out_error(e)


def select_waf_metrics_enable_server(ip):
	query = Waf.select(Waf.metrics).join(Server, on=(Waf.server_id == Server.server_id)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.metrics


def select_waf_servers(serv):
	query = Server.select(Server.ip).join(Waf, on=(Waf.server_id == Server.server_id)).where(Server.ip == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.ip


def select_waf_nginx_servers(serv):
	query = Server.select(Server.ip).join(WafNginx, on=(WafNginx.server_id == Server.server_id)).where(Server.ip == serv)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for en in query_res:
			return en.ip


def insert_waf_nginx_server(server_ip):
	try:
		server_id = Server.get(Server.ip == server_ip).server_id
		WafNginx.insert(server_id=server_id).execute()
	except Exception as e:
		out_error(e)


def select_waf_servers_metrics_for_master():
	query = Server.select(Server.ip).join(
		Waf, on=(Waf.server_id == Server.server_id)
	).where((Server.enable == 1) & Waf.metrics == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_waf_servers_metrics(uuid):
	try:
		user_group = User.get(User.username == get_user_name_by_uuid(uuid))
	except Exception as e:
		out_error(e)
	else:
		if user_group.groups == '1':
			query = Waf.select(Server.ip).join(Server, on=(Waf.server_id == Server.server_id)).where(
				(Server.enable == 1) & (Waf.metrics == 1)
			)
		else:
			query = Waf.select(Server.ip).join(Server, on=(Waf.server_id == Server.server_id)).where(
				(Server.enable == 1) & (Waf.metrics == 1) & (Server.groups == user_group.groups)
			)
		try:
			query_res = query.execute()
		except Exception as e:
			out_error(e)
		else:
			return query_res


def insert_waf_metrics_enable(serv, enable):
	try:
		server_id = Server.get(Server.ip == serv).server_id
		Waf.insert(server_id=server_id, metrics=enable).execute()
	except Exception as e:
		out_error(e)


def insert_waf_rules(serv):
	data_source = [
		{'serv': serv, 'rule_name': 'Ignore static', 'rule_file': 'modsecurity_crs_10_ignore_static.conf',
			'desc': 'This ruleset will skip all tests for media files, but will skip only the request body phase (phase 2) '
					'for text files. To skip the outbound stage for text files, add file 47 (skip_outbound_checks) '
					'to your configuration, in addition to this fileth/aws/login'},
		{'serv': serv, 'rule_name': 'Brute force protection', 'rule_file': 'modsecurity_crs_11_brute_force.conf',
			'desc': 'Anti-Automation Rule for specific Pages (Brute Force Protection) This is a rate-limiting rule set and '
					'does not directly correlate whether the authentication attempt was successful or not'},
		{'serv': serv, 'rule_name': 'DOS Protections', 'rule_file': 'modsecurity_crs_11_dos_protection.conf',
			'desc': 'Enforce an existing IP address block and log only 1-time/minute. We do not want to get flooded by alerts '
					'during an attack or scan so we are only triggering an alert once/minute.  You can adjust how often you '
					'want to receive status alerts by changing the expirevar setting below'},
		{'serv': serv, 'rule_name': 'XML enabler', 'rule_file': 'modsecurity_crs_13_xml_enabler.conf',
			'desc': 'The rules in this file will trigger the XML parser upon an XML request'},
		{'serv': serv, 'rule_name': 'Protocol violations', 'rule_file': 'modsecurity_crs_20_protocol_violations.conf',
			'desc': 'Some protocol violations are common in application layer attacks. Validating HTTP requests eliminates a '
					'large number of application layer attacks. The purpose of this rules file is to enforce HTTP RFC requirements '
					'that state how  the client is supposed to interact with the server. http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html'},
		{'serv': serv, 'rule_name': 'Protocol anomalies', 'rule_file': 'modsecurity_crs_21_protocol_anomalies.conf',
			'desc': 'Some common HTTP usage patterns are indicative of attacks but may also be used by non-browsers for '
					'legitimate uses. Do not accept requests without common headers. All normal web browsers include Host, '
					'User-Agent and Accept headers. Implies either an attacker or a legitimate automation client'},
		{'serv': serv, 'rule_name': 'Detect CC#', 'rule_file': 'modsecurity_crs_25_cc_known.conf',
			'desc': 'Detect CC# in input, log transaction and sanitize'},
		{'serv': serv, 'rule_name': 'CC traker', 'rule_file': 'modsecurity_crs_25_cc_track_pan.conf',
			'desc': 'Credit Card Track 1 and 2 and PAN Leakage Checks'},
		{'serv': serv, 'rule_name': 'HTTP policy', 'rule_file': 'modsecurity_crs_30_http_policy.conf',
			'desc': 'HTTP policy enforcement The HTTP policy enforcement rule set sets limitations on the use of HTTP by '
					'clients. Few applications require the breadth and depth of the HTTP protocol. On the other hand many '
					'attacks abuse valid but rare HTTP use patterns. Restricting  HTTP protocol usage is effective in '
					'therefore effective in blocking many  application layer attacks'},
		{'serv': serv, 'rule_name': 'Bad robots', 'rule_file': 'modsecurity_crs_35_bad_robots.conf',
			'desc': 'Bad robots detection is based on checking elements easily controlled by the client. As such a '
					'determined attacked can bypass those checks. Therefore bad robots detection should not be viewed '
					'as a security mechanism against targeted attacks but rather as a nuisance reduction, eliminating '
					'most of the random attacks against your web site'},
		{'serv': serv, 'rule_name': 'OS Injection Attacks', 'rule_file': 'modsecurity_crs_40_generic_attacks.conf',
			'desc': 'OS Command Injection Attacks'},
		{'serv': serv, 'rule_name': 'SQL injection', 'rule_file': 'modsecurity_crs_41_sql_injection_attacks.conf',
			'desc': 'SQL injection protection'},
		{'serv': serv, 'rule_name': 'XSS Protections', 'rule_file': 'modsecurity_crs_41_xss_attacks.conf',
			'desc': 'XSS attacks protection'},
		{'serv': serv, 'rule_name': 'Comment spam', 'rule_file': 'modsecurity_crs_42_comment_spam.conf',
			'desc': 'Comment spam is an attack against blogs, guestbooks, wikis and other types of interactive web sites '
					'that accept and display hyperlinks submitted by visitors. The spammers automatically post specially '
					'crafted random comments which include links that point to the spammer\'s web site. The links artificially '
					'increase the site\'s search engine ranking and may make the site more noticable in search results.'},
		{'serv': serv, 'rule_name': 'Trojans Protections', 'rule_file': 'modsecurity_crs_45_trojans.conf ',
			'desc': 'The trojan access detection rules detects access to known Trojans already installed on a server. '
					'Uploading of Trojans is part of the Anti-Virus rules  and uses external Anti Virus program when uploading '
					'files. Detection of Trojans access is especially important in a hosting environment where the actual Trojan '
					'upload may be done through valid methods and not through hacking'},
		{'serv': serv, 'rule_name': 'RFI Protections', 'rule_file': 'modsecurity_crs_46_slr_et_lfi_attacks.conf',
			'desc': 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference '
					'external scripts. The perpetrator’s goal is to exploit the referencing function in an application to upload '
					'malware (e.g., backdoor shells) from a remote URL located within a different domain'},
		{'serv': serv, 'rule_name': 'RFI Protections 2', 'rule_file': 'modsecurity_crs_46_slr_et_rfi_attacks.conf',
			'desc': 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference '
					'external scripts. The perpetrator’s goal is to exploit the referencing function in an application to '
					'upload malware (e.g., backdoor shells) from a remote URL located within a different domain'},
		{'serv': serv, 'rule_name': 'SQLi Protections', 'rule_file': 'modsecurity_crs_46_slr_et_sqli_attacks.conf',
			'desc': 'SQLi injection attacks protection'},
		{'serv': serv, 'rule_name': 'XSS Protections 2', 'rule_file': 'modsecurity_crs_46_slr_et_xss_attacks.conf',
			'desc': 'XSS attacks protection'},
		{'serv': serv, 'rule_name': 'Common exceptions', 'rule_file': 'modsecurity_crs_47_common_exceptions.conf',
			'desc': 'This file is used as an exception mechanism to remove common false positives that may be encountered'},
	]
	try:
		WafRules.insert_many(data_source).execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def insert_nginx_waf_rules(serv):
	data_source = [
		{'serv': serv, 'rule_name': 'Initialization', 'rule_file': 'REQUEST-901-INITIALIZATION.conf',
			'desc': 'This file REQUEST-901-INITIALIZATION.conf initializes the Core Rules and performs preparatory actions. '
					'It also fixes errors and omissions of variable definitions in the file crs-setup.conf The setup.conf'
					'can and should be edited by the user, this file. is part of the CRS installation and should not be altered.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Drupal exclusion rules', 'rule_file': 'REQUEST-903.9001-DRUPAL-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default Drupal install. The exclusions are only active '
					'if crs_exclusions_drupal=1 is set. See rule 900130 in crs-setup.conf for instructions.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Nextcloud exclusion rules', 'rule_file': 'REQUEST-903.9003-NEXTCLOUD-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default NextCloud install. They will likely work with OwnCloud '
					'too, but you may have to modify them. The exclusions are only active if crs_exclusions_nextcloud=1 is set. '
					'See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Dokuwiki exclusion rules', 'rule_file': 'REQUEST-903.9004-DOKUWIKI-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default Dokuwiki install. The exclusions are only active '
					'if crs_exclusions_dokuwiki=1 is set. See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'CPanel exclusion rules', 'rule_file': 'REQUEST-903.9005-CPANEL-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default CPanel install. The exclusions are only active '
					'if crs_exclusions_cpanel=1 is set. See rule 900130 in crs-setup.conf for instructions.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'XenForo exclusion rules', 'rule_file': 'REQUEST-903.9006-XENFORO-EXCLUSION-RULES.conf',
			'desc': 'These exclusions remedy false positives in a default XenForo install. The exclusions are only active '
					'if crs_exclusions_xenforo=1 is set. See rule 900130 in crs-setup.conf for instructions.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Common exceptions', 'rule_file': 'REQUEST-905-COMMON-EXCEPTIONS.conf',
			'desc': 'This file is used as an exception mechanism to remove common false positives that may be encountered.',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'IP reputation', 'rule_file': 'REQUEST-910-IP-REPUTATION.conf',
			'desc': 'IP reputation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Method enforcement', 'rule_file': 'REQUEST-911-METHOD-ENFORCEMENT.conf',
			'desc': 'Method enforcement rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'DDOS protection', 'rule_file': 'REQUEST-912-DOS-PROTECTION.conf',
			'desc': 'Anti-Automation rules to detect Denial of Service attacks.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Protocol enforcement', 'rule_file': 'REQUEST-920-PROTOCOL-ENFORCEMENT.conf',
			'desc': 'Some protocol violations are common in application layer attacks. Validating HTTP requests eliminates '
					'a large number of application layer attacks. The purpose of this rules file is to enforce HTTP RFC '
					'requirements that state how the client is supposed to interact with the server.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Protocol attack', 'rule_file': 'REQUEST-921-PROTOCOL-ATTACK.conf',
			'desc': 'Protocol attack rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack LFI', 'rule_file': 'REQUEST-930-APPLICATION-ATTACK-LFI.conf',
			'desc': 'Application attack LFI rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack RCE', 'rule_file': 'REQUEST-932-APPLICATION-ATTACK-RCE.conf',
			'desc': 'Application attack RCE rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack PHP', 'rule_file': 'REQUEST-933-APPLICATION-ATTACK-PHP.conf',
			'desc': 'Application attack PHP rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack NodeJS', 'rule_file': 'REQUEST-934-APPLICATION-ATTACK-NODEJS.conf',
			'desc': 'Application attack NodeJS rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack SQLI', 'rule_file': 'REQUEST-942-APPLICATION-ATTACK-SQLI.conf',
			'desc': 'Application attack SQLI rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack session-fixation', 'rule_file': 'REQUEST-943-APPLICATION-ATTACK-SESSION-FIXATION.conf',
			'desc': 'Application attack session-fixation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack JAVA', 'rule_file': 'REQUEST-944-APPLICATION-ATTACK-JAVA.conf',
			'desc': 'Application attack JAVA rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Application attack blocking evaluation', 'rule_file': 'REQUEST-949-BLOCKING-EVALUATION.conf',
			'desc': 'Application attack blocking evaluation rule.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages', 'rule_file': 'RESPONSE-950-DATA-LEAKAGES.conf',
			'desc': 'The paranoia level skip rules 950020, 950021 and 950022 have odd numbers not in sync with other paranoia '
					'level skip rules in other. files. This is done to avoid rule id collisions with CRSv2. This is also true '
					'for rule 950130.', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages SQL', 'rule_file': 'RESPONSE-951-DATA-LEAKAGES-SQL.conf',
			'desc': 'Data leakages SQL rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages JAVA', 'rule_file': 'RESPONSE-952-DATA-LEAKAGES-JAVA.conf',
			'desc': 'Data leakages JAVA rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages PHP', 'rule_file': 'RESPONSE-953-DATA-LEAKAGES-PHP.conf',
			'desc': 'Data leakages PHP rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Data leakages IIS', 'rule_file': 'RESPONSE-954-DATA-LEAKAGES-IIS.conf',
			'desc': 'Data leakages IIS rule', 'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Blocking evaluation', 'rule_file': 'RESPONSE-959-BLOCKING-EVALUATION.conf',
			'desc': 'You should set the score to the proper threshold you would prefer. If kept at "@gt 0" it will work '
					'similarly to previous Mod CRS rules and will create an event in the error_log file if there are any '
					'rules that match.  If you would like to lessen the number of events generated in the error_log file, '
					'you should increase the anomaly score threshold to something like "@gt 20".  This would only generate '
					'an event in the error_log file if there are multiple lower severity rule matches or if any 1 higher '
					'severity item matches. You should also set the desired disruptive action (deny, redirect, etc...).',
			'service': 'nginx'},
		{'serv': serv, 'rule_name': 'Correlation', 'rule_file': 'RESPONSE-980-CORRELATION.conf',
			'desc': 'This file is used in post processing after the response has been sent to the client (in the logging phase). '
					'Its purpose is to provide inbound+outbound correlation of events to provide a more intelligent designation '
					'as to the outcome or result of the transaction - meaning, was this a successful attack?',
			'service': 'nginx'},
	]
	try:
		WafRules.insert_many(data_source).execute()
	except Exception as e:
		out_error(e)
	else:
		return True


def select_waf_rules(serv, service):
	query = WafRules.select(WafRules.id, WafRules.rule_name, WafRules.en, WafRules.desc).where(
		(WafRules.serv == serv)
		& (WafRules.service == service)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_waf_rules(serv):
	query = WafRules.delete().where(WafRules.serv == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_waf_rule_by_id(rule_id):
	try:
		query = WafRules.get(WafRules.id == rule_id)
	except Exception as e:
		out_error(e)
	else:
		return query.rule_file


def update_enable_waf_rules(rule_id, serv, en):
	query = WafRules.update(en=en).where((WafRules.id == rule_id) & (WafRules.serv == serv))
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_new_waf_rule(rule_name: str, rule_file: str, rule_description: str, service: str, serv: str) -> int:
	try:
		last_id = WafRules.insert(
			serv=serv,
			rule_name=rule_name,
			rule_file=rule_file,
			desc=rule_description,
			service=service
		).execute()
	except Exception as e:
		out_error(e)
	else:
		return last_id


def delete_waf_server(server_id):
	query = Waf.delete().where(Waf.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_waf_metrics(serv, conn):
	cur_date = get_date.return_date('regular')
	try:
		WafMetrics.insert(serv=serv, conn=conn, date=cur_date).execute()
	except Exception as e:
		out_error(e)


def delete_waf_metrics():
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = WafMetrics.delete().where(WafMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_waf_metrics_enable(name, enable):
	server_id = 0
	try:
		server_id = Server.get(Server.hostname == name).server_id
	except Exception as e:
		out_error(e)

	try:
		Waf.update(metrics=enable).where(Waf.server_id == server_id).execute()
	except Exception as e:
		out_error(e)


def delete_metrics():
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = Metrics.delete().where(Metrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_http_metrics():
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = MetricsHttpStatus.delete().where(MetricsHttpStatus.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_nginx_metrics():
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = NginxMetrics.delete().where(NginxMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_apache_metrics():
	cur_date = get_date.return_date('regular', timedelta_minus=3)
	query = ApacheMetrics.delete().where(ApacheMetrics.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_metrics(serv, service, **kwargs):
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


def update_setting(param: str, val: str, user_group: int) -> bool:
	print(val)
	query = Setting.update(value=val).where((Setting.param == param) & (Setting.group == user_group))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def get_ver():
	try:
		ver = Version.get()
	except Exception as e:
		out_error(e)
	else:
		return ver.version


def select_roles():
	query = Role.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.alert == 1) & (Server.enable == 1) & (Server.groups == kwargs.get('group'))
		)
	else:
		query = Server.select(Server.ip).where((Server.alert == 1) & (Server.enable == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_all_alerts(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			((Server.alert == 1) | (Server.nginx_alert == 1)) & (Server.enable == 1) & (Server.groups == kwargs.get('group'))
		)
	else:
		query = Server.select(Server.ip).where(((Server.alert == 1) | (Server.nginx_alert == 1)) & (Server.enable == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_nginx_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.nginx_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.nginx == 1)
		)
	else:
		query = Server.select(Server.ip).where(
			(Server.nginx_alert == 1)
			& (Server.enable == 1)
			& (Server.nginx == 1)
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_apache_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.apache_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.apache == 1)
		)
	else:
		query = Server.select(Server.ip).where((Server.apache_alert == 1) & (Server.enable == 1) & (Server.apache == 1))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_keepalived_alert(**kwargs):
	if kwargs.get("group") is not None:
		query = Server.select(Server.ip).where(
			(Server.keepalived_alert == 1)
			& (Server.enable == 1)
			& (Server.groups == kwargs.get('group'))
			& (Server.keepalived == 1)
		)
	else:
		query = Server.select(Server.ip).where(
			(Server.keepalived_alert == 1)
			& (Server.enable == 1)
			& (Server.keepalived == 1)
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_keep_alive():
	query = Server.select(Server.ip, Server.groups, Server.server_id).where(Server.active == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_nginx_keep_alive():
	query = Server.select(Server.ip, Server.groups, Server.server_id).where(Server.nginx_active == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_apache_keep_alive():
	query = Server.select(Server.ip, Server.groups, Server.server_id).where(Server.apache_active == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_keepalived_keep_alive():
	query = Server.select(Server.ip, Server.port, Server.groups, Server.server_id).where(Server.keepalived_active == 1)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_keepalived(serv):
	try:
		keepalived = Server.get(Server.ip == serv).keepalived
	except Exception as e:
		out_error(e)
	else:
		return keepalived


def select_update_keep_alive_restart(server_id: int, service: str) -> int:
	try:
		restarted = KeepaliveRestart.get(
			(KeepaliveRestart.server_id == server_id) &
			(KeepaliveRestart.service == service)
		).restarted
	except Exception as e:
		out_error(e)
	else:
		return restarted or 0
	finally:
		return 0


def update_keep_alive_restart(server_id: int, service: str, restarted: int) -> None:
	query = KeepaliveRestart.insert(server_id=server_id, service=service, restarted=restarted).on_conflict('replace')
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_keepalived(serv):
	query = Server.update(keepalived='1').where(Server.ip == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_apache(serv):
	try:
		apache = Server.get(Server.ip == serv).apache
	except Exception as e:
		out_error(e)
	else:
		return apache


def update_apache(serv: str) -> bool:
	query = Server.update(apache='1').where(Server.ip == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_nginx(serv):
	try:
		query_res = Server.get(Server.ip == serv).nginx
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_nginx(serv: str) -> bool:
	query = Server.update(nginx=1).where(Server.ip == serv)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def select_haproxy(serv):
	try:
		query_res = Server.get(Server.ip == serv).haproxy
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_haproxy(serv):
	query = Server.update(haproxy=1).where(Server.ip == serv)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_firewall(serv):
	query = Server.update(firewall_enable=1).where(Server.ip == serv)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_server_pos(pos, server_id):
	query = Server.update(pos=pos).where(Server.server_id == server_id)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def check_token_exists(token):
	try:
		import http.cookies
		import os
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		if get_token(user_id.value) == token:
			return True
		else:
			return False
	except Exception:
		return False


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


def insert_smon_ping(smon_id, hostname, packet_size):
	try:
		SmonPingCheck.insert(smon_id=smon_id, ip=hostname, packet_size=packet_size).execute()
	except Exception as e:
		out_error(e)


def insert_smon_tcp(smon_id, hostname, port):
	try:
		SmonTcpCheck.insert(smon_id=smon_id, ip=hostname, port=port).execute()
	except Exception as e:
		out_error(e)


def insert_smon_dns(smon_id: int, hostname: str, port: int, resolver: str, record_type: str) -> None:
	try:
		SmonDnsCheck.insert(smon_id=smon_id, ip=hostname, port=port, resolver=resolver, record_type=record_type).execute()
	except Exception as e:
		out_error(e)


def insert_smon_http(smon_id, url, body):
	try:
		SmonHttpCheck.insert(smon_id=smon_id, url=url, body=body).execute()
	except Exception as e:
		out_error(e)


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


def select_smon_ping(user_group):
	if user_group == 1:
		query = SmonPingCheck.select()
	else:
		query = SmonPingCheck.select().where(SMON.user_group == user_group)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_ping() -> object:
	query = SmonPingCheck.select(SmonPingCheck, SMON).join_from(SmonPingCheck, SMON).where(SMON.en == '1')
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_tcp() -> object:
	query = SmonTcpCheck.select(SmonTcpCheck, SMON).join_from(SmonTcpCheck, SMON).where(SMON.en == '1')
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_http() -> object:
	query = SmonHttpCheck.select(SmonHttpCheck, SMON).join_from(SmonHttpCheck, SMON).where(SMON.en == '1')
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_en_smon_dns() -> object:
	query = SmonDnsCheck.select(SmonDnsCheck, SMON).join_from(SmonDnsCheck, SMON).where(SMON.en == '1')
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_tcp(user_group):
	if user_group == 1:
		query = SmonTcpCheck.select()
	else:
		query = SmonTcpCheck.select().where(SMON.user_group == user_group)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_http(user_group):
	if user_group == 1:
		query = SmonHttpCheck.select()
	else:
		query = SmonHttpCheck.select().where(SMON.user_group == user_group)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_smon_dns(user_group):
	if user_group == 1:
		query = SmonDnsCheck.select()
	else:
		query = SmonDnsCheck.select().where(SMON.user_group == user_group)

	try:
		query_res = query.execute()
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


def update_smonHttp(smon_id, url, body):
	query = (SmonHttpCheck.update(url=url, body=body).where(SmonHttpCheck.smon_id == smon_id))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonTcp(smon_id, ip, port):
	query = (SmonTcpCheck.update(ip=ip, port=port).where(SmonTcpCheck.smon_id == smon_id))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonPing(smon_id, ip, packet_size):
	query = (SmonPingCheck.update(ip=ip, packet_size=packet_size).where(SmonPingCheck.smon_id == smon_id))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_smonDns(smon_id: int, ip: str, port: int, resolver: str, record_type: str):
	query = (SmonDnsCheck.update(ip=ip, port=port, resolver=resolver, record_type=record_type)
			 .where(SmonDnsCheck.smon_id == smon_id))
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


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


def alerts_history(service, user_group, **kwargs):
	cursor = conn.cursor()
	and_host = ''

	if kwargs.get('host'):
		and_host = "and ip = '{}'".format(kwargs.get('host'))

	if user_group == 1:
		sql_user_group = ""
	else:
		sql_user_group = "and user_group = '{}'".format(user_group)

	sql = (
		f"select message, level, ip, port, date "
		f"from alerts "
		f"where service = '{service}' {sql_user_group} {and_host} "
		f"order by date desc; "
	)
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_status(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).status
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_http_status(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).http_status
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_body_status(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).body_status
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_script(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).script
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_http(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).http
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_body(smon_id):
	try:
		query_res = SMON.get(SMON.id == smon_id).body
	except Exception as e:
		out_error(e)
	else:
		return query_res


def change_status(status, smon_id):
	query = SMON.update(status=status).where(SMON.id == smon_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def change_body_status(status, smon_id):
	query = SMON.update(body_status=status).where(SMON.id == smon_id)
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
		return False
	else:
		return True


def set_to_zero_time_state(smon_id):
	query = SMON.update(time_state=0).where(SMON.id == smon_id)
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


def select_one_smon(smon_id: int, check_id: int) -> object:
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


def insert_smon_history(smon_id: int, response_time: float, status: int, check_id: int, mes='') -> None:
	cur_date = get_date.return_date('regular')
	try:
		SmonHistory.insert(smon_id=smon_id, response_time=response_time, status=status, date=cur_date,
						   check_id=check_id, mes=mes).execute()
	except Exception as e:
		out_error(e)


def select_smon_history(smon_id: int, check_id: int) -> object:
	query = SmonHistory.select().where(
		(SmonHistory.smon_id == smon_id) &
		(SmonHistory.check_id == check_id)
	).limit(40).order_by(SmonHistory.date.desc())
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_last_smon_status_by_check(smon_id: int, check_id: int) -> object:
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
				return i.status
		except Exception:
			return ''


def get_last_smon_res_time_by_check(smon_id: int, check_id: int) -> object:
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


def get_smon_history_count_checks(smon_id: int, check_id: int) -> dict:
	count_checks = {}
	query = SmonHistory.select(fn.Count(SmonHistory.status)).where(
		(SmonHistory.smon_id == smon_id) &
		(SmonHistory.check_id == check_id)
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
		(SmonHistory.check_id == check_id) &
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


def get_avg_resp_time(smon_id: int, check_id: int) -> object:
	try:
		query_res = SmonHistory.select(fn.AVG(SmonHistory.response_time)).where(
			(SmonHistory.smon_id == smon_id) &
			(SmonHistory.check_id == check_id)
		).scalar()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_alerts(user_group, level, ip, port, message, service):
	cur_date = get_date.return_date('regular')
	try:
		Alerts.insert(
			user_group=user_group, message=message, level=level, ip=ip, port=port, service=service,
			date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def select_alerts(user_group):
	cursor = conn.cursor()
	if mysql_enable == '1':
		sql = """ select level, message, `date` from alerts where user_group = '%s' and `date` <= (now()+ INTERVAL 10 second) """ % (
			user_group)
	else:
		sql = """ select level, message, `date` from alerts where user_group = '%s' and `date` >= datetime('now', '-20 second', 'localtime')
		and `date` <=  datetime('now', 'localtime') ; """ % (
			user_group)
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def select_all_alerts_for_all():
	cursor = conn.cursor()
	if mysql_enable == '1':
		sql = """ select level, message, `date`, user_group from alerts where `date` <= (now()+ INTERVAL 10 second) """
	else:
		sql = """ select level, message, `date`, user_group from alerts where `date` >= datetime('now', '-10 second', 'localtime')
			and `date` <=  datetime('now', 'localtime') ; """
	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		return cursor.fetchall()


def is_cloud():
	cursor = conn.cursor()
	sql = """ select * from cloud_uuid """
	try:
		cursor.execute(sql)
	except Exception:
		return ""
	else:
		for cl_uuid in cursor.fetchall():
			return cl_uuid[0]


def return_firewall(serv):
	try:
		query_res = Server.get(Server.ip == serv).firewall_enable
	except Exception:
		return False
	else:
		return True if query_res == 1 else False


def select_geoip_country_codes():
	query = GeoipCodes.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


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


def delete_port_scanner_settings(server_id):
	query = PortScannerSettings.delete().where(PortScannerSettings.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_port_scanner_port(serv, user_group_id, port, service_name):
	cur_date = get_date.return_date('regular')
	try:
		PortScannerPorts.insert(
			serv=serv, port=port, user_group_id=user_group_id, service_name=service_name,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def select_ports(serv):
	cursor = conn.cursor()
	sql = """select port from port_scanner_ports where serv = '%s' """ % serv

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
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


def delete_ports(serv):
	query = PortScannerPorts.delete().where(PortScannerPorts.serv == serv)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_port_scanner_history(serv, port, port_status, service_name):
	cur_date = get_date.return_date('regular')
	try:
		PortScannerHistory.insert(
			serv=serv, port=port, status=port_status, service_name=service_name, date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def delete_alert_history(keep_interval: int, service: str):
	cur_date = get_date.return_date('regular', timedelta_minus=keep_interval)
	query = Alerts.delete().where(
		(Alerts.date < cur_date) & (Alerts.service == service)
	)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_smon_history():
	cur_date = get_date.return_date('regular', timedelta_minus=1)
	query = SmonHistory.delete().where(SmonHistory.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def delete_portscanner_history(keep_interval: int):
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


def add_provider_do(provider_name, provider_group, provider_token):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.insert(
			name=provider_name, type='do', group=provider_group, key=provider_token,
			create_date=cur_date, edit_date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def add_provider_aws(provider_name, provider_group, provider_key, provider_secret):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.insert(
			name=provider_name, type='aws', group=provider_group, key=provider_key, secret=provider_secret,
			create_date=cur_date, edit_date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def add_provider_gcore(provider_name, provider_group, provider_user, provider_pass):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.insert(
			name=provider_name, type='gcore', group=provider_group, key=provider_user,
			secret=provider_pass, create_date=cur_date, edit_date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def select_providers(user_group, **kwargs):
	if user_group == 1:
		query = ProvidersCreds.select()
	else:
		if kwargs.get('key'):
			query = ProvidersCreds.select().where(
				(ProvidersCreds.key == kwargs.get('key'))
				& (ProvidersCreds.group == user_group)
			)
		else:
			query = ProvidersCreds.select().where(ProvidersCreds.group == user_group)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_provider(provider_id):
	query = ProvidersCreds.delete().where(ProvidersCreds.id == provider_id)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def add_server_aws(
	region, instance_type, public_ip, floating_ip, volume_size, ssh_key_name, name, os, firewall,
	provider_id, group_id, status, delete_on_termination, volume_type
):
	cur_date = get_date.return_date('regular')
	try:
		ProvisionedServers.insert(
			region=region, instance_type=instance_type, public_ip=public_ip, floating_ip=floating_ip,
			volume_size=volume_size, volume_type=volume_type, ssh_key_name=ssh_key_name, name=name, os=os,
			firewall=firewall, provider_id=provider_id, group_id=group_id, delete_on_termination=delete_on_termination,
			type='aws', status=status, date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def add_server_gcore(
	project, region, instance_type, network_type, network_name, volume_size, ssh_key_name, name, os,
	firewall, provider_id, group_id, status, delete_on_termination, volume_type
):
	cur_date = get_date.return_date('regular')
	try:
		ProvisionedServers.insert(
			region=region, instance_type=instance_type, public_ip=network_type, network_name=network_name,
			volume_size=volume_size, volume_type=volume_type, ssh_key_name=ssh_key_name, name=name,
			os=os, firewall=firewall, provider_id=provider_id, group_id=group_id, type='gcore',
			delete_on_termination=delete_on_termination, project=project, status=status, date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def add_server_do(
	region, size, privet_net, floating_ip, ssh_ids, ssh_key_name, name, oss, firewall, monitoring, backup,
	provider_id, group_id, status
):
	cur_date = get_date.return_date('regular')
	try:
		ProvisionedServers.insert(
			region=region, instance_type=size, private_networking=privet_net, floating_ip=floating_ip,
			ssh_ids=ssh_ids, ssh_key_name=ssh_key_name, name=name, os=oss, firewall=firewall,
			monitoring=monitoring, backup=backup, provider_id=provider_id, group_id=group_id,
			type='do', status=status, date=cur_date
		).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def select_aws_server(server_id):
	prov_serv = ProvisionedServers.alias()
	query = (
		prov_serv.select(
			prov_serv.region, prov_serv.instance_type, prov_serv.public_ip, prov_serv.floating_ip, prov_serv.volume_size,
			prov_serv.ssh_key_name, prov_serv.name, prov_serv.os, prov_serv.firewall, prov_serv.provider_id,
			prov_serv.group_id, prov_serv.id, prov_serv.delete_on_termination, prov_serv.volume_type
		).where(prov_serv.id == server_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_gcore_server(server_id):
	prov_serv = ProvisionedServers.alias()
	query = (
		prov_serv.select(
			prov_serv.region, prov_serv.instance_type, prov_serv.public_ip, prov_serv.floating_ip, prov_serv.volume_size,
			prov_serv.ssh_key_name, prov_serv.name, prov_serv.os, prov_serv.firewall, prov_serv.provider_id,
			prov_serv.group_id, prov_serv.id, prov_serv.delete_on_termination, prov_serv.project, prov_serv.network_name,
			prov_serv.volume_type, prov_serv.name_template
		).where(prov_serv.id == server_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_do_server(server_id):
	prov_serv = ProvisionedServers.alias()
	query = (
		prov_serv.select(
			prov_serv.region, prov_serv.instance_type, prov_serv.private_networking, prov_serv.floating_ip,
			prov_serv.ssh_ids, prov_serv.ssh_key_name, prov_serv.name, prov_serv.os, prov_serv.firewall, prov_serv.backup,
			prov_serv.monitoring, prov_serv.provider_id, prov_serv.group_id, prov_serv.id
		).where(prov_serv.id == server_id))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_provisioning_server_status(status, user_group_id, name, provider_id, **kwargs):
	if kwargs.get('update_ip'):
		query = ProvisionedServers.update(status=status, IP=kwargs.get('update_ip')).where(
			(ProvisionedServers.name == name) & (ProvisionedServers.group_id == user_group_id) & (ProvisionedServers.provider_id == provider_id)
		)
	else:
		query = ProvisionedServers.update(status=status).where(
			(ProvisionedServers.name == name)
			& (ProvisionedServers.group_id == user_group_id)
			& (ProvisionedServers.provider_id == provider_id)
		)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_provisioning_server_gcore_name(name, template_name, user_group_id, provider_id):
	query = ProvisionedServers.update(name_template=template_name).where(
		(ProvisionedServers.name == name)
		& (ProvisionedServers.group_id == user_group_id)
		& (ProvisionedServers.provider_id == provider_id)
	)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_provisioning_server_error(status, user_group_id, name, provider_id):
	query = ProvisionedServers.update(last_error=status).where(
		(ProvisionedServers.name == name)
		& (ProvisionedServers.group_id == user_group_id)
		& (ProvisionedServers.provider_id == provider_id)
	)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_server_aws(
	region, size, public_ip, floating_ip, volume_size, ssh_name, workspace, oss, firewall, provider,
	group, status, server_id, delete_on_termination, volume_type
):
	query = ProvisionedServers.update(
		region=region, instance_type=size, public_ip=public_ip, floating_ip=floating_ip, volume_size=volume_size,
		ssh_key_name=ssh_name, name=workspace, os=oss, firewall=firewall, provider_id=provider, group_id=group,
		status=status, delete_on_termination=delete_on_termination, volume_type=volume_type
	).where(ProvisionedServers.id == server_id)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_server_gcore(
	region, size, network_type, network_name, volume_size, ssh_name, workspace, oss, firewall,
	provider, group, status, server_id, delete_on_termination, volume_type, project
):
	query = ProvisionedServers.update(
		region=region, instance_type=size, public_ip=network_type, network_name=network_name, volume_size=volume_size,
		ssh_key_name=ssh_name, name=workspace, os=oss, firewall=firewall, provider_id=provider, group_id=group,
		status=status, delete_on_termination=delete_on_termination, volume_type=volume_type, project=project
	).where(ProvisionedServers.id == server_id)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_server_do(
	size, privet_net, floating_ip, ssh_ids, ssh_name, oss, firewall, monitoring, backup, provider, group,
	status, server_id
):
	query = ProvisionedServers.update(
		instance_type=size, private_networking=privet_net, floating_ip=floating_ip, ssh_ids=ssh_ids,
		ssh_key_name=ssh_name, os=oss, firewall=firewall, monitoring=monitoring, backup=backup, provider_id=provider,
		group_id=group, status=status
	).where(ProvisionedServers.id == server_id)
	try:
		query.execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def delete_provisioned_servers(server_id):
	query = ProvisionedServers.delete().where(ProvisionedServers.id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_provisioned_servers(**kwargs):
	prov_serv = ProvisionedServers.alias()
	if kwargs.get('new'):
		query = (
			prov_serv.select(
				prov_serv.id, prov_serv.name, prov_serv.provider_id, prov_serv.type, prov_serv.group_id,
				prov_serv.instance_type, prov_serv.status, prov_serv.date, prov_serv.region, prov_serv.os,
				prov_serv.IP, prov_serv.last_error, prov_serv.name_template
			).where(
				(prov_serv.name == kwargs.get('new'))
				& (prov_serv.group_id == kwargs.get('group'))
				& (prov_serv.type == kwargs.get('type'))
			)
		)
	else:
		query = prov_serv.select(
			prov_serv.id, prov_serv.name, prov_serv.provider_id, prov_serv.type, prov_serv.group_id,
			prov_serv.instance_type, prov_serv.status, prov_serv.date, prov_serv.region, prov_serv.os,
			prov_serv.IP, prov_serv.last_error, prov_serv.name_template
		)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_aws_provider(provider_id):
	try:
		query_res = ProvidersCreds.get(ProvidersCreds.id == provider_id)
	except Exception:
		return ""
	else:
		return query_res.key, query_res.secret


def select_gcore_provider(provider_id):
	try:
		query_res = ProvidersCreds.get(ProvidersCreds.id == provider_id)
	except Exception:
		return ""
	else:
		return query_res.key, query_res.secret


def select_do_provider(provider_id):
	try:
		query_res = ProvidersCreds.get(ProvidersCreds.id == provider_id)
	except Exception:
		return ""
	else:
		return query_res.key


def update_do_provider(new_name, new_token, provider_id):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.update(
			name=new_name, key=new_token, edit_date=cur_date
		).where(ProvidersCreds.id == provider_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_gcore_provider(new_name, new_user, new_pass, provider_id):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.update(
			name=new_name, key=new_user, secret=new_pass, edit_date=cur_date
		).where(ProvidersCreds.id == provider_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def update_aws_provider(new_name, new_key, new_secret, provider_id):
	cur_date = get_date.return_date('regular')
	try:
		ProvidersCreds.update(
			name=new_name, key=new_key, secret=new_secret, edit_date=cur_date
		).where(ProvidersCreds.id == provider_id).execute()
		return True
	except Exception as e:
		out_error(e)
		return False


def is_serv_protected(serv):
	try:
		query_res = Server.get(Server.ip == serv)
	except Exception:
		return ""
	else:
		return True if query_res.protected else False


def select_user_services(user_id):
	try:
		query_res = User.get(User.user_id == user_id).user_services
	except Exception as e:
		out_error(e)
		return ""
	else:
		return query_res


def update_user_services(services, user_id):
	try:
		User.update(user_services=services).where(User.user_id == user_id).execute()
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
		pass
	else:
		return result


def delete_service_settings(server_id: int):
	query = ServiceSetting.delete().where(ServiceSetting.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def insert_action_history(service: str, action: str, server_id: int, user_id: int, user_ip: str, server_ip: str, hostname: str):
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
		return False
	else:
		return True


def delete_action_history_for_period():
	time_period = get_setting('action_keep_history_range')
	cur_date = get_date.return_date('regular', timedelta_minus=time_period)
	query = ActionHistory.delete().where(ActionHistory.date < cur_date)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_action_history_by_server_id(server_id: int):
	query = ActionHistory.select().where(ActionHistory.server_id == server_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def select_action_history_by_user_id(user_id: int):
	query = ActionHistory.select().where(ActionHistory.user_id == user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


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


def insert_config_version(server_id: int, user_id: int, service: str, local_path: str, remote_path: str, diff: str):
	cur_date = get_date.return_date('regular')
	try:
		ConfigVersion.insert(
			server_id=server_id,
			user_id=user_id,
			service=service,
			local_path=local_path,
			remote_path=remote_path,
			diff=diff,
			date=cur_date
		).execute()
	except Exception as e:
		out_error(e)


def select_config_version(server_ip: str, service: str) -> str:
	server_id = select_server_id_by_ip(server_ip)
	query = ConfigVersion.select().where(
		(ConfigVersion.server_id == server_id)
		& (ConfigVersion.service == service)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_config_version(service: str, local_path: str):
	query_res = ConfigVersion.delete().where(
		(ConfigVersion.service == service)
		& (ConfigVersion.local_path == local_path)
	)
	try:
		query_res.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_remote_path_from_version(server_ip: str, service: str, local_path: str):
	server_id = select_server_id_by_ip(server_ip)
	try:
		query_res = ConfigVersion.get(
			(ConfigVersion.server_id == server_id)
			& (ConfigVersion.service == service)
			& (ConfigVersion.local_path == local_path)
		).remote_path
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_system_info(
	server_id: int, os_info: str, sys_info: str, cpu: str, ram: str, network: str, disks: str
):
	try:
		SystemInfo.insert(
			server_id=server_id, os_info=os_info, sys_info=sys_info, cpu=cpu, ram=ram, network=network, disks=disks
		).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)


def delete_system_info(server_id: int):
	query = SystemInfo.delete().where(SystemInfo.server_id == server_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def select_one_system_info(server_id: int):
	query = SystemInfo.select().where(SystemInfo.server_id == server_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_system_info():
	query = SystemInfo.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def is_system_info(server_id):
	try:
		query_res = SystemInfo.get(SystemInfo.server_id == server_id).server_id
	except Exception:
		return True
	else:
		if query_res != '':
			return False
		else:
			return True


def select_os_info(server_id):
	try:
		query_res = SystemInfo.get(SystemInfo.server_id == server_id).os_info
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_services():
	query = Services.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


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


def insert_user_name(user_name):
	try:
		UserName.insert(UserName=user_name).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_user_name():
	try:
		query_res = UserName.get().UserName
	except Exception:
		return False
	else:
		return query_res


def get_super_admin_count() -> int:
	query = UserGroups.select(UserGroups.user_id, UserGroups.user_role_id).distinct().where(UserGroups.user_role_id == 1).group_by(UserGroups.user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		try:
			return len(list(query_res))
		except Exception as e:
			raise Exception(f'error: {e}')


def update_user_name(user_name):
	user_update = UserName.update(UserName=user_name)
	try:
		user_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_user_status(status, plan, method):
	user_update = UserName.update(Status=status, Method=method, Plan=plan)
	try:
		user_update.execute()
	except Exception:
		return False
	else:
		return True


def select_user_status():
	try:
		query_res = UserName.get().Status
	except Exception:
		return False
	else:
		return query_res


def check_user_status():
	try:
		UserName.get().Status
	except Exception as e:
		raise Exception(str(e))
	else:
		return True


def select_user_plan():
	try:
		query_res = UserName.get().Plan
	except Exception:
		return False
	else:
		return query_res


def select_user_all():
	try:
		query_res = UserName.select()
	except Exception:
		return False
	else:
		return query_res


def insert_new_git(server_id, service_id, repo, branch, period, cred, description):
	try:
		GitSetting.insert(
			server_id=server_id, service_id=service_id, repo=repo, branch=branch, period=period,
			cred_id=cred, description=description
		).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_gits(**kwargs):
	if kwargs.get("server_id") is not None and kwargs.get("service_id") is not None:
		query = GitSetting.select().where(
			(GitSetting.server_id == kwargs.get("server_id")) & (GitSetting.service_id == kwargs.get("service_id")))
	else:
		query = GitSetting.select().order_by(GitSetting.id)

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def delete_git(git_id):
	query = GitSetting.delete().where(GitSetting.id == git_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_users_emails_by_group_id(group_id: int):
	query = User.select(User.email).where((User.groups == group_id) & (User.role != 'guest'))
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_user_email_by_uuid(uuid: str) -> str:
	user_id = get_user_id_by_uuid(uuid)
	try:
		query_res = User.get(User.user_id == user_id).email
	except Exception as e:
		out_error(e)
		return ""
	else:
		return query_res


def select_checker_settings(service_id: int):
	query = CheckerSetting.select().where(CheckerSetting.service_id == service_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_checker_settings_for_server(service_id: int, server_id: int):
	query = CheckerSetting.select().where(
		(CheckerSetting.service_id == service_id)
		& (CheckerSetting.server_id == server_id)
	)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def insert_new_checker_setting_for_server(server_ip: str) -> None:
	server_id = ()
	try:
		server_id = Server.get(Server.ip == server_ip).server_id
	except Exception as e:
		out_error(e)

	for service_id in range(1, 5):
		CheckerSetting.insert(
			server_id=server_id, service_id=service_id
		).on_conflict_ignore().execute()


def update_haproxy_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, backend_alert: int,
	maxconn_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, service_alert=service_alert,
		backend_alert=backend_alert, maxconn_alert=maxconn_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_keepalived_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, backend_alert: int,
	setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id,
		service_alert=service_alert, backend_alert=backend_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def update_service_checker_settings(
	email: int, telegram_id: int, slack_id: int, pd_id: int, service_alert: int, setting_id: int
) -> bool:
	settings_update = CheckerSetting.update(
		email=email, telegram_id=telegram_id, slack_id=slack_id, pd_id=pd_id, service_alert=service_alert
	).where(CheckerSetting.id == setting_id)
	try:
		settings_update.execute()
	except Exception:
		return False
	else:
		return True


def select_provisioning_params():
	query = ProvisionParam.select()

	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
		return
	else:
		return query_res


def select_service(slug: str) -> str:
	try:
		query_res = Services.get(Services.slug == slug)
	except Exception as e:
		out_error(e)
		return 'there is no service'
	else:
		return query_res


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


def select_checker_service_status(server_id: int, service_id: int, service_check: str) -> int:
	try:
		service_check_status = ServiceStatus.get(
			(ServiceStatus.server_id == server_id)
			& (ServiceStatus.service_id == service_id)
			& (ServiceStatus.service_check == service_check)
		).status
	except Exception as e:
		return out_error(e)
	else:
		return service_check_status


def select_checker_services_status() -> tuple:
	try:
		services_check_status = ServiceStatus.select().execute()
	except Exception as e:
		return out_error(e)
	else:
		return services_check_status


def inset_or_update_service_status(
		server_id: int, service_id: int, service_check: str, status: int
) -> None:
	query = ServiceStatus.insert(
		server_id=server_id, service_id=service_id, service_check=service_check, status=status
	).on_conflict('replace')
	try:
		query.execute()
	except Exception as e:
		out_error(e)


def update_smon_ssl_expire_date(smon_id: str, expire_date: str) -> None:
	SMON_update = SMON.update(ssl_expire_date=expire_date).where(SMON.id == smon_id)
	try:
		SMON_update.execute()
	except Exception as e:
		out_error(e)


def update_smon_alert_status(smon_id: str, alert_value: int, alert: str) -> None:
	if alert == 'ssl_expire_warning_alert':
		SMON_update = SMON.update(ssl_expire_warning_alert=alert_value).where(SMON.id == smon_id)
	else:
		SMON_update = SMON.update(ssl_expire_critical_alert=alert_value).where(SMON.id == smon_id)
	try:
		SMON_update.execute()
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


def update_user_role(user_id: int, group_id: int, role_id: int) -> None:
	try:
		UserGroups.insert(user_id=user_id, user_group_id=group_id, user_role_id=role_id).on_conflict('replace').execute()
	except Exception as e:
		out_error(e)


def get_role_id(user_id: int, group_id: int) -> int:
	try:
		role_id = UserGroups.get((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
	except Exception as e:
		out_error(e)
	else:
		return int(role_id.user_role_id)


def is_user_super_admin(user_id: int) -> bool:
	query = UserGroups.select().where(UserGroups.user_id == user_id)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		for i in query_res:
			if i.user_role_id == 1:
				return True
		else:
			return False
