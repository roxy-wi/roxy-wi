#!/usr/bin/env python3
import os
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('config.html')

print('Content-type: text/html\n')
funct.check_login()

form = funct.form
serv = form.getvalue('serv')
service = form.getvalue('service')
is_serv_protected = False
try:
	config_file_name = form.getvalue('config_file_name').replace('92', '/')
except:
	config_file_name = ''
config_read = ""
cfg = ""
stderr = ""
error = ""
aftersave = ""

try:
	user, user_id, role, token, servers, user_services = funct.get_users_params()
except Exception as e:
	print(str(e))

if service == 'keepalived':
	if funct.check_login(service=3):
		title = "Working with Keepalived configuration files"
		action = "config.py?service=keepalived"
		configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
		file_format = 'conf'
		servers = sql.get_dick_permit(keepalived=1)
elif service == 'nginx':
	if funct.check_login(service=2):
		title = "Working with Nginx configuration files"
		action = "config.py?service=nginx"
		configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')
		file_format = 'conf'
		servers = sql.get_dick_permit(nginx=1)
elif service == 'apache':
	if funct.check_login(service=2):
		title = "Working with Apache configuration files"
		action = "config.py?service=apache"
		configs_dir = funct.get_config_var('configs', 'apache_save_configs_dir')
		file_format = 'conf'
		servers = sql.get_dick_permit(apache=1)
else:
	if funct.check_login(service=1):
		title = "Working with HAProxy configuration files"
		action = "config.py"
		configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
		file_format = 'cfg'
		servers = sql.get_dick_permit(haproxy=1)

if serv is not None:
	if service == 'nginx' or service == 'apache':
		conf_file_name_short = config_file_name.split('/')[-1]
		cfg = configs_dir + serv + "-" + conf_file_name_short + "-" + funct.get_data('config') + "." + file_format
	else:
		cfg = configs_dir + serv + "-" + funct.get_data('config') + "."+file_format

if serv is not None and form.getvalue('open') is not None and form.getvalue('new_config') is None:
	funct.check_is_server_in_group(serv)
	is_serv_protected = sql.is_serv_protected(serv)

	if service == 'keepalived':
		error = funct.get_config(serv, cfg, keepalived=1)
		try:
			funct.logging(serv, " Keepalived config has been opened for ")
		except Exception:
			pass
	elif service == 'nginx':
		error = funct.get_config(serv, cfg, nginx=1, config_file_name=config_file_name)
		try:
			funct.logging(serv, " Nginx config has been opened ")
		except Exception:
			pass
	elif service == 'apache':
		error = funct.get_config(serv, cfg, apache=1, config_file_name=config_file_name)
		try:
			funct.logging(serv, " Apache config has been opened ")
		except Exception:
			pass
	else:
		error = funct.get_config(serv, cfg)
		try:
			funct.logging(serv, " HAProxy config has been opened ")
		except Exception:
			pass
	
	try:
		conf = open(cfg, "r")
		config_read = conf.read()
		conf.close()
	except IOError:
		error += '<br />Cannot read imported config file'

	os.system("/bin/mv %s %s.old" % (cfg, cfg))

if form.getvalue('new_config') is not None:
	config_read = ' '

if serv is not None and form.getvalue('config') is not None:
	import sys
	funct.check_is_server_in_group(serv)

	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("error: Cannot read imported config file")

	if service == 'keepalived':
		stderr = funct.upload_and_restart(serv, cfg, just_save=save, keepalived=1, oldcfg=oldcfg)
	elif service == 'nginx':
		stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, nginx=1, oldcfg=oldcfg, config_file_name=config_file_name)
	elif service == 'apache':
		stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, apache=1, oldcfg=oldcfg, config_file_name=config_file_name)
	else:
		stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, oldcfg=oldcfg)

	funct.diff_config(oldcfg, cfg)

	os.system("/bin/rm -f " + configs_dir + "*.old")

	if stderr:
		print(stderr)
	else:
		if save == 'test':
			print('Config is ok')
		else:
			print('Config is ok <br /> Config has been updated')
	sys.exit()

template = template.render(h2=1, title=title,
							role=role,
							action=action,
							user=user,
							select_id="serv",
							serv=serv,
							aftersave=aftersave,
							config=config_read,
							cfg=cfg,
							selects=servers,
							stderr=stderr,
							error=error,
							service=service,
							user_services=user_services,
							config_file_name=config_file_name,
							is_serv_protected=is_serv_protected,
							token=token)
print(template)
