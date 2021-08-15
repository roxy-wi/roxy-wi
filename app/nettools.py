#!/usr/bin/env python3
import funct
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('nettools.html')
form = funct.form

print('Content-type: text/html\n')
funct.check_login()

try:
    user, user_id, role, token, servers, user_services = funct.get_users_params(virt=1)
except Exception:
    pass


output_from_parsed_template = template.render(h2=1, autorefresh=0,
                                              title="Network tools",
                                              role=role,
                                              user=user,
                                              servers=servers,
                                              versions=funct.versions(),
                                              user_services=user_services,
                                              token=token)
print(output_from_parsed_template)