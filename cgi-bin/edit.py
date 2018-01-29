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

print('<center><h2>Edit & show HAproxy settings</h2></center>')
print('<center><h3>Choose server & action: Disable/Enable server or output any information about the server:</h3>')
print('<form action="edit.py" method="get">')
print('<p><select autofocus required name="serv" id="serv">')
print('<option disabled selected>Choose server</option>')
	
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

print('</select>')
print('<select autofocus required name="servaction" id="chooseServer">')
print('<option disabled selected>Choose action</option>')
print('<option value=1 %s>Disable server</option>' % selected1)
print('<option value=2 %s>Enable server</option>' % selected2)
print('<option value=3 %s>Show</option>' % selected3)
print('</select>')
print('<input type="text" name="servbackend"  size=40 placeholder="Backend/Server, show info, pools or help" required>')
print('<p>')
funct.mode_admin("Enter")
print('</p></form>')

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

	print('<center><h3>You %s %s on HAproxy %s. <a href="viewsttats.py?serv=%s" title="View stat" target="_blank">Look it		    </a> or <a href="edit.py" title="Edit">Edit something else</a>'  % (enable, backend, serv, serv))
	print('</center>')

	print('\n<center><p>'.join(map(str, output)))
	
	action = 'edit.py ' + enable + ' ' + backend
	funct.logging(serv, action)

funct.footer()