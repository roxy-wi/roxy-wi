#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

import pytz

import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('admin.html')
form = funct.form

print('Content-type: text/html\n')

user, user_id, role, token, servers, user_services = funct.get_users_params()

try:
	funct.check_login(user_id, token)
except Exception as e:
	print(f'error {e}')
	sys.exit()

funct.page_for_admin()

try:
	users = sql.select_users()
	settings = sql.get_setting('', all=1)
	ldap_enable = sql.get_setting('ldap_enable')
	services = sql.select_services()
	gits = sql.select_gits()
except Exception:
	pass

try:
	user_status, user_plan = funct.return_user_status()
except Exception as e:
	user_status, user_plan = 0, 0
	funct.logging('localhost', 'Cannot get a user plan: ' + str(e), haproxywi=1)

rendered_template = template.render(
	title="Admin area: Manage users", role=role, user=user, users=users, groups=sql.select_groups(),
	servers=sql.select_servers(full=1), roles=sql.select_roles(), masters=sql.select_servers(get_master_servers=1),
	sshs=sql.select_ssh(), token=token, settings=settings, backups=sql.select_backups(),
	page="users.py", user_services=user_services, ldap_enable=ldap_enable, user_status=user_status,
	user_plan=user_plan, gits=gits, services=services, timezones=pytz.all_timezones
)
print(rendered_template)
