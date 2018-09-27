#!/usr/bin/env python3
import html
import cgi
import os, http.cookies
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('configver.html')

funct.check_login()
funct.page_for_admin(level = 2)

form = cgi.FieldStorage()
serv = form.getvalue('serv')
view = form.getvalue('view')
hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
stderr = ""
aftersave = ""
configver = ""

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit()
	token = sql.get_token(user_id.value)
except:
	pass

if serv is not None and form.getvalue('config') is not None:
	configver = form.getvalue('configver')
	configver = hap_configs_dir + configver
	save = form.getvalue('save')
	aftersave = 1
	try:
		funct.logging(serv, "configver.py upload old config %s" % configver)
	except:
		pass

	MASTERS = sql.is_master(serv)
	for master in MASTERS:
		if master[0] != None:
			funct.upload_and_restart(master[0], configver, just_save=save)
			
	stderr = funct.upload_and_restart(serv, configver, just_save=save)
	
	if save:
		c = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		c["restart"] = form.getvalue('serv')
		print(c)
		
print('Content-type: text/html\n')
template = template.render(h2 = 1, title = "Old Versions HAProxy config",
							role = sql.get_user_role_by_uuid(user_id.value),
							action = "configver.py",
							user = user,
							select_id = "serv",
							serv = serv,
							return_files = funct.get_files(),
							aftersave = aftersave,
							configver = configver,
							selects = servers,
							stderr = stderr,
							open = form.getvalue('open'),
							onclick = "showUploadConfig()",
							note = 1,
							token = token,
							view = view)
print(template)
