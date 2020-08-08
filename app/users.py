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
	user, user_id, role, token, servers = funct.get_users_params()
	users = sql.select_users()
	settings = sql.get_setting('', all=1)
	ldap_enable = sql.get_setting('ldap_enable')
	grafana, stderr = funct.subprocess_execute("service grafana-server status |grep Active |awk '{print $1}'")
	services = []
	services_name = {"checker_haproxy":"Master checker service", 
					"keep_alive":"Auto start service", 
					"metrics_haproxy":"Master metrics service", 
					"prometheus":"Prometheus service", 
					"grafana-server":"Grafana service", 
					"smon":"Simple monitoring network ports",
					"fail2ban": "Fail2ban service"}
	for s, v in services_name.items():
		cmd = "systemctl status %s |grep Act |awk  '{print $2}'" %s
		status, stderr = funct.subprocess_execute(cmd)
		services.append([s, status, v])
except:
	pass


template = template.render(title = "Admin area: Manage users",
							role = role,
							user = user,
							users = users,
							groups = sql.select_groups(),
							servers = sql.select_servers(full=1),
							roles = sql.select_roles(),
							masters = sql.select_servers(get_master_servers=1),
							sshs = sql.select_ssh(),
							telegrams = sql.select_telegram(),
							token = token,
							versions = funct.versions(),
							settings = settings,
							backups = sql.select_backups(),
							services = services,
						   	grafana = ''.join(grafana),
						   	page = "users.py",
							ldap_enable = ldap_enable)
print(template)
