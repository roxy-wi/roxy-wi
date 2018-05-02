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
from configparser import ConfigParser, ExtendedInterpolation

cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
form = cgi.FieldStorage()
ref = form.getvalue('ref')
login = form.getvalue('login')
password = form.getvalue('pass')

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)	

def login_page(error):
	if error == "error":
		funct.head("Login page")
		printError = "<h2>Login page. Enter please</h2><br /><br /><b style='color: red'>Somthing wrong :( I'm sad about this, but try again!</b><br /><br />"
	else:
		printError = "<h2>Login page. Enter please</h2><br /><br />"	
	
	if create_db.check_db():
		if create_db.create_table():
			print('<div class="alert alert-success">DB was created<br />')
			create_db.update_all()
			print('<br />Now you can login, default: admin/admin</div>')
	create_db.update_all_silent()
	
	ref = form.getvalue('ref')
	if ref is None:
		ref = "/index.html"		
				
	print('<center><form name="auth" action="login.py" class="form-horizontal" method="get">')
	print(printError)
	print('<label for="login">Login: </label>  <input type="text" name="login" required class="form-control"><br /><br />')
	print('<label for="pass">Pass: </label>   <input type="password" name="pass" required class="form-control"><br /><br />')
	print('<input type="hidden" value="%s" name="ref">' % ref)
	print('<button type="submit" name="Login" value="Enter">Sign Up</button>')
	print('</form></center>')
	
	try:
		if config.get('main', 'session_ttl'):
			session_ttl = config.getint('main', 'session_ttl')
	except:
		print('<center><div class="alert alert-danger">Can not find "session_ttl" parametr. Check into config, "main" section</div>')	
	
if form.getvalue('logout') is not None:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	try:
		sql.delete_uuid(user_id.value)
	except:
		pass
	print("Set-cookie: uuid=; expires=Wed May 18 03:33:20 2003; path=/app/; httponly")
	print("Content-type: text/html\n")
	print('<meta http-equiv="refresh" content="0; url=/app/login.py">')
	
if login is None:		
	funct.head("Login page")
	login_page("n")
	
if login is not None and password is not None:
	if form.getvalue('ref') is None:
		ref = "/index.html"	
		
	USERS = sql.select_users()
	session_ttl = config.getint('main', 'session_ttl')
	expires = datetime.datetime.utcnow() + datetime.timedelta(days=session_ttl)
	user_uuid = str(uuid.uuid4())
	
	for users in USERS:	
		if login in users[1] and password == users[3]:
			c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
			c["uuid"] = user_uuid
			c["uuid"]["path"] = "/app/"
			c["uuid"]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
			print(c)
			sql.write_user_uuid(login, user_uuid)
				
			print("Content-type: text/html\n")			
			print('<html><head><title>Redirecting</title><meta charset="UTF-8">')
			print('<link href="/style.css" rel="stylesheet">')
			print('<meta http-equiv="refresh" content="0; url=%s">' % ref)
			sys.exit()
	login_page("error")
	
funct.footer()