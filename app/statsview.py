#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('statsview.html')
form = funct.form
serv = form.getvalue('serv')
service = form.getvalue('service')

print('Content-type: text/html\n')
funct.check_login()

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(virt=1, haproxy=1)

	if serv is None:
		first_serv = servers
		for i in first_serv:
			serv = i[2]
			break
except Exception:
	pass

if service in ('haproxy', 'nginx', 'apache'):
	service_desc = sql.select_service(service)
	if funct.check_login(service=service_desc.service_id):
		title = f'{service_desc.service} stats page'
		sql.get_dick_permit(service=service_desc.slug)
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')

rendered_template = template.render(
	h2=1, autorefresh=1, title=title, role=role, user=user, onclick="showStats()", select_id="serv",
	selects=servers, serv=serv, service=service, user_services=user_services, token=token
)
print(rendered_template)
