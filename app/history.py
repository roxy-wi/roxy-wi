#!/usr/bin/env python3
import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('history.html')

print('Content-type: text/html\n')
funct.check_login()

try:
    user, user_id, role, token, servers, user_services \
        = funct.get_users_params()
    services = []
except Exception:
    pass

form = funct.form
serv = funct.is_ip_or_dns(form.getvalue('serv'))
service = form.getvalue('service')
user_id = form.getvalue('user_id')

if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
    service_desc = sql.select_service(service)
    if funct.check_login(service=service_desc.service_id):
        title = f'{service_desc.service} service history'
        server_id = sql.select_server_id_by_ip(serv)
        history = sql.select_action_history_by_server_id_and_service(
            server_id,
            service_desc.service
        )
elif service == 'server':
    if serv:
        title = serv + ' history'
        if funct.check_is_server_in_group(serv):
            server_id = sql.select_server_id_by_ip(serv)
            history = sql.select_action_history_by_server_id(server_id)
elif service == 'user':
    if user_id:
        title = 'User history'
        history = sql.select_action_history_by_user_id(user_id)

users = sql.select_users()

try:
    user_status, user_plan = funct.return_user_status()
except Exception as e:
    user_status, user_plan = 0, 0
    funct.logging('localhost', 'Cannot get a user plan: ' + str(e), haproxywi=1)

rendered_template = template.render(
    h2=1, autorefresh=0, title=title, role=role, user=user, users=users, serv=serv, service=service,
    history=history, user_services=user_services, token=token, user_status=user_status, user_plan=user_plan
)
print(rendered_template)
