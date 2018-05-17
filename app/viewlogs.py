#!/usr/bin/env python3
import os
import sql
import http, cgi
import funct
import sql
import glob
import datetime
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('viewlogs.html')
form = cgi.FieldStorage()

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin()

log_path = funct.get_config_var('main', 'log_path')
time_storage = funct.get_config_var('logs', 'log_time_storage')
time_storage = int(time_storage)

try:
	time_storage_hours = time_storage * 24
	for dirpath, dirnames, filenames in os.walk(log_path):
		for file in filenames:
			curpath = os.path.join(dirpath, file)
			file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
			if datetime.datetime.now() - file_modified > datetime.timedelta(hours=time_storage_hours):
				os.remove(curpath)
except:
	print('<center><div class="alert alert-danger" style="margin: 0; margin-bottom: 10px;">Can\'t delete old logs file. <br> Please check "log_time_storage" in config and <br>exist directory </div></center>')
	pass
	
try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass
	
def get_files():
	file = set()
	for files in glob.glob(os.path.join(log_path,'*.log')):
		file.add(files.split('/')[5])
	return sorted(file, reverse=True)

output_from_parsed_template = template.render(h2 = 1,
												autorefresh = 1, 
												title = "View logs",
												role = sql.get_user_role_by_uuid(user_id.value),
												user = user,
												onclick = "viewLogs()",
												serv = form.getvalue('viewlogs'),
												select_id = "viewlogs",
												selects = get_files())										
print(output_from_parsed_template)
