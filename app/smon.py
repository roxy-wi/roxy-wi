#!/usr/bin/env python3
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('smon.html')

print('Content-type: text/html\n')
user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception as e:
	print(f'error {e}')
	sys.exit()

roxywi_common.check_user_group()
form = common.form
action = form.getvalue('action')
sort = form.getvalue('sort')
autorefresh = 0
lang = user_params['lang']
telegrams = ''
slacks = ''
pds = ''
user_group = roxywi_common.get_user_group(id=1)
cmd = "systemctl is-active roxy-wi-smon"
smon_status, stderr = server_mod.subprocess_execute(cmd)


if action == 'add':
	telegrams = sql.get_user_telegram_by_group(user_group)
	slacks = sql.get_user_slack_by_group(user_group)
	pds = sql.get_user_pd_by_group(user_group)
	smon = sql.select_smon(user_group, action='add')
	roxywi_auth.page_for_admin(level=3)
	if lang == 'ru':
		title = "SMON: Админка"
	elif lang == 'fr':
		title = "SMON: Administratrice"
	else:
		title = "SMON: Admin"
elif action == 'history':
	if form.getvalue('host'):
		needed_host = common.is_ip_or_dns(form.getvalue('host'))
		smon = sql.alerts_history('SMON', user_group, host=needed_host)
	else:
		smon = sql.alerts_history('SMON', user_group)
	if lang == 'ru':
		title = "SMON: История"
	elif lang == 'fr':
		title = "SMON: Histoire"
	else:
		title = "SMON: History"
elif action == 'checker_history':
	smon = sql.alerts_history('Checker', user_group)
	if lang == 'ru':
		title = "Checker: История"
	elif lang == 'fr':
		title = "Checker: Histoire"
	else:
		title = "Checker: History"
else:
	smon = sql.smon_list(user_group)
	if lang == 'ru':
		title = "SMON: Дашборд"
	elif lang == 'fr':
		title = "SMON: Tableau de bord"
	else:
		title = "SMON: Dashboard"
	autorefresh = 1

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

rendered_template = template.render(
	h2=1, title=title, autorefresh=autorefresh, role=user_params['role'], user=user_params['user'], group=user_group,
	telegrams=telegrams, slacks=slacks, pds=pds, lang=lang, smon=smon, smon_status=smon_status, smon_error=stderr,
	action=action, sort=sort, user_services=user_params['user_services'], user_status=user_subscription['user_status'],
	user_plan=user_subscription['user_plan'], token=user_params['token']
)
print(rendered_template)
