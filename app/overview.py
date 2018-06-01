#!/usr/bin/env python3
import funct, sql
import create_db
import os, http.cookies
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('ovw.html')
	
print('Content-type: text/html\n')
create_db.update_all_silent()
funct.check_login()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	users = sql.select_users()
	groups = sql.select_groups()
	token = sql.get_token(user_id.value)
except:
	pass

output_from_parsed_template = template.render(h2 = 1,
												autorefresh = 1,
												title = "Overview",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												users = users,
												groups = groups,
												token = token)
print(output_from_parsed_template)											