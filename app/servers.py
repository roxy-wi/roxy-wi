#!/usr/bin/env python3
import sys

import pytz

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('servers.html')
form = common.form

print('Content-type: text/html\n')
user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception:
	print('error: your session is expired')
	sys.exit()

roxywi_auth.page_for_admin(level=2)
try:
	ldap_enable = sql.get_setting('ldap_enable')
	user_group = roxywi_common.get_user_group(id=1)
	settings = sql.get_setting('', all=1)
	geoip_country_codes = sql.select_geoip_country_codes()
	services = sql.select_services()
	gits = sql.select_gits()
	servers = roxywi_common.get_dick_permit(virt=1, disable=0, only_group=1)
	masters = sql.select_servers(get_master_servers=1, uuid=user_params['user_uuid'].value)
	is_needed_tool = common.is_tool('ansible')
	user_roles = sql.select_user_roles_by_group(user_group)
except Exception:
	pass

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

if user_params['lang'] == 'ru':
	title = 'Сервера: '
else:
	title = "Servers: "

rendered_template = template.render(
	h2=1, title=title, role=user_params['role'], user=user_params['user'], users=sql.select_users(group=user_group),
	groups=sql.select_groups(), servers=servers, roles=sql.select_roles(), sshs=sql.select_ssh(group=user_group),
	masters=masters, group=user_group, services=services, timezones=pytz.all_timezones, guide_me=1,
	token=user_params['token'], settings=settings, backups=sql.select_backups(), page="servers.py",
	geoip_country_codes=geoip_country_codes, user_services=user_params['user_services'], ldap_enable=ldap_enable,
	user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], gits=gits,
	is_needed_tool=is_needed_tool, lang=user_params['lang'], user_roles=user_roles
)
print(rendered_template)
