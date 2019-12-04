#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http
import cgi
import sys
import os
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('admin.html')
form = funct.form

print('Content-type: text/html\n')

funct.check_login()
funct.page_for_admin()
try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	users = sql.select_users()
	servers = sql.get_dick_permit()
	token = sql.get_token(user_id.value)
	settings = sql.get_setting('', all=1)
	ldap_enable = sql.get_setting('ldap_enable')
except:
	pass


template = template.render(title = "Admin area: users manage",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							users = users,
							groups = sql.select_groups(),
							servers = sql.select_servers(full=1),
							roles = sql.select_roles(),
							masters = sql.select_servers(get_master_servers=1),
							sshs = sql.select_ssh(),
							telegrams = sql.select_telegram(),
							token = token,
							versions = funct.versions(),
							settings = settings,
							ldap_enable = ldap_enable)
print(template)
