#!/usr/bin/env python3
import funct

mysql_enable = funct.get_config_var('mysql', 'enable')

if mysql_enable == '1':
	mysql_user = funct.get_config_var('mysql', 'mysql_user')
	mysql_password = funct.get_config_var('mysql', 'mysql_password')
	mysql_db = funct.get_config_var('mysql', 'mysql_db')
	mysql_host = funct.get_config_var('mysql', 'mysql_host')
	mysql_port = funct.get_config_var('mysql', 'mysql_port')
	import mysql.connector as sqltool
else:
	db = "haproxy-wi.db"
	import sqlite3 as sqltool
	
def check_db():
	if mysql_enable == '0':
		import os
		if os.path.isfile(db):
			if os.path.getsize(db) > 100:
				with open(db,'r', encoding = "ISO-8859-1") as f:
					header = f.read(100)
					if header.startswith('SQLite format 3'):
						return False
					else:
						return True
		else:
			return True
	else:
		from mysql.connector import errorcode
		con, cur = get_cur()
		sql = """ select id from `groups` where id='1' """
		try:
			cur.execute(sql)
		except sqltool.Error as err:
			print('<div class="alert alert-danger">')
			if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
				print("Something is wrong with your user name or password")
			elif err.errno == errorcode.ER_BAD_DB_ERROR:
				print("Database does not exist")
			else:
				print(err)
			print('</div>')
			return True
		else:
			return False
			con.close()
			
def get_cur():
	try:
		if mysql_enable == '0':
			con = sqltool.connect(db, isolation_level=None)  
		else:
			con = sqltool.connect(user=mysql_user, password=mysql_password,
									host=mysql_host, port=mysql_port,
									database=mysql_db)	
		cur = con.cursor()
	except sqltool.Error as e:
		funct.logging('DB ', ' '+e, haproxywi=1, login=1)
	else:
		return con, cur
			
def create_table(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '0':
		sql = """
		CREATE TABLE IF NOT EXISTS user (
			`id`	INTEGER NOT NULL,
			`username`	VARCHAR ( 64 ) UNIQUE,
			`email`	VARCHAR ( 120 ) UNIQUE,
			`password`	VARCHAR ( 128 ),
			`role`	VARCHAR ( 128 ),
			`groups`	VARCHAR ( 120 ),
			ldap_user INTEGER NOT NULL DEFAULT 0,
			activeuser INTEGER NOT NULL DEFAULT 1,
			PRIMARY KEY(`id`) 
		);
		INSERT INTO user (username, email, password, role, groups) VALUES ('admin','admin@localhost','21232f297a57a5a743894a0e4a801fc3','admin','1'),
		 ('editor','editor@localhost','5aee9dbd2a188839105073571bee1b1f','editor','1'),
		 ('guest','guest@localhost','084e0343a0486ff05530df6c705c8bb4','guest','1');
		CREATE TABLE IF NOT EXISTS `servers` (
			`id`	INTEGER NOT NULL,
			`hostname`	VARCHAR ( 64 ),
			`ip`	VARCHAR ( 64 ) UNIQUE,
			`groups`	VARCHAR ( 64 ),
			type_ip INTEGER NOT NULL DEFAULT 0,
			enable INTEGER NOT NULL DEFAULT 1,
			master INTEGER NOT NULL DEFAULT 0,
			cred INTEGER NOT NULL DEFAULT 1,
			alert INTEGER NOT NULL DEFAULT 0,
			metrics INTEGER NOT NULL DEFAULT 0,
			port INTEGER NOT NULL DEFAULT 22,
			`desc` varchar(64),
			active INTEGER NOT NULL DEFAULT 0,
			PRIMARY KEY(`id`) 
		);
		CREATE TABLE IF NOT EXISTS `role` (
			`id`	INTEGER NOT NULL,
			`name`	VARCHAR ( 80 ) UNIQUE,
			`description`	VARCHAR ( 255 ),
			PRIMARY KEY(`id`) 
		);
		INSERT INTO `role` (name, description) VALUES ('admin','Can do everything'),
		 ('editor','Can edit configs'),
		 ('guest','Read only access');
		
		CREATE TABLE IF NOT EXISTS `groups` (
			`id`	INTEGER NOT NULL,
			`name`	VARCHAR ( 80 ),
			`description`	VARCHAR ( 255 ),
			PRIMARY KEY(`id`)
		);
		INSERT INTO `groups` (name, description) VALUES ('All','All servers enter in this group');
		CREATE TABLE IF NOT EXISTS `cred` (
			`id` integer primary key autoincrement,
			`name`	VARCHAR ( 64 ),
			`enable`	INTEGER NOT NULL DEFAULT 1,
			`username`	VARCHAR ( 64 ) NOT NULL,
			`password`	VARCHAR ( 64 ) NOT NULL,
			groups INTEGER NOT NULL DEFAULT 1,
			UNIQUE(name,groups)
		);
		CREATE TABLE IF NOT EXISTS `uuid` (`user_id` INTEGER NOT NULL, `uuid` varchar ( 64 ),`exp` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `token` (`user_id` INTEGER, `token` varchar(64), `exp` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `telegram` (`id` integer primary key autoincrement, `token` VARCHAR ( 64 ), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1);
		CREATE TABLE IF NOT EXISTS `metrics` (`serv` varchar(64), curr_con INTEGER, cur_ssl_con INTEGER, sess_rate INTEGER, max_sess_rate INTEGER,`date` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64), value varchar(64), section varchar(64), `desc` varchar(100), `group` INTEGER NOT NULL DEFAULT 1, UNIQUE(param, `group`));
		CREATE TABLE IF NOT EXISTS `version` (`version` varchar(64));
		CREATE TABLE IF NOT EXISTS `options` ( `id`	INTEGER NOT NULL, `options`	VARCHAR ( 64 ), `groups`	VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
		CREATE TABLE IF NOT EXISTS `saved_servers` ( `id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `description` VARCHAR ( 120 ), `groups` VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
		CREATE TABLE IF NOT EXISTS `backups` ( `id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `rhost` VARCHAR ( 120 ), `rpath` VARCHAR ( 120 ), `type` VARCHAR ( 120 ), `time` VARCHAR ( 120 ),  cred INTEGER, `description` VARCHAR ( 120 ), PRIMARY KEY(`id`));
		CREATE TABLE IF NOT EXISTS `waf` (`server_id` INTEGER UNIQUE, metrics INTEGER);
		CREATE TABLE IF NOT EXISTS `waf_metrics` (`serv` varchar(64), conn INTEGER, `date`  DATETIME default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS user_groups(user_id INTEGER NOT NULL, user_group_id INTEGER NOT NULL, UNIQUE(user_id,user_group_id));
		"""
		try:
			cur.executescript(sql)
		except sqltool.Error as e:
			if kwargs.get('silent') != 1:
				if e.args[0] == 'column email is not unique' or e == "1060 (42S21): column email is not unique' ":
					print('Updating... go to version 3.0')
				else:
					print("An error occurred:", e)
			return False
		else:
			return True
	else:
		try: 
			for line in open("haproxy-wi.db.sql"):
				cur.execute(line)
		except sqltool.Error as e:
			print('<div class="alert alert-danger">')
			print("An error occurred:", e)
			print('</div>')
			return False
		else:
			return True
	cur.close() 
	con.close()
	
	
def update_db_v_31(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64), value varchar(64), section varchar(64), `desc` varchar(100), `group` INTEGER NOT NULL DEFAULT 1, UNIQUE(param, `group`));")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('time_zone', 'UTC', 'main', 'Time Zone');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('proxy', '', 'main', 'Proxy server. Use proto://ip:port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('session_ttl', '5', 'main', 'Time to live users sessions. In days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('token_ttl', '5', 'main', 'Time to live users tokens. In days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('tmp_config_path', '/tmp/', 'main', 'Temp store configs, for check. Path must exist');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('cert_path', '/etc/ssl/certs/', 'main', 'Path to SSL dir. Folder owner must be a user which set in the SSH settings. Path must exist');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('lists_path', 'lists', 'main', 'Path to black/white lists. This is a relative path, begins with $HOME_HAPROXY-WI');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('local_path_logs', '/var/log/haproxy.log', 'logs', 'Logs save locally, enabled by default');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('syslog_server_enable', '0', 'logs', 'If exist syslog server for HAproxy logs, enable this option');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('syslog_server', '0', 'logs', 'IP address syslog server');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('log_time_storage', '14', 'logs', 'Time of storage of logs of user activity, in days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_user', 'admin', 'haproxy', 'Username for Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_password', 'password', 'haproxy', 'Password for Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_port', '8085', 'haproxy', 'Port Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_page', 'stats', 'haproxy', 'URI Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_dir', '/etc/haproxy/', 'haproxy', 'Path to HAProxy dir');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_config_path', '/etc/haproxy/haproxy.cfg', 'haproxy', 'Path to HAProxy config');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('server_state_file', '/etc/haproxy/haproxy.state', 'haproxy', 'Path to HAProxy state file');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock', '/var/run/haproxy.sock', 'haproxy', 'Path to HAProxy sock file');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock_port', '1999', 'haproxy', 'HAProxy sock port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('firewall_enable', '0', 'haproxy', 'If enable this option Haproxy-wi will be configure firewalld based on config port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('apache_log_path', '/var/log/httpd/', 'logs', 'Path to Apache logs');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_enable', '0', 'ldap', 'If 1 ldap enabled');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_server', '', 'ldap', 'IP address ldap server');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_port', '389', 'ldap', 'Default port is 389 or 636');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_user', '', 'ldap', 'Login for connect to LDAP server. Enter: user@domain.com');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_password', '', 'ldap', 'Password for connect to LDAP server');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_base', '', 'ldap', 'Base domain. Example: dc=domain, dc=com');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_domain', '', 'ldap', 'Domain for login, that after @, like user@domain.com, without user@');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_class_search', 'user', 'ldap', 'Class to search user');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_user_attribute', 'sAMAccountName', 'ldap', 'User\'s attribute for search');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_search_field', 'mail', 'ldap', 'Field where user e-mail saved');")
	
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 3.2')
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_4_5_2(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `version` (`version` varchar(64)); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... go to version 3.4.7')
			else:
				print("DB was update to 3.4.5.3")
			return False
		else:
			return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_4_5_22(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '0':
		sql = """insert into version ('version') values ('3.4.5.2'); """
	else:
		sql = """INSERT INTO version VALUES ('3.4.5.2'); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('Cannot insert version %s' % e)
	cur.close() 
	con.close()
	

def update_db_v_3_4_7(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `options` ( `id`	INTEGER NOT NULL, `options`	VARCHAR ( 64 ), `groups`	VARCHAR ( 120 ), PRIMARY KEY(`id`)); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: id' or e == "1060 (42S21): Duplicate column name 'id' ":
				print('Updating... go to version 2.6')
			else:
				print("DB was update to 3.4.7")
			return False
		else:
			return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_5_3(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `saved_servers` ( `id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `description` VARCHAR ( 120 ), `groups` VARCHAR ( 120 ), PRIMARY KEY(`id`));  """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: id' or e == "1060 (42S21): Duplicate column name 'id' ":
				print('DB was update to 3.5.3')
			else:
				print("DB was update to 3.5.3")
			return False
		else:
			return True
	cur.close() 
	con.close()	
	
	
def update_db_v_3_8_1(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_class_search', 'user', 'ldap', 'Class to search user');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('ldap_user_attribute', 'sAMAccountName', 'ldap', 'User attribute for search');")
	
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 3.12.0.0')
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_12(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `backups` ( `id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `rhost` VARCHAR ( 120 ), `rpath` VARCHAR ( 120 ), `type` VARCHAR ( 120 ), `time` VARCHAR ( 120 ),  cred INTEGER, `description` VARCHAR ( 120 ), PRIMARY KEY(`id`));  """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: id' or e == "1060 (42S21): Duplicate column name 'id' ":
				print('Updating... go to version 3.12.1.0')
			else:
				print("Updating... go to version 3.12.1.0")
			return False
		else:
			return True
	cur.close() 
	con.close()	
	
	
def update_db_v_3_12_1(**kwargs):
	con, cur = get_cur()
	sql = """INSERT  INTO settings (param, value, section, `desc`) values('ssl_local_path', 'certs', 'main', 'Path to dir for local save SSL certs. This is a relative path, begins with $HOME_HAPROXY-WI/app/'); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: param' or e == "1060 (42S21): Duplicate column name 'param' ":
				print('Updating... go to version 3.12.1.0')
			else:
				print("Updating... go to version 3.12.1.0")
			return False
		else:
			return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_13(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN keepalived INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: keepalived' or e == " 1060 (42S21): Duplicate column name 'keepalived' ":
				print('Updating... go to version 4.0.0')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version 4.0.0")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("update settings set section = 'main', `desc` = 'Temp store configs, for check' where param = 'tmp_config_path';")
	sql.append("update settings set section = 'main' where param = 'cert_path';")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_path_error_logs', '/var/log/nginx/error.log', 'nginx', 'Nginx error log');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_stats_user', 'admin', 'nginx', 'Username for Stats web page Nginx');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_stats_password', 'password', 'nginx', 'Password for Stats web page Nginx');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_stats_port', '8086', 'nginx', 'Stats port for web page Nginx');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_stats_page', 'stats', 'nginx', 'URI Stats for web page Nginx');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_dir', '/etc/nginx/conf.d/', 'nginx', 'Path to Nginx dir');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('nginx_config_path', '/etc/nginx/conf.d/default.conf', 'nginx', 'Path to Nginx config');")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... one more for version 4.0.0')
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_41(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN nginx INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: nginx' or e == " 1060 (42S21): Duplicate column name 'nginx' ":
				print('Updating... one more for version 4.0.0')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... one more for version 4.0.0")
		return True
	cur.close() 
	con.close()
	

def update_db_v_42(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN haproxy INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or e == " 1060 (42S21): Duplicate column name 'haproxy' ":
				print('Updating... go to version 4.2.3')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version 4.2.3")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_2_3(**kwargs):
	con, cur = get_cur()
	sql = """
	update settings set section = 'main' where param = 'firewall_enable';
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or e == " 1060 (42S21): Duplicate column name 'haproxy' ":
				print('Updating... go to version 4.3.0')
			else:
				print("An error occurred:", e)
		return False
	else:
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_3(**kwargs):
	con, cur = get_cur()
	sql = """
	CREATE TABLE IF NOT EXISTS user_groups(user_id INTEGER NOT NULL, user_group_id INTEGER NOT NULL, UNIQUE(user_id,user_group_id));
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or e == " 1060 (42S21): Duplicate column name 'haproxy' ":
				print('Updating... go to version 4.3.0')
			else:
				print("An error occurred:", e)
		return False
	else:
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_3_0(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """
		insert OR IGNORE into user_groups(user_id, user_group_id) select user.id, user.groups from user;
		"""
	else:
		sql = """
		insert OR IGNORE into user_groups(user_id, user_group_id) select id, groups from user;
		"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: haproxy' or e == " 1060 (42S21): Duplicate column name 'haproxy' ":
				print('Updating... go to version 4.3.1')
			else:
				print("An error occurred:", e)
		return False
	else:
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_3_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN pos INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: pos' or e == " 1060 (42S21): Duplicate column name 'pos' ":
				print('Updating... go to version 4.3.2')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 4.3.1")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_3_2(**kwargs):
	con, cur = get_cur()
	sql = """
	INSERT  INTO settings (param, value, section, `desc`) values('ldap_type', '0', 'ldap', 'If 0 then will be used LDAP, if 1 then will be used LDAPS ');
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'columns param, group are not unique' or e == " 1060 (42S21): columns param, group are not unique ":
				print('DB was update to 4.3.2')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 4.3.2")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_4_4(**kwargs):
	con, cur = get_cur()
	sql = """
		CREATE TABLE IF NOT EXISTS `smon` (
			`id`	INTEGER NOT NULL,
			`ip`	INTEGER,
			`port` INTEGER,
			`status` INTEGER DEFAULT 1,
			`en` INTEGER DEFAULT 1,
			`desc` varchar(64),
			`response_time` varchar(64),
			`time_state` integer default 0,
			`group` varchar(64),
			`script` varchar(64),
			`http` varchar(64),
			`http_status` INTEGER DEFAULT 1,
			`body` varchar(64),
			`body_status` INTEGER DEFAULT 1,
			`telegram_channel_id` INTEGER,
			`user_group` INTEGER,
			UNIQUE(ip, port, http, body),
			PRIMARY KEY(`id`) 
		);"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: pos' or e == " 1060 (42S21): Duplicate column name 'pos' ":
				print('Updating... go to version 4.4.1')
			else:
				print("An error occurred:", e)
		return False
	else:
		return True
	cur.close() 
	con.close()


def update_db_v_4_4_2(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `waf_rules` (`id`	INTEGER NOT NULL,
				serv varchar(64),
				`rule_name` varchar(64),
				`rule_file` varchar(64),
				`desc` varchar(1024),
				`en` INTEGER DEFAULT 1,
				UNIQUE(serv, rule_name),
				PRIMARY KEY(`id`) ); """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... go to version 4.4.1')
			else:
				print("Updating... go to version to 4.4.1")
			return False
		else:
			return True
	cur.close()
	con.close()


def update_db_v_4_4_2_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `settings` ADD COLUMN `group` INTEGER NOT NULL DEFAULT 1;
	"""
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: group' or e == " 1060 (42S21): Duplicate column name 'group' ":
				print('Updating... go to version 4.4.2')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 4.4.2")
		return True
	cur.close()
	con.close()
	
	
def update_ver(**kwargs):
	con, cur = get_cur()
	sql = """update version set version = '4.4.2.0'; """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('Cannot update version')
	cur.close() 
	con.close()
						
			
def update_all():	
	update_db_v_31()
	update_db_v_3_4_5_2()
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_3_4_7()
	update_db_v_3_5_3()
	update_db_v_3_8_1()
	update_db_v_3_12()
	update_db_v_3_12_1()
	update_db_v_3_13()
	update_db_v_4()
	update_db_v_41()
	update_db_v_42()
	update_db_v_4_2_3()
	update_db_v_4_3()
	update_db_v_4_3_0()
	update_db_v_4_3_1()
	update_db_v_4_3_2()
	update_db_v_4_4()
	update_db_v_4_4_2()
	update_db_v_4_4_2_1()
	update_ver()
		
	
def update_all_silent():
	update_db_v_31(silent=1)
	update_db_v_3_4_5_2(silent=1)
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_3_4_7(silent=1)
	update_db_v_3_5_3(silent=1)
	update_db_v_3_8_1(silent=1)
	update_db_v_3_12(silent=1)
	update_db_v_3_12_1(silent=1)
	update_db_v_3_13(silent=1)
	update_db_v_4(silent=1)
	update_db_v_41(silent=1)
	update_db_v_42(silent=1)
	update_db_v_4_2_3(silent=1)
	update_db_v_4_3(silent=1)
	update_db_v_4_3_0(silent=1)
	update_db_v_4_3_1(silent=1)
	update_db_v_4_3_2(silent=1)
	update_db_v_4_4(silent=1)
	update_db_v_4_4_2(silent=1)
	update_db_v_4_4_2_1(silent=1)
	update_ver()
	
		
if __name__ == "__main__":
	create_table()
	update_all()
