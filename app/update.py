#!/usr/bin/env python3
import http.cookies
import os
import funct, sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('update.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	token = sql.get_token(user_id.value)
except:
	pass
	
try: 
	current_ver = funct.check_ver()
	current_ver_without_dots = current_ver.split('.')
	current_ver_without_dots = ''.join(current_ver_without_dots)
except:
	current_ver = "Sorry cannot get current version"

try:
	new_ver = funct.check_new_version()
	new_ver_without_dots = new_ver.split('.')
	new_ver_without_dots = ''.join(new_ver_without_dots)
except:
	new_ver = "Sorry cannot get new version"

output_from_parsed_template = template.render(h2 = 1, title = "Check updates",
													role = sql.get_user_role_by_uuid(user_id.value),
													user = user,
													current_ver = current_ver,
													current_ver_without_dots = current_ver_without_dots,
													new_ver = new_ver,
													new_ver_without_dots = new_ver_without_dots,
													token = token)
print(output_from_parsed_template)