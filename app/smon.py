#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('smon.html')
smon_status = ''
stderr = ''
form = funct.form
action = form.getvalue('action')
sort = form.getvalue('sort')

print('Content-type: text/html\n')
funct.check_login()

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
	user_group = funct.get_user_group(id=1)
	cmd = "systemctl is-active roxy-wi-smon"
	smon_status, stderr = funct.subprocess_execute(cmd)
except Exception as e:
	print(str(e))

if action == 'add':
	smon = sql.select_smon(user_group, action='add')
	funct.page_for_admin(level=3)
	title = "SMON Admin"
	autorefresh = 0
elif action == 'history':
	if form.getvalue('host'):
		smon = sql.alerts_history('SMON', user_group, host=form.getvalue('host'))
	else:
		smon = sql.alerts_history('SMON', user_group)
	title = "SMON History"
	autorefresh = 0
elif action == 'checker_history':
	smon = sql.alerts_history('Checker', user_group)
	title = "Checker History"
	autorefresh = 0
else:
	smon = sql.smon_list(user_group)
	title = "SMON Dashboard"
	autorefresh = 1

try:
	user_status, user_plan = funct.return_user_status()
except Exception as e:
	user_status, user_plan = 0, 0
	funct.logging('localhost', 'Cannot get a user plan: ' + str(e), haproxywi=1)

rendered_template = template.render(
	h2=1, title=title, autorefresh=autorefresh, role=role, user=user, group=user_group,
	telegrams=sql.get_user_telegram_by_group(user_group), slacks=sql.get_user_slack_by_group(user_group),
	smon=smon, smon_status=smon_status, smon_error=stderr, action=action, sort=sort, user_services=user_services,
	user_status=user_status, user_plan=user_plan, token=token
)
print(rendered_template)
