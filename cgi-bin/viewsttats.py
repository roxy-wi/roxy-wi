#!/usr/bin/env python3
import html
import cgi
import requests
import funct
import sql
import configparser
from requests_toolbelt.utils import dump

print("Content-type: text/html\n")
funct.check_config()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
haproxy_user = config.get('haproxy', 'user')
haproxy_pass = config.get('haproxy', 'password')
stats_port = config.get('haproxy', 'stats_port')
stats_page = config.get('haproxy', 'stats_page')

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

funct.choose_only_select(serv)

print('</select>'		
		'<a class="ui-button ui-widget ui-corner-all" id="show" title="Show stats" onclick="showStats()">Show</a>'
		'</form>')

try:
	response = requests.get('http://%s:%s/%s' % (serv, stats_port, stats_page), auth=(haproxy_user, haproxy_pass)) 
except requests.exceptions.ConnectTimeout:
	print('Oops. Connection timeout occured!')
except requests.exceptions.ReadTimeout:
	print('Oops. Read timeout occured')
except requests.exceptions.HTTPError as errh:
    print ("Http Error:",errh)
except requests.exceptions.ConnectionError as errc:
    print ("Error Connecting:",errc)
except requests.exceptions.Timeout as errt:
    print ("Timeout Error:",errt)
except requests.exceptions.RequestException as err:
    print ("OOps: Something Else",err)

data = response.content
print('<a name="conf"></a><div id="ajax" style="margin-left: 10px;">')
print(data.decode('utf-8'))
print('</div>')

funct.head("Stats HAproxy configs")
print('</div>')
funct.footer()
