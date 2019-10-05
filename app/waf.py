#!/usr/bin/env python3
import os
import sql
import http
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('waf.html')

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


template = template.render(h2 = 1, title = "Web application firewall",
							autorefresh = 1,
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							servers = sql.select_waf_servers_metrics(user_id.value),
							versions = funct.versions(),
							token = token)											
print(template)