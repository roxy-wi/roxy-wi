#!/usr/bin/env python3
import distro
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
			'desc': 'The path for NGINX logs', 'group': '1'},
		{'param': 'nginx_stats_user', 'value': 'admin', 'section': 'nginx', 'desc': 'Username for accessing NGINX stats page',
			'group': '1'},
		{'param': 'nginx_stats_password', 'value': 'password', 'section': 'nginx',
			'desc': 'Password for Stats web page NGINX', 'group': '1'},
		{'param': 'nginx_stats_port', 'value': '8086', 'section': 'nginx', 'desc': 'Stats port for web page NGINX',
			'group': '1'},
		{'param': 'nginx_stats_page', 'value': 'stats', 'section': 'nginx', 'desc': 'URI Stats for web page NGINX',
			'group': '1'},
		{'param': 'nginx_dir', 'value': '/etc/nginx/', 'section': 'nginx',
			'desc': 'Path to the NGINX directory with config files', 'group': '1'},
		{'param': 'nginx_config_path', 'value': '/etc/nginx/nginx.conf', 'section': 'nginx',
			'desc': 'Path to the main NGINX configuration file', 'group': '1'},
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
		{'param': 'smon_check_interval', 'value': '1', 'section': 'monitoring', 'desc': 'Check interval for SMON (in minutes)',
			'group': '1'},
		{'param': 'port_scan_interval', 'value': '5', 'section': 'monitoring',
			'desc': 'Check interval for Port scanner (in minutes)', 'group': '1'},
		{'param': 'portscanner_keep_history_range', 'value': '14', 'section': 'monitoring',
			'desc': 'Retention period for Port scanner history', 'group': '1'},
		{'param': 'smon_keep_history_range', 'value': '14', 'section': 'monitoring',
			'desc': 'Retention period for SMON history', 'group': '1'},
		{'param': 'checker_keep_history_range', 'value': '14', 'section': 'monitoring',
			'desc': 'Retention period for Checker history', 'group': '1'},
		{'param': 'checker_maxconn_threshold', 'value': '90', 'section': 'monitoring',
			'desc': 'Threshold value for alerting, in %', 'group': '1'},
		{'param': 'checker_check_interval', 'value': '1', 'section': 'monitoring',
			'desc': 'Check interval for Checker (in minutes)', 'group': '1'},
		{'param': 'rabbitmq_host', 'value': '127.0.0.1', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server host', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_port', 'value': '5672', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server port', 'group': '1'},
		{'param': 'rabbitmq_vhost', 'value': '/', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server vhost', 'group': '1'},
		{'param': 'rabbitmq_queue', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server queue', 'group': '1'},
		{'param': 'rabbitmq_user', 'value': 'roxy-wi', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user', 'group': '1'},
		{'param': 'rabbitmq_password', 'value': 'roxy-wi123', 'section': 'rabbitmq', 'desc': 'RabbitMQ-server user password', 'group': '1'},
		{'param': 'apache_path_logs', 'value': '/var/log/httpd/', 'section': 'apache',
			'desc': 'The path for Apache logs', 'group': '1'},
		{'param': 'apache_stats_user', 'value': 'admin', 'section': 'apache',
			'desc': 'Username for accessing Apache stats page', 'group': '1'},
		{'param': 'apache_stats_password', 'value': 'password', 'section': 'apache',
			'desc': 'Password for Apache stats webpage', 'group': '1'},
		{'param': 'apache_stats_port', 'value': '8087', 'section': 'apache', 'desc': 'Stats port for webpage Apache',
			'group': '1'},
		{'param': 'apache_stats_page', 'value': 'stats', 'section': 'apache', 'desc': 'URI Stats for webpage Apache',
			'group': '1'},
		{'param': 'apache_dir', 'value': '/etc/httpd/', 'section': 'apache',
			'desc': 'Path to the Apache directory with config files', 'group': '1'},
		{'param': 'apache_config_path', 'value': '/etc/httpd/conf/httpd.conf', 'section': 'apache',
			'desc': 'Path to the main Apache configuration file', 'group': '1'},
		{'param': 'apache_container_name', 'value': 'apache', 'section': 'apache',
			'desc': 'Docker container name for Apache service', 'group': '1'},
	]
	try:
		Setting.insert_many(data_source).on_conflict_ignore().execute()
	except Exception as e:
		print(str(e))

	data_source = [
		{'username': 'admin', 'email': 'admin@localhost', 'password': '21232f297a57a5a743894a0e4a801fc3', 'role': 'superAdmin', 'groups': '1'},
		{'username': 'editor', 'email': 'editor@localhost', 'password': '5aee9dbd2a188839105073571bee1b1f', 'role': 'admin', 'groups': '1'},
		{'username': 'guest', 'email': 'guest@localhost', 'password': '084e0343a0486ff05530df6c705c8bb4', 'role': 'guest', 'groups': '1'}
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
		{'service_id': 1, 'service': 'HAProxy'},
		{'service_id': 2, 'service': 'NGINX'},
		{'service_id': 3, 'service': 'Keepalived'},
		{'service_id': 4, 'service': 'Apache'},
	]

	try:
		Services.insert_many(data_source).on_conflict_ignore().execute()
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


def update_db_v_3_4_5_22():
	try:
		Version.insert(version='3.4.5.2').execute()
	except Exception as e:
		print('Cannot insert version %s' % e)


# Needs for updating user_group. Do not delete
def update_db_v_4_3_0(**kwargs):
	try:
		UserGroups.insert_from(User.select(User.user_id, User.groups),
								fields=[UserGroups.user_id, UserGroups.user_group_id]).on_conflict_ignore().execute()
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or str(e) == '(1060, "Duplicate column name \'haproxy\'")':
				print('Updating... go to version 4.3.1')
			else:
				print("An error occurred:", e)


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
		print(str(e))
	else:
		groups = query_res

	for g in groups:
		try:
			data_source = [
				{'param': 'nginx_container_name', 'value': 'nginx', 'section': 'nginx',
				 'desc': 'Docker container name for NGINX service',
				 'group': g.group_id},
				{'param': 'haproxy_container_name', 'value': 'haproxy', 'section': 'haproxy',
				 'desc': 'Docker container name for HAProxy service',
				 'group': g.group_id},
				{'param': 'apache_path_logs', 'value': '/var/log/httpd/', 'section': 'apache',
				 'desc': 'The path for Apache logs', 'group': g.group_id},
				{'param': 'apache_stats_user', 'value': 'admin', 'section': 'apache',
				 'desc': 'Username for accessing Apache stats page', 'group': g.group_id},
				{'param': 'apache_stats_password', 'value': 'password', 'section': 'apache',
				 'desc': 'Password for Apache stats webpage', 'group': g.group_id},
				{'param': 'apache_stats_port', 'value': '8087', 'section': 'apache', 'desc': 'Stats port for webpage Apache',
				 'group': g.group_id},
				{'param': 'apache_stats_page', 'value': 'stats', 'section': 'apache', 'desc': 'URI Stats for webpage Apache',
				 'group': g.group_id},
				{'param': 'apache_dir', 'value': '/etc/httpd/', 'section': 'apache',
				 'desc': 'Path to the Apache directory with config files', 'group': g.group_id},
				{'param': 'apache_config_path', 'value': '/etc/httpd/conf/httpd.conf', 'section': 'apache',
				 'desc': 'Path to the main Apache configuration file', 'group': g.group_id},
				{'param': 'apache_container_name', 'value': 'apache', 'section': 'apache',
				 'desc': 'Docker container name for Apache service', 'group': g.group_id},
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
	query = Setting.update(value='/etc/nginx/').where(Setting.param == 'nginx_dir')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 5.4.3-1")


def update_db_v_6_0(**kwargs):
	cursor = conn.cursor()
	sql = list()
	sql.append("alter table servers add column apache integer default 0")
	sql.append("alter table servers add column apache_active integer default 0")
	sql.append("alter table servers add column apache_alert integer default 0")
	sql.append("alter table servers add column apache_metrics integer default 0")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 6.0.0.0')


def update_db_v_6_0_1(**kwargs):
	query = Groups.update(name='Default').where(Groups.group_id == '1')
	try:
		query.execute()
	except Exception as e:
		print("An error occurred:", e)
	else:
		if kwargs.get('silent') != 1:
			print("Updating... DB has been updated to version 6.0.0.0-1")


def update_ver():
	query = Version.update(version='6.0.2.0')
	try:
		query.execute()
	except:
		print('Cannot update version')


def update_all():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_4_3_0()
	update_db_v_5_1_3()
	update_db_v_5_2_4()
	update_db_v_5_2_4_1()
	update_db_v_5_2_5_1()
	update_db_v_5_2_5_2()
	update_db_v_5_2_5_3()
	update_db_v_5_2_6()
	update_db_v_5_3_0()
	update_db_v_5_3_1()
	update_db_v_5_3_2_2()
	update_db_v_5_4_2()
	update_db_v_5_4_3()
	update_db_v_5_4_3_1()
	update_db_v_6_0()
	update_db_v_6_0_1()
	update_ver()


def update_all_silent():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_4_3_0(silent=1)
	update_db_v_5_1_3(silent=1)
	update_db_v_5_2_4(silent=1)
	update_db_v_5_2_4_1(silent=1)
	update_db_v_5_2_5_1(silent=1)
	update_db_v_5_2_5_2(silent=1)
	update_db_v_5_2_5_3(silent=1)
	update_db_v_5_2_6(silent=1)
	update_db_v_5_3_0(silent=1)
	update_db_v_5_3_1(silent=1)
	update_db_v_5_3_2_2(silent=1)
	update_db_v_5_4_2(silent=1)
	update_db_v_5_4_3(silent=1)
	update_db_v_5_4_3_1(silent=1)
	update_db_v_6_0(silent=1)
	update_db_v_6_0_1(silent=1)
	update_ver()


if __name__ == "__main__":
	create_tables()
	default_values()
	update_all()
