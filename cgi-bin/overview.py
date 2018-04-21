#!/usr/bin/env python3
import html
import cgi
import funct
import ovw

funct.head("Overview")
funct.check_config()
funct.check_login()
funct.get_auto_refresh("Overview")	

print('<script> window.onload = showOverview()</script><div id="ajax"></div>')

funct.footer()