#!/usr/bin/env python3
import html
import cgi
import os, http.cookies
import funct
import sql
from configparser import ConfigParser, ExtendedInterpolation
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('configver.html')
print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)
form = cgi.FieldStorage()
serv = form.getvalue('serv')
config_read = ""
configver = ""
stderr = ""
aftersave = ""

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
except:
	pass

path_config = "haproxy-webintarface.config"
config = ConfigParser(interpolation=ExtendedInterpolation())
config.read(path_config)
form = cgi.FieldStorage()
serv = form.getvalue('serv')
configver = form.getvalue('configver')
hap_configs_dir = config.get('configs', 'haproxy_save_configs_dir')

def get_files():
	import glob
	file = set()
	return_files = set()
	for files in glob.glob(os.path.join(hap_configs_dir,'*.cfg')):		
		file.add(files.split('/')[6])
	files = sorted(file, reverse=True)
	for file in files:
		ip = file.split("-")
		if serv == ip[0]:
			return_files.add(file)
	return sorted(return_files, reverse=True)

if form.getvalue('serv') is not None and form.getvalue('config') is not None:
	configver = form.getvalue('configver')
	configver = hap_configs_dir + configver
	save = form.getvalue('save')
	try:
		funct.logging(serv, "configver.py upload old config %s" % configver)
	except:
		pass

	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload_and_restart(master[0], configver, just_save=save)
			
	stderr = funct.upload_and_restart(serv, configver, just_save=save)
	aftersave = 1

	
output_from_parsed_template = template.render(h2 = 1, title = "Old Versions HAProxy config",
													role = sql.get_user_role_by_uuid(user_id.value),
													action = "configver.py",
													user = user,
													select_id = "serv",
													serv = serv,
													return_files = get_files(),
													aftersave = aftersave,
													config = config_read,
													configver = configver,
													selects = servers,
													stderr = stderr,
													open = form.getvalue('open'),
													onclick = "showUploadConfig()",
													note = 1)
print(output_from_parsed_template)
