#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import subprocess 
import os
import funct
import configparser

form = cgi.FieldStorage()
serv = form.getvalue('serv')

funct.head("HAproxy Logs")
funct.check_config()
funct.check_login("config.py")

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
	
print('<center><h2>HAproxy Logs</h2></center>')
print('<center><h3>Choose server & number rows</h3>')
print('<form action="logs.py" method="get">')
print('<p><select autofocus required name="serv" id="serv">')
print('<option disabled>Choose server</option>')

for i in sorted(listhap.listhap):
	if listhap.listhap.get(i) == serv:
		selected = 'selected'
	else:
		selected = ''

	if listhap.listhap.get(i) == '172.28.5.17' or listhap.listhap.get(i) == '172.28.9.161':
		continue

	print('<option value="%s" %s>%s</option>' % (listhap.listhap.get(i), selected, i))

print('</select>')

if form.getvalue('serv') is not None:
        rows = 'value='+form.getvalue('rows')
else:
	rows = 'value=10'

if form.getvalue('grep') is not None:
	grep = 'value='+form.getvalue('grep')
else:
	grep = 'value='

print('<input type="text" name="rows" %s required>' % rows)
print('|grep') 
print('<input type="text" name="grep" %s>' % grep)
print('<p><button type="submit">Show</button></p></form>')

if form.getvalue('serv') is not None:
	rows = form.getvalue('rows')
	grep = form.getvalue('grep')
	
	if grep is not None:
        	grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''

	syslog_server_enable = config.get('logs', 'syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "disable":
		local_path_logs = config.get('logs', 'local_path_logs')
		syslog_server = serv	
		commands = [ 'sudo tail -%s %s %s %s' % (rows, local_path_logs, grep_act, grep) ]	
	else:
		commands = [ 'sudo tail -%s /var/log/%s/syslog.log %s %s' % (rows, serv, grep_act, grep) ]
		syslog_server = config.get('logs', 'syslog_server')
	
	funct.ssh_command(syslog_server, commands, show_log="show_log")
	
funct.footer()