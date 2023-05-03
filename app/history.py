#!/usr/bin/env python3
import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('history.html')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(service='keepalived')

form = common.form
serv = common.is_ip_or_dns(form.getvalue('serv'))
service = form.getvalue('service')
user_id_history = form.getvalue('user_id')

if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
	service_desc = sql.select_service(service)
	if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
		server_id = sql.select_server_id_by_ip(serv)
		history = sql.select_action_history_by_server_id_and_service(server_id, service_desc.service)
elif service == 'server':
	if serv:
		if roxywi_common.check_is_server_in_group(serv):
			server_id = sql.select_server_id_by_ip(serv)
			history = sql.select_action_history_by_server_id(server_id)
elif service == 'user':
	if user_id_history:
		history = sql.select_action_history_by_user_id(user_id_history)

users = sql.select_users()

try:
	user_subscription = roxywi_common.return_user_status()
except Exception as e:
	user_subscription = roxywi_common.return_unsubscribed_user_status()
	roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

try:
	sql.delete_action_history_for_period()
except Exception as e:
	print(e)

rendered_template = template.render(
	h2=1, autorefresh=0, role=user_params['role'], user=user_params['user'], users=users, serv=serv,
	service=service, history=history, user_services=user_params['user_services'], token=user_params['token'],
	user_status=user_subscription['user_status'], user_plan=user_subscription['user_plan'], lang=user_params['lang']
)
print(rendered_template)
