#!/usr/bin/env python3
import html
import cgi
import requests
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation
from requests_toolbelt.utils import dump

print("Content-type: text/html\n")

form = cgi.FieldStorage()
serv = form.getvalue('serv')

if serv is None:
	first_serv = sql.get_dick_permit()
	for i in first_serv:
		serv = i[2]
		break
		
print('<a name="top"></a><div class="container">')

funct.get_auto_refresh("HAproxy statistics")	

print('<br />'
		'<form style="padding-left: 20px;" action="viewsttats.py" method="get">'
			'<select autofocus required name="serv" id="serv">'
				'<option disabled>Choose server</option>')

funct.choose_only_select(serv, master_slave=1)

print('</select>'		
		'<a class="ui-button ui-widget ui-corner-all" id="show" title="Show stats" onclick="showStats()">Show</a>'
		'</form>'
		'<div id="ajax" style="margin-left: 10px;"></div>')

funct.head("Stats HAproxy configs")
print('</div><script> window.onload = showStats()</script>')
funct.footer()
