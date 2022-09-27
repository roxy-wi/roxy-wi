#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('logs.html')
form = funct.form
print('Content-type: text/html\n')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception:
	pass

if form.getvalue('grep') is None:
	grep = ""
else:
	grep = form.getvalue('grep')

exgrep = form.getvalue('exgrep') if form.getvalue('exgrep') else ''

if form.getvalue('rows') is None:
	rows = 10
else:
	if form.getvalue('rows1') is not None:
		rows = form.getvalue('rows1')
	else:
		rows = form.getvalue('rows')

hour = form.getvalue('hour')
hour1 = form.getvalue('hour1')
minut = form.getvalue('minut')
minut1 = form.getvalue('minut1')
waf = form.getvalue('waf')
service = funct.checkAjaxInput(form.getvalue('service'))
remote_file = form.getvalue('file')

if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
	service_desc = sql.select_service(service)
	if funct.check_login(user_id, token, service=service_desc.service_id):
		title = f"{service_desc.service}`s logs"
		servers = sql.get_dick_permit(service=service_desc.slug)
elif waf == '1':
	if funct.check_login(service=1):
		title = "WAF logs"
		servers = sql.get_dick_permit(haproxy=1)
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')

template = template.render(
	h2=1, autorefresh=1, title=title, role=role, user=user, select_id="serv", selects=servers,
	serv=form.getvalue('serv'), rows=rows, grep=grep, exgrep=exgrep, hour=hour, hour1=hour1, minut=minut,
	minut1=minut1, waf=waf, service=service, user_services=user_services, token=token, remote_file=remote_file
)
print(template)
