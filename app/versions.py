#!/usr/bin/env python3
import os

from jinja2 import Environment, FileSystemLoader

import funct
import sql
import modules.roxy_wi_tools as roxy_wi_tools

get_config_var = roxy_wi_tools.GetConfigVar()
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('delver.html')

print('Content-type: text/html\n')

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params(disable=1)
except Exception:
	pass

funct.page_for_admin(level=3)

form = funct.form
serv = funct.is_ip_or_dns(form.getvalue('serv'))
service = funct.checkAjaxInput(form.getvalue('service'))
Select = form.getvalue('del')
configver = form.getvalue('configver')
conf_format = 'cfg'
configs_dir = ''
stderr = ""
aftersave = ""
file = set()

if configver:
	template = env.get_template('configver.html')

if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
	service_desc = sql.select_service(service)
	if funct.check_login(user_id, token, service=service_desc.service_id):
		title = f"Working with versions {service_desc.service} configs"
		servers = sql.get_dick_permit(service=service_desc.slug)
		action = f'versions.py?service={service_desc.slug}'
		conf_format = 'conf'

		if service in ('haproxy', 'nginx', 'apache'):
			configs_dir = get_config_var.get_config_var('configs', f'{service_desc.service}_save_configs_dir')
		else:
			configs_dir = get_config_var.get_config_var('configs', 'kp_save_configs_dir')

		if service == 'haproxy':
			conf_format = 'cfg'
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')

if serv is not None and form.getvalue('del') is not None:
	if Select is not None:
		aftersave = 1
		env = Environment(loader=FileSystemLoader('templates/'))
		template = env.get_template('delver.html')
		for get in form:
			if conf_format in get and serv in get:
				try:
					if form.getvalue('style') == 'new':
						if sql.delete_config_version(service, form.getvalue(get)):
							try:
								os.remove(form.getvalue(get))
							except OSError as e:
								if 'No such file or directory' in str(e):
									pass
					else:
						os.remove(os.path.join(configs_dir, form.getvalue(get)))
					try:
						file.add(form.getvalue(get) + "<br />")
						funct.logging(
							serv, "Version of config has been deleted: %s" % form.getvalue(get), login=1, keep_history=1, service=service
						)
					except Exception:
						pass
				except OSError as e:
					stderr = "Error: %s - %s." % (e.filename, e.strerror)

if serv is not None and form.getvalue('config') is not None:
	configver = configs_dir + configver
	save = form.getvalue('save')
	aftersave = 1

	try:
		funct.logging(
			serv, "Version of config has been uploaded %s" % configver, login=1, keep_history=1, service=service
		)
	except Exception:
		pass

	if service == 'keepalived':
		stderr = funct.upload_and_restart(serv, configver, just_save=save, keepalived=1)
	elif service == 'nginx':
		config_file_name = sql.select_remote_path_from_version(server_ip=serv, service=service, local_path=configver)
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save, nginx=1, config_file_name=config_file_name)
	elif service == 'apache':
		config_file_name = sql.select_remote_path_from_version(server_ip=serv, service=service, local_path=configver)
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save, apache=1, config_file_name=config_file_name)
	else:
		stderr = funct.master_slave_upload_and_restart(serv, configver, just_save=save)


rendered_template = template.render(
	h2=1, title=title, role=role, user=user, select_id="serv", serv=serv, aftersave=aftersave, selects=servers,
	stderr=stderr, open=form.getvalue('open'), Select=form.getvalue('del'), file=file, configver=configver,
	service=service, user_services=user_services, action=action, token=token
)
print(rendered_template)
