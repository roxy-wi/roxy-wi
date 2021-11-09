#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import funct
import sql
import create_db
import os
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('ovw.html')

print('Content-type: text/html\n')

funct.check_login()

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
	groups = sql.select_groups()
	user_group = funct.get_user_group(id=1)

	if (role == 2 or role == 3) and int(user_group) != 1:
		servers_for_grep = ''
		i = 1
		servers_len = len(servers)

		for s in servers:
			if i != servers_len:
				servers_for_grep += s[2]+'\|'
			else:
				servers_for_grep += s[2]

			i += 1

		cmd = "ps ax |grep 'metrics_worker\|metrics_waf_worker.py\|metrics_nginx_worker.py'|grep -v grep|grep '%s' |wc -l" % servers_for_grep
		metrics_worker, stderr = funct.subprocess_execute(cmd)
		cmd = "ps ax |grep 'checker_worker\|checker_nginx'|grep -v grep |grep '%s' |wc -l" % servers_for_grep
		checker_worker, stderr = funct.subprocess_execute(cmd)
		i = 0
		for s in sql.select_all_alerts(group=user_group):
			i += 1
		is_checker_worker = i
		is_metrics_workers = sql.select_servers_metrics_for_master(group=user_group)
		i = 0
		for s in is_metrics_workers:
			i += 1
		is_metrics_worker = i
		grafana = ''
		prometheus = ''
		host = ''
	else:
		cmd = "ps ax |grep 'metrics_worker\|metrics_waf_worker.py\|metrics_nginx_worker.py' |grep -v grep |wc -l"
		metrics_worker, stderr = funct.subprocess_execute(cmd)
		cmd = "ps ax |grep 'checker_worker\|checker_nginx' |grep -v grep |wc -l"
		checker_worker, stderr = funct.subprocess_execute(cmd)
		i = 0
		for s in sql.select_all_alerts():
			i += 1
		is_checker_worker = i
		is_metrics_workers = sql.select_servers_metrics_for_master()
		i = 0
		for s in is_metrics_workers:
			i += 1
		is_metrics_worker = i
		cmd = "ps ax |grep grafana|grep -v grep|wc -l"
		grafana, stderr = funct.subprocess_execute(cmd)
		cmd = "ps ax |grep 'prometheus ' |grep -v grep|wc -l"
		prometheus, stderr = funct.subprocess_execute(cmd)
		host = os.environ.get('HTTP_HOST', '')

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

except Exception as e:
	role = ''
	user = ''
	users = ''
	groups = ''
	roles = ''
	metrics_master = ''
	metrics_worker = ''
	checker_master = ''
	checker_worker = ''
	keep_alive = ''
	smon = ''
	grafana = ''
	prometheus = ''
	versions = ''
	haproxy_wi_log = ''
	servers = ''
	stderr = ''
	is_checker_worker = ''
	is_metrics_worker = ''
	token = ''


template = template.render(h2=1,
							autorefresh=1,
							title="Overview",
							role=role,
							user=user,
							groups=groups,
							roles=sql.select_roles(),
							metrics_master=''.join(metrics_master),
							metrics_worker=''.join(metrics_worker),
							checker_master=''.join(checker_master),
							checker_worker=''.join(checker_worker),
							keep_alive=''.join(keep_alive),
							smon=''.join(smon),
							port_scanner=''.join(port_scanner),
							grafana=''.join(grafana),
							prometheus=''.join(prometheus),
							haproxy_wi_log_id=funct.haproxy_wi_log(log_id=1, file="roxy-wi-", with_date=1),
							metrics_log_id=funct.haproxy_wi_log(log_id=1, file="metrics-", with_date=1),
							checker_log_id=funct.haproxy_wi_log(log_id=1, file="checker-", with_date=1),
							keep_alive_log_id=funct.haproxy_wi_log(log_id=1, file="keep_alive"),
							checker_error_log_id=funct.haproxy_wi_log(log_id=1, file="checker-error"),
							metrics_error_log_id=funct.haproxy_wi_log(log_id=1, file="metrics-error"),
							error=stderr,
							haproxy_wi_log=funct.haproxy_wi_log(),
							servers=servers,
							is_checker_worker=is_checker_worker,
							is_metrics_worker=is_metrics_worker,
							host=host,
							user_services=user_services,
							token=token)
print(template)
