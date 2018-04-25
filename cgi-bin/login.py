#!/usr/bin/env python3
import cgi
import html
import os
import sys
import funct
import http.cookies
import sql
import create_db

cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
form = cgi.FieldStorage()
ref = form.getvalue('ref')
login = form.getvalue('login')
password = form.getvalue('pass')

def login_page(error):
	if error == "error":
		printError = "<h2>Login page. Enter please</h2><br /><br /><b style='color: red'>Somthing wrong :( I'm sad about this, but try again!</b><br /><br />"
	else:
		printError = "<h2>Login page. Enter please</h2><br /><br />"	
		
	if create_db.check_db():
		if create_db.create_table():
			print('<div class="alert alert-success">DB was created<br />')
			create_db.update_all()
			print('<br />Now you can login, default: admin/admin</div>')
	
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
	
if form.getvalue('logout') is not None:
	print("Set-cookie: login=; expires=Wed May 18 03:33:20 2003; path=/cgi-bin/; httponly")
	print("Set-cookie: role=; expires=Wed May 18 03:33:20 2003; path=/cgi-bin/; httponly")
	print("Content-type: text/html\n")
	print('<meta http-equiv="refresh" content="0; url=/">')
	
if login is None:		
	funct.head("Login page")
	login_page("n")
	
if login is not None and password is not None:
	USERS = sql.select_users()
	for users in USERS:	
		if login in users[1] and password == users[3]:
			if users[4] == "admin":
				role = 1
			elif users[4] == "editor":
				role = 2
			else:
				role = 3
			c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
			c["login"] = login
			c["login"]["path"] = "/cgi-bin/"
			c["login"]["expires"] = "Wed May 18 03:33:20 2033"
			c["role"] = role
			c["role"]["path"] = "/cgi-bin/"
			c["role"]["expires"] = "Wed May 18 03:33:20 2033"
			c["group"] = users[4]
			c["group"]["path"] = "/cgi-bin/"
			c["group"]["expires"] = "Wed May 18 03:33:20 2033"
			print(c)
			if form.getvalue('ref') is None:
				ref = "/index.html"		
			print("Content-type: text/html\n")
			print('<html><head><title>Redirecting</title><meta charset="UTF-8">')
			print('<link href="/style.css" rel="stylesheet">')
			print('<meta http-equiv="refresh" content="0; url=%s">' % ref)
			sys.exit()
	login_page("error")
	
funct.footer()