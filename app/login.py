#!/usr/bin/env python3
import cgi
import html
import os
import sys
import funct
import http.cookies
import sql
import create_db
import datetime
import uuid
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('login.html')
form = cgi.FieldStorage()

cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
user_id = cookie.get('uuid')
ref = form.getvalue('ref')
login = form.getvalue('login')
password = form.getvalue('pass')
db_create = ""
error_log = ""
error = ""

if ref is None:
	ref = "/index.html"	
	
if form.getvalue('error'):
	error_log = '<div class="alert alert-danger">Somthing wrong :( I\'m sad about this, but try again!</div><br /><br />'

try:
	if sql.get_setting('session_ttl'):
		session_ttl = sql.get_setting('session_ttl')
except:
	error = '<center><div class="alert alert-danger">Can not find "session_ttl" parametr. Check into settings, "main" section</div>'
	pass
	
try:
	role = sql.get_user_role_by_uuid(user_id.value)
	user = sql.get_user_name_by_uuid(user_id.value)
except:
	role = ""
	user = ""
	pass
	
if form.getvalue('logout'):
	try:
		sql.delete_uuid(user_id.value)
	except:
		pass
	print("Set-cookie: uuid=; expires=Wed May 18 03:33:20 2003; path=/app/; httponly")
	print("Content-type: text/html\n")
	print('<meta http-equiv="refresh" content="0; url=/app/login.py">')

if login is not None and password is not None:

	USERS = sql.select_users()
	session_ttl = int()
	session_ttl = sql.get_setting('session_ttl')
	session_ttl = int(session_ttl)
	
	expires = datetime.datetime.utcnow() + datetime.timedelta(days=session_ttl) 
	user_uuid = str(uuid.uuid4())
	user_token = str(uuid.uuid4())
	
	for users in USERS:	
		if login in users[1] and password == users[3]:
			c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
			c["uuid"] = user_uuid
			c["uuid"]["path"] = "/app/"
			c["uuid"]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
			print(c)
			sql.write_user_uuid(login, user_uuid)
			sql.write_user_token(login, user_token)
			funct.logging('locahost', sql.get_user_name_by_uuid(user_uuid)+' log in')
			print("Content-type: text/html\n")			
			print('ok')
			sys.exit()	
		
	print("Content-type: text/html\n")	
	print('<center><div class="alert alert-danger">Somthing wrong :( I\'m sad about this, but try again!</div><br /><br />')
	sys.exit()
			
if login is None:
	print("Content-type: text/html\n")	
	if create_db.check_db():
		if create_db.create_table():	
			create_db.update_all()
			db_create = '<div class="alert alert-success">DB was created<br /><br />Now you can login, default: admin/admin</div>'
				
create_db.update_all_silent()

output_from_parsed_template = template.render(h2 = 1, title = "Login page. Enter please",
													role = role,
													user = user,
													error_log = error_log,
													error = error,
													ref = ref,
													db_create = db_create)											
print(output_from_parsed_template)