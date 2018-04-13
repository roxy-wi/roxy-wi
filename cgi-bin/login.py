#!/usr/bin/env python3
import cgi
import html
import os
import funct
import http.cookies
import json

cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
form = cgi.FieldStorage()
ref = form.getvalue('ref')
login = form.getvalue('login')
password = form.getvalue('pass')
USERS = '/var/www/haproxy-wi/cgi-bin/users'

try:
	with open(USERS, "r") as user:
		pass
except IOError:
	print("Can't load users DB")

def login_page(error):
	if error == "error":
		printError = "<b style='color: red'>Somthing wrong :( I'm sad about this, but try again!</b><br /><br />"
	else:
		printError = "<h2>Login page. Enter please</h2><br /><br />"	
	
	ref = form.getvalue('ref')
	if ref is None:
		ref = "/index.html"		
		
	funct.head("Login page")
		
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
	login_page("n")
	
if login is not None and password is not None:
	for f in open(USERS, 'r'):
		users = json.loads(f)	
		if login in users['login'] and password == users['password']:
			if users['role'] == "admin":
				role = 2
			elif users['role'] == "editor":
				role = 1
			else:
				role = 0
			c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
			c["login"] = login
			c["login"]["path"] = "/cgi-bin/"
			c["login"]["expires"] = "Wed May 18 03:33:20 2033"
			c["role"] = role
			c["role"]["path"] = "/cgi-bin/"
			c["role"]["expires"] = "Wed May 18 03:33:20 2033"
			c["group"] = users['group']
			c["group"]["path"] = "/cgi-bin/"
			c["group"]["expires"] = "Wed May 18 03:33:20 2033"
			print(c)
			if form.getvalue('ref') is None:
				ref = "/index.html"		
			print("Content-type: text/html\n")
			print('<html><head><title>Redirecting</title><meta charset="UTF-8">')
			print('<link href="/style.css" rel="stylesheet">')
			print('<meta http-equiv="refresh" content="0; url=%s">' % ref)
			break
	login_page("error")
	
funct.footer()



