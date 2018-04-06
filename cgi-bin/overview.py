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
haproxy_config_path  = config.get('haproxy', 'haproxy_config_path')
status_command = config.get('haproxy', 'status_command')
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
			'<td class="padding10">Login</td>'
			'<td>Group</td>'
			'<td class="padding10">'
				'Role'
			'</td><td style="width: 200px;">'
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
		print('<tr ' + style + '><td class="padding10 first-collumn">' + users['login'] +'</td><td class="second-collumn">')
		print(users['group']+'</td><td>')
		print(users['role'])
		print('</td><td></td></tr>')
	print('</table>')
print('<table class="overview">'
	'<tr class="overviewHead">'
		'<td class="padding10">Server</td>'
		'<td class="padding10">'
			'HAproxy status'
		'</td>'
		'<td class="padding10">'
			'Action'
		'</td>'
		'<td>'
			'Last edit'
		'</td>'
		'<td>'
			'<a href=""  title="Update status" id="update">'
				'<img alt="Update" src="/image/pic/update.png" class="icon" style="padding-right: 8px; float: right">'
			'</a></span>'
		'</td>'
	'</tr>')
	
listhap = funct.get_dick_after_permit()

commands = [ "ps -Af |grep [h]aproxy |wc -l" ]
commands1 = [ "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % haproxy_config_path ]

for i in sorted(listhap):
	print('<tr><td class="padding10 first-collumn"><a href="#%s" title="Go to %s status" style="color: #000">%s</a></td><td  class="second-collumn">' % (i, i, i))
	funct.ssh_command(listhap.get(i), commands, server_status="1")
	print('</td><td>')
	if funct.is_admin():
		print('<a href="/cgi-bin/overview.py#" class="start" id="%s" title="Start HAproxy service" onclick = "if (! confirm(\'Start service?\')) return false;"><img src=/image/pic/start.png alt="start" class="icon" ></a>' % listhap.get(i))
		print('<a href="/cgi-bin/overview.py#" class="stop" id="%s" title="Stop HAproxy service" onclick = "if (! confirm(\'Stop service?\')) return false;"><img src=/image/pic/stop.png alt="start" class="icon"></a>' % listhap.get(i))
		print('<a href="/cgi-bin/overview.py#" class="restart" id="%s" title="Restart HAproxy service" onclick = "if (! confirm(\'Restart service?\')) return false;"><img src=/image/pic/update.png alt="restart" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/configshow.py?serv=%s&open=open#conf"  title="Show config"><img src=/image/pic/show.png alt="show" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/config.py?serv=%s&open=open#conf"  title="Edit config"><img src=/image/pic/edit.png alt="edit" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/diff.py?serv=%s&open=open#diff"  title="Compare config"><img src=/image/pic/compare.png alt="compare" class="icon"></a>' % listhap.get(i))
	print('<a href="/cgi-bin/map.py?serv=%s&open=open#map"  title="Map listen/frontend/backend"><img src=/image/pic/map.png alt="map" class="icon"></a>' % listhap.get(i))
	print('</td><td>')
	funct.ssh_command(listhap.get(i), commands1)
	print('</td><td></td></tr>')

print('</table><table class="overview"><tr class="overviewHead">'
		'<td class="padding10">Server</td>'
		'<td class="padding10">'
			'HAproxy info'
		'</td>'
		'<td>'
			'Server status'
			'<span style="float: right; margin-left: 80&;">'
				'<a href=""  title="Update status" id="update">'
					'<img alt="Update" src="/image/pic/update.png" class="icon" style="padding-right: 8px; float: right">'
				'</a>'
			'</span>'
		'</td>'
	'</tr>')
print('</td></tr>')
commands = [ "cat " + haproxy_config_path + " |grep -E '^listen|^backend|^frontend' |grep -v stats |wc -l",  
			"uname -smor", 
			"haproxy -v |head -1", 
			status_command + "|grep Active | sed 's/^[ \t]*//'" ]
commands1 =  [ "top -u haproxy -b -n 1" ]
for i in sorted(listhap):
	print('<tr><td class="overviewTr first-collumn"><a name="'+i+'"></a><h3 title="IP ' + listhap.get(i) + '">' + i + ':</h3></td>')
	print('<td class="overviewTd"><span>Total listen/frontend/backend:</span><pre>')
	funct.ssh_command(listhap.get(i), commands)
	print('</pre></td><td class="overviewTd"><pre>')
	funct.ssh_command(listhap.get(i), commands1)
	print('</pre></td></tr>')
	
print('<tr></table>')
funct.footer()