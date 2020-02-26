#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('waf.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

try:
	user, user_id, role, token, servers = funct.get_users_params()
except:
	pass


template = template.render(h2 = 1, title = "Web application firewall",
							autorefresh = 1,
							role = role,
							user = user,
							servers = sql.select_waf_servers_metrics(user_id.value),
							servers_all = servers,
							versions = funct.versions(),
							token = token)											
print(template)