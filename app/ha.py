#!/usr/bin/env python3
import http.cookies
import cgi
import os
import funct, sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('ha.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

form = funct.form
serv = form.getvalue('serv')

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
	token = sql.get_token(user_id.value)
except:
	pass


output_from_parsed_template = template.render(h2 = 1, title = "Configure HA",
													role = sql.get_user_role_by_uuid(user_id.value),
													user = user,
													serv = serv,
													selects = servers,
													versions = funct.versions(),
													token = token)
print(output_from_parsed_template)
