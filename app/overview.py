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
if create_db.check_db():
	if create_db.create_table():	
		create_db.update_all()
create_db.update_all_silent()
funct.check_login()

try:
	user, user_id, role, token, servers = funct.get_users_params()
	groups = sql.select_groups()
	import http.cookies
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	group = cookie.get('group')
	user_group = group.value

	if (role == 2 or role == 3) and int(user_group) != 1:
		users = sql.select_users(group=user_group)
		servers_for_grep = ''
		i = 0
		servers_len = len(servers)

		for s in servers:
			i += 1
			if i != servers_len:
				servers_for_grep += s[2]+'|'
			else:
				servers_for_grep += s[2]

		cmd = "ps ax |grep -e 'metrics_worker\|metrics_waf_worker.py'|grep -E %s|grep -v grep |wc -l" % servers_for_grep
		metrics_worker, stderr = funct.subprocess_execute(cmd)
		cmd = "ps ax |grep checker_worker|grep -E %s |grep -v grep |wc -l" % servers_for_grep
		checker_worker, stderr = funct.subprocess_execute(cmd)
		i = 0
		for s in sql.select_alert(group=user_group):
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
		users = sql.select_users()
		cmd = "ps ax |grep -e 'metrics_worker\|metrics_waf_worker.py' |grep -v grep |wc -l"
		metrics_worker, stderr = funct.subprocess_execute(cmd)
		cmd = "ps ax |grep checker_worker |grep -v grep |wc -l"
		checker_worker, stderr = funct.subprocess_execute(cmd)
		i = 0
		for s in sql.select_alert():
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

	cmd = "ps ax |grep metrics_master |grep -v grep |wc -l"
	metrics_master, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep checker_mas |grep -v grep |wc -l"
	checker_master, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
	keep_alive, stderr = funct.subprocess_execute(cmd)
	cmd = "systemctl status smon |grep Act |awk  '{print $2}'"
	smon, stderr = funct.subprocess_execute(cmd)

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

template = template.render(h2 = 1,
							autorefresh = 1,
							title = "Overview",
							role = role,
							user = user,
							users = users,
							groups = groups,
							users_groups = sql.select_user_groups_with_names(1, all=1),
							roles = sql.select_roles(),
							metrics_master = ''.join(metrics_master),
							metrics_worker = ''.join(metrics_worker),
							checker_master = ''.join(checker_master),
							checker_worker = ''.join(checker_worker),
							keep_alive = ''.join(keep_alive),
							smon = ''.join(smon),
							grafana = ''.join(grafana),
							prometheus = ''.join(prometheus),
							haproxy_wi_log_id = funct.haproxy_wi_log(log_id=1, file="haproxy-wi-", with_date=1),
							metrics_log_id = funct.haproxy_wi_log(log_id=1, file="metrics-", with_date=1),
							checker_log_id = funct.haproxy_wi_log(log_id=1, file="checker-", with_date=1),
							keep_alive_log_id = funct.haproxy_wi_log(log_id=1, file="keep_alive"),
							checker_error_log_id = funct.haproxy_wi_log(log_id=1, file="checker-error"),
							metrics_error_log_id = funct.haproxy_wi_log(log_id=1, file="metrics-error"),
							error = stderr,
							versions = funct.versions(),
							haproxy_wi_log = funct.haproxy_wi_log(),
							servers = servers,
							is_checker_worker = is_checker_worker,
							is_metrics_worker = is_metrics_worker,
							host = host,
							token = token)
print(template)