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
	services_name = {'checker_haproxy': 'Master backends checker service',
					'keep_alive': 'Auto start service',
					'metrics_haproxy': 'Master metrics service',
					'prometheus': 'Prometheus service',
					'grafana-server': 'Grafana service',
					'smon': 'Simple monitoring network ports',
					'fail2ban': 'Fail2ban service'}
	for s, v in services_name.items():
		cmd = "systemctl status %s |grep Act |awk  '{print $2}'" % s
		status, stderr = funct.subprocess_execute(cmd)
		if s != 'keep_alive':
			service_name = s.split('_')[0]
		else:
			service_name = s
		cmd = "rpm --query haproxy-wi-"+service_name+"-* |awk -F\""+service_name + "\" '{print $2}' |awk -F\".noa\" '{print $1}' |sed 's/-//1' |sed 's/-/./'"
		service_ver, stderr = funct.subprocess_execute(cmd)
		services.append([s, status, v, service_ver[0]])

	openvpn_configs = ''
	openvpn_sess = ''
	openvpn = ''

	stdout, stderr = funct.subprocess_execute("rpm --query openvpn3-client")
	if stdout[0] != 'package openvpn3-client is not installed':
		cmd = "sudo openvpn3 configs-list |grep -E 'ovpn|(^|[^0-9])[0-9]{4}($|[^0-9])' |grep -v net|awk -F\"    \" '{print $1}'|awk 'ORS=NR%2?\" \":\"\\n\"'"
		openvpn_configs, stderr = funct.subprocess_execute(cmd)
		cmd = "sudo openvpn3 sessions-list|grep -E 'Config|Status'|awk -F\":\" '{print $2}'|awk 'ORS=NR%2?\" \":\"\\n\"'| sed 's/^ //g'"
		cmd = 'echo "client.ovpn  Connection, Client connected"'
		openvpn_sess, stderr = funct.subprocess_execute(cmd)
		openvpn = stdout[0]


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
							telegrams=sql.select_telegram(),
							token=token,
							versions=funct.versions(),
							checker_ver=funct.check_new_version(service='checker'),
							smon_ver=funct.check_new_version(service='smon'),
							metrics_ver=funct.check_new_version(service='metrics'),
							keep_ver=funct.check_new_version(service='keep'),
							openvpn=openvpn,
							openvpn_configs=openvpn_configs,
							openvpn_sess=openvpn_sess,
							settings=settings,
							backups=sql.select_backups(),
							services=services,
							grafana=''.join(grafana),
							page="users.py",
							ldap_enable=ldap_enable)
print(template)
