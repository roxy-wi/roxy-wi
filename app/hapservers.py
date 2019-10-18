#!/usr/bin/env python3
import funct, sql
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
	cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
	keep_alive, stderr = funct.subprocess_execute(cmd)
except:
	pass

haproxy_sock_port = sql.get_setting('haproxy_sock_port')
haproxy_config_path  = sql.get_setting('haproxy_config_path')
commands = [ "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % haproxy_config_path ]
servers_with_status1 = []
out1 = ""
for s in servers:
	servers_with_status = list()
	cmd = 'echo "show info" |nc %s %s -w 1 |grep -e "Ver\|Uptime:\|Process_num"' % (s[2], haproxy_sock_port)
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
	servers_with_status.append(s[12])
	try:
		servers_with_status.append(funct.ssh_command(s[2], commands))
	except:
		servers_with_status.append('Cannot get last date')
	
	servers_with_status1.append(servers_with_status)


template = template.render(h2 = 1,
							autorefresh = 0,
							title = "HAProxy servers overview",
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							users = users,
							groups = groups,
							servers = servers_with_status1,
							versions = funct.versions(),
							keep_alive = ''.join(keep_alive),
							token = token)
print(template)											
