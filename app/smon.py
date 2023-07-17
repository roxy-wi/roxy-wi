#!/usr/bin/env python3
import sys

from datetime import datetime
from pytz import timezone
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
smon_statuses = ''
smon_ping = ''
smon_tcp = ''
smon_http = ''
smon_dns = ''
smon = ''

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

if action == 'add':
	telegrams = sql.get_user_telegram_by_group(user_group)
	slacks = sql.get_user_slack_by_group(user_group)
	pds = sql.get_user_pd_by_group(user_group)
	smon = sql.select_smon(user_group)
	smon_ping = sql.select_smon_ping(user_group)
	smon_tcp = sql.select_smon_tcp(user_group)
	smon_http = sql.select_smon_http(user_group)
	smon_dns = sql.select_smon_dns(user_group)
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
elif action == 'dashboard':
	dashboard_id = int(form.getvalue('dashboard_id'))
	check_id = int(form.getvalue('check_id'))
	smon_name = sql.get_smon_service_name_by_id(dashboard_id)
	check_interval = sql.get_setting('smon_check_interval')
	smon = sql.select_one_smon(dashboard_id, check_id)
	present = datetime.now(timezone('UTC'))
	present = present.strftime('%b %d %H:%M:%S %Y %Z')
	present = datetime.strptime(present, '%b %d %H:%M:%S %Y %Z')
	cert_day_diff = 'N/A'
	count_checks = sql.get_smon_history_count_checks(dashboard_id, check_id)
	try:
		uptime = round(count_checks['up'] * 100 / count_checks['total'], 2)
	except Exception:
		uptime = 0
	try:
		avg_res_time = round(sql.get_avg_resp_time(dashboard_id, check_id), 2)
	except Exception:
		avg_res_time = 0
	try:
		last_resp_time = round(sql.get_last_smon_res_time_by_check(dashboard_id, check_id), 2)
	except Exception:
		last_resp_time = 0
	template = env.get_template('include/smon/smon_history.html')

	for s in smon:
		if s.smon_id.ssl_expire_date is not None:
			ssl_expire_date = datetime.strptime(s.smon_id.ssl_expire_date, '%Y-%m-%d %H:%M:%S')
			cert_day_diff = (ssl_expire_date - present).days

	rendered_template = template.render(
		h2=1, autorefresh=1, role=user_params['role'], user=user_params['user'], smon=smon, group=user_group, lang=lang,
		user_status=user_subscription['user_status'], check_interval=check_interval, user_plan=user_subscription['user_plan'],
		token=user_params['token'], uptime=uptime, user_services=user_params['user_services'], avg_res_time=avg_res_time,
		smon_name=smon_name, cert_day_diff=cert_day_diff, check_id=check_id, dashboard_id=dashboard_id, last_resp_time=last_resp_time
	)
	print(rendered_template)
	sys.exit()
else:
	smon = sql.smon_list(user_group)
	if lang == 'ru':
		title = "SMON: Дашборд"
	elif lang == 'fr':
		title = "SMON: Tableau de bord"
	else:
		title = "SMON: Dashboard"
	autorefresh = 1

rendered_template = template.render(
	h2=1, title=title, autorefresh=autorefresh, role=user_params['role'], user=user_params['user'], group=user_group,
	telegrams=telegrams, slacks=slacks, pds=pds, lang=lang, smon=smon, smon_status=smon_status, smon_error=stderr,
	action=action, sort=sort, user_services=user_params['user_services'], user_status=user_subscription['user_status'],
	user_plan=user_subscription['user_plan'], token=user_params['token'], smon_ping=smon_ping, smon_tcp=smon_tcp,
	smon_http=smon_http, smon_dns=smon_dns

)
print(rendered_template)
