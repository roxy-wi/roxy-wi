#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import funct

mysql_enable = funct.get_config_var('mysql', 'enable')

if mysql_enable == '1':	
	import mysql.connector as sqltool
else:
	db = "haproxy-wi.db"
	import sqlite3 as sqltool
	
	
def get_cur():
	try:
		if mysql_enable == '0':
			con = sqltool.connect(db, isolation_level=None)  
		else:
			mysql_user = funct.get_config_var('mysql', 'mysql_user')
			mysql_password = funct.get_config_var('mysql', 'mysql_password')
			mysql_db = funct.get_config_var('mysql', 'mysql_db')
			mysql_host = funct.get_config_var('mysql', 'mysql_host')
			mysql_port = funct.get_config_var('mysql', 'mysql_port')	
			con = sqltool.connect(user=mysql_user, password=mysql_password,
									host=mysql_host, port=mysql_port,
									database=mysql_db)	
		cur = con.cursor()
	except sqltool.Error as e:
		funct.logging('DB ', ' '+e, haproxywi=1, login=1)
	else:
		return con, cur
		
	
def add_user(user, email, password, role, activeuser):
	con, cur = get_cur()
	if password != 'aduser':
		sql = """INSERT INTO user (username, email, password, role, activeuser) VALUES ('%s', '%s', '%s', '%s', '%s')""" % (user, email, funct.get_hash(password), role, activeuser)
	else:
		sql = """INSERT INTO user (username, email, role, ldap_user, activeuser) VALUES ('%s', '%s', '%s', '1', '%s')""" % (user, email, role, activeuser)		
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()   
	
	
def update_user(user, email, role, id, activeuser):
	con, cur = get_cur()
	sql = """update user set username = '%s', 
			email = '%s',
			role = '%s',
			activeuser = '%s'
			where id = '%s'""" % (user, email,  role, activeuser, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	
	
def update_user_groups(groups, id):
	con, cur = get_cur()
	sql = """insert into user_groups(user_id, user_group_id) values('%s', '%s')""" % (id, groups)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	
	
def delete_user_groups(id):
	con, cur = get_cur()
	sql = """delete from user_groups
			where user_id = '%s'""" % (id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	
	
def update_user_password(password, id):
	con, cur = get_cur()
	sql = """update user set password = '%s'
			where id = '%s'""" % (funct.get_hash(password), id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	

def delete_user(id):
	con, cur = get_cur()
	sql = """delete from user where id = '%s'""" % (id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()
	con.close()
	
def add_group(name, description):
	con, cur = get_cur()
	sql = """INSERT INTO groups (name, description) VALUES ('%s', '%s')""" % (name, description)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		sql = """select last_insert_rowid()"""
		try:
			cur.execute(sql)
			con.commit()
		except sqltool.Error as e:
			funct.out_error(e)
			con.rollback()
		else:
			for g in cur.fetchall():
				group_id = g[0]
			add_setting_for_new_group(group_id)

		return True

	cur.close()    
	con.close()


def add_setting_for_new_group(group_id):
	con, cur = get_cur()
	group_id = str(group_id)
	sql = list()
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('time_zone', 'UTC', 'main', 'Time Zone','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('proxy', '', 'main', 'Proxy server. Use proto://ip:port','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('session_ttl', '5', 'main', 'Time to live users sessions. In days', '" + group_id + "')")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('token_ttl', '5', 'main', 'Time to live users tokens. In days','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('tmp_config_path', '/tmp/', 'main', 'Temp store configs, for check. Path must exist','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('cert_path', '/etc/ssl/certs/', 'main', 'Path to SSL dir. Folder owner must be a user which set in the SSH settings. Path must exist','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('local_path_logs', '/var/log/haproxy.log', 'logs', 'Logs save locally, enabled by default','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('syslog_server_enable', '0', 'logs', 'If exist syslog server for HAproxy logs, enable this option','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('syslog_server', '0', 'logs', 'IP address syslog server','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('log_time_storage', '14', 'logs', 'Time of storage of logs of user activity, in days','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('stats_user', 'admin', 'haproxy', 'Username for Stats web page HAproxy','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('stats_password', 'password', 'haproxy', 'Password for Stats web page HAproxy','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('stats_port', '8085', 'haproxy', 'Port Stats web page HAproxy','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('stats_page', 'stats', 'haproxy', 'URI Stats web page HAproxy','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('haproxy_dir', '/etc/haproxy/', 'haproxy', 'Path to HAProxy dir','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('haproxy_config_path', '/etc/haproxy/haproxy.cfg', 'haproxy', 'Path to HAProxy config','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('server_state_file', '/etc/haproxy/haproxy.state', 'haproxy', 'Path to HAProxy state file','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('haproxy_sock', '/var/run/haproxy.sock', 'haproxy', 'Path to HAProxy sock file','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('haproxy_sock_port', '1999', 'haproxy', 'HAProxy sock port','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('firewall_enable', '0', 'haproxy', 'If enable this option Haproxy-wi will be configure firewalld based on config port','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_path_error_logs', '/var/log/nginx/error.log', 'nginx', 'Nginx error log','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_stats_user', 'admin', 'nginx', 'Username for Stats web page Nginx','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_stats_password', 'password', 'nginx', 'Password for Stats web page Nginx','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_stats_port', '8086', 'nginx', 'Stats port for web page Nginx','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_stats_page', 'stats', 'nginx', 'URI Stats for web page Nginx','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_dir', '/etc/nginx/conf.d/', 'nginx', 'Path to Nginx dir','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('nginx_config_path', '/etc/nginx/conf.d/default.conf', 'nginx', 'Path to Nginx config','" + group_id + "');")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_enable', '0', 'ldap', 'If 1 ldap enabled', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_server', '', 'ldap', 'IP address ldap server', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_port', '389', 'ldap', 'Default port is 389 or 636', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_user', '', 'ldap', 'Login for connect to LDAP server. Enter: user@domain.com',  " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_password', '', 'ldap', 'Password for connect to LDAP server', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_base', '', 'ldap', 'Base domain. Example: dc=domain, dc=com', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_domain', '', 'ldap', 'Domain for login, that after @, like user@domain.com, without user@', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_class_search', 'user', 'ldap', 'Class to search user', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_user_attribute', 'sAMAccountName', 'ldap', 'User attribute for search', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_search_field', 'mail', 'ldap', 'Field where user e-mail saved', " + group_id + ");")
	sql.append("INSERT  INTO settings (param, value, section, `desc`, `group`) values('ldap_type', '0', 'ldap', 'If 0 then will be used LDAP, if 1 then will be used LDAPS ', " + group_id + ");")

	for i in sql:
		try:
			cur.execute(i)
			con.commit()
		except sqltool.Error as e:
			funct.out_error(e)
	else:
		return True
	cur.close()
	con.close()


def delete_group_settings(group_id):
	con, cur = get_cur()
	sql = """ delete from settings where `group` = '%s'""" % (group_id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def delete_group(id):
	con, cur = get_cur()
	sql = """ delete from groups where id = '%s'""" % (id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		delete_group_settings(id)
		return True
	cur.close()    
	con.close() 
	
	
def update_group(name, descript, id):
	con, cur = get_cur()
	sql = """ update groups set 
		name = '%s',
		description = '%s' 
		where id = '%s';
		""" % (name, descript, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	

def add_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx):
	con, cur = get_cur()
	sql = """ INSERT INTO servers (hostname, ip, groups, type_ip, enable, master, cred, port, `desc`, haproxy, nginx) 
			VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
		""" % (hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx)
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False	
	cur.close()    
	con.close() 	
	

def delete_server(id):
	con, cur = get_cur()
	sql = """ delete from servers where id = '%s'""" % (id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else: 
		return True
	cur.close()    
	con.close() 		
	
	
def update_hapwi_server(id, alert, metrics, active):
	con, cur = get_cur()
	sql = """ update servers set 
			alert = '%s',
			metrics = '%s',
			active = '%s'
			where id = '%s'""" % (alert, metrics, active, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	

def update_server(hostname, group, typeip, enable, master, id, cred, port, desc, haproxy, nginx):
	con, cur = get_cur()
	sql = """ update servers set 
			hostname = '%s',
			groups = '%s',
			type_ip = '%s',
			enable = '%s',
			master = '%s',
			cred = '%s',
			port = '%s',
			`desc` = '%s',
			haproxy = '%s',
			nginx = '%s'
			where id = '%s'""" % (hostname, group, typeip, enable, master, cred, port, desc, haproxy, nginx, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	

def update_server_master(master, slave):
	con, cur = get_cur()
	sql = """ select id from servers where ip = '%s' """ % master
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	for id in cur.fetchall():
		sql = """ update servers set master = '%s' where ip = '%s' """ % (id[0], slave)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def select_users(**kwargs):
	con, cur = get_cur()
	sql = """select * from user ORDER BY id"""
	if kwargs.get("user") is not None:
		sql = """select * from user where username='%s' """ % kwargs.get("user")
	if kwargs.get("id") is not None:
		sql = """select * from user where id='%s' """ % kwargs.get("id")
	if kwargs.get("group") is not None:
		sql = """ select user.* from user left join user_groups as groups on user.id = groups.user_id where groups.user_group_id = '%s' group by id;
		""" % kwargs.get("group")
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  


def select_user_groups(id, **kwargs):
	con, cur = get_cur()
	sql = """select user_group_id from user_groups where user_id = '%s' """ % id
	if kwargs.get("limit") is not None:
		sql = """select user_group_id from user_groups where user_id = '%s' limit 1 """ % id

	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		if kwargs.get("limit") is not None:
			for g in cur.fetchall():
				return g[0]	
		else:
			return cur.fetchall()
	cur.close()    
	con.close()


def check_user_group(user_id, group_id):
	con, cur = get_cur()
	sql = """select * from user_groups where user_id='%s' and user_group_id = '%s' """ % (user_id, group_id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
		print(str(e))
	else:
		for g in cur.fetchall():
			#print(str(g[0]))
			if g[0] != '':
				return True
			else:
				#print('Atata!')
				return False

	cur.close()
	con.close()


def select_user_groups_with_names(id, **kwargs):
	con, cur = get_cur()
	if kwargs.get("all") is not None:
		sql = """select user_groups.user_id, groups.name from user_groups 
			left join groups as groups on user_groups.user_group_id = groups.id """
	else:
		sql = """select user_groups.user_group_id, groups.name from user_groups 
			left join groups as groups on user_groups.user_group_id = groups.id 
			where user_groups.user_id = '%s' """ % id
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		if kwargs.get("limit") is not None:
			for g in cur.fetchall():
				return g[0]	
		else:
			return cur.fetchall()
	cur.close()    
	con.close() 		
	
	
def select_groups(**kwargs):
	con, cur = get_cur()
	sql = """select * from groups ORDER BY id"""
	if kwargs.get("group") is not None:
		sql = """select * from groups where name='%s' """ % kwargs.get("group")
	if kwargs.get("id") is not None:
		sql = """select * from groups where id='%s' """ % kwargs.get("id")

	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  
	
	
def select_server_by_name(name):
	con, cur = get_cur()
	sql = """select ip from servers where hostname='%s' """ % name
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for name in cur.fetchone():
			return name
	cur.close()    
	con.close()
	
	
def select_servers(**kwargs):
	con, cur = get_cur()
	sql = """select * from servers where enable = '1' ORDER BY groups """
	
	if kwargs.get("server") is not None:
		sql = """select * from servers where ip='%s' """ % kwargs.get("server")
	if kwargs.get("full") is not None:
		sql = """select * from servers ORDER BY hostname """ 
	if kwargs.get("get_master_servers") is not None:
		sql = """select id,hostname from servers where master = 0 and type_ip = 0 and enable = 1 ORDER BY groups """ 
	if kwargs.get("get_master_servers") is not None and kwargs.get('uuid') is not None:
		sql = """ select servers.id, servers.hostname from servers 
			left join user as user on servers.groups = user.groups 
			left join uuid as uuid on user.id = uuid.user_id 
			where uuid.uuid = '%s' and servers.master = 0 and servers.type_ip = 0 and servers.enable = 1 ORDER BY servers.groups 
			""" % kwargs.get('uuid')
	if kwargs.get("id"):
		sql = """select * from servers where id='%s' """ % kwargs.get("id")
	if kwargs.get("hostname"):
		sql = """select * from servers where hostname='%s' """ % kwargs.get("hostname")
	if kwargs.get("id_hostname"):
		sql = """select * from servers where hostname='%s' or id = '%s' or ip = '%s'""" % (kwargs.get("id_hostname"), kwargs.get("id_hostname"), kwargs.get("id_hostname"))
	if kwargs.get("server") and kwargs.get("keep_alive"):
		sql = """select active from servers where ip='%s' """ % kwargs.get("server")
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  
	
def write_user_uuid(login, user_uuid):
	con, cur = get_cur()
	session_ttl = get_setting('session_ttl')
	session_ttl = int(session_ttl)
	sql = """ select id from user where username = '%s' """ % login
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	for id in cur.fetchall():
		if mysql_enable == '1':
			sql = """ insert into uuid (user_id, uuid, exp) values('%s', '%s',  now()+ INTERVAL '%s' day) """ % (id[0], user_uuid, session_ttl)
		else:
			sql = """ insert into uuid (user_id, uuid, exp) values('%s', '%s',  datetime('now', '+%s days')) """ % (id[0], user_uuid, session_ttl)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
def write_user_token(login, user_token):
	con, cur = get_cur()
	token_ttl = get_setting('token_ttl')	
	sql = """ select id from user where username = '%s' """ % login
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	for id in cur.fetchall():
		if mysql_enable == '1':
			sql = """ insert into token (user_id, token, exp) values('%s', '%s',  now()+ INTERVAL %s day) """ % (id[0], user_token, token_ttl)
		else:
			sql = """ insert into token (user_id, token, exp) values('%s', '%s',  datetime('now', '+%s days')) """ % (id[0], user_token, token_ttl)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
def get_token(uuid):
	con, cur = get_cur()
	sql = """ select token.token from token left join uuid as uuid on uuid.user_id = token.user_id where uuid.uuid = '%s' """ % uuid
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for token in cur.fetchall():
			return token[0]				
	cur.close()    
	con.close()
	
	
def delete_uuid(uuid):
	con, cur = get_cur()
	sql = """ delete from uuid where uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
		con.commit()
	except sqltool.Error as e:
		pass
	cur.close()    
	con.close() 
	
	
def delete_old_uuid():
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ delete from uuid where exp < now() or exp is NULL """
		sql1 = """ delete from token where exp < now() or exp is NULL """
	else:
		sql = """ delete from uuid where exp < datetime('now') or exp is NULL""" 
		sql1 = """ delete from token where exp < datetime('now') or exp is NULL""" 
	try:    
		cur.execute(sql)
		cur.execute(sql1)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()		


def update_last_act_user(uuid):
	con, cur = get_cur()
	session_ttl = get_setting('session_ttl')
	
	if mysql_enable == '1':
		sql = """ update uuid set exp = now()+ INTERVAL %s day where uuid = '%s' """ % (session_ttl, uuid)
	else:
		sql = """ update uuid set exp = datetime('now', '+%s days') where uuid = '%s' """ % (session_ttl, uuid)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def get_user_name_by_uuid(uuid):
	con, cur = get_cur()
	sql = """ select user.username from user left join uuid as uuid on user.id = uuid.user_id where uuid.uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 


def get_user_id_by_uuid(uuid):
	con, cur = get_cur()
	sql = """ select user.id from user left join uuid as uuid on user.id = uuid.user_id where uuid.uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 
	
	
def get_user_role_by_uuid(uuid):
	con, cur = get_cur()
	try:
		if mysql_enable == '1':
			cur.execute( """ select role.id from user left join uuid as uuid on user.id = uuid.user_id left join role on role.name = user.role where uuid.uuid = '%s' """ % uuid )
		else:
			cur.execute("select role.id from user left join uuid as uuid on user.id = uuid.user_id left join role on role.name = user.role where uuid.uuid = ?", (uuid,))	
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for user_id in cur.fetchall():
			return int(user_id[0])
	cur.close()    
	con.close() 
	
	
def get_role_id_by_name(name):
	con, cur = get_cur()
	sql = """ select id from role where name = '%s' """ % name
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 


def get_user_telegram_by_group(group):
	con, cur = get_cur()
	sql = """ select telegram.* from telegram where groups = '%s' """ % group
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def get_telegram_by_ip(ip):
	con, cur = get_cur()
	sql = """ select telegram.* from telegram left join servers as serv on serv.groups = telegram.groups where serv.ip = '%s' """ % ip
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()


def get_telegram_by_id(id):
	con, cur = get_cur()
	sql = """ select * from telegram where id = '%s' """ % id
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def get_dick_permit(**kwargs):
	import http.cookies
	import os
	if kwargs.get('username'):
		user = kwargs.get('username')
		grp = '1'
	else:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		group = cookie.get('group')
		grp = group.value
		user = get_user_id_by_uuid(user_id.value)
	disable = ''
	haproxy = ''
	nginx = ''
	keepalived = ''
	ip = ''
	
	if kwargs.get('virt'):
		type_ip = "" 
	else:
		type_ip = "and type_ip = 0" 
	if kwargs.get('disable') == 0:
		disable = 'or enable = 0'
	if kwargs.get('ip'):
		ip = "and ip = '%s'" % kwargs.get('ip')
	if kwargs.get('haproxy'):
		haproxy = "and haproxy = 1"
	if kwargs.get('nginx'):
		nginx = "and nginx = 1"
	if kwargs.get('keepalived'):
		nginx = "and keepalived = 1"

	if funct.check_user_group():
		con, cur = get_cur()
		if grp == '1':
			sql = """ select * from servers where enable = 1 %s %s %s order by pos""" % (disable, type_ip, nginx)
		else:
			sql = """ select * from servers where groups = '{group}' and (enable = 1 {disable}) {type_ip} {ip} {haproxy} {nginx} {keepalived} order by pos
			""".format(group=grp, disable=disable, type_ip=type_ip, ip=ip, haproxy=haproxy, nginx=nginx, keepalived=keepalived)

		try:
			cur.execute(sql)
		except sqltool.Error as e:
			funct.out_error(e)
		else:
			return cur.fetchall()

		cur.close()
		con.close()
	else:
		print('Atata!')



def is_master(ip, **kwargs):
	con, cur = get_cur()
	sql = """ select slave.ip, slave.hostname from servers as master left join servers as slave on master.id = slave.master where master.ip = '%s' """ % ip
	if kwargs.get('master_slave'):
		sql = """ select master.hostname, master.ip, slave.hostname, slave.ip from servers as master left join servers as slave on master.id = slave.master where slave.master > 0 """
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_ssh(**kwargs):
	con, cur = get_cur()
	sql = """select * from cred """
	if kwargs.get("name") is not None:
		sql = """select * from cred where name = '%s' """ % kwargs.get("name")
	if kwargs.get("id") is not None:
		sql = """select * from cred where id = '%s' """ % kwargs.get("id")
	if kwargs.get("serv") is not None:
		sql = """select serv.cred, cred.* from servers as serv left join cred on cred.id = serv.cred where serv.ip = '%s' """ % kwargs.get("serv")
	if kwargs.get("group") is not None:
		sql = """select * from cred where groups = '%s' """ % kwargs.get("group")
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def insert_new_ssh(name, enable, group, username, password):
	con, cur = get_cur()
	sql = """insert into cred(name, enable, groups, username, password) values ('%s', '%s', '%s', '%s', '%s') """ % (name, enable, group, username, password)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def delete_ssh(id):
	con, cur = get_cur()
	sql = """ delete from cred where id = %s """ % (id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def update_ssh(id, name, enable, group, username, password):
	con, cur = get_cur()
	sql = """ update cred set 
			name = '%s',
			enable = '%s',
			groups = %s,
			username = '%s',
			password = '%s' where id = '%s' """ % (name, enable, group, username, password, id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def insert_backup_job(server, rserver, rpath, type, time, cred, description):
	con, cur = get_cur()
	sql = """insert into backups(server, rhost, rpath, `type`, `time`, `cred`, `description`) 
			values ('%s', '%s', '%s', '%s', '%s', '%s', '%s') """ % (server, rserver, rpath, type, time, cred, description)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		print('error: '+str(e))
		con.rollback()
		return False
	else:
		return True
	cur.close()
	con.close()


def select_backups(**kwargs):
	con, cur = get_cur()
	sql = """select * from backups ORDER BY id"""
	if kwargs.get("server") is not None and kwargs.get("rserver") is not None:
		sql = """select * from backups where server='%s' and rhost = '%s' """ % (kwargs.get("server"), kwargs.get("rserver"))
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def update_backup(server, rserver, rpath, type, time, cred, description, id):
	con, cur = get_cur()
	sql = """update backups set server = '%s', 
			rhost = '%s', 
			rpath = '%s', 
			type = '%s', 
			time = '%s', 
			cred = '%s', 
			description = '%s' where id = '%s' """ % (server, rserver, rpath, type, time, cred, description, id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()
	con.close()


def delete_backups(id):
	con, cur = get_cur()
	sql = """ delete from backups where id = %s """ % (id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def check_exists_backup(server):
	con, cur = get_cur()
	sql = """ select id from backups where server = '%s' """ % server
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for s in cur.fetchall():
			if s[0] is not None:
				return True
			else:
				return False
	cur.close()
	con.close()


def insert_new_telegram(token, chanel, group):
	con, cur = get_cur()
	sql = """insert into telegram(`token`, `chanel_name`, `groups`) values ('%s', '%s', '%s') """ % (token, chanel, group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('<span class="alert alert-danger" id="error">An error occurred: ' + e.args[0] + ' <a title="Close" id="errorMess"><b>X</b></a></span>')
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def delete_telegram(id):
	con, cur = get_cur()
	sql = """ delete from telegram where id = %s """ % (id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def select_telegram(**kwargs):
	con, cur = get_cur()
	sql = """select * from telegram  """
	if kwargs.get('group'):
		sql = """select * from telegram where groups = '%s' """ % kwargs.get('group')
	if kwargs.get('token'):
		sql = """select * from telegram where token = '%s' """ % kwargs.get('token')
	if kwargs.get('id'):
		sql = """select * from telegram where id = '%s' """ % kwargs.get('id')
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def insert_new_telegram(token, chanel, group):
	con, cur = get_cur()
	sql = """insert into telegram(`token`, `chanel_name`, `groups`) values ('%s', '%s', '%s') """ % (token, chanel, group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		print('<span class="alert alert-danger" id="error">An error occurred: ' + e.args[0] + ' <a title="Close" id="errorMess"><b>X</b></a></span>')
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def update_telegram(token, chanel, group, id):
	con, cur = get_cur()
	sql = """ update telegram set 
			`token` = '%s',
			`chanel_name` = '%s',
			`groups` = '%s'
			where id = '%s' """ % (token, chanel, group, id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def insert_new_option(option, group):
	con, cur = get_cur()
	sql = """insert into options(`options`, `groups`) values ('%s', '%s') """ % (option, group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def select_options(**kwargs):
	con, cur = get_cur()
	sql = """select * from options  """
	if kwargs.get('option'):
		sql = """select * from options where options = '%s' """ % kwargs.get('option')
	if kwargs.get('group'):
		sql = """select options from options where groups = '{}' and options like '{}%' """.format(kwargs.get('group'), kwargs.get('term'))
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def update_options(option, id):
	con, cur = get_cur()
	sql = """ update options set 
			options = '%s'
			where id = '%s' """ % (option, id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def delete_option(id):
	con, cur = get_cur()
	sql = """ delete from options where id = %s """ % (id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def insert_new_savedserver(server, description, group):
	con, cur = get_cur()
	sql = """insert into saved_servers(`server`, `description`, `groups`) values ('%s', '%s', '%s') """ % (server, description, group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def select_saved_servers(**kwargs):
	con, cur = get_cur()
	sql = """select * from saved_servers  """
	if kwargs.get('server'):
		sql = """select * from saved_servers where server = '%s' """ % kwargs.get('server')
	if kwargs.get('group'):
		sql = """select server,description from saved_servers where groups = '{}' and server like '{}%' """.format(kwargs.get('group'), kwargs.get('term'))
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def update_savedserver(server, description, id):
	con, cur = get_cur()
	sql = """ update saved_servers set 
			server = '%s',
			description = '%s'
			where id = '%s' """ % (server, description, id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def delete_savedserver(id):
	con, cur = get_cur()
	sql = """ delete from saved_servers where id = %s """ % (id)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	else:
		return True
	cur.close()
	con.close()


def insert_mentrics(serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ insert into metrics (serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate, date) values('%s', '%s', '%s', '%s', '%s', now()) """ % (serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate)
	else:
		sql = """ insert into metrics (serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate, date) values('%s', '%s', '%s', '%s', '%s',  datetime('now', 'localtime')) """ % (serv, curr_con, cur_ssl_con, sess_rate, max_sess_rate)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def select_waf_metrics_enable(id):
	con, cur = get_cur()
	sql = """ select waf.metrics from waf  left join servers as serv on waf.server_id = serv.id where server_id = '%s' """ % id
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_waf_metrics_enable_server(ip):
	con, cur = get_cur()
	sql = """ select waf.metrics from waf  left join servers as serv on waf.server_id = serv.id where ip = '%s' """ % ip
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for enable in cur.fetchall():
			return enable[0]
	cur.close()
	con.close()

def select_waf_servers(serv):
	con, cur = get_cur()
	sql = """ select serv.ip from waf left join servers as serv on waf.server_id = serv.id where serv.ip = '%s' """ % serv
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_all_waf_servers():
	con, cur = get_cur()
	sql = """ select serv.ip from waf left join servers as serv on waf.server_id = serv.id """
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_waf_servers_metrics(uuid, **kwargs):
	con, cur = get_cur()
	sql = """ select * from user where username = '%s' """ % get_user_name_by_uuid(uuid)

	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for group in cur:
			if group[5] == '1':
				sql = """ select servers.ip from servers left join waf as waf on waf.server_id = servers.id where servers.enable = 1 and waf.metrics = '1'  """
			else:
				sql = """ select servers.ip from servers left join waf as waf on waf.server_id = servers.id where servers.enable = 1 and waf.metrics = '1' and servers.groups like '%{group}%' """.format(group=group[5])
		try:
			cur.execute(sql)
		except sqltool.Error as e:
			funct.out_error(e)
		else:
			return cur.fetchall()
	cur.close()
	con.close()


def select_waf_metrics(serv, **kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ select * from waf_metrics where serv = '%s' order by `date` desc limit 60 """ % serv
	else:
		sql = """ select * from (select * from waf_metrics where serv = '%s' order by `date` desc limit 60) order by `date`""" % serv
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def insert_waf_metrics_enable(serv, enable):
	con, cur = get_cur()
	sql = """ insert into waf (server_id, metrics) values((select id from servers where ip = '%s'), '%s') """ % (serv, enable)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()

def insert_waf_rules(serv):
	con, cur = get_cur()
	sql = list()
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Ignore static', 'modsecurity_crs_10_ignore_static.conf', 'This ruleset will skip all tests for media files, but will skip only the request body phase (phase 2) for text files. To skip the outbound stage for text files, add file 47 (skip_outbound_checks) to your configuration, in addition to this fileth/aws/login');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Brute force protection', 'modsecurity_crs_11_brute_force.conf', 'Anti-Automation Rule for specific Pages (Brute Force Protection) This is a rate-limiting rule set and does not directly correlate whether the authentication attempt was successful or not');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'DOS Protections', 'modsecurity_crs_11_dos_protection.conf', 'Enforce an existing IP address block and log only 1-time/minute. We do not want to get flooded by alerts during an attack or scan so we are only triggering an alert once/minute.  You can adjust how often you want to receive status alerts by changing the expirevar setting below');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Proxy abuse', 'modsecurity_crs_11_proxy_abuse.conf', 'Rule set for detecting Open Proxy Abuse/Chaining');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Slow DOS protection', 'modsecurity_crs_11_slow_dos_protection.conf', 'Rule set for detecting Slow HTTP Denial of Service Attacks');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'XML enabler', 'modsecurity_crs_13_xml_enabler.conf', 'The rules in this file will trigger the XML parser upon an XML request');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Session hijacking', 'modsecurity_crs_16_session_hijacking.conf', 'This rule file will identify outbound Set-Cookie/Set-Cookie2 response headers and then initiate the proper ModSecurity session persistent collection (setsid). The rules in this file are required if you plan to run other checks such as  Session Hijacking, Missing HTTPOnly flag, etc...');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Protocol violations', 'modsecurity_crs_20_protocol_violations.conf', 'Some protocol violations are common in application layer attacks. Validating HTTP requests eliminates a large number of application layer attacks. The purpose of this rules file is to enforce HTTP RFC requirements that state how  the client is supposed to interact with the server. http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Protocol anomalies', 'modsecurity_crs_21_protocol_anomalies.conf', 'Some common HTTP usage patterns are indicative of attacks but may also be used by non-browsers for legitimate uses. Do not accept requests without common headers. All normal web browsers include Host, User-Agent and Accept headers. Implies either an attacker or a legitimate automation client');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Detect CC#', 'modsecurity_crs_25_cc_known.conf', 'Detect CC# in input, log transaction and sanitize');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'CC traker', 'modsecurity_crs_25_cc_track_pan.conf', 'Credit Card Track 1 and 2 and PAN Leakage Checks');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'HTTP policy', 'modsecurity_crs_30_http_policy.conf', 'HTTP policy enforcement The HTTP policy enforcement rule set sets limitations on the use of HTTP by clients. Few applications require the breadth and depth of the HTTP protocol. On the other hand many attacks abuse valid but rare HTTP use patterns. Restricting  HTTP protocol usage is effective in therefore effective in blocking many  application layer attacks');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Bad robots', 'modsecurity_crs_35_bad_robots.conf', 'Bad robots detection is based on checking elements easily controlled by the client. As such a determined attacked can bypass those checks. Therefore bad robots detection should not be viewed as a security mechanism against targeted attacks but rather as a nuisance reduction, eliminating most of the random attacks against your web site');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'OS Injection Attacks', 'modsecurity_crs_40_generic_attacks.conf', 'OS Command Injection Attacks');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'SQL injection', 'modsecurity_crs_41_sql_injection_attacks.conf', 'SQL injection protection');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'XSS Protections', 'modsecurity_crs_41_xss_attacks.conf', 'XSS attacks protection');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Comment spam', 'modsecurity_crs_42_comment_spam.conf', 'Comment spam is an attack against blogs, guestbooks, wikis and other types of interactive web sites that accept and display hyperlinks submitted by visitors. The spammers automatically post specially crafted random comments which include links that point to the spammer\'s web site. The links artificially increas the site's search engine ranking and may make the site more noticable in search results.');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'CSP enforcement', 'modsecurity_crs_42_csp_enforcement.conf', 'The purpose of these settings is to send CSP response headers to Mozilla FireFox users so that you can enforce how dynamic content is used. CSP usage helps to prevent XSS attacks against your users.');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'CSRF Protections', 'modsecurity_crs_43_csrf_protection.conf', 'You must have also activated the session hijacking conf file as it initiates the Session Collection and creates the CSRF token');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Trojans Protections', 'modsecurity_crs_45_trojans.conf ', 'The trojan access detection rules detects access to known Trojans already installed on a server. Uploading of Trojans is part of the Anti-Virus rules  and uses external Anti Virus program when uploading files. Detection of Trojans access is especially important in a hosting environment where the actual Trojan upload may be done through valid methods and not through hacking');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Joomla Protections', 'modsecurity_crs_46_slr_et_joomla_attacks.conf', 'Use this if you have Joomla CMS');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'RFI Protections', 'modsecurity_crs_46_slr_et_lfi_attacks.conf', 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference external scripts. The perpetrator’s goal is to exploit the referencing function in an application to upload malware (e.g., backdoor shells) from a remote URL located within a different domain');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'phpBB Protections', 'modsecurity_crs_46_slr_et_phpbb_attacks.conf', 'Use this if you have phpBB forum');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'RFI Protections 2', 'modsecurity_crs_46_slr_et_rfi_attacks.conf', 'Remote file inclusion is an attack targeting vulnerabilities in web applications that dynamically reference external scripts. The perpetrator’s goal is to exploit the referencing function in an application to upload malware (e.g., backdoor shells) from a remote URL located within a different domain');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'SQLi Protections', ' modsecurity_crs_46_slr_et_sqli_attacks.conf', 'SQLi injection attacks protection');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Wordpress Protections', 'modsecurity_crs_46_slr_et_wordpress_attacks.conf', 'Use this if you have Wordpess CMS');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'XSS Protections 2', 'modsecurity_crs_46_slr_et_xss_attacks.conf', 'XSS attacks protection');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Common exceptions', 'modsecurity_crs_47_common_exceptions.conf', 'This file is used as an exception mechanism to remove common false positives that may be encountered');" % serv)
	sql.append("INSERT  INTO waf_rules (serv, rule_name, rule_file, `desc`) values('%s', 'Hader tagging', 'modsecurity_crs_49_header_tagging.conf', 'This file will add Request Header Tagging which allows ModSecurity to communicate any event/rule matches it finds with the downstream application server.  The concept is similar to that of Anti-SPAM apps for Email (such as SpamAssassin). The idea is that if the WAF is in a DetectionOnly mode, it can still share data with the destination app server and then the app server may choose to inspect the new WAF request headers and factor in this data into a possible blocking decision. This concept is tremendously useful in a distributed architecture and/or when there are Fraud Detection Systems at the app server layer that can correlate the WAF data into the overall Fraud Score.  This is also useful in Hosting Environments where the decision to block may not be as clear');" % serv)
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


def select_waf_rules(serv):
	con, cur = get_cur()
	sql = """ select id, rule_name, en, `desc` from waf_rules where serv = '%s' """ % serv
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def delete_waf_server(id):
	con, cur = get_cur()
	sql = """ delete from waf where server_id = '%s' """ % id
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def insert_waf_mentrics(serv, conn):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ insert into waf_metrics (serv, conn, date) values('%s', '%s', now()) """ % (serv, conn)
	else:
		sql = """ insert into waf_metrics (serv, conn, date) values('%s', '%s',  datetime('now', 'localtime')) """ % (serv, conn)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def delete_waf_mentrics():
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ delete from metrics where date < now() - INTERVAL 3 day """
	else:
		sql = """ delete from metrics where date < datetime('now', '-3 days') """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def update_waf_metrics_enable(name, enable):
	con, cur = get_cur()
	sql = """ update waf set metrics = %s where server_id = (select id from servers where hostname = '%s') """ % (enable, name)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def delete_mentrics():
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ delete from metrics where date < now() - INTERVAL 3 day """
	else:
		sql = """ delete from metrics where date < datetime('now', '-3 days') """
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()
	con.close()


def select_metrics(serv, **kwargs):
	con, cur = get_cur()
	if mysql_enable == '1':
		sql = """ select * from metrics where serv = '%s' order by `date` desc limit 60 """ % serv
	else:
		sql = """ select * from (select * from metrics where serv = '%s' order by `date` desc limit 60) order by `date` """ % serv
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_servers_metrics_for_master(**kwargs):
	con, cur = get_cur()
	sql = """select ip from servers where metrics = 1 """
	if kwargs.get('group') is not None:
		sql = """select ip from servers where metrics = 1 and groups = '%s' """ % kwargs.get('group')
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def select_servers_metrics(uuid, **kwargs):
	con, cur = get_cur()
	import http.cookies
	import os
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	group = cookie.get('group')
	group = group.value

	if funct.check_user_group():
		if group == '1':
			sql = """ select ip from servers where enable = 1 and metrics = '1' """
		else:
			sql = """ select ip from servers where groups = '{group}' and metrics = '1'""".format(group=group)
		try:
			cur.execute(sql)
		except sqltool.Error as e:
			funct.out_error(e)
		else:
			return cur.fetchall()
	cur.close()
	con.close()


def select_table_metrics(uuid):
	con, cur = get_cur()
	import http.cookies
	import os
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	group = cookie.get('group')
	group = group.value

	if funct.check_user_group():
		if group == '1':
			groups = ""
		else:
			groups = "and servers.groups = '{group}' ".format(group=group)
	if mysql_enable == '1':
		sql = """
                select ip.ip, hostname, avg_sess_1h, avg_sess_24h, avg_sess_3d, max_sess_1h, max_sess_24h, max_sess_3d, avg_cur_1h, avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
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
		select ip.ip, hostname, avg_sess_1h, avg_sess_24h, avg_sess_3d, max_sess_1h, max_sess_24h, max_sess_3d, avg_cur_1h, avg_cur_24h, avg_cur_3d, max_con_1h, max_con_24h, max_con_3d from
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
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def get_setting(param, **kwargs):
	user_group = funct.get_user_group(id=1)

	if user_group == '' or param == 'lists_path':
		user_group = '1'

	con, cur = get_cur()
	sql = """select value from `settings` where param='%s' and `group` = '%s'""" % (param, user_group)
	if kwargs.get('all'):
		sql = """select * from `settings` where `group` = '%s' order by section desc""" % user_group
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		if kwargs.get('all'):
			return cur.fetchall()
		else:
			for value in cur.fetchone():
				return value
	cur.close()
	con.close()


def update_setting(param, val):
	user_group = funct.get_user_group(id=1)

	if funct.check_user_group():
		con, cur = get_cur()
		sql = """update `settings` set `value` = '%s' where param = '%s' and `group` = '%s' """ % (val, param, user_group)
		try:
			cur.execute(sql)
			con.commit()
			return True
		except sqltool.Error as e:
			funct.out_error(e)
			con.rollback()
			return False
		cur.close()
		con.close()
	
	
def get_ver():
	con, cur = get_cur()
	sql = """ select * from version; """ 
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for ver in cur.fetchall():
			return ver[0]
	cur.close()    
	con.close()

	
def select_roles(**kwargs):
	con, cur = get_cur()
	sql = """select * from role ORDER BY id"""
	if kwargs.get("roles") is not None:
		sql = """select * from role where name='%s' """ % kwargs.get("roles")
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  


def select_alert(**kwargs):
	con, cur = get_cur()
	sql = """select ip from servers where alert = 1 """
	if kwargs.get("group") is not None:
		sql = """select ip from servers where alert = 1 and `groups` = '%s' """ % kwargs.get("group")
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close() 
	
	
def select_keep_alive(**kwargs):
	con, cur = get_cur()
	sql = """select ip from servers where active = 1 """
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close() 
	
	
def select_keealived(serv, **kwargs):
	con, cur = get_cur()
	sql = """select keepalived from `servers` where ip='%s' """ % serv
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for value in cur.fetchone():
			return value
	cur.close()    
	con.close()  
	
	
def update_keepalived(serv):
	con, cur = get_cur()
	sql = """update `servers` set `keepalived` = '1' where ip = '%s' """ % serv
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	cur.close()    
	con.close()

	
def select_nginx(serv, **kwargs):
	con, cur = get_cur()
	sql = """select nginx from `servers` where ip='%s' """ % serv
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		for value in cur.fetchone():
			return value
	cur.close()    
	con.close()  
	
	
def update_nginx(serv):
	con, cur = get_cur()
	sql = """update `servers` set `nginx` = '1' where ip = '%s' """ % serv
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	cur.close()    
	con.close()
	
	
def update_haproxy(serv):
	con, cur = get_cur()
	sql = """update `servers` set `haproxy` = '1' where ip = '%s' """ % serv
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	cur.close()    
	con.close()
	
	
def update_server_pos(pos, id):
	con, cur = get_cur()
	sql = """ update servers set 
			pos = '%s'
			where id = '%s'""" % (pos, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def check_token_exists(token):
	try:
		import http.cookies
		import os
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_id = cookie.get('uuid')
		if get_token(user_id.value) == token:
			return True
		else:
			try:
				funct.logging('localhost', ' tried do action with wrong token', haproxywi=1, login=1)
			except:
				funct.logging('localhost', ' An action with wrong token', haproxywi=1)
				return False
	except:
		try:
			funct.logging('localhost', ' cannot check token', haproxywi=1, login=1)
		except:
			funct.logging('localhost', ' Cannot check token', haproxywi=1)
			return False


def insert_smon(server, port, enable, proto, uri, body, group, desc, telegram, user_group):
	try:
		http = proto+':'+uri
	except:
		http = ''
	con, cur = get_cur()
	sql = """INSERT INTO smon (ip, port, en, `desc`, `group`, http, body, telegram_channel_id, user_group, `status`) 
			VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '3')
			""" % (server, port, enable, desc, group, http, body, telegram, user_group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()
	con.close()


def select_smon(user_group, **kwargs):
	con, cur = get_cur()

	funct.check_user_group()

	if user_group == 1:
		user_group = ''
	else:
		if kwargs.get('ip'):
			user_group = "and user_group = '%s'" % user_group
		else:
			user_group = "where user_group='%s'" % user_group

	if kwargs.get('ip'):
		try:
			http = kwargs.get('proto')+':'+kwargs.get('uri')
		except:
			http = ''
		sql = """select id, ip, port, en, http, body, telegram_channel_id, `desc`, `group`, user_group from smon 
		where ip='%s' and port='%s' and http='%s' and body='%s' %s 
		""" % (kwargs.get('ip'), kwargs.get('port'), http, kwargs.get('body'), user_group)
	elif kwargs.get('action') == 'add':
		sql = """select id, ip, port, en, http, body, telegram_channel_id, `desc`, `group`, user_group from smon
		%s order by `group`""" % user_group
	else:
		sql = """select * from `smon` %s """ % user_group
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		funct.out_error(e)
	else:
		return cur.fetchall()
	cur.close()
	con.close()


def delete_smon(id, user_group):
	con, cur = get_cur()

	funct.check_user_group()

	sql = """delete from smon
			where id = '%s' and user_group = '%s' """ % (id, user_group)
	try:
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()
	con.close()


def update_smon(id, ip, port, body, telegram, group, desc, en):
	funct.check_user_group()
	con, cur = get_cur()
	sql = """ update smon set 
			ip = '%s',
			port = '%s',
			body = '%s',
			telegram_channel_id = '%s',
			`group` = '%s',
			`desc` = '%s',
			en = '%s'
			where id = '%s'""" % (ip, port, body, telegram, group, desc, en, id)
	try:
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		funct.out_error(e)
		con.rollback()
		return False
	cur.close()
	con.close()


def select_en_service():
	con, cur = get_cur()
	sql = """ select ip, port, telegram_channel_id, id from smon where en = 1"""
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		return cur.fetchall()


def select_status(id):
	con, cur = get_cur()
	sql = """ select status from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for status in cur:
			return status[0]


def select_http_status(id):
	con, cur = get_cur()
	sql = """ select http_status from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for status in cur:
			return status[0]


def select_body_status(id):
	con, cur = get_cur()
	sql = """ select body_status from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for status in cur:
			return status[0]


def select_script(id):
	con, cur = get_cur()
	sql = """ select script from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for script in cur:
			return script[0]


def select_http(id):
	con, cur = get_cur()
	sql = """ select http from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for script in cur:
			return script[0]


def select_body(id):
	con, cur = get_cur()
	sql = """ select body from smon where id = '%s' """ % (id)
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for script in cur:
			return script[0]


def change_status(status, id):
	con, cur = get_cur()
	sql = """ update smon set status = '%s' where id = '%s' """ % (status, id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def change_http_status(status, id):
	con, cur = get_cur()
	sql = """ update smon set http_status = '%s' where id = '%s' """ % (status, id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def change_body_status(status, id):
	con, cur = get_cur()
	sql = """ update smon set body_status = '%s' where id = '%s' """ % (status, id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def add_sec_to_state_time(time, id):
	con, cur = get_cur()
	sql = """ update smon set time_state = '%s' where id = '%s' """ % (time, id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def set_to_zero_time_state(id):
	con, cur = get_cur()
	sql = """ update smon set time_state = 0 where id = '%s' """ % (id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def response_time(time, id):
	con, cur = get_cur()
	sql = """ update smon set response_time = '%s' where id = '%s' """ % (time, id)
	try:
		cur.executescript(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	cur.close()
	con.close()


def smon_list(user_group):
	con, cur = get_cur()

	if user_group == 1:
		user_group = ''
	else:
		user_group = "where user_group='%s'" % user_group

	sql = """ select ip,port,status,en,`desc`,response_time,time_state,`group`,script,http,http_status,body,body_status 
	from smon %s order by `group` desc """ % user_group
	try:
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		return cur.fetchall()


form = funct.form
error_mess = 'error: All fields must be completed'


def check_token():
	if not check_token_exists(form.getvalue('token')):
		print('Content-type: text/html\n')
		print("error: Your token has been expired")		
		import sys
		sys.exit()
		
		
def show_update_option(option):
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
	template = env.get_template('/new_option.html')

	print('Content-type: text/html\n')
	template = template.render(options=select_options(option=option))
	print(template)	
	
	
def show_update_savedserver(server):
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
	template = env.get_template('/new_saved_servers.html')

	print('Content-type: text/html\n')
	template = template.render(server=select_saved_servers(server=server))
	print(template)	

	
if form.getvalue('getoption'):
	group = form.getvalue('getoption')	
	term = form.getvalue('term')	
	print('Content-type: application/json\n')
	check_token()
	options = select_options(group=group,term=term)

	a = {}
	v = 0
	for i in options:
		a[v] = i[0]
		v = v + 1
	import json
	print(json.dumps(a))

	
if form.getvalue('newtoption'):
	option = form.getvalue('newtoption')	
	group = form.getvalue('newoptiongroup')	
	print('Content-type: text/html\n')
	check_token()
	if option is None or group is None:
		print(error_mess)
	else:
		if insert_new_option(option, group):
			show_update_option(option)
	
	
if form.getvalue('updateoption') is not None:
	option = form.getvalue('updateoption')
	id = form.getvalue('id')			
	check_token()
	if option is None or id is None:
		print('Content-type: text/html\n')
		print(error_mess)
	else:		
		update_options(option, id)

			
if form.getvalue('optiondel') is not None:
	print('Content-type: text/html\n')
	check_token()
	if delete_option(form.getvalue('optiondel')):
		print("Ok")
		
		
if form.getvalue('getsavedserver'):
	group = form.getvalue('getsavedserver')	
	term = form.getvalue('term')	
	print('Content-type: application/json\n')
	check_token()
	servers = select_saved_servers(group=group,term=term)

	a = {}
	v = 0
	for i in servers:
		a[v] = {}
		a[v]['value'] = {}
		a[v]['desc'] = {}
		a[v]['value'] = i[0]
		a[v]['desc'] = i[1]
		v = v + 1
	import json
	print(json.dumps(a))

	
if form.getvalue('newsavedserver'):
	savedserver = form.getvalue('newsavedserver')	
	description = form.getvalue('newsavedserverdesc')	
	group = form.getvalue('newsavedservergroup')	
	print('Content-type: text/html\n')
	check_token()
	if savedserver is None or group is None:
		print(error_mess)
	else:
		if insert_new_savedserver(savedserver, description, group):
			show_update_savedserver(savedserver)
	
	
if form.getvalue('updatesavedserver') is not None:
	savedserver = form.getvalue('updatesavedserver')
	description = form.getvalue('description')
	id = form.getvalue('id')	
	print('Content-type: text/html\n')	
	check_token()
	if savedserver is None or id is None:
		print(error_mess)
	else:		
		update_savedserver(savedserver, description, id)
	
	
if form.getvalue('savedserverdel') is not None:
	print('Content-type: text/html\n')
	check_token()
	if delete_savedserver(form.getvalue('savedserverdel')):
		print("Ok")
