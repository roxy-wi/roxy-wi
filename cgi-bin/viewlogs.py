#!/usr/bin/env python3
import html
import cgi
import os
import funct
from configparser import ConfigParser, ExtendedInterpolation
import glob

form = cgi.FieldStorage()
viewlog = form.getvalue('viewlogs')

funct.head("View logs")
funct.check_config()
funct.check_login()

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)

log_path = config.get('main', 'log_path')

funct.page_for_admin()
funct.get_auto_refresh("View logs")	

os.chdir(log_path)
print('<script src="/inc/users.js"></script>'
		'<a name="top"></a>'
		'<center><h3>Choose log file</h3><br />'
		'<select id="viewlogs">')
	
i = 0
for files in sorted(glob.glob('*.log')):
	i = i + 1
	if files == viewlog:
		selected = 'selected'
	else:
		selected = ''
	print('<option value="%s" %s>%s</option>' % (files, selected, files))
		
print('</select>'
		'<a class="ui-button ui-widget ui-corner-all" id="show" title="Show stats" onclick="viewLogs()">Show</a>'
		'</center><br />'
		'<div id="ajax"></div>'
		'<script>'
			'window.onload = viewLogs()'
		'</script>')
		
funct.footer()