#!/usr/bin/env python3
import html
import cgi
import funct
import sql
import os, http
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('logs.html')
form = cgi.FieldStorage()

if form.getvalue('grep') is None:
	grep = ""
else:
	grep = form.getvalue('grep')
	
if form.getvalue('rows') is None:
	rows = 10
else:
	rows = form.getvalue('rows')
	
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

output_from_parsed_template = template.render(h2 = 1,
												autorefresh = 1,
												title = "Show logs",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												onclick = "showLog()",
												select_id = "serv",
												selects = servers,
												serv = form.getvalue('serv'),
												rows = rows,
												grep = grep,
												token = token)											
print(output_from_parsed_template)



