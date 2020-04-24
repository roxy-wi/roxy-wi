#!/usr/bin/env python3
import os
import funct, sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('delver.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

form = funct.form
serv = form.getvalue('serv')
Select = form.getvalue('del')
configver = form.getvalue('configver')
service = form.getvalue('service')
stderr = ""
aftersave = ""
file = set()

if form.getvalue('configver'):
	template = env.get_template('configver.html')

try:
	user, user_id, role, token, servers = funct.get_users_params(disable=1)
except:
	pass
	
	
if service == 'keepalived':
	configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
	title = "Working with versions Keepalived configs"
	files = funct.get_files(dir=configs_dir, format='conf')
	action = 'versions.py?service=keepalived'	
	format = 'conf'
	servers = sql.get_dick_permit(keepalived=1)
elif service == 'nginx':
	configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
	title = "Working with versions Nginx configs"
	files = funct.get_files(dir=configs_dir, format='conf')
	action = 'versions.py?service=nginx'	
	format = 'conf'
	servers = sql.get_dick_permit(nginx=1)
else:
	title = "Working with versions HAProxy configs"
	files = funct.get_files()
	action = "versions.py"
	configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	format = 'cfg'


if serv is not None and form.getvalue('del') is not None:
	if Select is not None:
		aftersave = 1
		env = Environment(loader=FileSystemLoader('templates/'))
		template = env.get_template('delver.html')
		for get in form:
			if format in get:
				try:
					os.remove(os.path.join(configs_dir, form.getvalue(get)))
					file.add(form.getvalue(get) + "<br />")
					funct.logging(serv, "versions.py were deleted configs: %s" % form.getvalue(get))				
				except OSError as e: 
					stderr = "Error: %s - %s." % (e.filename,e.strerror)
		print('<meta http-equiv="refresh" content="10; url=versions.py?service=%s&serv=%s&open=open">' % (service, form.getvalue('serv')))	


if serv is not None and form.getvalue('config') is not None:
	configver = configs_dir + configver
	save = form.getvalue('save')
	aftersave = 1
	try:
		funct.logging(serv, "configver.py upload old config %s" % configver)
	except:
		pass
	if service == 'keepalived':
		stderr = funct.upload_and_restart(serv, configver, just_save=save, keepalived=1)
	elif service == 'nginx':
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save, nginx=1)
	else:
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save)
		
		
template = template.render(h2 = 1, title = title,
							role = role,
							action = action,
							user = user,
							select_id = "serv",
							serv = serv,
							aftersave = aftersave,
							return_files = files,
							selects = servers,
							stderr = stderr,
							open = form.getvalue('open'),
							Select = form.getvalue('del'),
							file = file,
							versions = funct.versions(),
							configver = configver,
							service = service,
							token = token)
print(template)
