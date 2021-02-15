#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(extensions=["jinja2.ext.do"], loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('provisioning.html')
form = funct.form

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level=2)
try:
    user, user_id, role, token, servers = funct.get_users_params()
    if role == 1:
        groups=sql.select_groups()
    else:
        groups=funct.get_user_group(id=1)
    user_group = funct.get_user_group(id=1)
except Exception as e:
    print(str(e))


output_from_parsed_template = template.render(title="Servers provisioning",
												role=role,
												user=user,
                                                groups=groups,
                                                user_group=user_group,
                                                servers=sql.select_provisioned_servers(),
                                                providers=sql.select_providers(user_group),
												token=token)
print(output_from_parsed_template)
