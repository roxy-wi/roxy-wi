#!/usr/bin/env python3
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common
import modules.server.server as server_mod

env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('provisioning.html')
form = common.form

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params()

try:
    roxywi_auth.check_login(user_params['user_uuid'], user_params['token'])
except Exception as e:
    print(f'error {e}')
    sys.exit()

roxywi_auth.page_for_admin(level=2)
try:
    if user_params['role'] == 1:
        groups = sql.select_groups()
    else:
        groups = roxywi_common.get_user_group(id=1)
    user_group = roxywi_common.get_user_group(id=1)

    cmd = 'which terraform'
    output, stderr = server_mod.subprocess_execute(cmd)

    if stderr != '':
        is_terraform = False
    else:
        is_terraform = True

    params = sql.select_provisioning_params()
except Exception as e:
    print(str(e))

rendered_template = template.render(
    title="Servers provisioning", role=user_params['role'], user=user_params['user'], groups=groups,
    user_group=user_group, servers=sql.select_provisioned_servers(), providers=sql.select_providers(user_group),
    is_terraform=is_terraform, user_services=user_params['user_services'], token=user_params['token'], params=params
)
print(rendered_template)
