#!/usr/bin/env python3
import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('logs.html')
form = common.form
print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

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
service = common.checkAjaxInput(form.getvalue('service'))
remote_file = form.getvalue('file')
service_name = ''

if service in ('haproxy', 'nginx', 'keepalived', 'apache') and waf != '1':
	service_desc = sql.select_service(service)
	service_name = service_desc.service
	if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
		servers = roxywi_common.get_dick_permit(service=service_desc.slug)
elif waf == '1':
	service_name = 'WAF'
	if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1):
		servers = roxywi_common.get_dick_permit(haproxy=1)
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')

template = template.render(
	h2=1, autorefresh=1, role=user_params['role'], user=user_params['user'], select_id="serv",
	selects=servers, serv=form.getvalue('serv'), rows=rows, grep=grep, exgrep=exgrep, hour=hour, hour1=hour1,
	minut=minut, minut1=minut1, waf=waf, service=service, user_services=user_params['user_services'],
	token=user_params['token'], remote_file=remote_file, lang=user_params['lang'], service_name=service_name
)
print(template)
