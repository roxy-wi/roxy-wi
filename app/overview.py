#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import psutil

import funct
import sql

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('ovw.html')

print('Content-type: text/html\n')

grafana = 0
metrics_worker = 0
checker_worker = 0
is_checker_worker = 0
is_metrics_worker = 0
servers_group = []
host = os.environ.get('HTTP_HOST', '')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception as e:
	print(f'error {e}')
	sys.exit()

try:
	funct.check_login(user_id, token)
except Exception as e:
	print(f'error {e}')
	sys.exit()

try:
	groups = sql.select_groups()
	user_group = funct.get_user_group(id=1)

	if (role == 2 or role == 3) and int(user_group) != 1:
		for s in servers:
			servers_group.append(s[2])

	is_checker_worker = len(sql.select_all_alerts(group=user_group))
	is_metrics_worker = len(sql.select_servers_metrics_for_master(group=user_group))

	for pids in psutil.pids():
		if pids < 300:
			continue
		try:
			pid = psutil.Process(pids)
			cmdline_out = pid.cmdline()
			if len(cmdline_out) > 2:
				if 'checker_' in cmdline_out[1]:
					if len(servers_group) > 0:
						if cmdline_out[2] in servers_group:
							checker_worker += 1
					else:
						checker_worker += 1
				elif 'metrics_' in cmdline_out[1]:
					if len(servers_group) > 0:
						if cmdline_out[2] in servers_group:
							metrics_worker += 1
					else:
						metrics_worker += 1
				if len(servers_group) == 0:
					if 'grafana' in cmdline_out[1]:
						grafana += 1
		except psutil.NoSuchProcess:
			pass

	cmd = "systemctl is-active roxy-wi-metrics"
	metrics_master, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl is-active roxy-wi-checker"
	checker_master, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl is-active roxy-wi-keep_alive"
	keep_alive, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl is-active roxy-wi-smon"
	smon, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl is-active roxy-wi-portscanner"
	port_scanner, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl is-active roxy-wi-socket"
	socket, stderr = funct.subprocess_execute(cmd)

except Exception as e:
	role = ''
	user = ''
	groups = ''
	roles = ''
	metrics_master = ''
	checker_master = ''
	keep_alive = ''
	smon = ''
	socket = ''
	servers = ''
	stderr = ''
	token = ''
	# print(str(e))

rendered_template = template.render(
	h2=1, autorefresh=1, title="Overview", role=role, user=user, groups=groups, roles=sql.select_roles(),
	metrics_master=''.join(metrics_master), metrics_worker=metrics_worker, checker_master=''.join(checker_master),
	checker_worker=checker_worker, keep_alive=''.join(keep_alive), smon=''.join(smon),
	port_scanner=''.join(port_scanner), grafana=grafana, socket=''.join(socket),
	roxy_wi_log_id=funct.roxy_wi_log(log_id=1, file="roxy-wi-"),
	metrics_log_id=funct.roxy_wi_log(log_id=1, file="metrics"),
	checker_log_id=funct.roxy_wi_log(log_id=1, file="checker"),
	keep_alive_log_id=funct.roxy_wi_log(log_id=1, file="keep_alive"),
	socket_log_id=funct.roxy_wi_log(log_id=1, file="socket"), error=stderr,
	roxy_wi_log=funct.roxy_wi_log(), servers=servers, is_checker_worker=is_checker_worker,
	is_metrics_worker=is_metrics_worker, host=host, user_services=user_services, token=token
)
print(rendered_template)
