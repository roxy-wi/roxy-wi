#!/usr/bin/env python3
import distro

import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('metrics.html')
form = funct.form
service = form.getvalue('service')
title = 'Metrics service'

print('Content-type: text/html\n')

user, user_id, role, token, servers, user_services = funct.get_users_params()

try:
	if distro.id() == 'ubuntu':
		cmd = "apt list --installed 2>&1 |grep roxy-wi-metrics"
	else:
		cmd = "rpm -q roxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
	service_ver, stderr = funct.subprocess_execute(cmd)
	services = '0'

	if not stderr:
		if service_ver[0] == ' is not installed' or service_ver == '':
			servers = ''
		else:
			if service == 'nginx':
				if funct.check_login(user_id, token, service=2):
					title = "NGINX`s metrics"
					servers = sql.select_nginx_servers_metrics_for_master()
			elif service == 'apache':
				if funct.check_login(user_id, token, service=4):
					title = "Apache`s metrics"
					servers = sql.select_apache_servers_metrics_for_master()
			else:
				if funct.check_login(user_id, token, service=1):
					title = "HAProxy`s metrics"
					servers = sql.select_servers_metrics()
					service = 'haproxy'
			services = '1'
except Exception:
	pass

try:
	user_status, user_plan = funct.return_user_status()
except Exception as e:
	user_status, user_plan = 0, 0
	funct.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)


template = template.render(
	h2=1, title=title, autorefresh=1, role=role, user=user, servers=servers, services=services,
	user_services=user_services, service=service, user_status=user_status, user_plan=user_plan, token=token
)
print(template)
