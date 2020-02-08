#!/usr/bin/env python3
import cgi
import os
import http.cookies
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
config_read = ""
cfg = ""
stderr = ""
error = ""
aftersave = ""

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	token = sql.get_token(user_id.value)
	role = sql.get_user_role_by_uuid(user_id.value)
except:
	pass


if service == 'keepalived':
	title = "Working with Keepalived configs"
	action = "config.py?service=keepalived"
	configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')	
	format = 'conf'
	servers = sql.get_dick_permit(keepalived=1)
elif service == 'nginx':
	title = "Working with Nginx configs"
	action = "config.py?service=nginx"
	configs_dir = funct.get_config_var('configs', 'nginx_save_configs_dir')	
	format = 'conf'
	servers = sql.get_dick_permit(nginx=1)
else:
	title = "Working with HAProxy configs"
	action = "config.py"
	configs_dir = funct.get_config_var('configs', 'haproxy_save_configs_dir')
	format = 'cfg'
	servers = sql.get_dick_permit()

if serv is not None:
	cfg = configs_dir + serv + "-" + funct.get_data('config') + "."+format

if serv is not None and form.getvalue('open') is not None :
	
	if service == 'keepalived':
		error = funct.get_config(serv, cfg, keepalived=1)
		try:
			funct.logging(serv, " Keepalived config has opened for ")
		except:
			pass
	elif service == 'nginx':
		error = funct.get_config(serv, cfg, nginx=1)
		try:
			funct.logging(serv, " Nginx config has opened ")
		except:
			pass
	else:
		error = funct.get_config(serv, cfg)
		try:
			funct.logging(serv, " HAProxy config has opened ")
		except:
			pass
	
	try:
		conf = open(cfg, "r")
		config_read = conf.read()
		conf.close
	except IOError:
		error += '<br />Can\'t read import config file'

	os.system("/bin/mv %s %s.old" % (cfg, cfg))	

if serv is not None and form.getvalue('config') is not None:
	try:
		funct.logging(serv, "config.py edited config")
	except:
		pass
		
	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')
	aftersave = 1
	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		error = "Can't read import config file"
	
	if service == 'keepalived':
		stderr = funct.upload_and_restart(serv, cfg, just_save=save, keepalived=1)
	elif service == 'nginx':
		stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save, nginx=1)
	else:
		stderr = funct.master_slave_upload_and_restart(serv, cfg, just_save=save)
		
	funct.diff_config(oldcfg, cfg)
		
	os.system("/bin/rm -f " + configs_dir + "*.old")


template = template.render(h2 = 1, title = title,
							role = role,
							action = action,
							user = user,
							select_id = "serv",
							serv = serv,
							aftersave = aftersave,
							config = config_read,
							cfg = cfg,
							selects = servers,
							stderr = stderr,
							error = error,
							note = 1,
							versions = funct.versions(),
							service = service,
							token = token)
print(template)
