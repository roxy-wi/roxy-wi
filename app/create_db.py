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
			con.close()
			return True
		else:
			con.close()
			return False


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
		funct.logging('DB ', ' '+str(e), haproxywi=1, login=1)
	else:
		return con, cur


def create_table(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '0':
		sql = """
		CREATE TABLE IF NOT EXISTS user (
			`id` INTEGER NOT NULL,
			`username` VARCHAR ( 64 ) UNIQUE,
			`email`	VARCHAR ( 120 ) UNIQUE,
			`password` VARCHAR ( 128 ),
			`role` VARCHAR ( 128 ),
			`groups` VARCHAR ( 120 ),
			ldap_user INTEGER NOT NULL DEFAULT 0,
			activeuser INTEGER NOT NULL DEFAULT 1,
			PRIMARY KEY(`id`) 
		);
		INSERT INTO user (username, email, password, role, groups) VALUES 
		('admin','admin@localhost','21232f297a57a5a743894a0e4a801fc3','admin','1'),
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
			keepalived INTEGER NOT NULL DEFAULT 0,
			PRIMARY KEY(`id`) 
		);
		CREATE TABLE IF NOT EXISTS `role` (
			`id`	INTEGER NOT NULL,
			`name`	VARCHAR ( 80 ) UNIQUE,
			`description`	VARCHAR ( 255 ),
			PRIMARY KEY(`id`) 
		);
		INSERT INTO `role` (name, description) VALUES 
		('admin','Can do everything'),
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
		CREATE TABLE IF NOT EXISTS `telegram` (`id` integer primary key autoincrement, `token` VARCHAR (64), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1);
		CREATE TABLE IF NOT EXISTS `metrics` (`serv` varchar(64), curr_con INTEGER, cur_ssl_con INTEGER, sess_rate INTEGER, max_sess_rate INTEGER,`date` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64), value varchar(64), section varchar(64), `desc` varchar(100), `group` INTEGER NOT NULL DEFAULT 1, UNIQUE(param, `group`));
		CREATE TABLE IF NOT EXISTS `version` (`version` varchar(64));
		CREATE TABLE IF NOT EXISTS `options` (`id` INTEGER NOT NULL, `options` VARCHAR ( 64 ), `groups` VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
		CREATE TABLE IF NOT EXISTS `saved_servers` (`id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `description` VARCHAR ( 120 ), `groups` VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
		CREATE TABLE IF NOT EXISTS `backups` (`id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `rhost` VARCHAR ( 120 ), `rpath` VARCHAR ( 120 ), `type` VARCHAR ( 120 ), `time` VARCHAR ( 120 ),  cred INTEGER, `description` VARCHAR ( 120 ), PRIMARY KEY(`id`));
		CREATE TABLE IF NOT EXISTS `waf` (`server_id` INTEGER UNIQUE, metrics INTEGER);
		CREATE TABLE IF NOT EXISTS `waf_metrics` (`serv` varchar(64), conn INTEGER, `date` DATETIME default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS user_groups(user_id INTEGER NOT NULL, user_group_id INTEGER NOT NULL, UNIQUE(user_id,user_group_id));
		CREATE TABLE IF NOT EXISTS port_scanner_settings (
			server_id INTEGER NOT NULL, 
			user_group_id INTEGER NOT NULL, 
			enabled INTEGER NOT NULL, 
			notify INTEGER NOT NULL, 
			history INTEGER NOT NULL, 
			UNIQUE(server_id)
		);
		CREATE TABLE IF NOT EXISTS port_scanner_ports (
			`serv` varchar(64), 
			user_group_id INTEGER NOT NULL,
			port INTEGER NOT NULL,
			service_name varchar(64),
			`date`  DATETIME default '0000-00-00 00:00:00'
		);
		CREATE TABLE IF NOT EXISTS port_scanner_history (
			`serv` varchar(64), 
			port INTEGER NOT NULL,
			status varchar(64),
			service_name varchar(64),
			`date`  DATETIME default '0000-00-00 00:00:00'
		);
		CREATE TABLE IF NOT EXISTS providers_creds (
			`id` INTEGER NOT NULL,
			`name` VARCHAR ( 64 ), 
			`type` VARCHAR ( 64 ),
			`group` VARCHAR ( 64 ), 
			`key` VARCHAR ( 64 ), 
			`secret` VARCHAR ( 64 ),
			`create_date`  DATETIME default '0000-00-00 00:00:00',
			`edit_date`  DATETIME default '0000-00-00 00:00:00',
			PRIMARY KEY(`id`)
		); 
		CREATE TABLE IF NOT EXISTS provisioned_servers (
			`id` INTEGER NOT NULL,
			`region` VARCHAR ( 64 ), 
			`instance_type` VARCHAR ( 64 ),
			`public_ip` INTEGER,
			`floating_ip` INTEGER,
			`volume_size` INTEGER,
			`backup` INTEGER,
			`monitoring` INTEGER,
			`private_networking` INTEGER,
			`ssh_key_name` VARCHAR ( 64 ),
			`ssh_ids` VARCHAR ( 64 ),
			`name` VARCHAR ( 64 ),
			`os` VARCHAR ( 64 ),
			`firewall` INTEGER,
			`provider_id` INTEGER,
			`type` VARCHAR ( 64 ),
			`status` VARCHAR ( 64 ),
			`group_id` INTEGER NOT NULL,
			`date`  DATETIME default '0000-00-00 00:00:00',
			`IP` VARCHAR ( 64 ),
			`last_error` VARCHAR ( 256 ),
			`delete_on_termination` INTEGER,
			PRIMARY KEY(`id`)
		);
		CREATE TABLE IF NOT EXISTS api_tokens (
			`token` varchar(64),
			`user_name` varchar(64),
			`user_group_id` INTEGER NOT NULL,
			`user_role` INTEGER NOT NULL,
			`create_date`  DATETIME default '0000-00-00 00:00:00',
			`expire_date`  DATETIME default '0000-00-00 00:00:00'
		);
		CREATE TABLE IF NOT EXISTS `metrics_http_status` (`serv` varchar(64), `2xx` INTEGER, `3xx` INTEGER, `4xx` INTEGER, `5xx` INTEGER,`date` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `slack` (`id` INTEGER NOT NULL, `token` VARCHAR (64), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(`id`));
		CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64), value varchar(64), section varchar(64), `desc` varchar(100), `group` INTEGER NOT NULL DEFAULT 1, UNIQUE(param, `group`));
		INSERT  INTO settings (param, value, section, `desc`) values('time_zone', 'UTC', 'main', 'Time Zone');
		INSERT  INTO settings (param, value, section, `desc`) values('proxy', '', 'main', 'Proxy server. Use proto://ip:port');
		INSERT  INTO settings (param, value, section, `desc`) values('session_ttl', '5', 'main', 'Time to live users sessions. In days');
		INSERT  INTO settings (param, value, section, `desc`) values('token_ttl', '5', 'main', 'Time to live users tokens. In days');
		INSERT  INTO settings (param, value, section, `desc`) values('tmp_config_path', '/tmp/', 'main', 'A temp folder of configs, for checking. The path must exist');
		INSERT  INTO settings (param, value, section, `desc`) values('cert_path', '/etc/ssl/certs/', 'main', 'A path to SSL dir. The folder owner must be an user who set in the SSH settings. The path must exist');
		INSERT  INTO settings (param, value, section, `desc`) values('ssl_local_path', 'certs', 'main', 'Path to dir for local save SSL certs. This is a relative path, begins with $HOME_HAPROXY-WI/app/');
		INSERT  INTO settings (param, value, section, `desc`) values('lists_path', 'lists', 'main', 'Path to black/white lists. This is a relative path, begins with $HOME_HAPROXY-WI');
		INSERT  INTO settings (param, value, section, `desc`) values('local_path_logs', '/var/log/haproxy.log', 'logs', 'Logs save locally, enabled by default');
		INSERT  INTO settings (param, value, section, `desc`) values('syslog_server_enable', '0', 'logs', 'If exist syslog server for HAProxy logs, enable this option');
		INSERT  INTO settings (param, value, section, `desc`) values('syslog_server', '0', 'logs', 'IP address of syslog server');
		INSERT  INTO settings (param, value, section, `desc`) values('log_time_storage', '14', 'logs', 'Storage time for user activity logs, in days');
		INSERT  INTO settings (param, value, section, `desc`) values('stats_user', 'admin', 'haproxy', 'Username for the HAProxy Stats web page');
		INSERT  INTO settings (param, value, section, `desc`) values('stats_password', 'password', 'haproxy', 'Password for the HAProxy Stats web page');
		INSERT  INTO settings (param, value, section, `desc`) values('stats_port', '8085', 'haproxy', 'Port for the HAProxy Stats web page');
		INSERT  INTO settings (param, value, section, `desc`) values('stats_page', 'stats', 'haproxy', 'URI for the HAProxy Stats web page');
		INSERT  INTO settings (param, value, section, `desc`) values('haproxy_dir', '/etc/haproxy/', 'haproxy', 'Path to HAProxy dir');
		INSERT  INTO settings (param, value, section, `desc`) values('haproxy_config_path', '/etc/haproxy/haproxy.cfg', 'haproxy', 'Path to HAProxy config');
		INSERT  INTO settings (param, value, section, `desc`) values('server_state_file', '/etc/haproxy/haproxy.state', 'haproxy', 'Path to HAProxy state file');
		INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock', '/var/run/haproxy.sock', 'haproxy', 'Path to HAProxy sock file');
		INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock_port', '1999', 'haproxy', 'HAProxy sock port');
		INSERT  INTO settings (param, value, section, `desc`) values('apache_log_path', '/var/log/httpd/', 'logs', 'Path to Apache logs folder');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_enable', '0', 'ldap', 'If 1 LDAP is enabled');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_server', '', 'ldap', 'LDAP server IP address');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_port', '389', 'ldap', 'Default port is 389 or 636');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_user', '', 'ldap', 'Username to connect to the LDAP server. Enter: user@domain.com');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_password', '', 'ldap', 'Password for connect to LDAP server');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_base', '', 'ldap', 'Base domain. Example: dc=domain, dc=com');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_domain', '', 'ldap', 'Domain for login, that after @, like user@domain.com, without user@');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_class_search', 'user', 'ldap', 'Class to search user');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_user_attribute', 'sAMAccountName', 'ldap', 'User attribute for searching');
		INSERT  INTO settings (param, value, section, `desc`) values('ldap_search_field', 'mail', 'ldap', 'Field where user e-mails are saved');
		CREATE TABLE IF NOT EXISTS `version` (`version` varchar(64));
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
		finally:
			cur.close()
			con.close()
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
		finally:
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


def update_db_v_4(**kwargs):
	con, cur = get_cur()
	sql = list()
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
	else:
		print("Updating... one more for version 4.0.0")

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
	else:
		print("Updating... go to version 4.2.3")

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

	cur.close() 
	con.close()
	
	
def update_db_v_4_3_0(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """
		insert IGNORE into user_groups(user_id, user_group_id) select user.id, user.groups from user;
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
	else:
		print("DB has been updated to 4.3.1")

	cur.close()
	con.close()
	
	
def update_db_v_4_3_2(**kwargs):
	con, cur = get_cur()
	sql = """
	INSERT  INTO settings (param, value, section, `desc`) values('ldap_type', '0', 'ldap', 'If 0 then LDAP is be used , if 1 then LDAPS');
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'columns param, group are not unique' or e == " 1060 (42S21): columns param, group are not unique ":
				print('Updating... go to version 4.4.0')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... go to version 4.4.0")

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
	else:
		print("DB has been updated to 4.4.2")

	cur.close()
	con.close()


def update_db_v_4_3_2_1(**kwargs):
	con, cur = get_cur()
	groups = ''
	sql = """ select id from `groups` """
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		groups = cur.fetchall()

	for g in groups:
		sql = """
		INSERT  INTO settings (param, value, section, `desc`, `group`) values('haproxy_enterprise', '0', 'haproxy', 'Use this option, if your HAProxy is enterprise. It change service name for rebooting/reloading', '%s');
		""" % g[0]
		try:
			cur.execute(sql)
			con.commit()
		except sqltool.Error as e:
			if kwargs.get('silent') != 1:
				if e.args[0] == 'columns param, group are not unique' or e == " 1060 (42S21): columns param, group are not unique ":
					pass
				else:
					print("An error occurred:", e)
		else:
			print("Updating... groups")
	cur.close()
	con.close()


def update_db_v_4_5(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `alerts` (`id`	INTEGER NOT NULL,
				`message` varchar(64),
				`level` varchar(64),
				`ip` varchar(64),
				`port` INTEGER,
				`user_group` INTEGER default 1,
				`service` varchar(64),
				`date`  DATETIME default '0000-00-00 00:00:00',
				PRIMARY KEY(`id`) ); """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... go to version 4.5.0')
			else:
				print("Updating... go to version to 4.5.0")

	cur.close()
	con.close()


def update_db_v_4_5_1(**kwargs):
	con, cur = get_cur()

	sql = """ select name from role where name  = 'superAdmin';"""
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		role = cur.fetchall()

	if not role:
		sql = list()
		sql.append("update role set name = 'superAdmin' where id = '1';")
		sql.append("update role set name = 'admin', `description` = 'Has access everywhere except the Admin area' where id = '2';")
		sql.append("update role set id = '4' where id = '3';")
		sql.append("INSERT  INTO role (id, name, `description`) values('3', 'editor', 'Has the same as the admin except the Servers page');")
		sql.append("update user set role = 'superAdmin' where role = 'admin';")
		sql.append("update user set role = 'admin' where role = 'editor';")
		for i in sql:
			try:
				cur.execute(i)
				con.commit()
			except sqltool.Error as e:
				pass
		else:
			if kwargs.get('silent') != 1:
				print('DB has been updated to 4.5.0')
	cur.close()
	con.close()


def update_db_v_4_5_4(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("ALTER TABLE `servers` ADD COLUMN `nginx_active` INTEGER NOT NULL DEFAULT 0;")
	sql.append("ALTER TABLE `servers` ADD COLUMN `firewall_enable` INTEGER NOT NULL DEFAULT 0;")
	sql.append("delete from settings where param = 'firewall_enable';")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 4.5.7')

	cur.close()
	con.close()


def update_db_v_4_5_7(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN nginx_alert INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: nginx_alert' or e == " 1060 (42S21): Duplicate column name 'nginx_alert' ":
				print('Updating... go to version 4.5.8')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to 4.3.1")

	cur.close()
	con.close()


def update_db_v_4_5_8(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `geoip_codes` (`id`	INTEGER NOT NULL,
				`code` varchar(64),
				`name` varchar(64),
				UNIQUE(`code`, `name`),
				PRIMARY KEY(`id`) ); """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: id' or e == "1060 (42S21): Duplicate column name 'id' ":
				print('Updating... go to version 4.5.0')
			else:
				print("Updating... go to version to 4.5.0")

	cur.close()
	con.close()


def update_db_v_4_5_8_1(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('RW','Rwanda');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SO','Somalia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('YE','Yemen');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IQ','Iraq');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SA','Saudi Arabia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IR','Iran');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CY','Cyprus');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TZ','Tanzania');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SY','Syria');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AM','Armenia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KE','Kenya');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CD','DR Congo');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DJ','Djibouti');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('UG','Uganda');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CF','Central African Republic');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SC','Seychelles');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('JO','Hashemite Kingdom of Jordan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LB','Lebanon');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KW','Kuwait');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('OM','Oman');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('QA','Qatar');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BH','Bahrain');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AE','United Arab Emirates');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IL','Israel');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TR','Turkey');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ET','Ethiopia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ER','Eritrea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('EG','Egypt');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SD','Sudan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GR','Greece');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BI','Burundi');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('EE','Estonia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LV','Latvia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AZ','Azerbaijan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LT','Republic of Lithuania');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SJ','Svalbard and Jan Mayen');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GE','Georgia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MD','Republic of Moldova');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BY','Belarus');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FI','Finland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AX','Åland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('UA','Ukraine');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MK','North Macedonia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HU','Hungary');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BG','Bulgaria');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AL','Albania');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PL','Poland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('RO','Romania');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('XK','Kosovo');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ZW','Zimbabwe');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ZM','Zambia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KM','Comoros');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MW','Malawi');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LS','Lesotho');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BW','Botswana');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MU','Mauritius');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SZ','Eswatini');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('RE','Réunion');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ZA','South Africa');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('YT','Mayotte');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MZ','Mozambique');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MG','Madagascar');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AF','Afghanistan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PK','Pakistan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BD','Bangladesh');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TM','Turkmenistan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TJ','Tajikistan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LK','Sri Lanka');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BT','Bhutan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IN','India');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MV','Maldives');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IO','British Indian Ocean Territory');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NP','Nepal');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MM','Myanmar');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('UZ','Uzbekistan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KZ','Kazakhstan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KG','Kyrgyzstan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TF','French Southern Territories');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HM','Heard Island and McDonald Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CC','Cocos [Keeling] Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PW','Palau');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VN','Vietnam');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TH','Thailand');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ID','Indonesia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LA','Laos');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TW','Taiwan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PH','Philippines');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MY','Malaysia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CN','China');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HK','Hong Kong');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BN','Brunei');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MO','Macao');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KH','Cambodia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KR','South Korea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('JP','Japan');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KP','North Korea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SG','Singapore');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CK','Cook Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TL','East Timor');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('RU','Russia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MN','Mongolia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AU','Australia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CX','Christmas Island');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MH','Marshall Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FM','Federated States of Micronesia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PG','Papua New Guinea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SB','Solomon Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TV','Tuvalu');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NR','Nauru');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VU','Vanuatu');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NC','New Caledonia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NF','Norfolk Island');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NZ','New Zealand');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FJ','Fiji');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LY','Libya');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CM','Cameroon');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SN','Senegal');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CG','Congo Republic');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PT','Portugal');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LR','Liberia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CI','Ivory Coast');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GH','Ghana');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GQ','Equatorial Guinea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NG','Nigeria');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BF','Burkina Faso');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TG','Togo');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GW','Guinea-Bissau');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MR','Mauritania');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BJ','Benin');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GA','Gabon');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SL','Sierra Leone');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ST','São Tomé and Príncipe');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GI','Gibraltar');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GM','Gambia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GN','Guinea');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TD','Chad');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NE','Niger');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ML','Mali');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('EH','Western Sahara');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TN','Tunisia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ES','Spain');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MA','Morocco');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MT','Malta');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DZ','Algeria');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FO','Faroe Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DK','Denmark');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IS','Iceland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GB','United Kingdom');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CH','Switzerland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SE','Sweden');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NL','Netherlands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AT','Austria');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BE','Belgium');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DE','Germany');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LU','Luxembourg');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IE','Ireland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MC','Monaco');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FR','France');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AD','Andorra');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LI','Liechtenstein');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('JE','Jersey');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IM','Isle of Man');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GG','Guernsey');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SK','Slovakia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CZ','Czechia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NO','Norway');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VA','Vatican City');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SM','San Marino');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('IT','Italy');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SI','Slovenia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('ME','Montenegro');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HR','Croatia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BA','Bosnia and Herzegovina');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AO','Angola');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NA','Namibia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SH','Saint Helena');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BV','Bouvet Island');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BB','Barbados');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CV','Cabo Verde');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GY','Guyana');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GF','French Guiana');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SR','Suriname');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PM','Saint Pierre and Miquelon');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GL','Greenland');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PY','Paraguay');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('UY','Uruguay');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BR','Brazil');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('FK','Falkland Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GS','South Georgia and the South Sandwich Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('JM','Jamaica');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DO','Dominican Republic');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CU','Cuba');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MQ','Martinique');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BS','Bahamas');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BM','Bermuda');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AI','Anguilla');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TT','Trinidad and Tobago');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KN','St Kitts and Nevis');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('DM','Dominica');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AG','Antigua and Barbuda');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('LC','Saint Lucia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TC','Turks and Caicos Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AW','Aruba');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VG','British Virgin Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VC','Saint Vincent and the Grenadines');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MS','Montserrat');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MF','Saint Martin');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BL','Saint Barthélemy');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GP','Guadeloupe');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GD','Grenada');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KY','Cayman Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BZ','Belize');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SV','El Salvador');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GT','Guatemala');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HN','Honduras');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NI','Nicaragua');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CR','Costa Rica');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VE','Venezuela');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('EC','Ecuador');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CO','Colombia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PA','Panama');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('HT','Haiti');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AR','Argentina');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CL','Chile');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BO','Bolivia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PE','Peru');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MX','Mexico');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PF','French Polynesia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PN','Pitcairn Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('KI','Kiribati');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TK','Tokelau');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('TO','Tonga');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('WF','Wallis and Futuna');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('WS','Samoa');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('NU','Niue');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('MP','Northern Mariana Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('GU','Guam');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PR','Puerto Rico');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('VI','U.S. Virgin Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('UM','U.S. Minor Outlying Islands');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AS','American Samoa');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CA','Canada');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('US','United States');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('PS','Palestine');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('RS','Serbia');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('AQ','Antarctica');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SX','Sint Maarten');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('CW','Curaçao');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('BQ','Bonaire');")
	sql.append("INSERT INTO geoip_codes ('code', 'name') values('SS','South Sudan');")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... go to version 4.5.6')

	cur.close()
	con.close()


def update_db_v_4_5_8_2(**kwargs):
	con, cur = get_cur()
	groups = ''
	sql = """ select id from `groups` """
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		groups = cur.fetchall()

	for g in groups:
		sql = """
		INSERT  INTO settings (param, value, section, `desc`, `group`) values('maxmind_key', '', 'haproxy', 'License key for downloading to GeoLite2 DB. You can create it on maxmind.com', '%s');
		""" % g[0]
		try:
			cur.execute(sql)
			con.commit()
		except sqltool.Error as e:
			if kwargs.get('silent') != 1:
				if e.args[0] == 'columns param, group are not unique' or e == " 1060 (42S21): columns param, group are not unique ":
					pass
				else:
					print("An error occurred:", e)
		else:
			print("Updating... groups")
	cur.close()
	con.close()


def update_db_v_4_5_9(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('smon_check_interval', '1', 'monitoring', 'SMON check interval, in minutes')")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('checker_check_interval', '1', 'monitoring', 'Checker check interval, in minutes')")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 4.5.9')
	cur.close()
	con.close()


def update_db_v_5(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS providers_creds (
				`id` INTEGER NOT NULL,
				`name` VARCHAR ( 64 ), 
				`type` VARCHAR ( 64 ),
				`group` VARCHAR ( 64 ), 
				`key` VARCHAR ( 64 ), 
				`secret` VARCHAR ( 64 ), 
				`create_date`  DATETIME default '0000-00-00 00:00:00',
				`edit_date`  DATETIME default '0000-00-00 00:00:00',
				PRIMARY KEY(`id`)
			); 
			"""
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.0.0')
			else:
				print("Updating... DB has been updated to version 5.0.0")

	cur.close()
	con.close()


def update_db_v_51(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS provisioned_servers (
				`id` INTEGER NOT NULL,
				`region` VARCHAR ( 64 ), 
				`instance_type` VARCHAR ( 64 ),
				`public_ip` INTEGER,
				`floating_ip` INTEGER,
				`volume_size` INTEGER,
				`backup` INTEGER,
				`monitoring` INTEGER,
				`private_networking` INTEGER,
				`ssh_key_name` VARCHAR ( 64 ),
				`ssh_ids` VARCHAR ( 64 ),
				`name` VARCHAR ( 64 ),
				`os` VARCHAR ( 64 ),
				`firewall` INTEGER,
				`provider_id` INTEGER,
				`type` VARCHAR ( 64 ),
				`status` VARCHAR ( 64 ),
				`group_id` INTEGER NOT NULL,
				`date`  DATETIME default '0000-00-00 00:00:00',
				`IP` VARCHAR ( 64 ),
				`last_error` VARCHAR ( 256 ),
				`delete_on_termination` INTEGER,
				PRIMARY KEY(`id`)
			);  """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.0.0')
			else:
				print("Updating... DB has been updated to version 5.0.0")

	cur.close()
	con.close()


def update_db_v_5_0_1(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("alter table provisioned_servers add column project VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column network_name VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column volume_type VARCHAR ( 64 )")
	sql.append("alter table provisioned_servers add column name_template VARCHAR ( 64 )")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.0.1')
	cur.close()
	con.close()


def update_db_v_5_1_0_11(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS port_scanner_settings (
			server_id INTEGER NOT NULL, 
			user_group_id INTEGER NOT NULL, 
			enabled INTEGER NOT NULL, 
			notify INTEGER NOT NULL, 
			history INTEGER NOT NULL, 
			UNIQUE(server_id)
		);  """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.1.0')
			else:
				print("Updating... DB has been updated to version 5.1.0")

	cur.close()
	con.close()


def update_db_v_5_1_0_12(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS port_scanner_ports (
			`serv` varchar(64), 
			user_group_id INTEGER NOT NULL,
			port INTEGER NOT NULL,
			service_name varchar(64),
			`date`  DATETIME default '0000-00-00 00:00:00'
		); """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.1.0')
			else:
				print("Updating... DB has been updated to version 5.1.0")

	cur.close()
	con.close()


def update_db_v_5_1_0_13(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS port_scanner_history (
			`serv` varchar(64), 
			port INTEGER NOT NULL,
			status varchar(64),
			service_name varchar(64),
			`date`  DATETIME default '0000-00-00 00:00:00'
		); """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.1.0')
			else:
				print("Updating... DB has been updated to version 5.1.0")

	cur.close()
	con.close()


def update_db_v_5_1_0(**kwargs):
	con, cur = get_cur()
	sql = """
	INSERT  INTO settings (param, value, section, `desc`) values('port_scan_interval', '5', 'monitoring', 'Port scanner check interval, in minutes');
	"""
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'columns param, group are not unique' or e == " 1060 (42S21): columns param, group are not unique ":
				print('Updating... DB has been updated to version 5.1.0')
			else:
				print("An error occurred:", e)
	else:
		print("Updating... DB has been updated to version 5.1.0")

	cur.close()
	con.close()


def update_db_v_5_1_0_1(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE api_tokens (
			`token` varchar(64),
			`user_name` varchar(64),
			`user_group_id` INTEGER NOT NULL,
			`user_role` INTEGER NOT NULL,
			`create_date`  DATETIME default '0000-00-00 00:00:00',
			`expire_date`  DATETIME default '0000-00-00 00:00:00'
		);  """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.1.0')
			else:
				print("Updating... DB has been updated to version 5.1.0")

	cur.close()
	con.close()


def update_db_v_5_1_1(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `slack` (
				`id` INTEGER NOT NULL, 
				`token` VARCHAR (64), 
				`chanel_name` INTEGER NOT NULL DEFAULT 1, 
				`groups` INTEGER NOT NULL DEFAULT 1, 
				PRIMARY KEY(`id`)
				);
  """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: version' or e == "1060 (42S21): Duplicate column name 'version' ":
				print('Updating... DB has been updated to version 5.1.1')
			else:
				print("Updating... DB has been updated to version 5.1.1")

	cur.close()
	con.close()


def update_db_v_5_1_2(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('smon_keep_history_range', '14', 'monitoring', 'How many days to keep the history for the SMON service')")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('checker_keep_history_range', '14', 'monitoring', 'How many days to keep the history for the Checker service')")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.1.2')
	cur.close()
	con.close()


def update_db_v_5_1_3(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN protected INTEGER NOT NULL DEFAULT 0;
	"""
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: protected' or e == " 1060 (42S21): Duplicate column name 'protected' ":
				print('Updating... DB has been updated to version 5.1.3')
			else:
				print("An error occurred:", e)
	else:
		print("DB has been updated to version 5.1.3")

	cur.close()
	con.close()


def update_db_v_5_2_0(**kwargs):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('portscanner_keep_history_range', '14', 'monitoring', 'How many days to keep the history for the Port scanner service')")
	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			pass
	else:
		if kwargs.get('silent') != 1:
			print('Updating... DB has been updated to version 5.2.0')
	cur.close()
	con.close()


def update_ver():
	con, cur = get_cur()
	sql = """update version set version = '5.2.0.0'; """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('Cannot update version')
	cur.close() 
	con.close()


def update_all():	
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_4()
	update_db_v_41()
	update_db_v_42()
	update_db_v_4_3()
	update_db_v_4_3_0()
	update_db_v_4_3_1()
	update_db_v_4_3_2()
	update_db_v_4_4()
	update_db_v_4_4_2()
	update_db_v_4_4_2_1()
	update_db_v_4_3_2_1()
	update_db_v_4_5()
	update_db_v_4_5_1()
	update_db_v_4_5_4()
	update_db_v_4_5_7()
	update_db_v_4_5_8()
	update_db_v_4_5_8_1()
	update_db_v_4_5_8_2()
	update_db_v_4_5_9()
	update_db_v_5()
	update_db_v_51()
	update_db_v_5_1_0_11()
	update_db_v_5_1_0_12()
	update_db_v_5_1_0_13()
	update_db_v_5_0_1()
	update_db_v_5_1_0()
	update_db_v_5_1_0_1()
	update_db_v_5_1_1()
	update_db_v_5_1_2()
	update_db_v_5_1_3()
	update_db_v_5_2_0()
	update_ver()


def update_all_silent():
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_4(silent=1)
	update_db_v_41(silent=1)
	update_db_v_42(silent=1)
	update_db_v_4_3(silent=1)
	update_db_v_4_3_0(silent=1)
	update_db_v_4_3_1(silent=1)
	update_db_v_4_3_2(silent=1)
	update_db_v_4_4(silent=1)
	update_db_v_4_4_2(silent=1)
	update_db_v_4_4_2_1(silent=1)
	update_db_v_4_3_2_1(silent=1)
	update_db_v_4_5(silent=1)
	update_db_v_4_5_1(silent=1)
	update_db_v_4_5_4(silent=1)
	update_db_v_4_5_7(silent=1)
	update_db_v_4_5_8(silent=1)
	update_db_v_4_5_8_1(silent=1)
	update_db_v_4_5_8_2(silent=1)
	update_db_v_4_5_9(silent=1)
	update_db_v_5(silent=1)
	update_db_v_51(silent=1)
	update_db_v_5_0_1(silent=1)
	update_db_v_5_1_0_11(silent=1)
	update_db_v_5_1_0_12(silent=1)
	update_db_v_5_1_0_13(silent=1)
	update_db_v_5_1_0(silent=1)
	update_db_v_5_1_0_1(silent=1)
	update_db_v_5_1_1(silent=1)
	update_db_v_5_1_2(silent=1)
	update_db_v_5_1_3(silent=1)
	update_db_v_5_2_0(silent=1)
	update_ver()


if __name__ == "__main__":
	create_table()
	update_all()
