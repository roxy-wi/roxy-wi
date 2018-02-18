#!/usr/bin/env python3
import html
import cgi
import funct
import configparser
import json
import listserv as listhap

funct.head("Overview")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
USERS = '/var/www/haproxy-wi/cgi-bin/users'

try:
	with open(USERS, "r") as user:
		pass
except IOError:
	print("Can't load users DB")

print('<h2>Quick Status </h2><table class="overview">')

commands = [ "ps -Af |grep [h]aproxy |wc -l" ]

print('<tr class="overviewHead">'
		'<td class="padding10">User name</td>'
		'<td class="padding10">'
			'Role'
			'<span style="float: right; margin-left: 80&;">'
				'<a href="#"  title="Show all users" id="show-all-users">'
					'Show all'
				'</a>'
		'</td>'
	'</tr>')

i = 0
style = ""
for f in open(USERS, 'r'):
	i = i + 1
	users = json.loads(f)
	if i is 4:
		style = 'style="display: none;" class="show-users"'
	print('<tr ' + style + '><td class="padding10">' + users['firstName'] + ' ' + users['lastName'] +'</td><td>')
	print(users['role'])
	print('</td></tr>')

print('<tr class="overviewHead">'
		'<td class="padding10">Server</td>'
		'<td class="padding10">'
			'HAproxy status'
			'<span style="float: right; margin-left: 80&;">'
				'<a href=""  title="Update status" id="update">'
					'<img alt="Update" src="/image/pic/update.png" style="max-width: 20px;">'
				'</a>'
		'</td>'
	'</tr>')
for i in sorted(listhap.listhap):
	print('<tr><td class="padding10">' + i + '</td><td>')
	funct.ssh_command(listhap.listhap.get(i), commands, server_status="1")
	print('</td></tr>')
print('<tr class="overviewHead">'
		'<td class="padding10">Server</td>'
		'<td class="padding10">'
			'Server status'
			'<span style="float: right; margin-left: 80&;">'
				'<a href=""  title="Update status" id="update">'
					'<img alt="Update" src="/image/pic/update.png" style="max-width: 20px;">'
				'</a>'
		'</td>'
	'</tr>')
print('</td></tr>')
commands = [ "cat /etc/haproxy/haproxy.cfg |grep -E '^listen|^backend|^frontend' |grep -v stats |wc -l", "uname -smor", "haproxy -v |head -1", "top -u haproxy -b -n 1" ]
for i in sorted(listhap.listhap):
	print('<tr><td class="overviewTr"><h3 title="IP ' + listhap.listhap.get(i) + '">' + i + ':</h3></td>')
	print('<td class="overviewTd"><span style="margin-left: -10px;">Total listen/frontend/backend:</span><pre>')
	funct.ssh_command(listhap.listhap.get(i), commands)
	print('</pre></td></tr>')

print('<tr>'
		'<iframe src="http://172.28.5.106:3000/d-solo/000000002/haproxy?refresh=1m&orgId=1&panelId=1&theme=light" height="200" frameborder="0"></iframe>'
		'<iframe src="http://172.28.5.106:3000/d-solo/000000002/haproxy?refresh=1m&orgId=1&panelId=2&theme=light" height="200" frameborder="0"></iframe>'
		'<iframe src="http://172.28.5.106:3000/d-solo/000000002/haproxy?refresh=1m&orgId=1&panelId=3&theme=light"  height="200" frameborder="0"></iframe>'
		'</tr></table>')
funct.footer()