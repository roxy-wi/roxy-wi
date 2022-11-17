#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.roxywi.auth as roxywi_auth
import modules.roxywi.common as roxywi_common

get_config_var = roxy_wi_tools.GetConfigVar()
form = common.form
serv = form.getvalue('serv')

print('Content-type: text/html\n')

user_params = roxywi_common.get_users_params(service='nginx')

try:
	roxywi_auth.check_login(user_params['user_uuid'], user_params['token'], service=2)
except Exception as e:
	print(f'error {e}')
	sys.exit()

roxywi_auth.page_for_admin(level=3)

if all(v is None for v in [form.getvalue('upstream'), form.getvalue('generateconfig')]):
	env = Environment(loader=FileSystemLoader('templates/'), autoescape=True)
	template = env.get_template('add_nginx.html')
	template = template.render(
		title="Add: ", role=user_params['role'], user=user_params['user'], selects=user_params['servers'], add=form.getvalue('add'), conf_add=form.getvalue('conf'),
		user_services=user_params['user_services'], token=user_params['token']
	)
	print(template)
elif form.getvalue('upstream') is not None:
	nginx_dir = sql.get_setting('nginx_dir')
	name = form.getlist('name')
	new_upstream = form.getvalue('upstream')
	ip = ''
	port = ''
	config_add = ''
	servers_split = ''

	if new_upstream is not None:
		config_add = f'upstream {new_upstream} {{\n'
		config_add += f'    {form.getvalue("balance")};\n'
		config_name = f'upstream_{new_upstream}'

	if form.getvalue('keepalive') is not None:
		config_add += f'    keepalive {form.getvalue("keepalive")};\n'

	if form.getvalue('servers') is not None:
		servers = form.getlist('servers')
		server_port = form.getlist('server_port')
		max_fails = form.getlist('max_fails')
		fail_timeout = form.getlist('fail_timeout')
		i = 0
		for server in servers:
			try:
				max_fails_val = f'max_fails={max_fails[i]}'
			except Exception:
				max_fails_val = 'max_fails=1'

			try:
				fail_timeout_val = f'fail_timeout={fail_timeout[i]}'
			except Exception:
				fail_timeout_val = 'fail_timeout=1'

			servers_split += f"    server {server}:{server_port[i]} {max_fails_val} {fail_timeout_val}s; \n"
			i += 1
	config_add += f'{servers_split} }}\n'

if form.getvalue('generateconfig') is None and serv is not None:
	slave_output = ''
	try:
		server_name = sql.get_hostname_by_server_ip(serv)
	except Exception:
		server_name = serv

	try:
		roxywi_common.check_is_server_in_group(serv)
		if config_add:
			sub_folder = 'conf.d' if 'upstream' in config_name else 'sites-enabled'

			service_configs_dir = get_config_var.get_config_var('configs', 'nginx_save_configs_dir')
			cfg = f'{service_configs_dir}{serv}-{config_name}.conf'
			nginx_dir = comon.return_nice_path(sql.get_setting('nginx_dir'))

			config_file_name = f'{nginx_dir}{sub_folder}/{config_name}.conf'

			try:
				with open(cfg, "w") as conf:
					conf.write(config_add)
			except IOError:
				print("error: Cannot save a new config")

			roxywi_common.logging(serv, "add_nginx.py add new %s" % config_name)

			output = config_mod.master_slave_upload_and_restart(serv, cfg, just_save="save", nginx=1, config_file_name=config_file_name)

			if output:
				print(output)
			else:
				print(config_name)

	except Exception:
		pass
else:
	print(config_add)
