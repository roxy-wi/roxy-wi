#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('logs.html')
form = funct.form

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
service = form.getvalue('service')
	
print('Content-type: text/html\n')
funct.check_login()

try:
	user, user_id, role, token, servers = funct.get_users_params()
except:
	pass

if service == 'nginx':
	title = "Nginx`s logs"
else:
	title = "HAProxy`s logs"

template = template.render(h2 = 1,
							autorefresh = 1,
							title = title,
							role = role,
							user = user,
							select_id = "serv",
							selects = servers,
							serv = form.getvalue('serv'),
							rows = rows,
							grep = grep,
							exgrep = exgrep,
							hour = hour,
							hour1 = hour1,
							minut = minut,
							minut1 = minut1,
							waf = waf,
							versions = funct.versions(),
							service = service,
							token = token)											
print(template)



