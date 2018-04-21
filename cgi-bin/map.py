#!/usr/bin/env python3
import html
import cgi
import os
import funct
import ovw

form = cgi.FieldStorage()
serv = form.getvalue('serv')

funct.head("Show HAproxy config")
funct.check_config()
funct.check_login()
funct.chooseServer("map.py", "Show HAproxy map", "n", onclick="showMap()")

print('<div id="ajax">')
if serv is not None:	
	ovw.get_map(serv)
print('</div>')
		
funct.footer()