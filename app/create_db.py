#!/usr/bin/env python3
import cgi
import os
import sys
import funct

mysql_enable = funct.get_config_var('mysql', 'enable')

if mysql_enable == '1':
	mysql_user = funct.get_config_var('mysql', 'mysql_user')
	mysql_password = funct.get_config_var('mysql', 'mysql_password')
	mysql_db = funct.get_config_var('mysql', 'mysql_db')
	mysql_host = funct.get_config_var('mysql', 'mysql_host')
	from mysql.connector import errorcode
	import mysql.connector as sqltool
else:
	db = "/var/www/haproxy-wi/app/haproxy-wi.db"
	import sqlite3 as sqltool
	
def check_db():
	if mysql_enable == '0':
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
									host=mysql_host,
									database=mysql_db)	
		cur = con.cursor()
	except sqltool.Error as e:
		print("An error occurred:", e)
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
			PRIMARY KEY(`id`) 
		);
		INSERT INTO user (username, email, password, role, groups) VALUES ('admin','admin@localhost','admin','admin','1'),
		 ('editor','editor@localhost','editor','editor','1'),
		 ('guest','guest@localhost','guest','guest','1');
		CREATE TABLE IF NOT EXISTS `servers` (
			`id`	INTEGER NOT NULL,
			`hostname`	VARCHAR ( 64 ) UNIQUE,
			`ip`	VARCHAR ( 64 ) UNIQUE,
			`groups`	VARCHAR ( 64 ),
			type_ip INTEGER NOT NULL DEFAULT 0,
			enable INTEGER NOT NULL DEFAULT 1,
			master INTEGER NOT NULL DEFAULT 0,
			cred INTEGER NOT NULL DEFAULT 1,
			alert INTEGER NOT NULL DEFAULT 0,
			metrics INTEGER NOT NULL DEFAULT 0,
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
			`name`	VARCHAR ( 80 ) UNIQUE,
			`description`	VARCHAR ( 255 ),
			PRIMARY KEY(`id`)
		);
		INSERT INTO `groups` (name, description) VALUES ('All','All servers enter in this group');
		CREATE TABLE IF NOT EXISTS `cred` (
			`id` integer primary key autoincrement,
			`name`	VARCHAR ( 64 ) UNIQUE,
			`enable`	INTEGER NOT NULL DEFAULT 1,
			`username`	VARCHAR ( 64 ) NOT NULL,
			`password`	VARCHAR ( 64 ) NOT NULL,
			groups INTEGER NOT NULL DEFAULT 1
		);
		CREATE TABLE IF NOT EXISTS `uuid` (`user_id` INTEGER NOT NULL, `uuid` varchar ( 64 ),`exp` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `token` (`user_id` INTEGER, `token` varchar(64), `exp` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `telegram` (`id` integer primary key autoincrement, `token` VARCHAR ( 64 ), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1);
		CREATE TABLE IF NOT EXISTS `metrics` (`serv` varchar(64), curr_con INTEGER, cur_ssl_con INTEGER, sess_rate INTEGER, max_sess_rate INTEGER,`date` timestamp default '0000-00-00 00:00:00');
		CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64) UNIQUE, value varchar(64), section varchar(64), `desc` varchar(100));
		CREATE TABLE IF NOT EXISTS `version` (`version` varchar(64));
		CREATE TABLE IF NOT EXISTS `options` ( `id`	INTEGER NOT NULL, `options`	VARCHAR ( 64 ), `groups`	VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
		CREATE TABLE IF NOT EXISTS `saved_servers` ( `id` INTEGER NOT NULL, `server` VARCHAR ( 64 ), `description` VARCHAR ( 120 ), `groups` VARCHAR ( 120 ), PRIMARY KEY(`id`)); 
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
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('time_zone', 'UTC', 'main', 'Time Zone');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('proxy', '', 'main', 'Proxy server. Use proto://ip:port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('session_ttl', '5', 'main', 'Time to live users sessions. In days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('token_ttl', '5', 'main', 'Time to live users tokens. In days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('local_path_logs', '/var/log/haproxy.log', 'logs', 'Logs save locally, disable by default');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('syslog_server_enable', '0', 'logs', 'If exist syslog server for HAproxy logs, enable this option');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('syslog_server', '0', 'logs', 'IP address syslog server');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('log_time_storage', '14', 'logs', 'Time of storage of logs of user activity, in days');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('restart_command', 'systemctl restart haproxy', 'haproxy', 'Command for restart HAproxy service');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('reload_command', 'systemctl reload haproxy', 'haproxy', 'Command for reload HAproxy service');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('status_command', 'systemctl status haproxy', 'haproxy', 'Command for status check HAproxy service');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_user', 'admin', 'haproxy', 'Username for Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_password', 'password', 'haproxy', 'Password for Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_port', '8085', 'haproxy', 'Port Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('stats_page', 'stats', 'haproxy', 'URI Stats web page HAproxy');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_dir', '/etc/haproxy/', 'haproxy', 'Path to HAProxy dir');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_config_path', '/etc/haproxy/haproxy.cfg', 'haproxy', 'Path to HAProxy config');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('server_state_file', '/etc/haproxy/haproxy.state', 'haproxy', 'Path to HAProxy state file');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock', '/var/run/haproxy.sock', 'haproxy', 'Path to HAProxy sock file');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('haproxy_sock_port', '1999', 'haproxy', 'HAProxy sock port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('tmp_config_path', '/tmp/', 'haproxy', 'Temp store configs, for haproxy check');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('cert_path', '/etc/ssl/certs/', 'haproxy', 'Path to SSL dir');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('firewall_enable', '0', 'haproxy', 'If enable this option Haproxy-wi will be configure firewalld based on config port');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`) values('lists_path', 'lists', 'main', 'Path to black/white lists');")
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
	
def update_db_v_3_2(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `waf` (`server_id` INTEGER UNIQUE, metrics INTEGER); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: server_id' or e == "1060 (42S21): Duplicate column name 'server_id' ":
				print('Updating... go to version 3.2')
			else:
				print("An error occurred:", e.args[0])
				return False
		else:
			return True
	cur.close() 
	con.close()	
	
def update_db_v_3_21(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `waf_metrics` (`serv` varchar(64), conn INTEGER, `date`  DATETIME default '0000-00-00 00:00:00'); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: token' or e == "1060 (42S21): Duplicate column name 'token' ":
				print('Updating... go to version 2.6')
			else:
				print("An error occurred:", e.args[0])
			return False
		else:
			return True
	cur.close() 
	con.close()
	
def update_db_v_3_2_3(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN port INTEGER NOT NULL DEFAULT 22;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: port' or e == " 1060 (42S21): Duplicate column name 'port' ":
				print('Updating... go to version 3.2.8')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 3.2.3")
		return True
	cur.close() 
	con.close()
	
def update_db_v_3_2_8(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN `desc` varchar(64);
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: desc' or e == " 1060 (42S21): Duplicate column name 'desc' ":
				print('Updating... go to version 3.3')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 3.2.8")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_31(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `user` ADD COLUMN ldap_user INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: ldap_user' or e == " 1060 (42S21): Duplicate column name 'ldap_user' ":
				print('Updating... go to version 3.4')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 3.3")
		return True
	cur.close() 
	con.close()
	

def update_db_v_3_4(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN active INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: active' or e == " 1060 (42S21): Duplicate column name 'active' ":
				print('Updating... go to version 3.4.1')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version 3.4.1")
		return True
	cur.close() 
	con.close()
	
	
def update_db_v_3_4_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `user` ADD COLUMN activeuser INTEGER NOT NULL DEFAULT 1;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: activeuser' or e == " 1060 (42S21): Duplicate column name 'activeuser' ":
				print('Updating... go to version 3.4.9.5')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version  3.4.5.2")
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
	
	
def update_db_v_3_4_9_5(**kwargs):
	con, cur = get_cur()
	sql = """INSERT  INTO settings (param, value, section, `desc`) values('reload_command', 'systemctl reload haproxy', 'haproxy', 'Command for reload HAproxy service'); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: param' or e == "1060 (42S21): Duplicate column name 'param' ":
				print('DB was update to 3.4.9.5')
			else:
				print("Updating... go to version 3.8.1")
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
			print('DB was update to 3.8.1')
		return True
	cur.close() 
	con.close()
	
def update_ver(**kwargs):
	con, cur = get_cur()
	sql = """update version set version = '3.9.3'; """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('Cannot update version')
	cur.close() 
	con.close()
	
	
def update_to_hash():
	cur_ver = funct.check_ver()
	cur_ver = cur_ver.replace('.','')
	i = 1
	ver = ''
	for l in cur_ver:
		ver += l
		i += 1
	if len(ver) < 4:
		ver += '00'
	if ver <= '3490':	
		con, cur = get_cur()
		sql = """select id, password from user """ 
		try:    
			cur.execute(sql)
		except sqltool.Error as e:
			out_error(e)
		else:
			for u in cur.fetchall():
				sql = """ update user set password = '%s' where id = '%s' """ % (funct.get_hash(u[1]), u[0])
				try:    
					cur.execute(sql)
					con.commit()
				except sqltool.Error as e:
					if kwargs.get('silent') != 1:
						print("An error occurred:", e)
						
			
def update_all():	
	update_db_v_31()
	update_db_v_3_2()
	update_db_v_3_21()
	update_db_v_3_2_3()
	update_db_v_3_2_8()
	update_db_v_3_31()
	update_db_v_3_4()
	update_db_v_3_4_1()
	update_db_v_3_4_5_2()
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_3_4_7()
	update_db_v_3_4_9_5()
	update_db_v_3_5_3()
	update_db_v_3_8_1()
	update_to_hash()
	update_ver()
		
	
def update_all_silent():
	update_db_v_31(silent=1)
	update_db_v_3_2(silent=1)
	update_db_v_3_21(silent=1)
	update_db_v_3_2_3(silent=1)
	update_db_v_3_2_8(silent=1)
	update_db_v_3_31(silent=1)
	update_db_v_3_4(silent=1)
	update_db_v_3_4_1(silent=1)
	update_db_v_3_4_5_2(silent=1)
	if funct.check_ver() is None:
		update_db_v_3_4_5_22()
	update_db_v_3_4_7(silent=1)
	update_db_v_3_4_9_5(silent=1)
	update_db_v_3_5_3(silent=1)
	update_db_v_3_8_1(silent=1)
	update_to_hash()
	update_ver()
	
		
if __name__ == "__main__":
	create_table()
	update_all()
		