#!/usr/bin/env python3
import os
import datetime
import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('logs.html')
form = funct.form

if form.getvalue('grep') is None:
	grep = ""
else:
	grep = form.getvalue('grep')

exgrep = form.getvalue('exgrep') if form.getvalue('exgrep') else ''

if form.getvalue('rows') is None:
	rows = 10
else:
	rows = form.getvalue('rows')

if form.getvalue('viewlogs') is None:
	serv = form.getvalue('serv')
else:
	serv = form.getvalue('viewlogs')

hour = form.getvalue('hour')
hour1 = form.getvalue('hour1')
minut = form.getvalue('minut')
minut1 = form.getvalue('minut1')

print('Content-type: text/html\n')
funct.check_login()
if form.getvalue('type') == '2':
	funct.page_for_admin(level=2)
	page = 'for_editor'
else:
	funct.page_for_admin()
	page = ''

log_path = funct.get_config_var('main', 'log_path')
time_storage = sql.get_setting('log_time_storage')

try:
	time_storage_hours = time_storage * 24
	for dirpath, dirnames, filenames in os.walk(log_path):
		for file in filenames:
			curpath = os.path.join(dirpath, file)
			file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
			if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
				os.remove(curpath)
except Exception:
	pass

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception:
	pass

selects = funct.get_files(log_path, format="log")
if form.getvalue('type') is None:
	selects.append(['fail2ban.log', 'fail2ban.log'])
	selects.append(['roxy-wi.error.log', 'error.log'])
	selects.append(['roxy-wi.access.log', 'access.log'])

rendered_template = template.render(
	h2=1, autorefresh=1, title="View internal logs", role=role, user=user, serv=serv, select_id="viewlogs",
	selects=selects, rows=rows, grep=grep, exgrep=exgrep, hour=hour, hour1=hour1, minut=minut,
	minut1=minut1, page=page, user_services=user_services, token=token
)
print(rendered_template)
