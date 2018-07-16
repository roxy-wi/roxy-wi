#!/usr/bin/env python3
import html, http.cookies
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

form = cgi.FieldStorage()
serv = form.getvalue('serv')
stderr = ""
aftersave = ""
file = set()
hap_configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.get_dick_permit(disable=0)
	token = sql.get_token(user_id.value)
except:
	pass

form = cgi.FieldStorage()
serv = form.getvalue('serv')
Select = form.getvalue('del')

if serv is not None and form.getvalue('open') is not None:
	if Select is not None:
		aftersave = 1
		for get in form:
			if "cfg" in get:
				try:
					os.remove(os.path.join(hap_configs_dir, form.getvalue(get)))
					file.add(form.getvalue(get) + "<br />")
					funct.logging(serv, "delver.py deleted config: %s" % form.getvalue(get))				
				except OSError as e: 
					stderr = "Error: %s - %s." % (e.filename,e.strerror)
		print('<meta http-equiv="refresh" content="10; url=delver.py?serv=%s&open=open">' % form.getvalue('serv'))		
		
output_from_parsed_template = template.render(h2 = 1, title = "Delete old versions HAProxy config",
													role = sql.get_user_role_by_uuid(user_id.value),
													action = "delver.py",
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
													token = token)
print(output_from_parsed_template)