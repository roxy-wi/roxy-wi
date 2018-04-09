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

funct.get_auto_refresh("HAproxy logs")	
print('<table class="overview">'
			'<tr class="overviewHead">'
				'<td class="padding10">Server</td>'
				'<td>Number rows</td>'
				'<td class="padding10">Ex for grep</td>'
				'<td> </td>'
			'</tr>'
			'<tr>'
				'<td class="padding10">'
				'<form action="logs.py" method="get">'
					'<select autofocus required name="serv" id="serv">'
						'<option disabled>Choose server</option>')

funct.choose_only_select(serv)

print('</select>')

if form.getvalue('serv') is not None:
        rows = 'value='+form.getvalue('rows')
else:
	rows = 'value=10'

if form.getvalue('grep') is not None:
	grep = 'value='+form.getvalue('grep')
else:
	grep = ' '

print('</td><td><input type="number" name="rows" id="rows" %s class="form-control" required></td>' % rows)
print('<td><input type="text" name="grep" id="grep" class="form-control" %s >' % grep)
print('</td>'
		'<td class="padding10" >'
			'<span id="loading" class="fa fa-spinner fa-spin"></span>'
			'<a class="ui-button ui-widget ui-corner-all" id="show" title="Show logs" onclick="showLog()">Show</a>')
if form.getvalue('serv') is not None:
	print('<span style="float: right; margin-top: 8px;">'
				'<a href=""  title="Update logs" id="update">'
					'<img alt="Update" src="/image/pic/update.png" style="max-width: 20px;">'
				'</a>'
			'</span>')
print('</td>'
		'</form>'
		'</tr></table>'
	'<div id="ajax">'
	'</div>')	
funct.footer()