#!/usr/bin/env python3
import html
import cgi
import os, sys
import funct
from configparser import ConfigParser, ExtendedInterpolation
import glob
import datetime

form = cgi.FieldStorage()
viewlog = form.getvalue('viewlogs')

funct.head("View logs")
funct.check_login()
funct.page_for_admin()
funct.get_auto_refresh("View logs")

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)	

try:
	if config.get('main', 'log_path'):
		log_path = config.get('main', 'log_path')
		time_storage = config.getint('logs', 'log_time_storage')
except:
	print('<center><div class="alert alert-danger">Can not find "log_path" and "log_time_storage" parametrs. Check into config</div>')	
try:
	os.chdir(log_path)
except IOError:
	print('<center><div class="alert alert-danger">No such file or directory: "%s". Please check "log_path" in config and exist directory</div>' % log_path)
	sys.exit()
	
print('<script src="/inc/users.js"></script>'
		'<a name="top"></a>'
		'<center><h3>Choose log file</h3><br />')
try:
	time_storage_hours = time_storage * 24
	for dirpath, dirnames, filenames in os.walk(log_path):
		for file in filenames:
			curpath = os.path.join(dirpath, file)
			file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
			if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
				os.remove(curpath)
except:
	print('<center><div class="alert alert-danger" style="margin: 0; margin-bottom: 10px;">Can\'t delete old logs file. <br> Please check "log_time_storage" in config and <br>exist directory </div>')
	pass
	
print('<select id="viewlogs">'
			'<option disabled selected>Choose log</option>')
	
for files in sorted(glob.glob('*.log'), reverse=True):
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