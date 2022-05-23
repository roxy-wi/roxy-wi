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


if service == 'nginx':
    if funct.check_login(service=2):
        title = 'Nginx service history'
        if serv:
            if funct.check_is_server_in_group(serv):
                server_id = sql.select_server_id_by_ip(serv)
                history = sql.select_action_history_by_server_id_and_service(
                    server_id,
                    service
                )
elif service == 'keepalived':
    if funct.check_login(service=3):
        title = 'Keepalived service history'
        if serv:
            if funct.check_is_server_in_group(serv):
                server_id = sql.select_server_id_by_ip(serv)
                history = sql.select_action_history_by_server_id_and_service(
                    server_id,
                    service
                )
elif service == 'apache':
    if funct.check_login(service=4):
        title = 'Apache service history'
        if serv:
            if funct.check_is_server_in_group(serv):
                server_id = sql.select_server_id_by_ip(serv)
                history = sql.select_action_history_by_server_id_and_service(
                    server_id,
                    service
                )
elif service == 'haproxy':
    if funct.check_login(service=1):
        title = "HAProxy service history"
        if serv:
            if funct.check_is_server_in_group(serv):
                server_id = sql.select_server_id_by_ip(serv)
                history = sql.select_action_history_by_server_id_and_service(
                    server_id,
                    service
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

template = template.render(
    h2=1,
    autorefresh=0,
    title=title,
    role=role,
    user=user,
    users=users,
    serv=serv,
	service=service,
    history=history,
    user_services=user_services,
	token=token
)
print(template)
