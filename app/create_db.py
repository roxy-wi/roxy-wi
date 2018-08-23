#!/usr/bin/env python3
import cgi
import html
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
	db = funct.get_app_dir()+"/haproxy-wi.db"
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
			PRIMARY KEY(`id`) 
		);
		CREATE TABLE IF NOT EXISTS `roles_users` (
			`user_id`	INTEGER,
			`role_id`	INTEGER,
			FOREIGN KEY(`user_id`) REFERENCES `user`(`id`),
			FOREIGN KEY(`role_id`) REFERENCES `role`(`id`)
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
		
		CREATE TABLE IF NOT EXISTS `servers` (
			`id`	INTEGER NOT NULL,
			`hostname`	VARCHAR ( 64 ) UNIQUE,
			`ip`	VARCHAR ( 64 ) UNIQUE,
			`groups`	VARCHAR ( 64 ),
			PRIMARY KEY(`id`)
		);		
		CREATE TABLE IF NOT EXISTS `uuid` (
			`user_id`	INTEGER NOT NULL,
			`uuid`	varchar ( 64 )
		);
		CREATE TABLE IF NOT EXISTS `cred` (
			`id` integer primary key autoincrement,
			`enable`	INTEGER NOT NULL DEFAULT 1,
			`username`	VARCHAR ( 64 ) NOT NULL,
			`password`	VARCHAR ( 64 ) NOT NULL
		);
		CREATE TABLE IF NOT EXISTS `token` (
			`user_id`	INTEGER,
			`token`	varchar(64),
			`exp`  DATETIME default '0000-00-00 00:00:00'
		);
		"""
		try:
			cur.executescript(sql)
		except sqltool.Error as e:
			if kwargs.get('silent') != 1:
				if e.args[0] == 'column email is not unique' or e == "1060 (42S21): column email is not unique' ":
					print('Updating... go to version 2.0.1<br />')
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
	
def update_db_v_2_0_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN type_ip INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: type_ip' or e == " 1060 (42S21): Duplicate column name 'type_ip' ":
				print('Updating... go to version 2.0.1.1<br />')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.0.1<br />")
		return True
	cur.close() 
	con.close()

def update_db_v_2_0_1_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN enable INTEGER NOT NULL DEFAULT 1;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: enable' or e == "1060 (42S21): Duplicate column name 'enable' ":
				print('Updating... go to version 2.0.5<br />')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.0.1.1<br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_0_5(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN master INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: master' or e == "1060 (42S21): Duplicate column name 'master' ":
				print('Updating... go to version 2.4<br />')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.0.5<br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_4(**kwargs):
	con, cur = get_cur()
	sql = """
	CREATE TABLE IF NOT EXISTS `uuid` (`user_id` INTEGER NOT NULL, `uuid` varchar ( 64 ) );
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print(kwargs.get('silent'))
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: user_id' or e == "1060 (42S21): Duplicate column name 'user_id' ":
				print('Updating... go to version 2.5.3')
			else:
				print("An error occurred:", e)
		return False
	else:
		if kwargs.get('silent') != 1:
			print("DB was update to 2.4 <br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_5_6(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """
		ALTER TABLE `uuid` ADD COLUMN `exp` timestamp default '0000-00-00 00:00:00';
		"""
	else:
		sql = """
		ALTER TABLE `uuid` ADD COLUMN `exp` DATETIME default '0000-00-00 00:00:00';
		"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: exp' or e == " 1060 (42S21): Duplicate column name 'exp' ":
				print('Updating... go to version 2.5.6.1')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.5.6.1<br />")
		return True
	cur.close() 
	con.close()

def update_db_v_2_5_6_1(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """
		CREATE TABLE IF NOT EXISTS `token` (`user_id` INTEGER, `token` varchar(64), `exp` timestamp default '0000-00-00 00:00:00');
		"""
	else:
		sql = """
		CREATE TABLE IF NOT EXISTS `token` (`user_id` INTEGER, `token` varchar(64), `exp`  DATETIME default '0000-00-00 00:00:00');
		"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: token' or e == "1060 (42S21): Duplicate column name 'token' ":
				print('Updating... go to version 2.6')
			else:
				print("An error occurred:", e)
			return False
		else:
			print("DB was update to 2.5.6.1<br />")
			return True
	cur.close() 
	con.close()
	
def update_db_v_2_6(**kwargs):
	con, cur = get_cur()
	sql = """ select name from cred limit 1 """
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		if mysql_enable == '0':
			sql = """ CREATE TABLE IF NOT EXISTS `cred_id` (
					`id` integer primary key autoincrement,
					`name`	VARCHAR ( 64 ) UNIQUE,
					`enable`	INTEGER NOT NULL DEFAULT 1,
					`username`	VARCHAR ( 64 ) NOT NULL,
					`password`	VARCHAR ( 64 ) NOT NULL
				); 
				INSERT INTO cred_id (id, enable, username, password) select id, enable, username, password from cred;
				drop table cred;
				ALTER TABLE cred_id RENAME to cred;
				"""
			try:    
				cur.executescript(sql)
			except sqltool.Error as e:
				if kwargs.get('silent') != 1:
					if e.args[0] == 'duplicate column name: name' or e == "1060 (42S21): Duplicate column name 'name' ":
						pass
					else:
						print("An error occurred:", e)
				return False
			else:
				print("DB was update to 2.6<br />")
				return True
		else:
			sql = [ "CREATE TABLE IF NOT EXISTS cred_id(`id` integer primary key AUTO_INCREMENT, `name` VARCHAR ( 64 ) UNIQUE, `enable` INTEGER NOT NULL DEFAULT 1, `username` VARCHAR ( 64 ) NOT NULL, `password`	VARCHAR ( 64 ) NOT NULL ); ", 
					"INSERT INTO cred_id (enable, username, password) select enable, username, password from cred;",
					"drop table cred;",
					"ALTER TABLE cred_id RENAME to cred;" ]
			try:    
				for i in sql:
					cur.execute(i)
			except sqltool.Error as e:
				if kwargs.get('silent') != 1:
					if e.args[0] == 'duplicate column name: id' or e == "1060 (42S21): Duplicate column name 'id' ":
						print('DB was updated. No more run')
					else:
						print("An error occurred:", e)
				return False
			else:
				pass
				return True
			cur.close() 
			con.close()
				
def update_db_v_2_61(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN cred INTEGER NOT NULL DEFAULT 1;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: cred' or e == "1060 (42S21): Duplicate column name 'cred' ":
				print('Updating... go to version 2.6.1')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.6<br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_6_1(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `cred` ADD COLUMN groups INTEGER NOT NULL DEFAULT 1;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: groups' or e == "1060 (42S21): Duplicate column name 'groups' ":
				print('Updating... go to version 2.7')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.6.1<br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_7(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `servers` ADD COLUMN alert INTEGER NOT NULL DEFAULT 0;
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: alert' or e == "1060 (42S21): Duplicate column name 'groups' ":
				print('Updating... go to version 2.7.2')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("DB was update to 2.7.2<br />")
		return True
	cur.close() 
	con.close()

def update_db_v_2_7_2(**kwargs):
	con, cur = get_cur()
	if mysql_enable == '0':
		sql = """ CREATE TABLE IF NOT EXISTS `telegram` (`id` integer primary key autoincrement, `token` VARCHAR ( 64 ), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1); """
	else:
		sql = """ CREATE TABLE IF NOT EXISTS `telegram` (`id` integer primary key auto_increment, `token` VARCHAR ( 64 ), `chanel_name` INTEGER NOT NULL DEFAULT 1, `groups` INTEGER NOT NULL DEFAULT 1); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: telegram' or e == "1060 (42S21): Duplicate column name 'telegram' ":
				print("Update finished. No run more")
			else:
				print("An error occurred:", e)
		return False
	else:
		return True
	cur.close() 
	con.close()
	
def update_db_v_2_8(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `metrics` (`serv` varchar(64), curr_con INTEGER, cur_ssl_con INTEGER, sess_rate INTEGER, max_sess_rate INTEGER,`date`  DATETIME default '0000-00-00 00:00:00'); """
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
		
def update_db_v_2_8_2(**kwargs):
	con, cur = get_cur()
	sql = """ ALTER TABLE `servers` ADD COLUMN metrics INTEGER NOT NULL DEFAULT 0 """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: metrics' or e == "1060 (42S21): Duplicate column name 'metrics' ":
				print('DB was update to 2.8')
			else:
				print("An error occurred:", e)
			return False
		else:
			#print("DB was update to 2.8<br />")
			return True
	cur.close() 
	con.close()	
		
def update_db_v_2_9(**kwargs):
	con, cur = get_cur()
	sql = """CREATE TABLE IF NOT EXISTS `settings` (`param` varchar(64) UNIQUE, value varchar(64)); """
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: token' or e == "1060 (42S21): Duplicate column name 'token' ":
				print('Updating... go to version 2.10')
			else:
				print("An error occurred:", e.args[0])
				return False
		else:
			return True
	cur.close() 
	con.close()	
	
def update_db_v_2_91(**kwargs):
	con, cur = get_cur()
	sql = """
	insert into `settings` (param, value) values ('lists_path', 'lists');
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'column param is not unique' or e == "1062 (23000): Duplicate entry 'lists_path' for key 'param'":
				print('Updating... go to version 3.0')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version 3.0<br />")
		return True
	cur.close() 
	con.close()
	
def update_db_v_3(**kwargs):
	con, cur = get_cur()
	sql = """
	ALTER TABLE `settings` ADD COLUMN section varchar(64);
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: section' or e == " 1060 (42S21): Duplicate column name 'section' ":
				print('Updating... go to version 3.1')
			else:
				print("An error occurred:", e)
		return False
	cur.close() 
	con.close()
		
def update_db_v_31(**kwargs):
	con, cur = get_cur()
	sql = [ "ALTER TABLE `settings` ADD COLUMN `desc` varchar(64); ", 
				"INSERT INTO settings (param, value, section, `desc`) values('time_zone', 'UTC', 'main', 'Time Zone');",
				"INSERT INTO settings (param, value, section, `desc`) values('proxy', '', 'main', 'Proxy server. Use proto://ip:port');",
				"INSERT INTO settings (param, value, section, `desc`) values('session_ttl', '5', 'main', 'Time to live users sessions. In days');",
				"INSERT INTO settings (param, value, section, `desc`) values('token_ttl', '5', 'main', 'Time to live users tokens. In days');",
				"INSERT INTO settings (param, value, section, `desc`) values('local_path_logs', '/var/log/haproxy.log', 'logs', 'Logs save locally, disable by default');",
				"INSERT INTO settings (param, value, section, `desc`) values('syslog_server_enable', '0', 'logs', 'If exist syslog server for HAproxy logs, enable this option');",
				"INSERT INTO settings (param, value, section, `desc`) values('syslog_server', '0', 'logs', 'IP address syslog server');",
				"INSERT INTO settings (param, value, section, `desc`) values('log_time_storage', '14', 'logs', 'Time of storage of logs of user activity, in days');",
				"INSERT INTO settings (param, value, section, `desc`) values('restart_command', 'systemctl restart haproxy', 'haproxy', 'Command for restart HAproxy service');",
				"INSERT INTO settings (param, value, section, `desc`) values('status_command', 'systemctl status haproxy', 'haproxy', 'Command for status check HAproxy service');",
				"INSERT INTO settings (param, value, section, `desc`) values('stats_user', 'admin', 'haproxy', 'Username for Stats web page HAproxy');",
				"INSERT INTO settings (param, value, section, `desc`) values('stats_password', 'password', 'haproxy', 'Password for Stats web page HAproxy');",
				"INSERT INTO settings (param, value, section, `desc`) values('stats_port', '8085', 'haproxy', 'Port Stats web page HAproxy');",
				"INSERT INTO settings (param, value, section, `desc`) values('stats_page', 'stats', 'haproxy', 'URI Stats web page HAproxy');",
				"INSERT INTO settings (param, value, section, `desc`) values('haproxy_dir', '/etc/haproxy/', 'haproxy', 'Path to HAProxy dir');",
				"INSERT INTO settings (param, value, section, `desc`) values('haproxy_config_path', '/etc/haproxy/haproxy.cfg', 'haproxy', 'Path to HAProxy config');",
				"INSERT INTO settings (param, value, section, `desc`) values('server_state_file', '/etc/haproxy/haproxy.state', 'haproxy', 'Path to HAProxy state file');",
				"INSERT INTO settings (param, value, section, `desc`) values('haproxy_sock', '/var/run/haproxy.sock', 'haproxy', 'Path to HAProxy sock file');",
				"INSERT INTO settings (param, value, section, `desc`) values('haproxy_sock_port', '1999', 'haproxy', 'HAProxy sock port');",
				"INSERT INTO settings (param, value, section, `desc`) values('tmp_config_path', '/tmp/', 'haproxy', 'Temp store configs, for haproxy check');",
				"INSERT INTO settings (param, value, section, `desc`) values('cert_path', '/etc/ssl/certs/', 'haproxy', 'Path to SSL dir');",
				"INSERT INTO settings (param, value, section, `desc`) values('firewall_enable', '0', 'haproxy', 'If enable this option Haproxy-wi will be configure firewalld based on config port');",
				"update settings set `section` = 'main', `desc` = 'Path to black/white lists' where param = 'lists_path' "]
	try:    
		for i in sql:
			cur.execute(i)
			con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'duplicate column name: desc' or e == "1060 (42S21): Duplicate column name 'desc' ":
				print('Updating... go to version 3.2')
			else:
				print("An error occurred:", e)
		return False
	else:
		pass
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
				print('DB was updated')
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
	
def update_db_v_3_2_1(**kwargs):
	con, cur = get_cur()
	sql = """
	insert into `settings` (param, value, section, `desc`) values ('apache_log_path', '/var/log/httpd/', 'logs', 'Path to Apache logs');
	"""
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		if kwargs.get('silent') != 1:
			if e.args[0] == 'column param is not unique' or e == "1062 (23000): Duplicate entry 'lists_path' for key 'param'":
				print('DB was update')
			else:
				print("An error occurred:", e)
		return False
	else:
		print("Updating... go to version 3.0<br />")
		return True
	cur.close() 
	con.close()
			
def update_all():	
	update_db_v_2_0_1()
	update_db_v_2_0_1_1()
	update_db_v_2_0_5()
	update_db_v_2_4()
	update_db_v_2_5_6()
	update_db_v_2_5_6_1()
	update_db_v_2_6()
	update_db_v_2_61()
	update_db_v_2_6_1()
	update_db_v_2_7()
	update_db_v_2_7_2()
	update_db_v_2_8()
	update_db_v_2_8_2()
	update_db_v_2_9()
	update_db_v_2_91()
	update_db_v_3()
	update_db_v_31()
	update_db_v_3_2()
	update_db_v_3_21()
	update_db_v_3_2_1()
	
def update_all_silent():
	update_db_v_2_0_1(silent=1)
	update_db_v_2_0_1_1(silent=1)
	update_db_v_2_0_5(silent=1)
	update_db_v_2_4(silent=1)
	update_db_v_2_5_6(silent=1)
	update_db_v_2_5_6_1(silent=1)
	update_db_v_2_6(silent=1)
	update_db_v_2_61(silent=1)
	update_db_v_2_6_1(silent=1)
	update_db_v_2_7(silent=1)
	update_db_v_2_7_2(silent=1)
	update_db_v_2_8(silent=1)
	update_db_v_2_8_2(silent=1)
	update_db_v_2_9(silent=1)
	update_db_v_2_91(silent=1)
	update_db_v_3(silent=1)
	update_db_v_31(silent=1)
	update_db_v_3_2(silent=1)
	update_db_v_3_21(silent=1)
	update_db_v_3_2_1(silent=1)
		