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
except:
	pass


template = template.render(h2 = 1, title = "Metrics",
							autorefresh = 1,
							role = role,
							user = user,
							servers = sql.select_servers_metrics(user_id.value),
							versions = funct.versions(),
							token = token)											
print(template)