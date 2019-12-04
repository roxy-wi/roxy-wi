#!/usr/bin/env python3
import html
import cgi
import os
import http.cookies
import funct
import sql
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/'))
template = env.get_template('config.html')

print('Content-type: text/html\n')
funct.check_login()
funct.page_for_admin(level = 2)

form = funct.form
serv = form.getvalue('serv')
log_path = funct.get_config_var('main', 'log_path')
kp_save_configs_dir = funct.get_config_var('configs', 'kp_save_configs_dir')
config_read = ""
cfg = ""
stderr = ""
aftersave = ""
error = ""

try:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	user = sql.get_user_name_by_uuid(user_id.value)
	servers = sql.is_master("123", master_slave=1)
	token = sql.get_token(user_id.value)
except:
	pass


if serv is not None:
	cfg = kp_save_configs_dir+ serv + '-' + funct.get_data('config') + '.conf'

if form.getvalue('serv') is not None and form.getvalue('open') is not None :
	
	try:
		funct.logging(serv, "keepalivedconfig.py open config")
	except:
		pass
	error = funct.get_config(serv, cfg, keepalived=1)
	
	try:
		conf = open(cfg, "r",encoding='utf-8', errors='ignore')
		config_read = conf.read()
		conf.close
	except IOError:
		error += "<br>Can't read import config file"

	os.system("/bin/mv %s %s.old" % (cfg, cfg))	

if form.getvalue('serv') is not None and form.getvalue('config') is not None:
	try:
		funct.logging(serv, "keepalivedconfig.py edited config")
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
		error += "Can't read import config file"
		
	stderr = funct.upload_and_restart(serv, cfg, just_save=save, keepalived=1)
		
	funct.diff_config(oldcfg, cfg)
	
	os.system("/bin/rm -f " + kp_save_configs_dir + "*.old")

output_from_parsed_template = template.render(h2 = 1, title = "Edit Runnig Keepalived config",
													role = sql.get_user_role_by_uuid(user_id.value),
													action = "keepalivedconfig.py",
													user = user,
													select_id = "serv",
													serv = serv,
													aftersave = aftersave,
													config = config_read,
													cfg = cfg,
													selects = servers,
													stderr = stderr,
													error = error,
													keepalived = 1,
													versions = funct.versions(),
													token = token)
print(output_from_parsed_template)
