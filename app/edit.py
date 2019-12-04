#!/usr/bin/env python3
import os
import http, cgi
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('runtimeapi.html')

print('Content-type: text/html\n')
funct.check_login()
form = funct.form

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit(virt=1)
	token = sql.get_token(user_id.value)
	servbackend = form.getvalue('servbackend')
	serv = form.getvalue('serv')
	if servbackend is None:
		servbackend = ""
except:
	pass


output_from_parsed_template = template.render(h2 = 1,
												title = "Runtime API",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												onclick = "showRuntime()",
												select_id = "serv",
												selects = servers,
												token = token,
												serv = serv,
												versions = funct.versions(),
												servbackend = servbackend)											
print(output_from_parsed_template)
