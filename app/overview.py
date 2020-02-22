#!/usr/bin/env python3
import funct, sql
import create_db
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('ovw.html')
	
print('Content-type: text/html\n')
if create_db.check_db():
	if create_db.create_table():	
		create_db.update_all()
create_db.update_all_silent()
funct.check_login()

try:
	user, user_id, role, token, servers = funct.get_users_params()
	users = sql.select_users()
	groups = sql.select_groups()
	cmd = "ps ax |grep checker_mas |grep -v grep |wc -l"
	checker_master, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep checker_worker |grep -v grep |wc -l"
	checker_worker, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep metrics_master |grep -v grep |wc -l"
	metrics_master, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep -e 'metrics_worker\|metrics_waf_worker.py' |grep -v grep |wc -l"
	metrics_worker, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
	keep_alive, stderr = funct.subprocess_execute(cmd)
	cmd = "ps ax |grep '(wsgi:api)'|grep -v grep|wc -l"
	api, stderr = funct.subprocess_execute(cmd)
except:
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
	api = ''
	date = ''
	error = ''
	versions = ''
	haproxy_wi_log = ''
	servers = ''


template = template.render(h2 = 1,
							autorefresh = 1,
							title = "Overview",
							role = role,
							user = user,
							users = users,
							groups = groups,
							roles = sql.select_roles(),
							metrics_master = ''.join(metrics_master),
							metrics_worker = ''.join(metrics_worker),
							checker_master = ''.join(checker_master),
							checker_worker = ''.join(checker_worker),
							keep_alive = ''.join(keep_alive),
							api = ''.join(api),
							date = funct.get_data('logs'),
							error = stderr,
							versions = funct.versions(),
							haproxy_wi_log = funct.haproxy_wi_log(),
							servers = servers,
							token = token)
print(template)											
