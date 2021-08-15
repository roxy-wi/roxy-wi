#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import funct
import sql
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('admin.html')
form = funct.form

print('Content-type: text/html\n')

funct.check_login()
funct.page_for_admin()

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
	users = sql.select_users()
	settings = sql.get_setting('', all=1)
	ldap_enable = sql.get_setting('ldap_enable')
	grafana, stderr = funct.subprocess_execute("systemctl is-active grafana-server")

except Exception:
	pass


template = template.render(title="Admin area: Manage users",
							role=role,
							user=user,
							users=users,
							groups=sql.select_groups(),
							servers=sql.select_servers(full=1),
							roles=sql.select_roles(),
							masters=sql.select_servers(get_master_servers=1),
							sshs=sql.select_ssh(),
							token=token,
							settings=settings,
							backups=sql.select_backups(),
							grafana=''.join(grafana),
							page="users.py",
							user_services=user_services,
							ldap_enable=ldap_enable)
print(template)
