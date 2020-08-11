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
time_storage = int(time_storage)

try:
	time_storage_hours = time_storage * 24
	for dirpath, dirnames, filenames in os.walk(log_path):
		for file in filenames:
			curpath = os.path.join(dirpath, file)
			try:
				funct.subprocess_execute('sudo chown apache:apache ' + curpath)
			except:
				pass
			file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
			if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
				os.remove(curpath)
except:
	print(
		'<center><div class="alert alert-danger" style="margin: 0; margin-bottom: 10px;">Can\'t delete old logs file. <br> Please check "log_time_storage" in config and <br>exist directory </div></center>')
	pass

try:
	user, user_id, role, token, servers = funct.get_users_params()
except:
	pass

selects = funct.get_files(log_path, format="log")
if form.getvalue('type') is None:
	selects.append(['fail2ban.log', 'fail2ban.log'])
	selects.append(['haproxy-wi.error.log', 'error.log'])
	selects.append(['haproxy-wi.access.log', 'access.log'])

output_from_parsed_template = template.render(h2=1,
                                              autorefresh=1,
                                              title="View internal logs",
                                              role=role,
                                              user=user,
                                              serv=serv,
                                              select_id="viewlogs",
                                              selects=selects,
                                              rows=rows,
                                              grep=grep,
                                              hour=hour,
                                              hour1=hour1,
                                              minut=minut,
                                              minut1=minut1,
                                              versions=funct.versions(),
											  page = page,
                                              token=token)
print(output_from_parsed_template)
