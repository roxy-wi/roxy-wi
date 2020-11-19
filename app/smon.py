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
	user, user_id, role, token, servers = funct.get_users_params()
	user_group = funct.get_user_group(id=1)
	cmd = "systemctl status smon |grep Active |awk '{print $2}'"
	smon_status, stderr = funct.subprocess_execute(cmd)
except Exception as e:
	pass

if action == 'add':
	smon = sql.select_smon(user_group, action='add')
	funct.page_for_admin(level=3)
	title = "SMON Admin"
	autorefresh = 0
elif action == 'history':
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


template = template.render(h2=1, title=title,
							autorefresh=autorefresh,
							role=role,
							user=user,
							group=user_group,
							telegrams=sql.get_user_telegram_by_group(user_group),
							versions=funct.versions(),
							smon=smon,
							smon_status=smon_status,
							smon_error=stderr,
							action=action,
							sort=sort,
							token=token)
print(template)
