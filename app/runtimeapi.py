#!/usr/bin/env python3
import sys

import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('runtimeapi.html')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(virt=1, haproxy=1)

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=1)
except Exception as e:
	print(f'error {e}')
	sys.exit()

form = common.form

try:
	servbackend = form.getvalue('servbackend')
	serv = form.getvalue('serv')
	if servbackend is None:
		servbackend = ""
except Exception:
	pass

rendered_template = template.render(
	h2=0, title="RunTime API", role=user_params['role'], user=user_params['user'], select_id="serv",
	selects=user_params['servers'], token=user_params['token'], user_services=user_params['user_services'], servbackend=servbackend
)
print(rendered_template)
