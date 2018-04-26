#!/usr/bin/env python3
import html
import cgi
import funct
import sql

form = cgi.FieldStorage()
serv = form.getvalue('serv')

funct.head("Runtime API")
funct.check_login()
funct.check_config()

print('<h2>Runtime API</h2>'
		'<table class="overview">'
			'<tr class="overviewHead">'
				'<td class="padding10 first-collumn">Server</td>'
				'<td>Disable/Enable server or output any information</td>'
				'<td class="padding10">Command</td>'
				'<td>Save change</td>'
				'<td></td>'
			'</tr>'
			'<tr>'
				'<td class="padding10 first-collumn" style="width: 25%;">'
				'<form action="edit.py" method="get">'
					'<select required name="serv" id="serv">'
						'<option disabled selected>Choose server</option>')

funct.choose_only_select(serv, virt=1)

print('</select></td>'
	'<td style="width: 30%;">'
		'<select required name="servaction" id="servaction">'
			'<option disabled selected>Choose action</option>')
if funct.is_admin():
	print('<option value="disable">Disable</option>')
	print('<option value="enable">Enable</option>')
	print('<option value="set">Set</option>')
print('<option value="show">Show</option>'
	'</select></td>'
	'<td>'
		'<input type="text" name="servbackend" id="servbackend" size=35 title="Frontend, backend/server, show: info, pools or help" required class="form-control">'
	'</td><td>'
		'<label for="save"></label><input type="checkbox" name="save" id="save" value="123">'
	'</td><td>'
		'<a class="ui-button ui-widget ui-corner-all" id="show" title="Enter" onclick="showRuntime()">Enter</a>'
	'</td></form>'
	'</tr></table>'
	'<div id="ajax">'
	'</div>')

funct.footer()