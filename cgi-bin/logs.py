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
funct.check_login()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
	
print('<center>'
		'<h2>HAproxy Logs</h2>'
	  '</center>'
		'<table class="overview">'
			'<tr class="overviewHead">'
				'<td class="padding10">Server</td>'
				'<td>Number rows</td>'
				'<td class="padding10">Ex for grep</td>'
			'</tr>'
			'<tr>'
				'<td class="padding10">'
				'<form action="logs.py" method="get">'
					'<select autofocus required name="serv" id="serv">'
						'<option disabled>Choose server</option>')

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
	grep = ' '

print('</td><td><input type="number" name="rows" %s class="form-control" required></td>' % rows)
print('<td><input type="text" name="grep" class="form-control" %s >' % grep)
print('</td></tr>'
		'<tr style="border:none;">'
			'<th style="border:none;">'
				'<td class="padding10" >'
					'<button type="submit">Show</button>'
				'</td>'
			'</th></form>'
		'</tr></table>')

if form.getvalue('serv') is not None:
	rows = form.getvalue('rows')
	grep = form.getvalue('grep')
	
	if grep is not None:
        	grep_act  = '|grep'
	else:
		grep_act = ''
		grep = ''

	syslog_server_enable = config.get('logs', 'syslog_server_enable')
	if syslog_server_enable is None or syslog_server_enable == "0":
		local_path_logs = config.get('logs', 'local_path_logs')
		syslog_server = serv	
		commands = [ 'sudo tail -%s %s %s %s' % (rows, local_path_logs, grep_act, grep) ]	
	else:
		commands = [ 'sudo tail -%s /var/log/%s/syslog.log %s %s' % (rows, serv, grep_act, grep) ]
		syslog_server = config.get('logs', 'syslog_server')
	
	funct.ssh_command(syslog_server, commands, show_log="1")
	
funct.footer()