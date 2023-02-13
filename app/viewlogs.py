#!/usr/bin/env python3
import os
import sys
import datetime

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools

get_config_var = roxy_wi_tools.GetConfigVar()
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('logs.html')
form = common.form
print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception:
	print('error: your session is expired')
	sys.exit()

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

if form.getvalue('type') == '2':
	roxywi_auth.page_for_admin(level=2)
	page = 'for_editor'
else:
	roxywi_auth.page_for_admin()
	page = ''

log_path = get_config_var.get_config_var('main', 'log_path')
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

selects = roxywi_common.get_files(log_path, file_format="log")
if form.getvalue('type') is None:
	selects.append(['fail2ban.log', 'fail2ban.log'])
	selects.append(['roxy-wi.error.log', 'error.log'])
	selects.append(['roxy-wi.access.log', 'access.log'])

if user_params['lang'] == 'ru':
	title = 'Просмотр внутренних логов'
else:
	title = 'View internal logs'

rendered_template = template.render(
	h2=1, autorefresh=1, title=title, role=user_params['role'], user=user_params['user'], serv=serv,
	select_id="viewlogs", selects=selects, rows=rows, grep=grep, exgrep=exgrep, hour=hour, hour1=hour1, minut=minut,
	minut1=minut1, page=page, user_services=user_params['user_services'], token=user_params['token'], lang=user_params['lang']
)
print(rendered_template)
