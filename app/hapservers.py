#!/usr/bin/env python3
import funct, sql
import create_db
import os, http.cookies
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('hapservers.html')
	
print('Content-type: text/html\n')
funct.check_login()

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	users = sql.select_users()
	groups = sql.select_groups()
	token = sql.get_token(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass

haproxy_sock_port = sql.get_setting('haproxy_sock_port')

servers_with_status1 = []
out1 = ""
for s in servers:
	# print(s[2])
	servers_with_status = list()
	cmd = 'echo "show info" |nc %s %s -w 1 |grep -e "Ver\|Uptime:\|Process_num"' % (s[2], haproxy_sock_port)
	# print(cmd	)
	out = funct.subprocess_execute(cmd)
	servers_with_status.append(s[0])
	servers_with_status.append(s[1])
	servers_with_status.append(s[2])
	servers_with_status.append(s[11])
	for k in out:
		if "Ncat:" not in k:
			out1 = out
		else:
			out1 = False
		servers_with_status.append(out1)
		
	servers_with_status1.append(servers_with_status)


template = template.render(h2 = 1,
							autorefresh = 1,
							title = "HAProxy servers overview",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							users = users,
							groups = groups,
							servers = servers_with_status1,
							versions = funct.versions(),
							token = token)
print(template)											
