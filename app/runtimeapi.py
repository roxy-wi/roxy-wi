#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('runtimeapi.html')

print('Content-type: text/html\n')
funct.check_login()
form = funct.form

try:
	user, user_id, role, token, servers = funct.get_users_params(virt=1)	
	servbackend = form.getvalue('servbackend')
	serv = form.getvalue('serv')
	if servbackend is None:
		servbackend = ""
except:
	pass


output_from_parsed_template = template.render(h2 = 1,
												title = "Runtime API",
												role = role,
												user = user,
												onclick = "showRuntime()",
												select_id = "serv",
												selects = servers,
												token = token,
												serv = serv,
												versions = funct.versions(),
												servbackend = servbackend)											
print(output_from_parsed_template)
