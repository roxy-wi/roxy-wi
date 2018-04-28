#!/usr/bin/env python3
import html
import cgi
import funct
import ovw

funct.head("Overview")
funct.check_config()
funct.check_login()
funct.get_auto_refresh("Overview")	
print("<script>if (cur_url[0] == 'overview.py') { $('#secIntervals').css('display', 'none');}</script>")
print('<script> window.onload = showOverview()</script><div id="ajax"></div>')

funct.footer()