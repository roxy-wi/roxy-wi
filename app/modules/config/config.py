import os
import re

from flask import render_template, request

import modules.db.sql as sql
import modules.server.ssh as mod_ssh
import modules.server.server as server_mod
import modules.common.common as common
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.service.common as service_common

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def get_config(server_ip, cfg, **kwargs):
	config_path = ''

	if kwargs.get("keepalived") or kwargs.get("service") == 'keepalived':
		config_path = sql.get_setting('keepalived_config_path')
	elif (
		kwargs.get("nginx") or kwargs.get("service") == 'nginx'
		or kwargs.get("apache") or kwargs.get("service") == 'apache'
	):
		config_path = common.checkAjaxInput(kwargs.get('config_file_name'))
		config_path = config_path.replace('92', '/')
	elif kwargs.get("waf") or kwargs.get("service") == 'waf':
		if kwargs.get("waf") == 'haproxy':
			config_path = f'{sql.get_setting("haproxy_dir")}/waf/rules/{kwargs.get("waf_rule_file")}'
		elif kwargs.get("waf") == 'nginx':
			config_path = f'{sql.get_setting("nginx_dir")}/waf/rules/{kwargs.get("waf_rule_file")}'
	else:
		config_path = sql.get_setting('haproxy_config_path')

	if not common.check_is_conf(config_path):
		raise Exception('error: nice try 2')

	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.get_sftp(config_path, cfg)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: cannot get config: {e}', roxywi=1)
		raise Exception(f'error: cannot get config: {e}')


def upload(server_ip, path, file):
	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.put_sftp(file, path)
	except Exception as e:
		error = str(e.args)
		roxywi_common.logging('Roxy-WI server', f'error: Cannot upload {file} to {path} to server: {server_ip}: {error}', roxywi=1)
		print(f'error: Cannot upload {file} to {path} to server: {server_ip}: {error}')
		raise Exception(error)


def upload_and_restart(server_ip: str, cfg: str, just_save: str, service: str, **kwargs):
	file_format = 'conf'
	config_path = kwargs.get('config_file_name')
	service_name = ''
	container_name = ''
	reload_or_restart_command = ''
	config_date = get_date.return_date('config')
	server_id = sql.select_server_id_by_ip(server_ip=server_ip)

	if config_path and config_path != 'undefined':
		config_path = kwargs.get('config_file_name').replace('92', '/')

	if service == 'haproxy':
		config_path = sql.get_setting('haproxy_config_path')
		file_format = 'cfg'

	if service == 'keepalived':
		config_path = sql.get_setting('keepalived_config_path')
		file_format = 'cfg'

	if '..' in config_path:
		raise Exception('error: nice try')

	tmp_file = f"{sql.get_setting('tmp_config_path')}/{config_date}.{file_format}"
	is_dockerized = sql.select_service_setting(server_id, service, 'dockerized')

	if is_dockerized == '1':
		service_cont_name = f'{service}_container_name'
		container_name = sql.get_setting(service_cont_name)
		reload_command = f" && sudo docker kill -s HUP {container_name}"
		restart_command = f" && sudo docker restart {container_name}"
	else:
		service_name = service
		if service == 'haproxy':
			haproxy_enterprise = sql.select_service_setting(server_id, 'haproxy', 'haproxy_enterprise')
			if haproxy_enterprise == '1':
				service_name = "hapee-2.0-lb"
		if service == 'apache':
			service_name = service_common.get_correct_apache_service_name(0, server_id)

		reload_command = f" && sudo systemctl reload {service_name}"
		restart_command = f" && sudo systemctl restart {service_name}"

	if just_save in ('save', 'test'):
		action = just_save
	elif just_save == 'reload':
		action = 'reload'
		reload_or_restart_command = reload_command
	else:
		try:
			service_common.is_not_allowed_to_restart(server_id, service)
		except Exception as e:
			return f'error: Cannot check is this service allowed to be restarted: {e}'

		action = 'restart'
		reload_or_restart_command = restart_command

	if kwargs.get('login'):
		login = kwargs.get('login')
	else:
		login = 1

	try:
		os.system(f"dos2unix -q {cfg}")
	except OSError:
		raise Exception('error: there is no dos2unix')

	if service == "keepalived":
		move_config = f"sudo mv -f {tmp_file} {config_path}"
		if action == "save":
			commands = [move_config]
		else:
			commands = [move_config + reload_or_restart_command]
	elif service == "nginx":
		if is_dockerized == '1':
			check_config = f"sudo docker exec -it exec {container_name} nginx -t "
		else:
			check_config = "sudo nginx -t "
		check_and_move = f"sudo mv -f {tmp_file} {config_path} && {check_config}"
		if action == "test":
			commands = [f"{check_config} && sudo rm -f {tmp_file}"]
		elif action == "save":
			commands = [check_and_move]
		else:
			commands = [check_and_move + reload_or_restart_command]
		if sql.return_firewall(server_ip):
			commands[0] += open_port_firewalld(cfg, server_ip=server_ip, service='nginx')
	elif service == "apache":
		if is_dockerized == '1':
			check_config = f"sudo docker exec -it exec {container_name} sudo apachectl configtest "
		else:
			check_config = "sudo apachectl configtest "
		check_and_move = f"sudo mv -f {tmp_file} {config_path} && {check_config}"
		if action == "test":
			commands = [f"{check_config} && sudo rm -f {tmp_file}"]
		elif action == "save":
			commands = [check_and_move]
		else:
			commands = [check_and_move + reload_or_restart_command]
		# if sql.return_firewall(server_ip):
		# 	commands[0] += open_port_firewalld(cfg, server_ip=server_ip, service='apache')
	elif service == 'waf':
		check_and_move = f"sudo mv -f {tmp_file} {config_path}"
		if action == "save":
			commands = [check_and_move]
		else:
			commands = [check_and_move + reload_or_restart_command]
	else:
		if is_dockerized == '1':
			check_config = f"sudo docker exec -it {container_name} haproxy -c -f {tmp_file}"
		else:
			check_config = f"sudo {service_name} -c -f {tmp_file}"
		move_config = f" && sudo mv -f {tmp_file} {config_path}"

		if action == "test":
			commands = [f"{check_config} && sudo rm -f {tmp_file}"]
		elif action == "save":
			commands = [check_config + move_config]
		else:
			commands = [check_config + move_config + reload_or_restart_command]
		if sql.return_firewall(server_ip):
			commands[0] += open_port_firewalld(cfg, server_ip=server_ip)

	try:
		upload(server_ip, tmp_file, cfg)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot upload config: {e}', roxywi=1)
		raise Exception(f'error: Cannot upload config: {e}')

	try:
		if action != 'test':
			roxywi_common.logging(server_ip, 'A new config file has been uploaded', login=login, keep_history=1, service=service)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

	# If master then save version of config in a new way
	if not kwargs.get('slave') and service != 'waf':
		from pathlib import Path

		diff = ''
		try:
			old_cfg = kwargs.get('oldcfg')
			path = Path(old_cfg)
		except Exception:
			old_cfg = ''
			path = Path(old_cfg)

		if not path.is_file():
			old_cfg = f'{tmp_file}.old'
			try:
				get_config(server_ip, old_cfg, service=service, config_file_name=config_path)
			except Exception:
				roxywi_common.logging('Roxy-WI server', 'Cannot download config for diff', roxywi=1)
		try:
			diff = diff_config(old_cfg, cfg, return_diff=1)
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

		try:
			user_id = roxywi_common.get_user_id(login=kwargs.get('login'))
			sql.insert_config_version(server_id, user_id, service, cfg, config_path, diff)
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

	try:
		error = server_mod.ssh_command(server_ip, commands)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(f'{e}')

	try:
		if action == 'reload' or action == 'restart':
			roxywi_common.logging(server_ip, f'Service has been {action}ed', login=login, keep_history=1, service=service)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

	if error.strip() != 'haproxy' and error.strip() != 'nginx':
		return error.strip()


def master_slave_upload_and_restart(server_ip, cfg, just_save, service, **kwargs):
	slave_output = ''
	masters = sql.is_master(server_ip)
	config_file_name = kwargs.get('config_file_name')
	oldcfg = kwargs.get('oldcfg')
	waf = kwargs.get('waf')

	try:
		server_name = sql.get_hostname_by_server_ip(server_ip)
	except Exception:
		server_name = server_ip

	if kwargs.get('login'):
		login = kwargs.get('login')
	else:
		login = ''

	for master in masters:
		if master[0] is not None:
			try:
				slv_output = upload_and_restart(
					master[0], cfg, just_save, service, waf=waf, config_file_name=config_file_name, slave=1
				)
				slave_output += f'<br>slave_server:\n{slv_output}'
			except Exception as e:
				return f'error: {e}'
	try:
		output = upload_and_restart(
			server_ip, cfg, just_save, service, waf=waf, config_file_name=config_file_name, oldcfg=oldcfg, login=login
		)
	except Exception as e:
		return f'error: {e}'

	output = server_name + ':\n' + output
	output = output + slave_output

	return output


def open_port_firewalld(cfg, server_ip, **kwargs):
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Cannot read exported config file</div>')
		return

	firewalld_commands = ' &&'
	ports = ''

	for line in conf:
		if kwargs.get('service') == 'nginx':
			if "listen " in line and '#' not in line:
				try:
					listen = ' '.join(line.split())
					listen = listen.split(" ")[1]
					listen = listen.split(";")[0]
					try:
						listen = int(listen)
						ports += str(listen) + ' '
						firewalld_commands += f' sudo firewall-cmd --zone=public --add-port={listen}/tcp --permanent -q &&'
					except Exception:
						pass
				except Exception:
					pass
		else:
			if "bind" in line:
				try:
					bind = line.split(":")
					bind[1] = bind[1].strip(' ')
					bind = bind[1].split("ssl")
					bind = bind[0].strip(' \t\n\r')
					try:
						bind = int(bind)
						firewalld_commands += f' sudo firewall-cmd --zone=public --add-port={bind}/tcp --permanent -q &&'
						ports += str(bind) + ' '
					except Exception:
						pass
				except Exception:
					pass

	firewalld_commands += 'sudo firewall-cmd --reload -q'
	roxywi_common.logging(server_ip, f' Next ports have been opened: {ports}')
	return firewalld_commands


def diff_config(oldcfg, cfg, **kwargs):
	log_path = get_config_var.get_config_var('main', 'log_path')
	user_group = roxywi_common.get_user_group()
	diff = ""
	date = get_date.return_date('date_in_log')
	log_date = get_date.return_date('logs')
	cmd = "/bin/diff -ub %s %s" % (oldcfg, cfg)

	try:
		user_uuid = request.cookies.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid)
	except Exception:
		login = ''

	output, stderr = server_mod.subprocess_execute(cmd)

	if kwargs.get('return_diff'):
		for line in output:
			diff += line + "\n"
		return diff
	else:
		for line in output:
			diff += f"{date} user: {login}, group: {user_group} {line}\n"

	log_file = f"{log_path}/config_edit-{log_date}"
	try:
		with open(log_file, 'a') as log:
			log.write(diff)
	except IOError:
		print(f'<center><div class="alert alert-danger">Can\'t read write change to log. {stderr}</div></center>')
		pass


def show_finding_in_config(stdout: str, **kwargs) -> str:
	grep = ''
	out = '<div class="line">--</div>'

	if kwargs.get('grep'):
		grep = kwargs.get('grep')
		grep = re.sub(r'[?|$|!|^|*|\]|\[|,| |]', r'', grep)

	for line in stdout:
		if kwargs.get('grep'):
			line = line.replace(grep, f'<span style="color: red; font-weight: bold;">{grep}</span>')
		line_class = "line" if '--' in line else "line3"
		out += f'<div class="{line_class}">{line}</div>'

	out += '<div class="line">--</div>'

	return out


def show_compare_config(server_ip: str, service: str) -> str:
	lang = roxywi_common.get_user_lang_for_flask()
	config_dir = get_config_var.get_config_var('configs', f'{service}_save_configs_dir')

	if service in ('nginx', 'apache', 'keepalived'):
		return_files = roxywi_common.get_files(config_dir, 'conf', server_ip=server_ip)
	elif service == 'haproxy':
		return_files = roxywi_common.get_files(config_dir, 'cfg', server_ip=server_ip)
	else:
		return 'error: Wrong service'

	return render_template('ajax/show_compare_configs.html', serv=server_ip, return_files=return_files, lang=lang)


def compare_config(service: str, left: str, right: str) -> str:
	lang = roxywi_common.get_user_lang_for_flask()

	if service in ('haproxy', 'nginx', 'apache', 'keepalived'):
		configs_dir = get_config_var.get_config_var('configs', f'{service}_save_configs_dir')
	else:
		return 'error: Wrong service'

	cmd = f'diff -pub {configs_dir}{left} {configs_dir}{right}'
	output, stderr = server_mod.subprocess_execute(cmd)

	return render_template('ajax/compare.html', stdout=output, lang=lang)


def show_config(server_ip: str, service: str, config_file_name: str, configver: str) -> str:
	user_uuid = request.cookies.get('uuid')
	group_id = int(request.cookies.get('group'))
	role_id = sql.get_user_role_by_uuid(user_uuid, group_id)

	try:
		config_file_name = config_file_name.replace('/', '92')
	except Exception:
		config_file_name = ''

	if service in ('nginx', 'apache', 'keepalived'):
		configs_dir = get_config_var.get_config_var('configs', f'{service}_save_configs_dir')
		cfg = '.conf'
	else:
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = '.cfg'

	if '..' in configs_dir:
		raise Exception('error: nice try')

	if configver is None:
		cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}{cfg}"
		try:
			get_config(server_ip, cfg, service=service, config_file_name=config_file_name)
		except Exception as e:
			raise Exception(e)
	else:
		cfg = configs_dir + configver

	try:
		with open(cfg, 'r') as file:
			conf = file.readlines()
	except Exception as e:
		raise Exception(f'error: Cannot read config file: {e}')

	if configver is None:
		os.remove(cfg)

	is_serv_protected = sql.is_serv_protected(server_ip)
	server_id = sql.select_server_id_by_ip(server_ip)
	hostname = sql.get_hostname_by_server_ip(server_ip)
	is_restart = sql.select_service_setting(server_id, service, 'restart')
	lang = roxywi_common.get_user_lang_for_flask()

	return render_template(
		'ajax/config_show.html', conf=conf, serv=server_ip, configver=configver, role=role_id, service=service,
		config_file_name=config_file_name, is_serv_protected=is_serv_protected, is_restart=is_restart, lang=lang,
		hostname=hostname
	)


def show_config_files(server_ip: str, service: str, config_file_name: str) -> str:
	service_config_dir = sql.get_setting(f'{service}_dir')
	return_files = server_mod.get_remote_files(server_ip, service_config_dir, 'conf')

	if 'error: ' in return_files:
		raise Exception(return_files)

	try:
		config_file_name = config_file_name.replace('92', '/')
	except Exception:
		config_file_name = ''

	return_files += ' ' + sql.get_setting(f'{service}_config_path')
	lang = roxywi_common.get_user_lang_for_flask()

	return render_template(
		'ajax/show_configs_files.html', serv=server_ip, service=service, return_files=return_files, lang=lang,
		config_file_name=config_file_name, path_dir=service_config_dir
	)


def list_of_versions(server_ip: str, service: str, configver: str, for_delver: int) -> str:
	if service not in ('haproxy', 'nginx', 'keepalived', 'apache'):
		raise Exception('error: wrong service')

	users = sql.select_users()
	service_desc = sql.select_service(service)
	configs = sql.select_config_version(server_ip, service_desc.slug)
	lang = roxywi_common.get_user_lang_for_flask()
	action = f'/app/config/versions/{service_desc.slug}/{server_ip}'
	configs_dir = get_config_var.get_config_var('configs', f'{service_desc.service}_save_configs_dir')

	if service == 'haproxy':
		files = roxywi_common.get_files(configs_dir, 'cfg', server_ip)
	else:
		files = roxywi_common.get_files(configs_dir, 'conf', server_ip)

	return render_template(
		'ajax/show_list_version.html', server_ip=server_ip, service=service, action=action, return_files=files,
		configver=configver, for_delver=for_delver, configs=configs, users=users, lang=lang
	)


def return_cfg(service: str, server_ip: str, config_file_name: str) -> str:
	if service == 'haproxy':
		file_format = 'cfg'
	else:
		file_format = 'conf'

	if service in ('haproxy', 'nginx', 'apache', 'keepalived'):
		configs_dir = get_config_var.get_config_var('configs', f'{service}_save_configs_dir')
	else:
		raise Exception('error: Wrong service')

	if service in ('nginx', 'apache'):
		config_file_name = config_file_name.replace('92', '/')
		conf_file_name_short = config_file_name.split('/')[-1]
		cfg = f"{configs_dir}{server_ip}-{conf_file_name_short}-{get_date.return_date('config')}.{file_format}"
	else:
		cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}.{file_format}"

	try:
		os.system(f"/bin/rm -f {configs_dir}*.old")
	except Exception:
		pass

	return cfg
