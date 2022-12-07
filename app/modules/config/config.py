import os
import re
import http.cookies

import modules.db.sql as sql
import modules.server.ssh as mod_ssh
import modules.server.server as mod_server
import modules.common.common as common
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.service.common as service_common

form = common.form
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
		config_path = kwargs.get('config_file_name')
	elif kwargs.get("waf") or kwargs.get("service") == 'waf':
		if kwargs.get("waf") == 'haproxy':
			config_path = f'{sql.get_setting("haproxy_dir")}/waf/rules/{kwargs.get("waf_rule_file")}'
		elif kwargs.get("waf") == 'nginx':
			config_path = f'{sql.get_setting("nginx_dir")}/waf/rules/{kwargs.get("waf_rule_file")}'
	else:
		config_path = sql.get_setting('haproxy_config_path')

	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.get_sftp(config_path, cfg)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: cannot get config: {e}', roxywi=1)


def upload(server_ip, path, file, **kwargs):
	full_path = path + file
	if kwargs.get('dir') == "fullpath":
		full_path = path

	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.put_sftp(file, full_path)
	except Exception as e:
		error = str(e.args)
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
		print(f' Cannot upload {file} to {full_path} to server: {server_ip} error: {error}')
		return error


def upload_and_restart(server_ip: str, cfg: str, **kwargs):
	error = ''
	service_name = ''
	container_name = ''
	reload_or_restart_command = ''
	file_format = 'conf'
	config_path = kwargs.get('config_file_name')
	config_date = get_date.return_date('config')
	server_id = sql.select_server_id_by_ip(server_ip=server_ip)

	if kwargs.get("nginx"):
		service = 'nginx'
	elif kwargs.get("apache"):
		service = 'apache'
	elif kwargs.get("keepalived"):
		service = 'keepalived'
		config_path = sql.get_setting('keepalived_config_path')
		file_format = 'cfg'
	elif kwargs.get('waf'):
		service = 'waf'
	else:
		service = 'haproxy'
		config_path = sql.get_setting('haproxy_config_path')
		file_format = 'cfg'

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
			service_name = service_common.get_correct_apache_service_name(server_ip, 0)

		reload_command = f" && sudo systemctl reload {service_name}"
		restart_command = f" && sudo systemctl restart {service_name}"

	if kwargs.get("just_save") == 'save':
		action = 'save'
	elif kwargs.get("just_save") == 'test':
		action = 'test'
	elif kwargs.get("just_save") == 'reload':
		action = 'reload'
		reload_or_restart_command = reload_command
	else:
		service_common.is_not_allowed_to_restart(server_id, service)
		action = 'restart'
		reload_or_restart_command = restart_command

	if kwargs.get('login'):
		login = kwargs.get('login')
	else:
		login = 1

	try:
		os.system(f"dos2unix {cfg}")
	except OSError:
		return 'error: there is no dos2unix'

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
		upload(server_ip, tmp_file, cfg, dir='fullpath')
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
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		return error

	try:
		error = mod_server.ssh_command(server_ip, commands)
		try:
			if action == 'reload' or action == 'restart':
				roxywi_common.logging(server_ip, f'Service has been {action}ed', login=login, keep_history=1, service=service)
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		return e

	if error.strip() != 'haproxy' and error.strip() != 'nginx':
		return error.strip()


def master_slave_upload_and_restart(server_ip, cfg, just_save, **kwargs):
	slave_output = ''

	try:
		server_name = sql.get_hostname_by_server_ip(server_ip)
	except Exception:
		server_name = server_ip

	if kwargs.get('login'):
		login = kwargs.get('login')
	else:
		login = ''

	is_master = [masters[0] for masters in sql.is_master(server_ip)]
	for master in is_master:
		slv_output = upload_and_restart(
			master, cfg, just_save=just_save, nginx=kwargs.get('nginx'), waf=kwargs.get('waf'),
			apache=kwargs.get('apache'), config_file_name=kwargs.get('config_file_name'), slave=1
		)
		slave_output += f'<br>slave_server:\n{slv_output}'

	output = upload_and_restart(
		server_ip, cfg, just_save=just_save, nginx=kwargs.get('nginx'), waf=kwargs.get('waf'),
		apache=kwargs.get('apache'), config_file_name=kwargs.get('config_file_name'),
		oldcfg=kwargs.get('oldcfg'), login=login
	)

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
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	log_path = get_config_var.get_config_var('main', 'log_path')
	user_group = roxywi_common.get_user_group()
	diff = ""
	date = get_date.return_date('date_in_log')
	log_date = get_date.return_date('logs')
	cmd = "/bin/diff -ub %s %s" % (oldcfg, cfg)

	try:
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except Exception:
		login = ''

	output, stderr = mod_server.subprocess_execute(cmd)

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


def get_userlists(config):
	return_config = ''
	with open(config, 'r') as f:
		for line in f:
			if line.startswith('userlist'):
				line = line.strip()
				return_config += line + ','

	return return_config


def get_ssl_cert(server_ip: str) -> None:
	cert_id = common.checkAjaxInput(form.getvalue('getcert'))

	cert_path = sql.get_setting('cert_path')
	commands = [f"openssl x509 -in {cert_path}/{cert_id} -text"]
	try:
		mod_server.ssh_command(server_ip, commands, ip="1")
	except Exception as e:
		print(f'error: Cannot connect to the server {e.args[0]}')


def get_ssl_certs(server_ip: str) -> None:
	cert_path = sql.get_setting('cert_path')
	commands = [f"sudo ls -1t {cert_path} |grep -E 'pem|crt|key'"]
	try:
		mod_server.ssh_command(server_ip, commands, ip="1")
	except Exception as e:
		print(f'error: Cannot connect to the server: {e.args[0]}')


def del_ssl_cert(server_ip: str) -> None:
	cert_id = form.getvalue('delcert')
	cert_id = common.checkAjaxInput(cert_id)
	cert_path = sql.get_setting('cert_path')
	commands = [f"sudo rm -f {cert_path}/{cert_id}"]
	try:
		mod_server.ssh_command(server_ip, commands, ip="1")
	except Exception as e:
		print(f'error: Cannot delete the certificate {e.args[0]}')


def upload_ssl_cert(server_ip: str) -> None:
	cert_local_dir = f"{os.path.dirname(os.getcwd())}/{sql.get_setting('ssl_local_path')}"
	cert_path = sql.get_setting('cert_path')
	name = ''

	if not os.path.exists(cert_local_dir):
		os.makedirs(cert_local_dir)

	if form.getvalue('ssl_name') is None:
		print('error: Please enter a desired name')
	else:
		name = f"{common.checkAjaxInput(form.getvalue('ssl_name'))}.pem"

	try:
		with open(name, "w") as ssl_cert:
			ssl_cert.write(form.getvalue('ssl_cert'))
	except IOError as e:
		print(f'error: Cannot save the SSL key file: {e.args[0]}')
		return 

	masters = sql.is_master(server_ip)
	for master in masters:
		if master[0] is not None:
			error = upload(master[0], cert_path, name)
			if not error:
				print(f'success: the SSL file has been uploaded to {master[0]} into: {cert_path}/{name} <br/>')
	try:
		error = upload(server_ip, cert_path, name)
		if not error:
			print(f'success: the SSL file has been uploaded to {server_ip} into: {cert_path}/{name}')
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)
	try:
		os.rename(name, cert_local_dir)
	except OSError as e:
		roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)

	roxywi_common.logging(server_ip, f"add.py#ssl uploaded a new SSL cert {name}", roxywi=1, login=1)
