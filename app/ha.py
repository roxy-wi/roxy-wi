#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('ha.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

form = funct.form
serv = form.getvalue('serv')

try:
	user, user_id, role, token, servers = funct.get_users_params()
except:
	pass


output_from_parsed_template = template.render(h2 = 1, title = "Create and configure HA cluster",
													role = role,
													user = user,
													serv = serv,
													selects = servers,
													versions = funct.versions(),
													token = token)
print(output_from_parsed_template)
