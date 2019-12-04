#!/usr/bin/env python3
import http.cookies
import cgi
import os
import funct, sql
import glob
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('delver.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

form = funct.form
serv = form.getvalue('serv')
Select = form.getvalue('del')
configver = form.getvalue('configver')
stderr = ""
aftersave = ""
file = set()
hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')

if form.getvalue('configver'):
	template = env.get_template('configver.html')

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit(disable=0)
	token = sql.get_token(user_id.value)
except:
	pass


if serv is not None and form.getvalue('del') is not None:
	if Select is not None:
		aftersave = 1
		for get in form:
			if "cfg" in get:
				try:
					os.remove(os.path.join(hap_configs_dir, form.getvalue(get)))
					file.add(form.getvalue(get) + "<br />")
					funct.logging(serv, "versions.py were deleted configs: %s" % form.getvalue(get))				
				except OSError as e: 
					stderr = "Error: %s - %s." % (e.filename,e.strerror)
		print('<meta http-equiv="refresh" content="10; url=versions.py?serv=%s&open=open">' % form.getvalue('serv'))	


if serv is not None and form.getvalue('config') is not None:
	configver = hap_configs_dir + configver
	save = form.getvalue('save')
	aftersave = 1
	try:
		funct.logging(serv, "configver.py upload old config %s" % configver)
	except:
		pass

	stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save)
		
		
output_from_parsed_template = template.render(h2 = 1, title = "Working with versions HAProxy configs",
													role = sql.get_user_role_by_uuid(user_id.value),
													action = "versions.py",
													user = user,
													select_id = "serv",
													serv = serv,
													aftersave = aftersave,
													return_files = funct.get_files(),
													selects = servers,
													stderr = stderr,
													open = form.getvalue('open'),
													Select = form.getvalue('del'),
													file = file,
													versions = funct.versions(),
													configver = configver,
													token = token)
print(output_from_parsed_template)
