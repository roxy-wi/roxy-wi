#!/usr/bin/env python3
import html, http, os
import cgi
import requests
import funct
import sql
from requests_toolbelt.utils import dump
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('viewstats.html')
form = cgi.FieldStorage()

serv = form.getvalue('serv') 
if serv is None:
	first_serv = sql.get_dick_permit()
	for i in first_serv:
		serv = i[2]
		break
		
print('Content-type: text/html\n')
funct.check_login()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit(virt=1)
except:
	pass

output_from_parsed_template = template.render(h2 = 1,
												autorefresh = 1,
												title = "HAProxy statistics",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												onclick = "showStats()",
												select_id = "serv",
												selects = servers,
												serv = serv)											
print(output_from_parsed_template)

