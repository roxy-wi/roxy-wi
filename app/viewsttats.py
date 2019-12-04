#!/usr/bin/env python3
import http.cookies, os
import cgi
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('viewstats.html')
form = funct.form
serv = form.getvalue('serv') 
		
print('Content-type: text/html\n')
funct.check_login()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	role = sql.get_user_role_by_uuid(user_id.value)
	servers = sql.get_dick_permit(virt=1)
	token = sql.get_token(user_id.value)
	
	if serv is None:
		first_serv = sql.get_dick_permit()
		for i in first_serv:
			serv = i[2]
			break
except:
	pass

	
output_from_parsed_template = template.render(h2 = 1,
												autorefresh = 1,
												title = "HAProxy statistics",
												role = role,
												user = user,
												onclick = "showStats()",
												select_id = "serv",
												selects = servers,
												serv = serv,
												versions = funct.versions(),
												token = token)											
print(output_from_parsed_template)

