#!/usr/bin/env python3
import distro

from modules.db.db_model import *


def default_values():
	if distro.id() == 'ubuntu':
		apache_dir = 'apache2'
	else:
		apache_dir = 'httpd'
	data_source = [
		{'param': 'time_zone', 'value': 'UTC', 'section': 'main', 'desc': 'Time Zone', 'group': '1'},
		{'param': 'proxy', 'value': '', 'section': 'main', 'desc': 'IP address and port of the proxy server. Use proto://ip:port', 'group': '1'},
		{'param': 'session_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user session (in days)', 'group': '1'},
		{'param': 'token_ttl', 'value': '5', 'section': 'main', 'desc': 'TTL for a user token (in days)', 'group': '1'},
		{'param': 'tmp_config_path', 'value': '/tmp/', 'section': 'main',
			'desc': 'Path to the temporary directory. A valid path should be specified as the value of this parameter. '
					'The directory must be owned by the user specified in SSH settings', 'group': '1'},
		{'param': 'cert_path', 'value': '/etc/ssl/certs/', 'section': 'main',
			'desc': 'Path to SSL dir. Folder owner must be a user which set in the SSH settings. Path must exist', 'group': '1'},
		{'param': 'ssl_local_path', 'value': 'certs', 'section': 'main',
			'desc': 'Path to the directory with the saved local SSL certificates. The value of this parameter is '
					'specified as a relative path beginning with $HOME_ROXY_WI/app/', 'group': '1'},
		{'param': 'lists_path', 'value': 'lists', 'section': 'main',
			'desc': 'Path to the black and the wild list. The value of this parameter should be specified as a relative path beginning with $HOME_ROXY-WI',
			'group': '1'},
		{'param': 'maxmind_key', 'value': '', 'section': 'main', 'desc': 'License key for downloading GeoIP DB. You can create it on maxmind.com', 'group': '1'},
		{'param': 'haproxy_path_logs', 'value': '/var/log/haproxy/', 'section': 'haproxy', 'desc': 'The path for HAProxy logs', 'group': '1'},
		{'param': 'syslog_server_enable', 'value': '0', 'section': 'logs', 'desc': 'Enable getting logs from a syslog server', 'group': '1'},
		{'param': 'syslog_server', 'value': '', 'section': 'logs', 'desc': 'IP address of the syslog_server', 'group': '1'},
		{'param': 'log_time_storage', 'value': '14', 'section': 'logs', 'desc': 'Retention period for user activity logs (in days)', 'group': '1'},
		{'param': 'stats_user', 'value': 'admin', 'section': 'haproxy', 'desc': 'Username for accessing HAProxy stats page', 'group': '1'},
		{'param': 'stats_password', 'value': 'password', 'section': 'haproxy', 'desc': 'Password for accessing HAProxy stats page', 'group': '1'},
		{'param': 'stats_port', 'value': '8085', 'section': 'haproxy', 'desc': 'Port for HAProxy stats page', 'group': '1'},
		{'param': 'stats_page', 'value': 'stats', 'section': 'haproxy', 'desc': 'URI for HAProxy stats page', 'group': '1'},
		{'param': 'haproxy_dir', 'value': '/etc/haproxy', 'section': 'haproxy', 'desc': 'Path to the HAProxy directory', 'group': '1'},
		{'param': 'haproxy_config_path', 'value': '/etc/haproxy/haproxy.cfg', 'section': 'haproxy', 'desc': 'Path to the HAProxy configuration file', 'group': '1'},
		{'param': 'server_state_file', 'value': '/etc/haproxy/haproxy.state', 'section': 'haproxy', 'desc': 'Path to the HAProxy state file', 'group': '1'},
		{'param': 'haproxy_sock', 'value': '/var/run/haproxy.sock', 'section': 'haproxy', 'desc': 'Socket port for HAProxy', 'group': '1'},
		{'param': 'haproxy_sock_port', 'value': '1999', 'section': 'haproxy', 'desc': 'HAProxy sock port', 'group': '1'},
		{'param': 'haproxy_container_name', 'value': 'haproxy', 'section': 'haproxy', 'desc': 'Docker container name for HAProxy service', 'group': '1'},
		{'param': 'apache_log_path', 'value': f'/var/log/{apache_dir}/', 'section': 'logs', 'desc': 'Path to Apache logs. Apache service for Roxy-WI', 'group': '1'},
		{'param': 'nginx_path_logs', 'value': '/var/log/nginx/', 'section': 'nginx', 'desc': 'The path for NGINX logs', 'group': '1'},
		{'param': 'nginx_stats_user', 'value': 'admin', 'section': 'nginx', 'desc': 'Username for accessing NGINX stats page', 'group': '1'},
		{'param': 'nginx_stats_password', 'value': 'password', 'section': 'nginx', 'desc': 'Password for Stats web page NGINX', 'group': '1'},
		{'param': 'nginx_stats_port', 'value': '8086', 'section': 'nginx', 'desc': 'Stats port for web page NGINX', 'group': '1'},
		{'param': 'nginx_stats_page', 'value': 'stats', 'section': 'nginx', 'desc': 'URI Stats for web page NGINX', 'group': '1'},
		{'param': 'nginx_dir', 'value': '/etc/nginx/', 'section': 'nginx', 'desc': 'Path to the NGINX directory with config files', 'group': '1'},
		{'param': 'nginx_config_path', 'value': '/etc/nginx/nginx.conf', 'section': 'nginx', 'desc': 'Path to the main NGINX configuration file', 'group': '1'},
		{'param': 'nginx_container_name', 'value': 'nginx', 'section': 'nginx', 'desc': 'Docker container name for NGINX service', 'group': '1'},
		{'param': 'ldap_enable', 'value': '0', 'section': 'ldap', 'desc': 'Enable LDAP', 'group': '1'},
		{'param': 'ldap_server', 'value': '', 'section': 'ldap', 'desc': 'IP address of the LDAP server', 'group': '1'},
		{'param': 'ldap_port', 'value': '389', 'section': 'ldap', 'desc': 'LDAP port (port 389 or 636 is used by default)', 'group': '1'},
		{'param': 'ldap_user', 'value': '', 'section': 'ldap', 'desc': 'LDAP username. Format: user@domain.com', 'group': '1'},
		{'param': 'ldap_password', 'value': '', 'section': 'ldap', 'desc': 'LDAP password', 'group': '1'},
		{'param': 'ldap_base', 'value': '', 'section': 'ldap', 'desc': 'Base domain. Example: dc=domain, dc=com', 'group': '1'},
		{'param': 'ldap_domain', 'value': '', 'section': 'ldap', 'desc': 'LDAP domain for logging in', 'group': '1'},
		{'param': 'ldap_class_search', 'value': 'user', 'section': 'ldap', 'desc': 'Class for searching the user', 'group': '1'},
		{'param': 'ldap_user_attribute', 'value': 'userPrincipalName', 'section': 'ldap', 'desc': 'Attribute to search users by', 'group': '1'},
		{'param': 'ldap_search_field', 'value': 'mail', 'section': 'ldap', 'desc': 'User\'s email address', 'group': '1'},
		{'param': 'ldap_type', 'value': '0', 'section': 'ldap', 'desc': 'Use LDAPS', 'group': '1'},
		{'param': 'smon_check_interval', 'value': '1', 'section': 'monitoring', 'desc': 'Check interval for SMON (in minutes)', 'group': '1'},
		{'param': 'port_scan_interval', 'value': '5', 'section': 'monitoring', 'desc': 'Check interval for Port scanner (in minutes)', 'group': '1'},
		{'param': 'portscanner_keep_history_range', 'value': '14', 'section': 'monitoring', 'desc': 'Retention period for Port scanner history', 'group': '1'},
		{'param': 'smon_keep_history_range', 'value': '14', 'section': 'monitoring', 'desc': 'Retention period for SMON history', 'group': '1'},
		{'param': 'checker_keep_history_range', 'value': '14', 'section': 'monitoring', 'desc': 'Retention period for Checker history', 'group': '1'},
		{'param': 'action_keep_history_range', 'value': '30', 'section': 'monitoring', 'desc': 'Retention period for Action history', 'group': '1'},
		{'param': 'checker_maxconn_threshold', 'value': '90', 'section': 'monitoring', 'desc': 'Threshold value for alerting, in %', 'group': '1'},
		{'param': 'checker_check_interval', 'value': '1', 'section': 'monitoring', 'desc': 'Check interval for Checker (in minutes)', 'group': '1'},
		{'param': 'smon_ssl_expire_warning_alert', 'value': '14', 'section': 'monitoring', 'desc': 'Warning alert about a SSL certificate expiration (in days)', 'group': '1'},
		{'param': 'smon_ssl_expire_critical_alert', 'value': '7', 'section': 'monitoring', 'desc': 'Critical alert about a SSL certificate expiration (in days)', 'group': '1'},
		{'param': 'rabbitmq_host', 'value': '127.0.0.1', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server host', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_vhost', 'value': '/', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server vhost', 'group': '1'},
		{'param': 'rabbitmq_queue', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server queue', 'group': '1'},
		{'param': 'rabbitmq_user', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user', 'group': '1'},
		{'param': 'rabbitmq_password', 'value': 'roxy-wi123', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user password', 'group': '1'},
		{'param': 'apache_path_logs', 'value': '/var/log/httpd/', 'section': 'apache', 'desc': 'The path for Apache logs', 'group': '1'},
		{'param': 'apache_stats_user', 'value': 'admin', 'section': 'apache', 'desc': 'Username for accessing Apache stats page', 'group': '1'},
		{'param': 'apache_stats_password', 'value': 'password', 'section': 'apache', 'desc': 'Password for Apache stats webpage', 'group': '1'},
		{'param': 'apache_stats_port', 'value': '8087', 'section': 'apache', 'desc': 'Stats port for webpage Apache', 'group': '1'},
		{'param': 'apache_stats_page', 'value': 'stats', 'section': 'apache', 'desc': 'URI Stats for webpage Apache', 'group': '1'},
		{'param': 'apache_dir', 'value': '/etc/httpd/', 'section': 'apache', 'desc': 'Path to the Apache directory with config files', 'group': '1'},
		{'param': 'apache_config_path', 'value': '/etc/httpd/conf/httpd.conf', 'section': 'apache', 'desc': 'Path to the main Apache configuration file', 'group': '1'},
		{'param': 'apache_container_name', 'value': 'apache', 'section': 'apache', 'desc': 'Docker container name for Apache service', 'group': '1'},
		{'param': 'keepalived_config_path', 'value': '/etc/keepalived/keepalived.conf', 'section': 'keepalived', 'desc': 'Path to the main Keepalived configuration file', 'group': '1'},
		{'param': 'keepalived_path_logs', 'value': '/var/log/keepalived/', 'section': 'keepalived', 'desc': 'The path for Keepalived logs', 'group': '1'},
		{'param': 'mail_ssl', 'value': '0', 'section': 'mail', 'desc': 'Enable TLS', 'group': '1'},
		{'param': 'mail_from', 'value': '', 'section': 'mail', 'desc': 'Address of sender', 'group': '1'},
		{'param': 'mail_smtp_host', 'value': '', 'section': 'mail', 'desc': 'SMTP server address', 'group': '1'},
		{'param': 'mail_smtp_port', 'value': '25', 'section': 'mail', 'desc': 'SMTP server port', 'group': '1'},
		{'param': 'mail_smtp_user', 'value': '', 'section': 'mail', 'desc': 'User for auth', 'group': '1'},
		{'param': 'mail_smtp_password', 'value': '', 'section': 'mail', 'desc': 'Password for auth', 'group': '1'},
	]
	try:
		Setting.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'username': 'admin', 'email': 'admin@localhost', 'password': '21232f297a57a5a743894a0e4a801fc3', 'role': '1', 'groups': '1'},
		{'username': 'editor', 'email': 'editor@localhost', 'password': '5aee9dbd2a188839105073571bee1b1f', 'role': '2', 'groups': '1'},
		{'username': 'guest', 'email': 'guest@localhost', 'password': '084e0343a0486ff05530df6c705c8bb4', 'role': '4', 'groups': '1'}
	]

	try:
		if Role.get(Role.name == 'superAdmin').role_id == 1:
			create_users = False
		else:
			create_users = True
	except Exception:
		create_users = True

	try:
		if create_users:
			User.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'user_id': '1', 'user_group_id': '1', 'user_role_id': '1'},
		{'user_id': '2', 'user_group_id': '1', 'user_role_id': '2'},
		{'user_id': '3', 'user_group_id': '1', 'user_role_id': '4'}
	]

	try:
		if create_users:
			UserGroups.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'name': 'superAdmin', 'description': 'Has the highest level of administrative permissions and controls the actions of all other users'},
		{'name': 'admin', 'description': 'Has access everywhere except the Admin area'},
		{'name': 'user', 'description': 'Has the same rights as the admin but has no access to the Servers page'},
		{'name': 'guest', 'description': 'Read-only access'}
	]

	try:
		Role.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	try:
		Groups.insert(name='Default', description='All servers are included in this group by default', group_id=1).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'service_id': 1, 'service': 'HAProxy', 'slug': 'haproxy'},
		{'service_id': 2, 'service': 'NGINX', 'slug': 'nginx'},
		{'service_id': 3, 'service': 'Keepalived', 'slug': 'keepalived'},
		{'service_id': 4, 'service': 'Apache', 'slug': 'apache'},
	]

	try:
		Services.insert_many(data_source).on_conflict_ignore().execute()
	except Exception:
		Services.drop_table()
		Services.create_table()
		try:
			Services.insert_many(data_source).on_conflict_ignore().execute()
		except Exception as e:
			print(str(e))

	data_source = [
		{'param': 'aws', 'name': 'AWS', 'optgroup': 'aws', 'section': 'provider', 'provider': 'aws', 'image': '/inc/images/provisioning/providers/aws.svg'},
		{'param': 'do', 'name': 'DigitalOcearn', 'optgroup': 'do', 'section': 'provider', 'provider': 'do', 'image': '/inc/images/provisioning/providers/do.svg'},
		{'param': 'gcore', 'name': 'G-Core Labs', 'optgroup': 'gcore', 'section': 'provider', 'provider': 'gcore', 'image': '/inc/images/provisioning/providers/gcore.svg'},
		{'param': 'us-east-1', 'name': 'N. Virginia', 'optgroup': 'US East', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'us-east-2', 'name': 'Ohio', 'optgroup': 'US East', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'us-west-1', 'name': 'N. California', 'optgroup': 'US West', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'us-west-2', 'name': 'Oregon', 'optgroup': 'US West', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'af-south-1', 'name': 'Cape Town', 'optgroup': 'Africa', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/za.svg'},
		{'param': 'ap-east-1', 'name': 'Hong Kong', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/hk.svg'},
		{'param': 'ap-south-1', 'name': 'Mumbai', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/in.svg'},
		{'param': 'ap-northeast-2', 'name': 'Seoul', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/kr.svg'},
		{'param': 'ap-southeast-1', 'name': 'Singapore', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/sg.svg'},
		{'param': 'ap-southeast-2', 'name': 'Sydney', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/au.svg'},
		{'param': 'ap-northeast-1', 'name': 'Tokyo', 'optgroup': 'Asia Pacific', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/jp.svg'},
		{'param': 'ca-central-1', 'name': 'Central', 'optgroup': 'Canada', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/ca.svg'},
		{'param': 'eu-central-1', 'name': 'Frankfurt', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws',
			'image': '/inc/images/provisioning/flags/de.svg'},
		{'param': 'eu-west-1', 'name': 'Ireland', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/ie.svg'},
		{'param': 'eu-west-2', 'name': 'London', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/gb.svg'},
		{'param': 'eu-south-1', 'name': 'Milan', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/fr.svg'},
		{'param': 'eu-west-3', 'name': 'Paris', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/fr.svg'},
		{'param': 'eu-north-1', 'name': 'Stockholm', 'optgroup': 'Europe', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/se.svg'},
		{'param': 'me-south-1', 'name': 'Bahrain', 'optgroup': 'Middle East', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/bh.svg'},
		{'param': 'sa-east-1', 'name': 'São Paulo', 'optgroup': 'South America', 'section': 'region', 'provider': 'aws', 'image': '/inc/images/provisioning/flags/br.svg'},
		{'param': 'nyc1', 'name': 'New York 1', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'nyc2', 'name': 'New York 2', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'nyc3', 'name': 'New York 3', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'sfo1', 'name': 'San Francisco 1', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'sfo2', 'name': 'San Francisco 2', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'sfo3', 'name': 'San Francisco 3', 'optgroup': 'USA', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': 'tor1', 'name': 'Toronto 1', 'optgroup': 'Canada', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/ca.svg'},
		{'param': 'ams2', 'name': 'Amsterdam 2', 'optgroup': 'Europe', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/nl.svg'},
		{'param': 'ams3', 'name': 'Amsterdam 3', 'optgroup': 'Europe', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/nl.svg'},
		{'param': 'fra1', 'name': 'Frankfurt 1', 'optgroup': 'Europe', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/de.svg'},
		{'param': 'lon1', 'name': 'London 1', 'optgroup': 'Europe', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/gb.svg'},
		{'param': 'sgp1', 'name': 'Singapore 1', 'optgroup': 'Asia', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/sg.svg'},
		{'param': 'blr1', 'name': 'Bangalore 1', 'optgroup': 'Asia', 'section': 'region', 'provider': 'do', 'image': '/inc/images/provisioning/flags/bh.svg'},
		{'param': '68', 'name': 'Chicago', 'optgroup': 'Americas', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': '14', 'name': 'Manassas', 'optgroup': 'Americas', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': '35', 'name': 'Santa-Clara', 'optgroup': 'Americas', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/us.svg'},
		{'param': '91', 'name': 'Sao Paulo', 'optgroup': 'Americas', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/br.svg'},
		{'param': '64', 'name': 'Hong-Kong', 'optgroup': 'Asia-Pacific', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/hk.svg'},
		{'param': '18', 'name': 'Singapore', 'optgroup': 'Asia-Pacific', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/sg.svg'},
		{'param': '88', 'name': 'Sydney', 'optgroup': 'Asia-Pacific', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/au.svg'},
		{'param': '29', 'name': 'Tokyo', 'optgroup': 'Asia-Pacific', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/jp.svg'},
		{'param': '46', 'name': 'Almaty', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/kz.svg'},
		{'param': '26', 'name': 'Amsterdam', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/nl.svg'},
		{'param': '51', 'name': 'Amsterdam-2', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/nl.svg'},
		{'param': '38', 'name': 'Frankfurt', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/de.svg'},
		{'param': '120', 'name': 'Darmstadt', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/de.svg'},
		{'param': '50', 'name': 'Istanbul', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/tr.svg'},
		{'param': '84', 'name': 'Johannesburg', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/za.svg'},
		{'param': '6', 'name': 'Luxembourg', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/lu.svg'},
		{'param': '76', 'name': 'Luxembourg-2', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/lu.svg'},
		{'param': '56', 'name': 'Paris', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/fr.svg'},
		{'param': '100', 'name': 'Paris-2', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/fr.svg'},
		{'param': '80', 'name': 'Warsaw', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/pl.svg'},
		{'param': '116', 'name': 'Dubai', 'optgroup': 'EMEA', 'section': 'region', 'provider': 'gcore', 'image': '/inc/images/provisioning/flags/ae.svg'},
		{'param': '22', 'name': 'Khabarovsk', 'optgroup': 'Russia and CIS', 'section': 'region', 'provider': 'edge', 'image': '/inc/images/provisioning/flags/ru.svg'},
		{'param': '10', 'name': 'Moscow', 'optgroup': 'Russia and CIS', 'section': 'region', 'provider': 'edge', 'image': '/inc/images/provisioning/flags/ru.svg'},
		{'param': '42', 'name': 'Saint Petersburg', 'optgroup': 'Russia and CIS', 'section': 'region', 'provider': 'edge', 'image': '/inc/images/provisioning/flags/ru.svg'},
		{'param': '60', 'name': 'Yekaterinburg', 'optgroup': 'Russia and CIS', 'section': 'region', 'provider': 'edge', 'image': '/inc/images/provisioning/flags/ru.svg'},
		{'param': '72', 'name': 'Novosibirsk', 'optgroup': 'Russia and CIS', 'section': 'region', 'provider': 'edge', 'image': '/inc/images/provisioning/flags/ru.svg'},
		{'param': 'ubuntu-18-04', 'name': 'Ubuntu 18.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20-04', 'name': 'Ubuntu 20.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20-14', 'name': 'Ubuntu 20.14', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-22-04', 'name': 'Ubuntu 22.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-23-04', 'name': 'Ubuntu 23.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'centos-7', 'name': 'CentOS 7', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos-8', 'name': 'CentOS 8', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos-9', 'name': 'CentOS 9', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'debian-9', 'name': 'Debian 9', 'optgroup': 'Debian', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-10', 'name': 'Debian 10', 'optgroup': 'Debian', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-11', 'name': 'Debian 11', 'optgroup': 'Debian', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'amazon-2_lts', 'name': 'Amazon Linux 2', 'optgroup': 'Amazon Linux', 'section': 'image', 'provider': 'aws', 'image': '/inc/images/provisioning/providers/aws.svg'},
		{'param': 'ubuntu-18-04-x64', 'name': 'Ubuntu 18.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20-04-x64', 'name': 'Ubuntu 20.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20-14-x64', 'name': 'Ubuntu 20.14', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-22-04-x64', 'name': 'Ubuntu 22.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-23-04-x64', 'name': 'Ubuntu 23.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'centos-7-x64', 'name': 'CentOS 7', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos-stream-8-x64', 'name': 'CentOS 8 Stream', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos-stream-9-x64', 'name': 'CentOS 9 Stream', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'rockylinux-8-4-x64', 'name': 'RockyLinux 8.4', 'optgroup': 'RockyLinux', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/rocky-linux.svg'},
		{'param': 'rockylinux-8-x64', 'name': 'RockyLinux 8.5', 'optgroup': 'RockyLinux', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/rocky-linux.svg'},
		{'param': 'debian-9-x64', 'name': 'Debian 9', 'optgroup': 'Debian', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-10-x64', 'name': 'Debian 10', 'optgroup': 'Debian', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-11-x64', 'name': 'Debian 11', 'optgroup': 'Debian', 'section': 'image', 'provider': 'do', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'ubuntu-18.04-x64', 'name': 'Ubuntu 18.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20.04-x64', 'name': 'Ubuntu 20.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-20.10-x64', 'name': 'Ubuntu 20.10', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-22.04-x64', 'name': 'Ubuntu 22.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-22.10-x64', 'name': 'Ubuntu 22.10', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'ubuntu-23.04-x64', 'name': 'Ubuntu 23.04', 'optgroup': 'Ubuntu', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/ubuntu.svg'},
		{'param': 'centos-7-1811-x64-qcow2', 'name': 'CentOS 7.6', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos-7-2003-x64-qcow2', 'name': 'CentOS 7.8', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos8-stream-0210-x64', 'name': 'CentOS 8.4', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'centos9-stream-0330-x64', 'name': 'CentOS 9', 'optgroup': 'CentOS', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/centos.svg'},
		{'param': 'fedora-33-x64-qcow2', 'name': 'Fedora 33', 'optgroup': 'Fedora', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/fedora.svg'},
		{'param': 'fedora-34-x64-qcow2', 'name': 'Fedora 34', 'optgroup': 'Fedora', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/fedora.svg'},
		{'param': 'fedora-35-x64-qcow2', 'name': 'Fedora 35', 'optgroup': 'Fedora', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/fedora.svg'},
		{'param': 'debian-9.7-x64-qcow2', 'name': 'Debian 9.7', 'optgroup': 'Debian', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-10.1-x64-qcow2', 'name': 'Debian 10.1', 'optgroup': 'Debian', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-10.3-x64-qcow2', 'name': 'Debian 10.3', 'optgroup': 'Debian', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'debian-11.generic-x64-qcow2', 'name': 'Debian 11', 'optgroup': 'Debian', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/debian.svg'},
		{'param': 'windows-server-2019', 'name': 'Windows 2019', 'optgroup': 'Windows', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/windows.svg'},
		{'param': 'windows-server-2022', 'name': 'Windows 2022', 'optgroup': 'Windows', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/windows.svg'},
		{'param': 'sles15-SP2', 'name': 'SLES 15-SP2', 'optgroup': 'SUSE', 'section': 'image', 'provider': 'gcore', 'image': '/inc/images/provisioning/oss/suse.svg'},
		{'param': 's-1vcpu-1gb', 'name': 's-1vcpu-1gb', 'optgroup': 'Base', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-2gb', 'name': 's-2vcpu-2gb', 'optgroup': 'Base', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-4gb', 'name': 's-2vcpu-4gb', 'optgroup': 'Base', 'section': 'size', 'provider': 'do'},
		{'param': 's-4vcpu-8gb', 'name': 's-4vcpu-8gb', 'optgroup': 'Base', 'section': 'size', 'provider': 'do'},
		{'param': 's-8vcpu-16gb', 'name': 's-8vcpu-16gb', 'optgroup': 'Base', 'section': 'size', 'provider': 'do'},
		{'param': 's-1vcpu-1gb-intel', 'name': 's-1vcpu-1gb-intel', 'optgroup': 'Premium Intel', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-2gb-intel', 'name': 's-2vcpu-2gb-intel', 'optgroup': 'Premium Intel', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-4gb-intel', 'name': 's-2vcpu-4gb-intel', 'optgroup': 'Premium Intel', 'section': 'size', 'provider': 'do'},
		{'param': 's-4vcpu-8gb-intel', 'name': 's-4vcpu-8gb-intel', 'optgroup': 'Premium Intel', 'section': 'size', 'provider': 'do'},
		{'param': 's-8vcpu-16gb-intel', 'name': 's-8vcpu-16gb-intel', 'optgroup': 'Premium Intel', 'section': 'size', 'provider': 'do'},
		{'param': 's-1vcpu-1gb-amd', 'name': 's-1vcpu-1gb-amd', 'optgroup': 'Premium AMD', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-2gb-amd', 'name': 's-2vcpu-2gb-amd', 'optgroup': 'Premium AMD', 'section': 'size', 'provider': 'do'},
		{'param': 's-2vcpu-4gb-amd', 'name': 's-2vcpu-4gb-amd', 'optgroup': 'Premium AMD', 'section': 'size', 'provider': 'do'},
		{'param': 's-4vcpu-8gb-amd', 'name': 's-4vcpu-8gb-amd', 'optgroup': 'Premium AMD', 'section': 'size', 'provider': 'do'},
		{'param': 's-8vcpu-16gb-amd', 'name': 's-8vcpu-16gb-amd', 'optgroup': 'Premium AMD', 'section': 'size', 'provider': 'do'},
		{'param': 'g-2vcpu-8gb', 'name': 'g-2vcpu-8gb', 'optgroup': 'General Purpose', 'section': 'size', 'provider': 'do'},
		{'param': 'g-4vcpu-16gb', 'name': 'g-4vcpu-16gb', 'optgroup': 'General Purpose', 'section': 'size', 'provider': 'do'},
		{'param': 'g-8vcpu-32gb', 'name': 'g-8vcpu-32gb', 'optgroup': 'General Purpose', 'section': 'size', 'provider': 'do'},
		{'param': 'g-32vcpu-128gb', 'name': 'g-32vcpu-128gb', 'optgroup': 'General Purpose', 'section': 'size', 'provider': 'do'},
		{'param': 'g-40vcpu-160gb', 'name': 'g-40vcpu-160gb', 'optgroup': 'General Purpose', 'section': 'size', 'provider': 'do'},
		{'param': 'c-4-8gib', 'name': 'c-4-8gib', 'optgroup': 'CPU-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'c-8-16gib', 'name': 'c-8-16gib', 'optgroup': 'CPU-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'c-16-32gib', 'name': 'c-16-32gib', 'optgroup': 'CPU-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'c-32-64gib', 'name': 'c-32-64gib', 'optgroup': 'CPU-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-2vcpu-16gb', 'name': 'm-2vcpu-16gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-4vcpu-32gb', 'name': 'm-4vcpu-32gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-8vcpu-64gb', 'name': 'm-8vcpu-64gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-16vcpu-128gb', 'name': 'm-16vcpu-128gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-24vcpu-192gb', 'name': 'm-24vcpu-192gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-32vcpu-256gb', 'name': 'm-32vcpu-256gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'm-32vcpu-256gb', 'name': 'm-32vcpu-256gb', 'optgroup': 'Memory-Optimized', 'section': 'size', 'provider': 'do'},
		{'param': 'g1-standard-1-2', 'name': 'g1-standard-1-2', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-2-4', 'name': 'g1-standard-2-4', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-2-8', 'name': 'g1-standard-2-8', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-4-8', 'name': 'g1-standard-4-8', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-4-16', 'name': 'g1-standard-4-16', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-8-16', 'name': 'g1-standard-8-16', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-8-32', 'name': 'g1-standard-8-32', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-16-32', 'name': 'g1-standard-16-32', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-16-64', 'name': 'g1-standard-16-64', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-32-64', 'name': 'g1-standard-32-64', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-standard-32-128', 'name': 'g1-standard-32-128', 'optgroup': 'Standard', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-cpu-2-2', 'name': 'g1-cpu-2-2', 'optgroup': 'vCPU', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-cpu-4-4', 'name': 'g1-cpu-4-4', 'optgroup': 'vCPU', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-cpu-8-8', 'name': 'g1-cpu-8-8', 'optgroup': 'vCPU', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-cpu-16-16', 'name': 'g1-cpu-16-16', 'optgroup': 'vCPU', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-cpu-32-32', 'name': 'g1-cpu-32-32', 'optgroup': 'vCPU', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-memory-4-32', 'name': 'g1-memory-4-32', 'optgroup': 'Memory', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-memory-8-64', 'name': 'g1-memory-8-64', 'optgroup': 'Memory', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-memory-16-128', 'name': 'g1-memory-16-128', 'optgroup': 'Memory', 'section': 'size', 'provider': 'gcore'},
		{'param': 'g1-memory-32-256', 'name': 'g1-memory-32-256', 'optgroup': 'Memory', 'section': 'size', 'provider': 'gcore'},
		{'param': 'gp2', 'name': 'gp2', 'optgroup': 'General Purpose SSD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'gp3', 'name': 'gp3', 'optgroup': 'General Purpose SSD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'standard', 'name': 'standard', 'optgroup': 'Magnetic', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'io1', 'name': 'io1', 'optgroup': 'Provisioned IOPS SSD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'io2', 'name': 'io2', 'optgroup': 'Provisioned IOPS SSD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'sc1', 'name': 'sc1', 'optgroup': 'Cold HDD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'st1', 'name': 'st1', 'optgroup': 'Throughput Optimized HDD', 'section': 'volume_type', 'provider': 'aws'},
		{'param': 'standard', 'name': 'standard', 'optgroup': 'Standard network SSD', 'section': 'volume_type', 'provider': 'gcore'},
		{'param': 'ssd_hiiops', 'name': 'ssd_hiiops', 'optgroup': 'High IOPS SSD', 'section': 'volume_type', 'provider': 'gcore'},
		{'param': 'cold', 'name': 'cold', 'optgroup': 'HDD disk', 'section': 'volume_type', 'provider': 'gcore'},
	]

	try:
		ProvisionParam.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'code': 'RW', 'name': 'Rwanda'},
		{'code': 'SO', 'name': 'Somalia'},
		{'code': 'YE', 'name': 'Yemen'},
		{'code': 'IQ', 'name': 'Iraq'},
		{'code': 'SA', 'name': 'Saudi Arabia'},
		{'code': 'IR', 'name': 'Iran'},
		{'code': 'CY', 'name': 'Cyprus'},
		{'code': 'TZ', 'name': 'Tanzania'},
		{'code': 'SY', 'name': 'Syria'},
		{'code': 'AM', 'name': 'Armenia'},
		{'code': 'KE', 'name': 'Kenya'},
		{'code': 'CD', 'name': 'DR Congo'},
		{'code': 'DJ', 'name': 'Djibouti'},
		{'code': 'UG', 'name': 'Uganda'},
		{'code': 'CF', 'name': 'Central African Republic'},
		{'code': 'SC', 'name': 'Seychelles'},
		{'code': 'JO', 'name': 'Hashemite Kingdom of Jordan'},
		{'code': 'LB', 'name': 'Lebanon'},
		{'code': 'KW', 'name': 'Kuwait'},
		{'code': 'OM', 'name': 'Oman'},
		{'code': 'QA', 'name': 'Qatar'},
		{'code': 'BH', 'name': 'Bahrain'},
		{'code': 'AE', 'name': 'United Arab Emirates'},
		{'code': 'IL', 'name': 'Israel'},
		{'code': 'TR', 'name': 'Turkey'},
		{'code': 'ET', 'name': 'Ethiopia'},
		{'code': 'ER', 'name': 'Eritrea'},
		{'code': 'EG', 'name': 'Egypt'},
		{'code': 'SD', 'name': 'Sudan'},
		{'code': 'GR', 'name': 'Greece'},
		{'code': 'BI', 'name': 'Burundi'},
		{'code': 'EE', 'name': 'Estonia'},
		{'code': 'LV', 'name': 'Latvia'},
		{'code': 'AZ', 'name': 'Azerbaijan'},
		{'code': 'LT', 'name': 'Republic of Lithuania'},
		{'code': 'SJ', 'name': 'Svalbard and Jan Mayen'},
		{'code': 'GE', 'name': 'Georgia'},
		{'code': 'MD', 'name': 'Republic of Moldova'},
		{'code': 'BY', 'name': 'Belarus'},
		{'code': 'FI', 'name': 'Finland'},
		{'code': 'AX', 'name': 'Åland'},
		{'code': 'UA', 'name': 'Ukraine'},
		{'code': 'MK', 'name': 'North Macedonia'},
		{'code': 'HU', 'name': 'Hungary'},
		{'code': 'BG', 'name': 'Bulgaria'},
		{'code': 'AL', 'name': 'Albania'},
		{'code': 'PL', 'name': 'Poland'},
		{'code': 'RO', 'name': 'Romania'},
		{'code': 'XK', 'name': 'Kosovo'},
		{'code': 'ZW', 'name': 'Zimbabwe'},
		{'code': 'ZM', 'name': 'Zambia'},
		{'code': 'KM', 'name': 'Comoros'},
		{'code': 'MW', 'name': 'Malawi'},
		{'code': 'LS', 'name': 'Lesotho'},
		{'code': 'BW', 'name': 'Botswana'},
		{'code': 'MU', 'name': 'Mauritius'},
		{'code': 'SZ', 'name': 'Eswatini'},
		{'code': 'RE', 'name': 'Réunion'},
		{'code': 'ZA', 'name': 'South Africa'},
		{'code': 'YT', 'name': 'Mayotte'},
		{'code': 'MZ', 'name': 'Mozambique'},
		{'code': 'MG', 'name': 'Madagascar'},
		{'code': 'AF', 'name': 'Afghanistan'},
		{'code': 'PK', 'name': 'Pakistan'},
		{'code': 'BD', 'name': 'Bangladesh'},
		{'code': 'TM', 'name': 'Turkmenistan'},
		{'code': 'TJ', 'name': 'Tajikistan'},
		{'code': 'LK', 'name': 'Sri Lanka'},
		{'code': 'BT', 'name': 'Bhutan'},
		{'code': 'IN', 'name': 'India'},
		{'code': 'MV', 'name': 'Maldives'},
		{'code': 'IO', 'name': 'British Indian Ocean Territory'},
		{'code': 'NP', 'name': 'Nepal'},
		{'code': 'MM', 'name': 'Myanmar'},
		{'code': 'UZ', 'name': 'Uzbekistan'},
		{'code': 'KZ', 'name': 'Kazakhstan'},
		{'code': 'KG', 'name': 'Kyrgyzstan'},
		{'code': 'TF', 'name': 'French Southern Territories'},
		{'code': 'HM', 'name': 'Heard Island and McDonald Islands'},
		{'code': 'CC', 'name': 'Cocos [Keeling] Islands'},
		{'code': 'PW', 'name': 'Palau'},
		{'code': 'VN', 'name': 'Vietnam'},
		{'code': 'TH', 'name': 'Thailand'},
		{'code': 'ID', 'name': 'Indonesia'},
		{'code': 'LA', 'name': 'Laos'},
		{'code': 'TW', 'name': 'Taiwan'},
		{'code': 'PH', 'name': 'Philippines'},
		{'code': 'MY', 'name': 'Malaysia'},
		{'code': 'CN', 'name': 'China'},
		{'code': 'HK', 'name': 'Hong Kong'},
		{'code': 'BN', 'name': 'Brunei'},
		{'code': 'MO', 'name': 'Macao'},
		{'code': 'KH', 'name': 'Cambodia'},
		{'code': 'KR', 'name': 'South Korea'},
		{'code': 'JP', 'name': 'Japan'},
		{'code': 'KP', 'name': 'North Korea'},
		{'code': 'SG', 'name': 'Singapore'},
		{'code': 'CK', 'name': 'Cook Islands'},
		{'code': 'TL', 'name': 'East Timor'},
		{'code': 'RU', 'name': 'Russia'},
		{'code': 'MN', 'name': 'Mongolia'},
		{'code': 'AU', 'name': 'Australia'},
		{'code': 'CX', 'name': 'Christmas Island'},
		{'code': 'MH', 'name': 'Marshall Islands'},
		{'code': 'FM', 'name': 'Federated States of Micronesia'},
		{'code': 'PG', 'name': 'Papua New Guinea'},
		{'code': 'SB', 'name': 'Solomon Islands'},
		{'code': 'TV', 'name': 'Tuvalu'},
		{'code': 'NR', 'name': 'Nauru'},
		{'code': 'VU', 'name': 'Vanuatu'},
		{'code': 'NC', 'name': 'New Caledonia'},
		{'code': 'NF', 'name': 'Norfolk Island'},
		{'code': 'NZ', 'name': 'New Zealand'},
		{'code': 'FJ', 'name': 'Fiji'},
		{'code': 'LY', 'name': 'Libya'},
		{'code': 'CM', 'name': 'Cameroon'},
		{'code': 'SN', 'name': 'Senegal'},
		{'code': 'CG', 'name': 'Congo Republic'},
		{'code': 'PT', 'name': 'Portugal'},
		{'code': 'LR', 'name': 'Liberia'},
		{'code': 'CI', 'name': 'Ivory Coast'},
		{'code': 'GH', 'name': 'Ghana'},
		{'code': 'GQ', 'name': 'Equatorial Guinea'},
		{'code': 'NG', 'name': 'Nigeria'},
		{'code': 'BF', 'name': 'Burkina Faso'},
		{'code': 'TG', 'name': 'Togo'},
		{'code': 'GW', 'name': 'Guinea-Bissau'},
		{'code': 'MR', 'name': 'Mauritania'},
		{'code': 'BJ', 'name': 'Benin'},
		{'code': 'GA', 'name': 'Gabon'},
		{'code': 'SL', 'name': 'Sierra Leone'},
		{'code': 'ST', 'name': 'São Tomé and Príncipe'},
		{'code': 'GI', 'name': 'Gibraltar'},
		{'code': 'GM', 'name': 'Gambia'},
		{'code': 'GN', 'name': 'Guinea'},
		{'code': 'TD', 'name': 'Chad'},
		{'code': 'NE', 'name': 'Niger'},
		{'code': 'ML', 'name': 'Mali'},
		{'code': 'EH', 'name': 'Western Sahara'},
		{'code': 'TN', 'name': 'Tunisia'},
		{'code': 'ES', 'name': 'Spain'},
		{'code': 'MA', 'name': 'Morocco'},
		{'code': 'MT', 'name': 'Malta'},
		{'code': 'DZ', 'name': 'Algeria'},
		{'code': 'FO', 'name': 'Faroe Islands'},
		{'code': 'DK', 'name': 'Denmark'},
		{'code': 'IS', 'name': 'Iceland'},
		{'code': 'GB', 'name': 'United Kingdom'},
		{'code': 'CH', 'name': 'Switzerland'},
		{'code': 'SE', 'name': 'Sweden'},
		{'code': 'NL', 'name': 'Netherlands'},
		{'code': 'AT', 'name': 'Austria'},
		{'code': 'BE', 'name': 'Belgium'},
		{'code': 'DE', 'name': 'Germany'},
		{'code': 'LU', 'name': 'Luxembourg'},
		{'code': 'IE', 'name': 'Ireland'},
		{'code': 'MC', 'name': 'Monaco'},
		{'code': 'FR', 'name': 'France'},
		{'code': 'AD', 'name': 'Andorra'},
		{'code': 'LI', 'name': 'Liechtenstein'},
		{'code': 'JE', 'name': 'Jersey'},
		{'code': 'IM', 'name': 'Isle of Man'},
		{'code': 'GG', 'name': 'Guernsey'},
		{'code': 'SK', 'name': 'Slovakia'},
		{'code': 'CZ', 'name': 'Czechia'},
		{'code': 'NO', 'name': 'Norway'},
		{'code': 'VA', 'name': 'Vatican City'},
		{'code': 'SM', 'name': 'San Marino'},
		{'code': 'IT', 'name': 'Italy'},
		{'code': 'SI', 'name': 'Slovenia'},
		{'code': 'ME', 'name': 'Montenegro'},
		{'code': 'HR', 'name': 'Croatia'},
		{'code': 'BA', 'name': 'Bosnia and Herzegovina'},
		{'code': 'AO', 'name': 'Angola'},
		{'code': 'NA', 'name': 'Namibia'},
		{'code': 'SH', 'name': 'Saint Helena'},
		{'code': 'BV', 'name': 'Bouvet Island'},
		{'code': 'BB', 'name': 'Barbados'},
		{'code': 'CV', 'name': 'Cabo Verde'},
		{'code': 'GY', 'name': 'Guyana'},
		{'code': 'GF', 'name': 'French Guiana'},
		{'code': 'SR', 'name': 'Suriname'},
		{'code': 'PM', 'name': 'Saint Pierre and Miquelon'},
		{'code': 'GL', 'name': 'Greenland'},
		{'code': 'PY', 'name': 'Paraguay'},
		{'code': 'UY', 'name': 'Uruguay'},
		{'code': 'BR', 'name': 'Brazil'},
		{'code': 'FK', 'name': 'Falkland Islands'},
		{'code': 'GS', 'name': 'South Georgia and the South Sandwich Islands'},
		{'code': 'JM', 'name': 'Jamaica'},
		{'code': 'DO', 'name': 'Dominican Republic'},
		{'code': 'CU', 'name': 'Cuba'},
		{'code': 'MQ', 'name': 'Martinique'},
		{'code': 'BS', 'name': 'Bahamas'},
		{'code': 'BM', 'name': 'Bermuda'},
		{'code': 'AI', 'name': 'Anguilla'},
		{'code': 'TT', 'name': 'Trinidad and Tobago'},
		{'code': 'KN', 'name': 'St Kitts and Nevis'},
		{'code': 'DM', 'name': 'Dominica'},
		{'code': 'AG', 'name': 'Antigua and Barbuda'},
		{'code': 'LC', 'name': 'Saint Lucia'},
		{'code': 'TC', 'name': 'Turks and Caicos Islands'},
		{'code': 'AW', 'name': 'Aruba'},
		{'code': 'VG', 'name': 'British Virgin Islands'},
		{'code': 'VC', 'name': 'Saint Vincent and the Grenadines'},
		{'code': 'MS', 'name': 'Montserrat'},
		{'code': 'MF', 'name': 'Saint Martin'},
		{'code': 'BL', 'name': 'Saint Barthélemy'},
		{'code': 'GP', 'name': 'Guadeloupe'},
		{'code': 'GD', 'name': 'Grenada'},
		{'code': 'KY', 'name': 'Cayman Islands'},
		{'code': 'BZ', 'name': 'Belize'},
		{'code': 'SV', 'name': 'El Salvador'},
		{'code': 'GT', 'name': 'Guatemala'},
		{'code': 'HN', 'name': 'Honduras'},
		{'code': 'NI', 'name': 'Nicaragua'},
		{'code': 'CR', 'name': 'Costa Rica'},
		{'code': 'VE', 'name': 'Venezuela'},
		{'code': 'EC', 'name': 'Ecuador'},
		{'code': 'CO', 'name': 'Colombia'},
		{'code': 'PA', 'name': 'Panama'},
		{'code': 'HT', 'name': 'Haiti'},
		{'code': 'AR', 'name': 'Argentina'},
		{'code': 'CL', 'name': 'Chile'},
		{'code': 'BO', 'name': 'Bolivia'},
		{'code': 'PE', 'name': 'Peru'},
		{'code': 'MX', 'name': 'Mexico'},
		{'code': 'PF', 'name': 'French Polynesia'},
		{'code': 'PN', 'name': 'Pitcairn Islands'},
		{'code': 'KI', 'name': 'Kiribati'},
		{'code': 'TK', 'name': 'Tokelau'},
		{'code': 'TO', 'name': 'Tonga'},
		{'code': 'WF', 'name': 'Wallis and Futuna'},
		{'code': 'WS', 'name': 'Samoa'},
		{'code': 'NU', 'name': 'Niue'},
		{'code': 'MP', 'name': 'Northern Mariana Islands'},
		{'code': 'GU', 'name': 'Guam'},
		{'code': 'PR', 'name': 'Puerto Rico'},
		{'code': 'VI', 'name': 'U.S. Virgin Islands'},
		{'code': 'UM', 'name': 'U.S. Minor Outlying Islands'},
		{'code': 'AS', 'name': 'American Samoa'},
		{'code': 'CA', 'name': 'Canada'},
		{'code': 'US', 'name': 'United States'},
		{'code': 'PS', 'name': 'Palestine'},
		{'code': 'RS', 'name': 'Serbia'},
		{'code': 'AQ', 'name': 'Antarctica'},
		{'code': 'SX', 'name': 'Sint Maarten'},
		{'code': 'CW', 'name': 'Curaçao'},
		{'code': 'BQ', 'name': 'Bonaire'},
		{'code': 'SS', 'name': 'South Sudan'}
	]

	try:
		GeoipCodes.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))


# Needs for insert version in first time
def update_db_v_3_4_5_22():
	try:
		Version.insert(version='3.4.5.2').execute()
	except Exception as e:
		print('Cannot insert version %s' % e)


# Needs for updating user_group. Do not delete
def update_db_v_4_3_0():
	try:
		UserGroups.insert_from(
			User.select(User.user_id, User.groups), fields=[UserGroups.user_id, UserGroups.user_group_id]
		).on_conflict_ignore().execute()
	except Exception as e:
		if e.args[0] == 'duplicate column name: haproxy' or str(e) == '(1060, "Duplicate column name \'haproxy\'")':
			print('Updating... go to version 4.3.1')
		else:
			print("An error occurred:", e)


def update_db_v_6_0():
	cursor = conn.cursor()
	sql = list()
	sql.append("alter table servers add column apache integer default 0")
	sql.append("alter table servers add column apache_active integer default 0")
	sql.append("alter table servers add column apache_alert integer default 0")
	sql.append("alter table servers add column apache_metrics integer default 0")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception:
			pass
	else:
		print('Updating... DB has been updated to version 6.0.0.0')


def update_db_v_6_0_1():
	query = Groups.update(name='Default').where(Groups.group_id == '1')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.0.0.0-1")


def update_db_v_6_1_0():
	for service_id in range(1, 5):
		try:
			servers_id = Server.select(Server.server_id).where(Server.type_ip == 0).execute()
			for server_id in servers_id:
				CheckerSetting.insert(
					server_id=server_id, service_id=service_id
				).on_conflict_ignore().execute()
		except Exception as e:
			if e.args[0] == 'duplicate column name: haproxy' or str(e) == '(1060, "Duplicate column name \'haproxy\'")':
				print('Updating... go to version 6.1.0')
			else:
				print("An error occurred:", e)


def update_db_v_6_1_3():
	if mysql_enable == '1':
		cursor = conn.cursor()
		sql = list()
		sql.append("ALTER TABLE `waf_rules` ADD COLUMN service VARCHAR ( 64 ) DEFAULT 'haproxy'")
		sql.append("ALTER TABLE `waf_rules` drop CONSTRAINT serv")
		sql.append("ALTER TABLE `waf_rules` ADD CONSTRAINT UNIQUE (serv, rule_name, service)")
		for i in sql:
			try:
				cursor.execute(i)
			except Exception:
				pass
		else:
			print('Updating... DB has been updated to version 6.1.3.0')
	else:
		pass


def update_db_v_6_1_4():
	servers = Server.select()
	services = Services.select()
	for server in servers:
		for service in services:
			settings = ('restart', 'dockerized', 'haproxy_enterprise')
			for setting in settings:
				if service.slug == 'keepalived':
					continue
				if service.slug != 'haproxy' and setting == 'haproxy_enterprise':
					continue
				set_value = 0
				try:
					ServiceSetting.insert(
						server_id=server.server_id, service=service.slug, setting=setting, value=set_value
					).on_conflict_ignore().execute()
				except Exception:
					pass


def update_db_v_6_2_1():
	try:
		Setting.update(section='main').where(Setting.param == 'maxmind_key').execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.2.2.0")


def update_db_v_6_3_4():
	cursor = conn.cursor()
	sql = list()
	sql.append("alter table smon add column ssl_expire_warning_alert integer default 0")
	sql.append("alter table smon add column ssl_expire_critical_alert integer default 0")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception:
			pass
	else:
		print('Updating... DB has been updated to version 6.3.4.0')


def update_db_v_6_3_5():
	cursor = conn.cursor()
	sql = list()
	sql.append("ALTER TABLE `action_history` ADD COLUMN server_ip varchar(64);")
	sql.append("ALTER TABLE `action_history` ADD COLUMN hostname varchar(64);")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception:
			pass
	else:
		print("Updating... DB has been updated to version 6.3.5.0")


def update_db_v_6_3_6():
	cursor = conn.cursor()
	sql = list()
	sql.append("ALTER TABLE `user_groups` ADD COLUMN user_role_id integer;")
	if mysql_enable == '1':
		sql.append("update user_groups u_g  inner join user as u on u_g.user_id = u.id inner join role as r on r.name = u.role set user_role_id = r.id where u_g.user_role_id is NULL;")
		sql.append("update user u inner join role as r on r.name = u.role set u.role = r.id;")
	else:
		sql.append("update user_groups as u_g set user_role_id = (select r.id from role as r inner join user as u on u.role = r.name where u_g.user_id = u.id) where user_role_id is null;")
		sql.append("update user as u set role = (select r.id from role as r where r.name = u.role);")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception:
			pass
	else:
		print("Updating... DB has been updated to version 6.3.6.0")


def update_db_v_6_3_8():
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `smon` ADD COLUMN ssl_expire_date varchar(64);
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if e.args[0] == 'duplicate column name: ssl_expire_date' or str(e) == '(1060, "Duplicate column name \'ssl_expire_date\'")':
			print('Updating... DB has been updated to version 6.3.8')
		else:
			print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.3.8")


def update_db_v_6_3_9():
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `checker_setting` ADD COLUMN pd_id integer default 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if e.args[0] == 'duplicate column name: pd_id' or str(e) == '(1060, "Duplicate column name \'pd_id\'")':
			print('Updating... DB has been updated to version 6.3.9')
		else:
			print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.3.9")


def update_db_v_6_3_11():
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `smon` ADD COLUMN pd_channel_id integer default 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if e.args[0] == 'duplicate column name: pd_channel_id' or str(e) == '(1060, "Duplicate column name \'pd_channel_id\'")':
			print('Updating... DB has been updated to version 6.3.11')
		else:
			print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.3.11")


def update_db_v_6_3_12():
	try:
		ProvisionParam.delete().where(
			(ProvisionParam.provider == 'gcore') &
			(ProvisionParam.optgroup == 'Russia and CIS')
		).execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 6.3.12")

def update_ver():
	try:
		Version.update(version='6.3.12.0').execute()
	except Exception:
		print('Cannot update version')


def check_ver():
	try:
		ver = Version.get()
	except Exception as e:
		print(str(e))
	else:
		return ver.version


def update_all():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_4_3_0()
	update_db_v_6_0()
	update_db_v_6_0_1()
	update_db_v_6_1_0()
	update_db_v_6_1_3()
	update_db_v_6_1_4()
	update_db_v_6_2_1()
	update_db_v_6_3_4()
	update_db_v_6_3_5()
	update_db_v_6_3_6()
	update_db_v_6_3_8()
	update_db_v_6_3_9()
	update_db_v_6_3_11()
	update_db_v_6_3_12()
	update_ver()


if __name__ == "__main__":
	create_tables()
	default_values()
	update_all()
