#!/usr/bin/env python3
import distro

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('metrics.html')
form = common.form
service = form.getvalue('service')
service_desc = ''

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

roxywi_common.check_user_group()

try:
	if distro.id() == 'ubuntu':
		cmd = "apt list --installed 2>&1 |grep roxy-wi-metrics"
	else:
		cmd = "rpm -q roxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
	service_ver, stderr = server_mod.subprocess_execute(cmd)
	services = '0'

	if not stderr:
		if service_ver[0] == ' is not installed' or service_ver == '':
			servers = ''
		else:
			service_desc = sql.select_service(service)

			if service == 'nginx':
				if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2):
					user_params['servers'] = sql.select_nginx_servers_metrics_for_master()
			elif service == 'apache':
				if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=4):
					user_params['servers'] = sql.select_apache_servers_metrics_for_master()
			else:
				if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1):
					group_id = roxywi_common.get_user_group(id=1)
					user_params['servers'] = sql.select_servers_metrics(group_id)
					service = 'haproxy'
			services = '1'
except Exception:
	pass

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

template = template.render(
	h2=1, autorefresh=1, role=user_params['role'], user=user_params['user'], servers=user_params['servers'],
	services=services, user_services=user_params['user_services'], service=service, user_status=user_subscription['user_status'],
	user_plan=user_subscription['user_plan'], token=user_params['token'], lang=user_params['lang'], service_desc=service_desc
)
print(template)
