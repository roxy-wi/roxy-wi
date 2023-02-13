#!/usr/bin/env python3
import sys

import modules.common.common as common
import modules.roxywi.roxy as roxywi_mod
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('nettools.html')
form = common.form

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(virt=1)

try:
    roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception as e:
    print(f'error {e}')
    sys.exit()

output_from_parsed_template = template.render(h2=1, autorefresh=0,
                                              role=user_params['role'],
                                              user=user_params['user'],
                                              servers=user_params['servers'],
                                              versions=roxywi_mod.versions(),
                                              user_services=user_params['user_services'],
                                              token=user_params['token'],
                                              lang=user_params['lang'])
print(output_from_parsed_template)
