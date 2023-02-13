#!/usr/bin/env python3
import sys

import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('ha.html')

print('Content-type: text/html\n')

form = common.form
serv = form.getvalue('serv')

user_params = roxywi_common.get_users_params()

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=3)
except Exception as e:
	print(f'error {e}')
	sys.exit()

roxywi_auth.page_for_admin(level=2)
is_needed_tool = common.is_tool('ansible')

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

parsed_template = template.render(
	h2=1, role=user_params['role'], user=user_params['user'], serv=serv, selects=user_params['servers'],
	user_services=user_params['user_services'], user_status=user_subscription['user_status'], lang=user_params['lang'],
	user_plan=user_subscription['user_plan'], is_needed_tool=is_needed_tool, token=user_params['token']
)
print(parsed_template)
