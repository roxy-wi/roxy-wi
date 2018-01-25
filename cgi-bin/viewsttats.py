#!/usr/bin/env python3
import html
import cgi
import requests
import funct
import listserv as listhap
import configparser
from requests_toolbelt.utils import dump

funct.check_config()

path_config = "haproxy-webintarface.config"
config = configparser.ConfigParser()
config.read(path_config)
haproxy_user = config.get('haproxy', 'user')
haproxy_pass = config.get('haproxy', 'password')
stats_port = config.get('haproxy', 'stats_port')

listhap.listhap = funct.merge_two_dicts(listhap.listhap, listhap.list_hap_vip)

form = cgi.FieldStorage()
serv = form.getvalue('serv')

if serv is None:
	first_serv = list(listhap.list_hap_vip.values())
	serv = first_serv[0]

try:
	response = requests.get('http://%s:%s/stats' % (serv, stats_port), auth=(haproxy_user, haproxy_pass)) 
except requests.exceptions.ConnectTimeout:
	print('Oops. Connection timeout occured!')
except requests.exceptions.ReadTimeout:
	print('Oops. Read timeout occured')

print("Content-type: text/html\n")
print('<meta http-equiv="refresh" content="%s; url=viewsttats.py?serv=%s">' % (config.get('haproxy', 'refresh_time') ,serv))

for i in listhap.listhap:
        if listhap.listhap.get(i) == serv:
                servname = i

print('<h3>Curent server IP - %s, name - %s </h3></br>' % (serv, servname))
print('<a href=/ title="Home Page" style="size:5">Home Page</a></br></br>')

print('<h3>Choose server!</h3></br>')
print('<form action="viewsttats.py" method="get">')
print('<p><select autofocus required name="serv">')
print('<option disabled>Choose server</option>')

funct.choose_server_with_vip(serv)

print('</select><input type="submit"></p></form>')

data = dump.dump_all(response)
print('<a name="conf"></a>')
print(data.decode('utf-8'))

