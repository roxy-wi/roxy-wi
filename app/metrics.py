#!/usr/bin/env python3
import sql
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('metrics.html')

print('Content-type: text/html\n')
funct.check_login()

try:
	user, user_id, role, token, servers = funct.get_users_params()
	cmd = "rpm --query haproxy-wi-metrics-* |awk -F\"metrics\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
	service_ver, stderr = funct.subprocess_execute(cmd)

	if service_ver == '* is not installed':
		servers = ''
	else:
		servers = sql.select_servers_metrics(user_id.value)
except:
	pass


template = template.render(h2=1, title="Metrics",
							autorefresh=1,
							role=role,
							user=user,
							servers=servers,
							versions=funct.versions(),
						   	services=service_ver[0],
							token=token)
print(template)
