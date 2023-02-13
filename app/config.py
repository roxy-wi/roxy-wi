#!/usr/bin/env python3
import os
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.auth as roxywi_auth
import modules.config.config as config_mod
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.common as roxywi_common

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()
env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
template = env.get_template('config.html')

print('Content-type: text/html\n')

form = common.form
serv = common.is_ip_or_dns(form.getvalue('serv'))
try:
	service = common.checkAjaxInput(form.getvalue('service'))
except Exception:
	print('<meta http-equiv="refresh" content="0; url=/app/">')

is_serv_protected = False

try:
	config_file_name = form.getvalue('config_file_name').replace('92', '/')
except Exception:
	config_file_name = ''

config_read = ""
cfg = ""
stderr = ""
error = ""
aftersave = ""
is_restart = ''
service_desc = ''

user_params = roxywi_common.get_users_params(service='nginx')

if service in ('haproxy', 'nginx', 'keepalived', 'apache'):
	service_desc = sql.select_service(service)
	if roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=service_desc.service_id):
		if user_params['lang'] == 'ru':
			title = f"Работа с конфигурационным файлом {service_desc.service}"
		else:
			title = f"Working with {service_desc.service} configuration files"
		action = f"config.py?service={service_desc.slug}"
		configs_dir = get_config_var.get_config_var('configs', 'kp_save_configs_dir')
		file_format = 'conf'
		servers = roxywi_common.get_dick_permit(service=service_desc.slug)

		if service in ('haproxy', 'nginx', 'apache'):
			configs_dir = get_config_var.get_config_var('configs', f'{service_desc.service}_save_configs_dir')
		else:
			configs_dir = get_config_var.get_config_var('configs', 'kp_save_configs_dir')

		if service == 'haproxy':
			file_format = 'cfg'
else:
	print('<meta http-equiv="refresh" content="0; url=/app/overview.py">')

if serv is not None:
	if service == 'nginx' or service == 'apache':
		conf_file_name_short = config_file_name.split('/')[-1]
		cfg = f"{configs_dir}{serv}-{conf_file_name_short}-{get_date.return_date('config')}.{file_format}"
	else:
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.{file_format}"

if serv is not None and form.getvalue('open') is not None and form.getvalue('new_config') is None:
	roxywi_common.check_is_server_in_group(serv)
	is_serv_protected = sql.is_serv_protected(serv)
	server_id = sql.select_server_id_by_ip(serv)
	is_restart = sql.select_service_setting(server_id, service, 'restart')

	if service == 'keepalived':
		error = config_mod.get_config(serv, cfg, keepalived=1)
		try:
			roxywi_common.logging(serv, " Keepalived config has been opened for ")
		except Exception:
			pass
	elif service == 'nginx':
		error = config_mod.get_config(serv, cfg, nginx=1, config_file_name=config_file_name)
		try:
			roxywi_common.logging(serv, " NGINX config has been opened ")
		except Exception:
			pass
	elif service == 'apache':
		error = config_mod.get_config(serv, cfg, apache=1, config_file_name=config_file_name)
		try:
			roxywi_common.logging(serv, " Apache config has been opened ")
		except Exception:
			pass
	else:
		error = config_mod.get_config(serv, cfg)
		try:
			roxywi_common.logging(serv, " HAProxy config has been opened ")
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
	roxywi_common.check_is_server_in_group(serv)

	config = form.getvalue('config')
	oldcfg = form.getvalue('oldconfig')
	save = form.getvalue('save')

	try:
		with open(cfg, "a") as conf:
			conf.write(config)
	except IOError:
		print("error: Cannot read imported config file")

	if service == 'keepalived':
		stderr = config_mod.upload_and_restart(serv, cfg, just_save=save, keepalived=1, oldcfg=oldcfg)
	elif service == 'nginx':
		stderr = config_mod.master_slave_upload_and_restart(serv, cfg, just_save=save, nginx=1, oldcfg=oldcfg, config_file_name=config_file_name)
	elif service == 'apache':
		stderr = config_mod.master_slave_upload_and_restart(serv, cfg, just_save=save, apache=1, oldcfg=oldcfg, config_file_name=config_file_name)
	else:
		stderr = config_mod.master_slave_upload_and_restart(serv, cfg, just_save=save, oldcfg=oldcfg)

	config_mod.diff_config(oldcfg, cfg)

	try:
		os.system("/bin/rm -f " + configs_dir + "*.old")
	except Exception as e:
		print('error: ' + str(e))

	if stderr:
		print(stderr)

	sys.exit()

template = template.render(
	h2=1, role=user_params['role'], action=action, user=user_params['user'], select_id="serv", serv=serv, aftersave=aftersave,
	config=config_read, cfg=cfg, selects=servers, stderr=stderr, error=error, service=service, is_restart=is_restart,
	user_services=user_params['user_services'], config_file_name=config_file_name, is_serv_protected=is_serv_protected,
	token=user_params['token'], lang=user_params['lang'], service_desc=service_desc
)
print(template)
