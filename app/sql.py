#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import funct

mysql_enable = funct.get_config_var('mysql', 'enable')

if mysql_enable == '1':	
	import mysql.connector as sqltool
else:
	db = "/var/www/haproxy-wi/app/haproxy-wi.db"
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
		
	
def out_error(e):
	if mysql_enable == '1':
		error = e
	else:
		error = e.args[0]
	print('Content-type: text/html\n')
	print('<span class="alert alert-danger" style="height: 20px;margin-bottom: 20px;" id="error">An error occurred: ' + error + ' <a title="Close" id="errorMess"><b>X</b></a></span>')
		
def add_user(user, email, password, role, group, activeuser):
	con, cur = get_cur()
	if password != 'aduser':
		sql = """INSERT INTO user (username, email, password, role, groups, activeuser) VALUES ('%s', '%s', '%s', '%s', '%s', '%s')""" % (user, email, funct.get_hash(password), role, group, activeuser)
	else:
		sql = """INSERT INTO user (username, email, role, groups, ldap_user, activeuser) VALUES ('%s', '%s', '%s', '%s', '1', '%s')""" % (user, email, role, group, activeuser)		
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()   
	
def update_user(user, email, role, group, id, activeuser):
	con, cur = get_cur()
	sql = """update user set username = '%s', 
			email = '%s',
			role = '%s', 
			groups = '%s',
			activeuser = '%s'
			where id = '%s'""" % (user, email,  role, group, activeuser, id)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
		return False
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
		out_error(e)
		con.rollback()
	else: 
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
		out_error(e)
		con.rollback()
		return False
	else:
		return True
	cur.close()    
	con.close()
	

def add_server(hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx):
	con, cur = get_cur()
	sql = """ INSERT INTO servers (hostname, ip, groups, type_ip, enable, master, cred, port, `desc`, haproxy, nginx) 
			VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
		""" % (hostname, ip, group, typeip, enable, master, cred, port, desc, haproxy, nginx)
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	

def update_server_master(master, slave):
	con, cur = get_cur()
	sql = """ select id from servers where ip = '%s' """ % master
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	for id in cur.fetchall():
		sql = """ update servers set master = '%s' where ip = '%s' """ % (id[0], slave)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
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
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  
	
	
def select_user_name_group(id):
	con, cur = get_cur()
	sql = """select name from groups where id='%s' """ % id
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		for group in cur.fetchone():
			return group
	cur.close()    
	con.close()  
	
	
def select_server_by_name(name):
	con, cur = get_cur()
	sql = """select ip from servers where hostname='%s' """ % name
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
	for id in cur.fetchall():
		if mysql_enable == '1':
			sql = """ insert into uuid (user_id, uuid, exp) values('%s', '%s',  now()+ INTERVAL '%s' day) """ % (id[0], user_uuid, session_ttl)
		else:
			sql = """ insert into uuid (user_id, uuid, exp) values('%s', '%s',  datetime('now', '+%s days')) """ % (id[0], user_uuid, session_ttl)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
	for id in cur.fetchall():
		if mysql_enable == '1':
			sql = """ insert into token (user_id, token, exp) values('%s', '%s',  now()+ INTERVAL %s day) """ % (id[0], user_token, token_ttl)
		else:
			sql = """ insert into token (user_id, token, exp) values('%s', '%s',  datetime('now', '+%s days')) """ % (id[0], user_token, token_ttl)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
def get_token(uuid):
	con, cur = get_cur()
	sql = """ select token.token from token left join uuid as uuid on uuid.user_id = token.user_id where uuid.uuid = '%s' """ % uuid
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
def get_user_name_by_uuid(uuid):
	con, cur = get_cur()
	sql = """ select user.username from user left join uuid as uuid on user.id = uuid.user_id where uuid.uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 

	
def get_user_role_by_uuid(uuid):
	con, cur = get_cur()
	try:
		cur.execute("select role.id from user left join uuid as uuid on user.id = uuid.user_id left join role on role.name = user.role where uuid.uuid = ?", (uuid,))	
	except sqltool.Error as e:
		out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 
	
	
def get_role_id_by_name(name):
	con, cur = get_cur()
	sql = """ select id from role where name = '%s' """ % name
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 
	
	
def get_user_group_by_uuid(uuid):
	con, cur = get_cur()
	sql = """ select user.groups from user left join uuid as uuid on user.id = uuid.user_id  where uuid.uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		out_error(e)
	else:
		for user_id in cur.fetchall():
			return user_id[0]
	cur.close()    
	con.close() 

def get_user_telegram_by_uuid(uuid):
	con, cur = get_cur()
	sql = """ select telegram.* from telegram left join user as user on telegram.groups = user.groups left join uuid as uuid on user.id = uuid.user_id where uuid.uuid = '%s' """ % uuid
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()

def get_dick_permit(**kwargs):
	import http.cookies
	import os
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	disable = ''
	haproxy = ''
	nginx = ''
	keepalived = ''
	ip = ''
	
	con, cur = get_cur()
	if kwargs.get('username'):
		sql = """ select * from user where username = '%s' """ % kwargs.get('username')
	else:
		sql = """ select * from user where username = '%s' """ % get_user_name_by_uuid(user_id.value)
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
				
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for group in cur:
			if group[5] == '1':
				sql = """ select * from servers where enable = 1 %s %s %s """ % (disable, type_ip, nginx)
			else:
				sql = """ select * from servers where groups like '%{group}%' and (enable = 1 {disable}) {type_ip} {ip} {haproxy} {nginx} {keepalived} 
				""".format(group=group[5], disable=disable, type_ip=type_ip, ip=ip, haproxy=haproxy, nginx=nginx, keepalived=keepalived)		
		try:   
			cur.execute(sql)
		except sqltool.Error as e:
			out_error(e)
		else:
			return cur.fetchall()
	
	cur.close()    
	con.close() 
	
	
def is_master(ip, **kwargs):
	con, cur = get_cur()
	sql = """ select slave.ip, slave.hostname from servers as master left join servers as slave on master.id = slave.master where master.ip = '%s' """ % ip
	if kwargs.get('master_slave'):
		sql = """ select master.hostname, master.ip, slave.hostname, slave.ip from servers as master left join servers as slave on master.id = slave.master where slave.master > 0 """
	try:
		cur.execute(sql)		
	except sqltool.Error as e:
		out_error(e)
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
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def insert_backup_job(server, rserver, rpath, type, time, cred, description):
	con, cur = get_cur()
	sql = """insert into backups(server, rhost, rpath, type, time, cred, description) values ('%s', '%s', '%s', '%s', '%s', '%s', '%s') """ % (server, rserver, rpath, type, time, cred, description)
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def select_waf_metrics_enable(id):
	con, cur = get_cur()
	sql = """ select waf.metrics from waf  left join servers as serv on waf.server_id = serv.id where server_id = '%s' """ % id
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
			out_error(e)
		else:
			return cur.fetchall()
	cur.close()    
	con.close() 
	
	
def select_waf_metrics(serv, **kwargs):
	con, cur = get_cur()
	sql = """ select * from (select * from waf_metrics where serv = '%s' order by `date` desc limit 60) order by `date`""" % serv
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def delete_waf_server(id):
	con, cur = get_cur()
	sql = """ delete from waf where server_id = '%s' """ % id
	try:    
		cur.execute(sql)
		con.commit()
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
	cur.close()    
	con.close()
	
	
def select_metrics(serv, **kwargs):
	con, cur = get_cur()
	sql = """ select * from (select * from metrics where serv = '%s' order by `date` desc limit 60) order by `date` """ % serv
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()
	
	
def select_servers_metrics_for_master():
	con, cur = get_cur()
	sql = """select ip from servers where metrics = 1 """
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close() 
	
	
def select_servers_metrics(uuid, **kwargs):
	con, cur = get_cur()
	sql = """ select * from user where username = '%s' """ % get_user_name_by_uuid(uuid)

	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for group in cur:
			if group[5] == '1':
				sql = """ select ip from servers where enable = 1 and metrics = '1' """
			else:
				sql = """ select ip from servers where groups like '%{group}%' and metrics = '1'""".format(group=group[5])		
		try:   
			cur.execute(sql)
		except sqltool.Error as e:
			out_error(e)
		else:
			return cur.fetchall()
	cur.close()    
	con.close() 
	
	
def select_table_metrics(uuid):
	con, cur = get_cur()
	groups = ""
	sql = """ select * from user where username = '%s' """ % get_user_name_by_uuid(uuid)
	
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		print("An error occurred:", e)
	else:
		for group in cur:
			if group[5] == '1':
				groups = ""
			else:
				groups = "and servers.groups like '%{group}%' ".format(group=group[5])
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
		out_error(e)
	else:		
		return cur.fetchall()
	cur.close()    
	con.close()
	
	
def get_setting(param, **kwargs):
	con, cur = get_cur()
	sql = """select value from `settings` where param='%s' """ % param
	if kwargs.get('all'):
		sql = """select * from `settings` order by section desc"""
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
	else:
		if kwargs.get('all'):
			return cur.fetchall()
		else:
			for value in cur.fetchone():
				return value
	cur.close()    
	con.close()  
	
	
def update_setting(param, val):
	con, cur = get_cur()
	sql = """update `settings` set `value` = '%s' where param = '%s' """ % (val, param)
	try:    
		cur.execute(sql)
		con.commit()
		return True
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
	else:
		return cur.fetchall()
	cur.close()    
	con.close()  
	
def select_alert(**kwargs):
	con, cur = get_cur()
	sql = """select ip from servers where alert = 1 """
	try:    
		cur.execute(sql)
	except sqltool.Error as e:
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
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
		out_error(e)
		con.rollback()
		return False
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

			
form = funct.form
error_mess = '<span class="alert alert-danger" id="error">All fields must be completed <a title="Close" id="errorMess"><b>X</b></a></span>'


def check_token():
	if not check_token_exists(form.getvalue('token')):
		print('Content-type: text/html\n')
		print("Your token has been expired")		
		import sys
		sys.exit()
		
		
def check_group(group, role_id):
	import http.cookies
	import os
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user_group = get_user_group_by_uuid(user_id.value)
	if user_group == group or user_group == '1' or role_id == 1:
		return True
	else:
		funct.logging('localhost', ' has tried to actions in not own group ', haproxywi=1, login=1)
		return False
		
		
def show_update_option(option):
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'))
	template = env.get_template('/new_option.html')

	print('Content-type: text/html\n')
	template = template.render(options=select_options(option=option))
	print(template)	
	
	
def show_update_savedserver(server):
	from jinja2 import Environment, FileSystemLoader
	env = Environment(loader=FileSystemLoader('templates/ajax'))
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
