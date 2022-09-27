#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('provisioning.html')
form = funct.form

print('Content-type: text/html\n')

user, user_id, role, token, servers, user_services = funct.get_users_params()

try:
    funct.check_login(user_id, token)
except Exception as e:
    print(f'error {e}')
    sys.exit()

funct.page_for_admin(level=2)
try:
    if role == 1:
        groups = sql.select_groups()
    else:
        groups = funct.get_user_group(id=1)
    user_group = funct.get_user_group(id=1)

    cmd = 'which terraform'
    output, stderr = funct.subprocess_execute(cmd)

    if stderr != '':
        is_terraform = False
    else:
        is_terraform = True

    params = sql.select_provisioning_params()
except Exception as e:
    print(str(e))

rendered_template = template.render(
    title="Servers provisioning", role=role, user=user, groups=groups, user_group=user_group,
    servers=sql.select_provisioned_servers(), providers=sql.select_providers(user_group),
    is_terraform=is_terraform, user_services=user_services, token=token, params=params
)
print(rendered_template)
