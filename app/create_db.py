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
		 'desc': 'Path to the directory with SSL certificates. An existing path should be specified as the value of this parameter. The directory must be owned by the user specified in SSH settings.',
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
		{'param': 'local_path_logs', 'value': '/var/log/haproxy.log', 'section': 'logs',
		 'desc': 'The default local path for saving logs', 'group': '1'},
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
		{'param': 'nginx_path_error_logs', 'value': '/var/log/nginx/error.log', 'section': 'nginx',
		 'desc': 'Nginx error log', 'group': '1'},
		{'param': 'nginx_stats_user', 'value': 'admin', 'section': 'nginx', 'desc': 'Username for accessing Nginx stats page',
		 'group': '1'},
		{'param': 'nginx_stats_password', 'value': 'password', 'section': 'nginx',
		 'desc': 'Password for Stats web page Ngin', 'group': '1'},
		{'param': 'nginx_stats_port', 'value': '8086', 'section': 'nginx', 'desc': 'Stats port for web page Nginx',
		 'group': '1'},
		{'param': 'nginx_stats_page', 'value': 'stats', 'section': 'nginx', 'desc': 'URI Stats for web page Nginx',
		 'group': '1'},
		{'param': 'nginx_dir', 'value': '/etc/nginx/conf.d/', 'section': 'nginx', 'desc': 'Path to the Nginx directory',
		 'group': '1'},
		{'param': 'nginx_config_path', 'value': '/etc/nginx/conf.d/default.conf', 'section': 'nginx',
		 'desc': 'Path to the Nginx configuration file', 'group': '1'},
		{'param': 'ldap_enable', 'value': '0', 'section': 'ldap', 'desc': 'Enable LDAP (1 - yes, 0 - no)',
		 'group': '1'},
		{'param': 'ldap_server', 'value': '', 'section': 'ldap', 'desc': 'IP address of the LDAP server', 'group': '1'},
		{'param': 'ldap_port', 'value': '389', 'section': 'ldap', 'desc': 'LDAP port (port 389 or 636 is used by default)',
		 'group': '1'},
		{'param': 'ldap_user', 'value': '', 'section': 'ldap',
		 'desc': 'Loging for connecting to LDAP server. Format: user@domain.com', 'group': '1'},
		{'param': 'ldap_password', 'value': '', 'section': 'ldap', 'desc': 'Password to connect to LDAP server',
		 'group': '1'},
		{'param': 'ldap_base', 'value': '', 'section': 'ldap', 'desc': 'Base domain. Example: dc=domain, dc=com',
		 'group': '1'},
		{'param': 'ldap_domain', 'value': '', 'section': 'ldap', 'desc': 'LDAP domain for the login', 'group': '1'},
		{'param': 'ldap_class_search', 'value': 'user', 'section': 'ldap', 'desc': 'Class for searching the user',
		 'group': '1'},
		{'param': 'ldap_user_attribute', 'value': 'sAMAccountName', 'section': 'ldap',
		 'desc': 'User attribute for search', 'group': '1'},
		{'param': 'ldap_search_field', 'value': 'mail', 'section': 'ldap',
		 'desc': 'The field for saving the user\'s e-mail address', 'group': '1'},
		{'param': 'ldap_type', 'value': '0', 'section': 'ldap', 'desc': 'Use LDAP (0) or LDAPS (1)', 'group': '1'},
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


def update_db_v_41(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN nginx INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: nginx'  or str(e) == '(1060, "Duplicate column name \'nginx\'")':
				print('Updating... one more for version 4.0.0')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... one more for version 4.0.0")


def update_db_v_42(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN haproxy INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or str(e) == '(1060, "Duplicate column name \'haproxy\'")':
				print('Updating... go to version 4.2.3')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... go to version 4.2.3")

	
	
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

	
def update_db_v_4_3_1(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN pos INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: pos' or str(e) == '(1060, "Duplicate column name \'pos\'")':
				print('Updating... go to version 4.3.2')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to 4.3.1")



def update_db_v_4_4_2_1(**kwargs):
	cursor = conn.cursor()
	sql = """ALTER TABLE `settings` ADD COLUMN `group` INTEGER NOT NULL DEFAULT 1;"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: group' or str(e) == '(1060, "Duplicate column name \'group\'")':
				print('Updating... go to version 4.4.2')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to 4.4.2")


def update_db_v_4_5_1(**kwargs):
	cursor = conn.cursor()
	sql = """ select name from role where name  = 'superAdmin';"""

	try:
		cursor.execute(sql)
	except Exception as e:
		out_error(e)
	else:
		role = cursor.fetchall()

	if not role:
		sql = list()
		sql.append("update role set name = 'superAdmin' where id = '1';")
		sql.append("update role set name = 'admin', `description` = 'Has access everywhere except the Admin area' where id = '2';")
		sql.append("update role set id = '4' where id = '3';")
		sql.append("INSERT INTO role (id, name, `description`) values('3', 'editor', 'Has the same as the admin except the Servers page');")
		sql.append("update user set role = 'superAdmin' where role = 'admin';")
		sql.append("update user set role = 'admin' where role = 'editor';")
		for i in sql:
			try:
				cursor.execute(i)
			except:
				pass
		else:
			if kwargs.get('silent') != 1:
				print('DB has been updated to 4.5.0')


def update_db_v_4_5_4(**kwargs):
	cursor = conn.cursor()
	sql = list()
	sql.append("ALTER TABLE `servers` ADD COLUMN `nginx_active` INTEGER NOT NULL DEFAULT 0;")
	sql.append("ALTER TABLE `servers` ADD COLUMN `firewall_enable` INTEGER NOT NULL DEFAULT 0;")
	sql.append("delete from settings where param = 'firewall_enable';")
	for i in sql:
		try:
			cursor.execute(i)
		except Exception as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 4.5.7')



def update_db_v_4_5_7(**kwargs):
	cursor = conn.cursor()
	sql = """
	ALTER TABLE `servers` ADD COLUMN nginx_alert INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cursor.execute(sql)
	except Exception as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: nginx_alert' or str(e) == '(1060, "Duplicate column name \'nginx_alert\'")':
				print('Updating... go to version 4.5.8')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to 4.3.1")



def update_db_v_4_5_8_1(**kwargs):
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
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 4.5.6')



def update_db_v_4_5_8_2(**kwargs):
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
			Setting.insert(param='maxmind_key',
						   value='',
						   section='haproxy',
						   desc='License key for downloading to GeoLite2 DB. You can create it on maxmind.com',
						   group=g.group_id).execute()

		except Exception as e:
			if kwargs.get('silent') != 1:
				if (
						str(e) == 'columns param, group are not unique' or
						str(e) == '(1062, "Duplicate entry \'maxmind_key-1\' for key \'param\'")' or
						str(e) == 'UNIQUE constraint failed: settings.param, settings.group'
				):
					pass
				else:
					print("An error occurred:", e)
		else:
			print("Updating... groups")


def update_db_v_4_5_9(**kwargs):
	data_source = [
		{'param': 'smon_check_interval', 'value': '1', 'section': 'monitoring', 'desc': 'Check interval for SMON (in minutes)',
		 'group': '1'},
		{'param': 'checker_check_interval', 'value': '1', 'section': 'monitoring',
		 'desc': 'Check interval for Checker (in minutes)', 'group': '1'},
		{'param': 'port_scan_interval', 'value': '5', 'section': 'monitoring',
		 'desc': 'Check interval for Port scanner (in minutes)', 'group': '1'},
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
			print('Updating... DB has been updated to version 4.5.9')


def update_db_v_5_0_1(**kwargs):
	cursor = conn.cursor()
	sql = list()
	sql.append("alter table provisioned_servers add column project VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column network_name VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column volume_type VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column name_template VARCHAR ( 64 )")
	for i in sql:
		try:
			cursor.execute(i)
		except:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.0.1')



def update_db_v_5_1_2(**kwargs):
	data_source = [
		{'param': 'smon_keep_history_range', 'value': '14', 'section': 'monitoring',
		 'desc': 'How many days to keep the history for the SMON service', 'group': '1'},
		{'param': 'checker_keep_history_range', 'value': '14', 'section': 'monitoring',
		 'desc': 'How many days to keep the history for the Checker service', 'group': '1'}
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
					   desc='How many days to keep the history for the Port scanner service').execute()
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
	sql = """ALTER TABLE `user` ADD COLUMN user_services varchar(20) DEFAULT '1 2 3';"""
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


def update_ver():
	query = Version.update(version='5.3.0.0')
	try:
		query.execute()
	except:
		print('Cannot update version')


def update_all():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_41()
	update_db_v_42()
	update_db_v_4_3_0()
	update_db_v_4_3_1()
	update_db_v_4_4_2_1()
	update_db_v_4_5_1()
	update_db_v_4_5_4()
	update_db_v_4_5_7()
	update_db_v_4_5_8_1()
	update_db_v_4_5_8_2()
	update_db_v_4_5_9()
	update_db_v_5_0_1()
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
	update_ver()


def update_all_silent():
	if check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_41(silent=1)
	update_db_v_42(silent=1)
	update_db_v_4_3_0(silent=1)
	update_db_v_4_3_1(silent=1)
	update_db_v_4_4_2_1(silent=1)
	update_db_v_4_5_1(silent=1)
	update_db_v_4_5_4(silent=1)
	update_db_v_4_5_7(silent=1)
	update_db_v_4_5_8_1(silent=1)
	update_db_v_4_5_8_2(silent=1)
	update_db_v_4_5_9(silent=1)
	update_db_v_5_0_1(silent=1)
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
	update_ver()


if __name__ == "__main__":
	create_tables()
	default_values()
	update_all()
