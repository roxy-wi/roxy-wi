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

print('<h2>Quick Status </h2>'
		'<table class="overview">')

if funct.is_admin():

	print('<tr class="overviewHead">'
			'<td class="padding10">User name</td>'
			'<td>Group</td>'
			'<td class="padding10">'
				'Role'
				'<!--<span class="add-button" title="Just a button, do nothing )">+ Add  </span>-->'
				'<span class="add-button">'
					'<a href="#"  title="Show all users" id="show-all-users" style="color: #fff">'
						'Show all'
					'</a>'
				'</span>'
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
		print(users['group']+'</td><td>')
		print(users['role'])
		print('</td></tr>')

print('<tr class="overviewHead">'
		'<td class="padding10">Server</td>'
		'<td class="padding10">'
			'HAproxy status'
		'</td>'
		'<td class="padding10">'
			'Action'
			'<!--<span class="add-button" title="Just a button, do nothing )">+ Add</span>-->'
				'<a href=""  title="Update status" id="update">'
					'<img alt="Update" src="/image/pic/update.png" class="icon" style="margin-left: 20px; float: right">'
				'</a></span>'
		'</td>'
	'</tr>')
	
listhap = funct.get_dick_after_permit()

commands = [ "ps -Af |grep [h]aproxy |wc -l" ]
for i in sorted(listhap):
	print('<tr><td class="padding10">' + i + '</td><td>')
	funct.ssh_command(listhap.get(i), commands, server_status="1")
	print('</td><td>')
	print('<a href="/cgi-bin/configshow.py?serv=%s&open=open#conf"  title="Show config"><img src=/image/pic/show.png alt="show" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/config.py?serv=%s&open=open#conf"  title="Edit config"><img src=/image/pic/edit.png alt="edit" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/diff.py?serv=%s&open=open#diff"  title="Compare config"><img src=/image/pic/compare.png alt="compare" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/map.py?serv=%s&open=open#map"  title="Map listen/frontend/backend"><img src=/image/pic/map.png alt="map" class="icon"></a>' % listhap.get(i))
	print('</td></tr>')
	
print('</table><table><tr class="overviewHead">'
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
for i in sorted(listhap):
	print('<tr><td class="overviewTr"><h3 title="IP ' + listhap.get(i) + '">' + i + ':</h3></td>')
	print('<td class="overviewTd"><span style="margin-left: -10px;">Total listen/frontend/backend:</span><pre>')
	funct.ssh_command(listhap.get(i), commands)
	print('</pre></td></tr>')

print('<tr></table>')
funct.footer()