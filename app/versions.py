#!/usr/bin/env python3
import os
import funct, sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('delver.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level=3)

form = funct.form
serv = form.getvalue('serv')
Select = form.getvalue('del')
configver = form.getvalue('configver')
service = form.getvalue('service')
conf_format = 'cfg'
configs_dir = ''
stderr = ""
aftersave = ""
file = set()

if configver:
	template = env.get_template('configver.html')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(disable=1)
except:
	pass

if service == 'keepalived':
	if funct.check_login(service=3):
		configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
		title = "Working with versions Keepalived configs"
		conf_format = 'conf'
		servers = sql.get_dick_permit(keepalived=1)
		action = 'versions.py?service=keepalived'
elif service == 'nginx':
	if funct.check_login(service=2):
		configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
		title = "Working with versions Nginx configs"
		conf_format = 'conf'
		servers = sql.get_dick_permit(nginx=1)
		action = 'versions.py?service=nginx'
else:
	service = 'haproxy'
	if funct.check_login(service=1):
		title = "Working with versions HAProxy configs"
		configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
		action = "versions.py"

if serv is not None and form.getvalue('del') is not None:
	if Select is not None:
		aftersave = 1
		env = Environment(loader=FileSystemLoader('templates/'))
		template = env.get_template('delver.html')
		for get in form:
			if conf_format in get:
				try:
					if form.getvalue('style') == 'new':
						if sql.delete_config_version(form.getvalue('service'), form.getvalue(get)):
							try:
								os.remove(form.getvalue(get))
							except OSError as e:
								if 'No such file or directory' in str(e):
									pass
					else:
						os.remove(os.path.join(configs_dir, form.getvalue(get)))
					file.add(form.getvalue(get) + "<br />")
					funct.logging(serv, "Version of config has been deleted: %s" % form.getvalue(get), login=1,
                              keep_history=1, service=service)
				except OSError as e:
					stderr = "Error: %s - %s." % (e.filename,e.strerror)

if serv is not None and form.getvalue('config') is not None:
	configver = configs_dir + configver
	save = form.getvalue('save')
	aftersave = 1

	try:
		funct.logging(serv, "Version of config has been uploaded %s" % configver, login=1,
                              keep_history=1, service=service)
	except Exception:
		pass

	if service == 'keepalived':
		stderr = funct.upload_and_restart(serv, configver, just_save=save, keepalived=1)
	elif service == 'nginx':
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save, nginx=1)
	else:
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save)
		
		
template = template.render(h2=1, title=title,
							role=role,
							user=user,
							select_id="serv",
							serv=serv,
							aftersave=aftersave,
							selects=servers,
							stderr=stderr,
							open=form.getvalue('open'),
							Select=form.getvalue('del'),
						   	file=file,
							configver=configver,
							service=service,
							user_services=user_services,
						   	action=action,
							token=token)
print(template)
