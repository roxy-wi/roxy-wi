#!/usr/bin/env python3
import html, http.cookies
import cgi
import os
import funct, sql
from configparser import ConfigParser, ExtendedInterpolation
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('ihap.html')
print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin()
form = cgi.FieldStorage()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass

output_from_parsed_template = template.render(h2 = 1, title = "Installation HAProxy",
													role = sql.get_user_role_by_uuid(user_id.value),
													user = user,
													select_id = "haproxyaddserv",
													selects = servers)
print(output_from_parsed_template)

