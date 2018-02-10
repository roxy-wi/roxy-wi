#!/usr/bin/env python3
import html
import cgi
import listserv as listhap
import subprocess 
import os
import http.cookies
import funct
from funct import head as head

form = cgi.FieldStorage()
serv = form.getvalue('serv')

head("Edit & show HAproxy settings")

funct.check_login()

print('<center>'
		'<h2>Edit & show HAproxy settings</h2>'
	  '</center>'
		'<table class="overview">'
			'<tr class="overviewHead">'
				'<td class="padding10">Server</td>'
				'<td>Disable/Enable server or output any information</td>'
				'<td class="padding10">Command</td>'
			'</tr>'
			'<tr>'
				'<td class="padding10" style="width: 35%;">'
				'<form action="edit.py" method="get">'
					'<select autofocus required name="serv">'
						'<option disabled selected>Choose server</option>')

funct.choose_server_with_vip(serv)

action = form.getvalue('servaction')
backend = form.getvalue('servbackend')

if action == '1':
	selected1 = 'selected'
	selected2 = ''
	selected3 = ''
elif action == '2':
	selected1 = ''
	selected2 = 'selected'
	selected3 = ''
elif action == '3':
	selected1 = ''
	selected2 = ''
	selected3 = 'selected'
else:
	selected1 = ''
	selected2 = ''
	selected3 = ''

print('</select></td>')
print('<td style="width: 35%;"><select autofocus required name="servaction">')
print('<option disabled selected>Choose action</option>')
print('<option value=1 %s>Disable server</option>' % selected1)
print('<option value=2 %s>Enable server</option>' % selected2)
print('<option value=3 %s>Show</option>' % selected3)
print('</select></td>')
print('<td><input type="text" name="servbackend" size=40 placeholder="Backend/Server, show info, pools or help" required class="form-control">')

print('</td></tr>'
		'<tr style="border:none;">'
			'<td></td><td class="padding10" style="border:none; padding-left: 12%;">')
funct.mode_admin("Enter")
print('</td></form>'
		'</tr></table>')

if form.getvalue('servaction') is not None:
	action = form.getvalue('servaction')
	backend = form.getvalue('servbackend')

	if action == '1':
		enable = 'disable server'
	elif action == '2':
		enable = 'enable server'
	elif action == '3':
		enable = 'show'

	cmd='echo "%s %s" |nc %s 1999' % (enable, backend, serv)
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()

	print('<center><h3>You %s %s on HAproxy %s. <a href="viewsttats.py?serv=%s" title="View stat" target="_blank">Look it</a> or <a href="edit.py" title="Edit">Edit something else</a></h3><br />'  % (enable, backend, serv, serv))
	print('<center>'.join(map(str, output)))
	
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)

funct.footer()