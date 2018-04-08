#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import subprocess 
import os
import http.cookies
import funct
import configparser
from funct import head as head

form = cgi.FieldStorage()
serv = form.getvalue('serv')
action = form.getvalue('servaction')
backend = form.getvalue('servbackend')

head("Runtime API")

funct.check_login()
funct.check_config()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)

server_state_file = config.get('haproxy', 'server_state_file')
haproxy_sock = config.get('haproxy', 'haproxy_sock')

if backend is None:
	backend = ""
	autofocus = ""
else: 
	autofocus = "autofocus"
	
if action == 'disable':
	selected1 = 'selected'
	selected2 = ''
	selected3 = ''
	selected4 = ''
elif action == 'enable':
	selected1 = ''
	selected2 = 'selected'
	selected3 = ''
	selected4 = ''
elif action == 'set':
	selected1 = ''
	selected2 = ''
	selected3 = 'selected'
	selected4 = ''
elif action == 'show':
	selected1 = ''
	selected2 = ''
	selected3 = ''
	selected4 = 'selected'
else:
	selected1 = ''
	selected2 = ''
	selected3 = ''
	selected4 = ''

print('<h2>Runtime API</h2>'
		'<table class="overview">'
			'<tr class="overviewHead">'
				'<td class="padding10">Server</td>'
				'<td>Disable/Enable server or output any information</td>'
				'<td class="padding10">Command</td>'
				'<td>Save change</td>'
				'<td></td>'
			'</tr>'
			'<tr>'
				'<td class="padding10" style="width: 25%;">'
				'<form action="edit.py" method="get">'
					'<select required name="serv">'
						'<option disabled selected>Choose server</option>')

funct.choose_server_with_vip(serv)

print('</select></td>'
	'<td style="width: 30%;">'
		'<select required name="servaction">'
			'<option disabled selected>Choose action</option>')
if funct.is_admin():
	print('<option value="disable" %s>Disable</option>' % selected1)
	print('<option value="enable" %s>Enable</option>' % selected2)
	print('<option value="set" %s>Set</option>' % selected3)
print('<option value="show" %s>Show</option>' % selected4)
print('</select></td>')
print('<td><input type="text" name="servbackend" size=35 title="Frontend, backend/server, show: info, pools or help" required class="form-control" value="%s" %s>' % (backend, autofocus))

print('</td><td>'
			'<input type="checkbox" name="save" title="Save changes after restart">'
		'</td><td>')
funct.get_button("Enter")
print('</td></form>'
		'</tr></table>')

if form.getvalue('servaction') is not None:
	enable = form.getvalue('servaction')
	cmd='echo "%s %s" |socat stdio %s | cut -d "," -f 1-2,5-10,34-36 | column -s, -t' % (enable, backend, haproxy_sock)
	
	if form.getvalue('save') == "on":
		save_command = 'echo "show servers state" | socat stdio %s > %s' % (haproxy_sock, server_state_file)
		command = [ cmd, save_command ] 
	else:
		command = [ cmd ] 
		
	if enable != "show":
			print('<center><h3>You %s %s on HAproxy %s. <a href="viewsttats.py?serv=%s" title="View stat" target="_blank">Look it</a> or <a href="edit.py" title="Edit">Edit something else</a></h3><br />' % (enable, backend, serv, serv))
			
	funct.ssh_command(serv, command, show_log="1")
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)

funct.footer()