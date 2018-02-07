#!/usr/bin/env python3
import html
import cgi
import funct
import configparser
import listserv as listhap

funct.head("Overview")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

print('<h2>Quick Status </h2><table class="overview">')

commands = [ "ps -Af |grep [h]aproxy |wc -l" ]

print('<tr class="overviewHead"><td class="padding10">Server</td><td class="padding10">HAproxy status</td></tr>')
for i in sorted(listhap.listhap):
	print('<tr><td class="padding10">' + i + '</td><td>')
	funct.ssh_command(listhap.listhap.get(i), commands, server_status="1")
	print('</td></tr>')
print('<tr class="overviewHead"><td class="padding10">Server</td><td class="padding10">Server status</td></tr>')
print('</td></tr>')
commands = [ "cat /etc/haproxy/haproxy.cfg |grep -E '^listen|^backend|^frontend' |grep -v stats |wc -l",  "haproxy -v |head -1", "top -u haproxy -b -n 1" ]
for i in sorted(listhap.listhap):
	print('<tr><td class="overviewTr"><h3 title="IP ' + listhap.listhap.get(i) + '">' + i + ':</h3></td>')
	print('<td class="overviewTd">Total listen/frontend/backend:<pre>')
	funct.ssh_command(listhap.listhap.get(i), commands)
	print('</pre></td></tr>')

print("</table>")
funct.footer()