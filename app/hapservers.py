#!/usr/bin/env python3
import funct, sql
import os, http.cookies
import cgi
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
except:
	pass
	
form = funct.form
serv = form.getvalue('serv')
service = form.getvalue('service')
autorefresh = 0

if service == 'nginx':
	title = "Nginx servers overview"
	keep_alive = ''
	stderr = ''
	servers = sql.get_dick_permit(virt=1, nginx=1)
	service = 'nginx'
else:
	title = "HAProxy servers overview"
	cmd = "ps ax |grep -e 'keep_alive.py' |grep -v grep |wc -l"
	keep_alive, stderr = funct.subprocess_execute(cmd)
	service = 'haproxy'
	if serv:
		servers = sql.select_servers(server=serv)
		autorefresh = 1
	else:
		servers = sql.get_dick_permit(virt=1, haproxy=1)
	
haproxy_sock_port = sql.get_setting('haproxy_sock_port')
servers_with_status1 = []
out1 = ''
for s in servers:
	servers_with_status = list()
	servers_with_status.append(s[0])
	servers_with_status.append(s[1])
	servers_with_status.append(s[2])
	servers_with_status.append(s[11])
	if service == 'nginx':
		cmd = [ "/usr/sbin/nginx -v && systemctl status nginx |grep -e 'Active\|Tasks' |awk '{print $2, $9$10$11$12$13}'" ] 
		out = funct.ssh_command(s[2], cmd)
		h = ()
		out1 = []
		for k in out.split():
			out1.append(k) 
		h = (out1, )
		servers_with_status.append(h)
		servers_with_status.append(h)
	else:
		cmd = 'echo "show info" |nc %s %s -w 1 |grep -e "Ver\|Uptime:\|Process_num"' % (s[2], haproxy_sock_port)
		out = funct.subprocess_execute(cmd)
		for k in out:
			if "Ncat:" not in k:
				out1 = out
			else:
				out1 = False
			servers_with_status.append(out1)

	servers_with_status.append(s[12])
	servers_with_status.append(sql.is_master(s[2]))
	servers_with_status.append(sql.select_servers(server=s[2]))
	
	servers_with_status1.append(servers_with_status)
	

template = template.render(h2 = 1,
							autorefresh = autorefresh,
							title = title,
							role = sql.get_user_role_by_uuid(user_id.value),
							user = user,
							users = users,
							groups = groups,
							servers = servers_with_status1,
							versions = funct.versions(),
							keep_alive = ''.join(keep_alive),
							serv = serv,
							service = service,
							token = token)
print(template)											
