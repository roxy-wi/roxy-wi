#!/usr/bin/env python3
import html
import cgi
import os
import funct
import sql
import http
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('settings.html')
form = cgi.FieldStorage()

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	settings = sql.get_setting('', all=1)
	token = sql.get_token(user_id.value)
except:
	pass

template = template.render(h2 = 1, title = "Settings",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							settings = settings,
							token = token)
print(template)