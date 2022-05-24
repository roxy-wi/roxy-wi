#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('runtimeapi.html')

print('Content-type: text/html\n')
funct.check_login(service=1)
form = funct.form

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(virt=1, haproxy=1)
	servbackend = form.getvalue('servbackend')
	serv = form.getvalue('serv')
	if servbackend is None:
		servbackend = ""
except Exception:
	pass

rendered_template = template.render(
	h2=0, title="RunTime API", role=role, user=user, select_id="serv", selects=servers, token=token,
	user_services=user_services, servbackend=servbackend
)
print(rendered_template)
