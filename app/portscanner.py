#!/usr/bin/env python3
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('portscanner.html')
form = common.form
serv = form.getvalue('history')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(virt=1)
lang = user_params['lang']

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception as e:
	print(f'error {e}')
	sys.exit()

if serv:
	if lang == 'ru':
		title = f'История Port scanner для {serv}'
	elif lang == 'fr':
		title = f'Historique du scanner de ports pour {serv}'
	else:
		title = f'Port scanner history for {serv}'
	port_scanner_settings = sql.select_port_scanner_history(serv)
	history = '1'
	port_scanner = ''
	port_scanner_stderr = ''
	count_ports = ''
else:
	history = ''
	if lang == 'ru':
		title = 'Дашборд Port scanner'
	elif lang == 'fr':
		title = 'Tableau de bord du scanner de ports'
	else:
		title = 'Port scanner dashboard'
	user_group = roxywi_common.get_user_group(id=1)
	port_scanner_settings = sql.select_port_scanner_settings(user_group)
	if not port_scanner_settings:
		port_scanner_settings = ''
		count_ports = ''
	else:
		count_ports = list()
		for s in user_params['servers']:
			count_ports_from_sql = sql.select_count_opened_ports(s[2])
			i = (s[2], count_ports_from_sql)
			count_ports.append(i)

	cmd = "systemctl is-active roxy-wi-portscanner"
	port_scanner, port_scanner_stderr = server_mod.subprocess_execute(cmd)

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

rendered_template = template.render(
	h2=1, autorefresh=0, title=title, role=user_params['role'], user=user_params['user'], servers=user_params['servers'],
	port_scanner_settings=port_scanner_settings, count_ports=count_ports, history=history, port_scanner=''.join(port_scanner),
	port_scanner_stderr=port_scanner_stderr, user_services=user_params['user_services'], user_status=user_subscription['user_status'],
	user_plan=user_subscription['user_plan'], token=user_params['token'], lang=lang
)
print(rendered_template)
