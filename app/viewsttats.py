#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('viewstats.html')
form = funct.form
serv = form.getvalue('serv') 
service = form.getvalue('service') 
		
print('Content-type: text/html\n')
funct.check_login()

if service == 'nginx':
	if funct.check_login(service=2):
		title = 'NGINX stats page'
else:
	if funct.check_login(service=1):
		title = 'HAProxy stats page'

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(virt=1, haproxy=1)
	
	if serv is None:
		first_serv = servers
		for i in first_serv:
			serv = i[2]
			break
except Exception:
	pass

	
output_from_parsed_template = template.render(h2=1,
												autorefresh=1,
												title=title,
												role=role,
												user=user,
												onclick="showStats()",
												select_id="serv",
												selects=servers,
												serv=serv,
												service=service,
												user_services=user_services,
												token=token)
print(output_from_parsed_template)

