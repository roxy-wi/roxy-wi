#!/usr/bin/env python3
import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('statsview.html')
print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(virt=1, haproxy=1)

form = common.form
serv = form.getvalue('serv')
service = form.getvalue('service')

try:
	if serv is None:
		first_serv = user_params['servers']
		for i in first_serv:
			serv = i[2]
			break
except Exception:
	pass

if service in ('haproxy', 'nginx', 'apache'):
	service_desc = sql.select_service(service)
	if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
		servers = roxywi_common.get_dick_permit(service=service_desc.slug)
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')



rendered_template = template.render(
	h2=1, autorefresh=1, role=user_params['role'], user=user_params['user'], onclick="showStats()",
	selects=servers, serv=serv, service=service, user_services=user_params['user_services'],
	token=user_params['token'], select_id="serv", lang=user_params['lang'], service_desc=service_desc
)
print(rendered_template)
