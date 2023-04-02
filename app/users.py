#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

import pytz

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.roxy as roxywi
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('admin.html')
form = common.form

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception as e:
	print('error: your session is expired')
	sys.exit()

roxywi_auth.page_for_admin()

users = sql.select_users()
settings = sql.get_setting('', all=1)
ldap_enable = sql.get_setting('ldap_enable')
services = sql.select_services()
gits = sql.select_gits()
masters = sql.select_servers(get_master_servers=1)
is_needed_tool = common.is_tool('ansible')
grafana = 0

if not roxywi.is_docker():
	grafana, stderr = server_mod.subprocess_execute("systemctl is-active grafana-server")
	grafana = grafana[0]

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

rendered_template = template.render(
	h2=1, role=user_params['role'], user=user_params['user'], users=users, groups=sql.select_groups(),
	servers=sql.select_servers(full=1), masters=masters, sshs=sql.select_ssh(), roles=sql.select_roles(),
	settings=settings, backups=sql.select_backups(), services=services, timezones=pytz.all_timezones,
	page="users.py", user_services=user_params['user_services'], ldap_enable=ldap_enable, gits=gits, guide_me=1,
	user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], token=user_params['token'],
	is_needed_tool=is_needed_tool, lang=user_params['lang'], grafana=grafana
)
print(rendered_template)
