#!/usr/bin/env python3
import html
import cgi
import funct
import ovw

funct.head("Overview")
funct.check_config()
funct.check_login()
funct.get_auto_refresh("Overview")	

print('<div id="ajax">')

ovw.get_overview()

print('</div>')

funct.footer()