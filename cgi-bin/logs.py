#!/usr/bin/env python3
import html
import cgi
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
				'<td class="padding10 first-collumn">Server</td>'
				'<td>Number rows</td>'
				'<td class="padding10">Ex for grep</td>'
				'<td> </td>'
			'</tr>'
			'<tr>'
				'<td class="padding10 first-collumn">'
				'<form action="logs.py" method="get">'
					'<select autofocus required name="serv" id="serv">'
						'<option disabled selected>Choose server</option>')

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
print('<td class="padding10 first-collumn"><input type="text" name="grep" id="grep" class="form-control" %s >' % grep)
print('</td>'
		'<td class="padding10 first-collumn">'
			'<a class="ui-button ui-widget ui-corner-all" id="show" title="Show logs" onclick="showLog()">Show</a>'
	  '</td>'
	'</form>'
	'</tr></table>'
	'<div id="ajax">'
	'</div>')	
funct.footer()