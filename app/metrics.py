#!/usr/bin/env python3
import funct
import sql
import distro
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('metrics.html')
form = funct.form
service = form.getvalue('service')

funct.check_login()
print('Content-type: text/html\n')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
	if distro.id() == 'ubuntu':
		cmd = "apt list --installed 2>&1 |grep roxy-wi-metrics"
	else:
		cmd = "rpm -q roxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
	service_ver, stderr = funct.subprocess_execute(cmd)
	services = '0'

	if not stderr:
		if service_ver[0] == '* is not installed' or service_ver == '':
			servers = ''
			title = 'Metrics service'
		else:
			if service == 'nginx':
				if funct.check_login(service=2):
					title = "Nginx`s metrics"
					servers = sql.select_nginx_servers_metrics_for_master()
			else:
				if funct.check_login(service=1):
					title = "HAProxy`s metrics"
					servers = sql.select_servers_metrics()
			services = '1'
except Exception as e:
	pass


template = template.render(h2=1, title=title,
							autorefresh=1,
							role=role,
							user=user,
							servers=servers,
							services=services,
							user_services=user_services,
							service=service,
							token=token)
print(template)
