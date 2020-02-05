#!/usr/bin/env python3

import cgi
import funct
import sql
import os, http
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('logs.html')
form = funct.form

if form.getvalue('grep') is None:
	grep = ""
else:
	grep = form.getvalue('grep')
	
if form.getvalue('rows') is None:
	rows = 10
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
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
	token = sql.get_token(user_id.value)
except:
	pass

if service == 'nginx':
	title = "Nginx`s logs"
else:
	title = "HAProxy`s logs"

template = template.render(h2 = 1,
							autorefresh = 1,
							title = title,
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							onclick = "showLog()",
							select_id = "serv",
							selects = servers,
							serv = form.getvalue('serv'),
							rows = rows,
							grep = grep,
							hour = hour,
							hour1 = hour1,
							minut = minut,
							minut1 = minut1,
							waf = waf,
							versions = funct.versions(),
							service = service,
							token = token)											
print(template)



