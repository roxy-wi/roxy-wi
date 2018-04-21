#!/usr/bin/env python3
import html
import cgi
import funct
import ovw
	
form = cgi.FieldStorage()
serv = form.getvalue('serv')
left = form.getvalue('left')
right = form.getvalue('right')

funct.head("Compare HAproxy configs")
funct.check_config()
funct.check_login()	
funct.chooseServer("diff.py#diff", "Compare HAproxy configs", "n", onclick="showCompareConfigs()")

print('<div id="ajax-compare">')

if serv is not None and form.getvalue('open') is not None :
	ovw.show_compare_configs(serv)
	
print('</div><div id=ajax>')

if serv is not None and right is not None:
	ovw.comapre_show()

print('</div>')
funct.footer()