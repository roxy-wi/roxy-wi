import json

from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.waf as waf_sql
import app.modules.db.server as server_sql
import app.modules.db.backup as backup_sql
import app.modules.db.checker as checker_sql
import app.modules.db.service as service_sql
import app.modules.db.history as history_sql
import app.modules.db.portscanner as ps_sql
import app.modules.server.ssh as mod_ssh
import app.modules.common.common as common
import app.modules.roxywi.auth as roxywi_auth
import app.modules.roxywi.common as roxywi_common


def ssh_command(server_ip: str, commands: str, **kwargs):
	if server_ip == '':
		raise Exception('error: IP cannot be empty')
	if kwargs.get('timeout'):
		timeout = kwargs.get('timeout')
	else:
		timeout = 2
	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			if isinstance(commands, list):
				command = commands[0]
			else:
				command = commands
			try:
				stdin, stdout, stderr = ssh.run_command(command, timeout=timeout)
				stdin.close()
			except Exception as e:
				roxywi_common.handle_exceptions(e, server_ip, 'Something wrong with SSH connection. Probably sudo with password', roxywi=1)

			if stderr:
				for line in stderr.readlines():
					if line:
						roxywi_common.handle_exceptions(line, server_ip, line, roxywi=1)

			if stdout.channel.recv_exit_status() and kwargs.get('rc'):
				roxywi_common.handle_exceptions(stdout.read().decode('utf-8'), server_ip, f'Cannot perform SSH command: {command} ', roxywi=1)

			if kwargs.get('raw'):
				return stdout.readlines()
			elif kwargs.get("show_log") == "1":
				import app.modules.roxywi.logs as roxywi_logs
				return roxywi_logs.show_log(stdout, grep=kwargs.get("grep"))
			else:
				return stdout.read().decode(encoding='UTF-8')
	except Exception as e:
		roxywi_common.handle_exceptions(e, server_ip, '', roxywi=1)


def subprocess_execute(cmd):
	import subprocess
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	return output, stderr


def subprocess_execute_stream(cmd):
	import subprocess
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, universal_newlines=True)
	for line in iter(p.stdout.readline, ''):
		yield line


def subprocess_execute_with_rc(cmd):
	import subprocess

	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	rc = p.returncode

	return_out = {'output': output, 'error': stderr, 'rc': rc}

	return return_out


def is_file_exists(server_ip: str, file: str) -> bool:
	cmd = f'[ -f {file} ] && echo yes || echo no'

	out = ssh_command(server_ip, cmd)
	return True if 'yes' in out else False


def is_service_active(server_ip: str, service_name: str) -> bool:
	cmd = f'systemctl is-active {service_name}'

	out = ssh_command(server_ip, cmd)
	out = out.strip()
	return True if 'active' == out else False


def get_remote_files(server_ip: str, config_dir: str, file_format: str):
	config_dir = common.return_nice_path(config_dir)
	if file_format == 'conf':
		command = f'sudo ls {config_dir}*/*.{file_format}'
	else:
		command = f'sudo ls {config_dir}|grep {file_format}$'
	config_files = ssh_command(server_ip, command)

	return config_files


def get_system_info(server_ip: str) -> None:
	server_ip = common.is_ip_or_dns(server_ip)
	if server_ip == '':
		raise Exception('IP cannot be empty')

	server_id = server_sql.select_server_id_by_ip(server_ip)
	command = "sudo lshw -quiet -json"
	command1 = 'sudo hostnamectl |grep "Operating System"|awk -F":" \'{print $2}\''

	try:
		sys_info_returned = ssh_command(server_ip, command, timeout=5)
	except Exception as e:
		raise Exception(f'Cannot connect to the server to get system info: {server_ip}: {e}')

	if 'not found' in sys_info_returned:
		raise Exception(f'You should install lshw on the server {server_ip}. Update System info after installation.')

	try:
		os_info = ssh_command(server_ip, command1)
	except Exception as e:
		raise Exception(f'Cannot connect to the server to get OS info: {server_ip} : {e}')

	os_info = os_info.strip()
	try:
		system_info = json.loads(sys_info_returned)
		_ = system_info['id']
	except Exception:
		sys_info_returned = json.loads(sys_info_returned)
		try:
			sys_info_returned = sys_info_returned[0]
		except Exception as e:
			raise Exception(f'error: Cannot parse output {e}')
		system_info = sys_info_returned

	sys_info = {'hostname': system_info['id'], 'family': ''}
	cpu = {'cpu_model': '', 'cpu_core': 0, 'cpu_thread': 0, 'hz': 0}
	network = {}
	ram = {'slots': 0, 'size': 0}
	disks = {}

	try:
		sys_info['family'] = system_info['configuration']['family']
	except Exception:
		pass

	for i in system_info['children']:
		if i['class'] == 'network':
			try:
				ip = i['configuration']['ip']
			except Exception:
				ip = ''
			network[i['logicalname']] = {
				'description': i['description'],
				'mac': i['serial'],
				'ip': ip,
				'up': i['configuration']['link']
			}
		for k, j in i.items():
			if isinstance(j, list):
				for b in j:
					try:
						if b['class'] == 'processor':
							cpu['cpu_model'] = b['product']
							cpu['cpu_core'] += 1
							cpu['hz'] = round(int(b['capacity']) / 1000000)
							try:
								cpu['cpu_thread'] += int(b['configuration']['threads'])
							except Exception:
								cpu['cpu_thread'] = 1
					except Exception:
						pass

					try:
						if b['id'] == 'memory':
							ram['size'] = round(b['size'] / 1073741824)
							ram['slots'] = len(b['children'])
					except Exception:
						pass

					try:
						if b['class'] == 'storage':
							for p, pval in b.items():
								if isinstance(pval, list):
									for disks_info in pval:
										for volume_info in disks_info['children']:
											if isinstance(volume_info['logicalname'], list):
												volume_name = volume_info['logicalname'][0]
												mount_point = volume_info['logicalname'][1]
												size = round(volume_info['capacity'] / 1073741824)
												size = str(size) + 'Gb'
												fs = volume_info['configuration']['mount.fstype']
												state = volume_info['configuration']['state']
												disks[volume_name] = {
													'mount_point': mount_point,
													'size': size,
													'fs': fs,
													'state': state
												}
					except Exception:
						pass

					try:
						if b['class'] == 'bridge':
							if 'children' in b:
								for s in b['children']:
									if s['class'] == 'network':
										if 'children' in s:
											for net in s['children']:
												network[net['logicalname']] = {
													'description': net['description'],
													'mac': net['serial']
												}
									if s['class'] == 'storage':
										for p, pval in s.items():
											if isinstance(pval, list):
												for disks_info in pval:
													if 'children' in disks_info:
														for volume_info in disks_info['children']:
															if isinstance(volume_info['logicalname'], dict):
																volume_name = volume_info['logicalname'][0]
																mount_point = volume_info['logicalname'][1]
																size = round(volume_info['size'] / 1073741824)
																size = str(size) + 'Gb'
																fs = volume_info['configuration']['mount.fstype']
																state = volume_info['configuration']['state']
																disks[volume_name] = {
																	'mount_point': mount_point,
																	'size': size,
																	'fs': fs,
																	'state': state
																}
									for z, n in s.items():
										if isinstance(n, list):
											for y in n:
												if y['class'] == 'network':
													try:
														for q in y['children']:
															try:
																ip = q['configuration']['ip']
															except Exception:
																ip = ''
															network[q['logicalname']] = {
																'description': q['description'],
																'mac': q['serial'],
																'ip': ip,
																'up': q['configuration']['link']}
													except Exception:
														try:
															network[y['logicalname']] = {
																'description': y['description'],
																'mac': y['serial'],
																'ip': y['configuration']['ip'],
																'up': y['configuration']['link']}
														except Exception:
															pass
												if y['class'] == 'disk':
													try:
														for q in y['children']:
															try:
																if isinstance(q['logicalname'], list):
																	volume_name = q['logicalname'][0]
																	mount_point = q['logicalname'][1]
																	size = round(q['capacity'] / 1073741824)
																	size = str(size) + 'Gb'
																	fs = q['configuration']['mount.fstype']
																	state = q['configuration']['state']
																	disks[volume_name] = {
																		'mount_point': mount_point,
																		'size': size,
																		'fs': fs,
																		'state': state
																	}
															except Exception as e:
																print(e)
													except Exception:
														pass
												if y['class'] == 'storage' or y['class'] == 'generic':
													try:
														for q in y['children']:
															for o in q['children']:
																try:
																	volume_name = o['logicalname']
																	mount_point = ''
																	size = round(o['size'] / 1073741824)
																	size = str(size) + 'Gb'
																	fs = ''
																	state = ''
																	disks[volume_name] = {
																		'mount_point': mount_point,
																		'size': size,
																		'fs': fs,
																		'state': state
																	}
																except Exception:
																	pass
																for w in o['children']:
																	try:
																		if isinstance(w['logicalname'], list):
																			volume_name = w['logicalname'][0]
																			mount_point = w['logicalname'][1]
																			try:
																				size = round(w['size'] / 1073741824)
																				size = str(size) + 'Gb'
																			except Exception:
																				size = ''
																			fs = w['configuration']['mount.fstype']
																			state = w['configuration']['state']
																			disks[volume_name] = {
																				'mount_point': mount_point,
																				'size': size,
																				'fs': fs,
																				'state': state
																			}
																	except Exception:
																		pass
													except Exception:
														pass
													try:
														for q, qval in y.items():
															if isinstance(qval, list):
																for o in qval:
																	for w in o['children']:
																		if isinstance(w['logicalname'], list):
																			volume_name = w['logicalname'][0]
																			mount_point = w['logicalname'][1]
																			size = round(w['size'] / 1073741824)
																			size = str(size) + 'Gb'
																			fs = w['configuration']['mount.fstype']
																			state = w['configuration']['state']
																			disks[volume_name] = {
																				'mount_point': mount_point,
																				'size': size,
																				'fs': fs,
																				'state': state
																			}
													except Exception:
														pass
					except Exception:
						pass

	try:
		server_sql.insert_system_info(server_id, os_info, sys_info, cpu, ram, network, disks)
	except Exception as e:
		raise e


def show_system_info(server_ip: str, server_id: int) -> str:
	if not server_sql.is_system_info(server_id):
		try:
			get_system_info(server_ip)
		except Exception as e:
			return f'Cannot get system info: {e}'
		try:
			system_info = server_sql.select_one_system_info(server_id)
		except Exception as e:
			return f'Cannot update server info: {e}'
	else:
		system_info = server_sql.select_one_system_info(server_id)
	return render_template('ajax/show_system_info.html', system_info=system_info, server_ip=server_ip, server_id=server_id)


def update_system_info(server_ip: str, server_id: int) -> str:
	server_sql.delete_system_info(server_id)

	try:
		get_system_info(server_ip)
	except Exception as e:
		return f'{e}'
	try:
		system_info = server_sql.select_one_system_info(server_id)
		return render_template('ajax/show_system_info.html', system_info=system_info, server_ip=server_ip, server_id=server_id)
	except Exception as e:
		return f'error: Cannot update server info: {e}'


def show_firewalld_rules(server_ip) -> str:
	input_chain2 = []
	cmd = "sudo iptables -L INPUT -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"
	cmd1 = "sudo iptables -L IN_public_allow -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"
	cmd2 = "sudo iptables -L OUTPUT -n --line-numbers|sed 's/  */ /g'|grep -v -E 'Chain|target'"

	try:
		input_chain = ssh_command(server_ip, cmd, raw=1)
	except Exception as e:
		roxywi_common.logging(server_ip, f'error: Cannot get Iptables Input chain: {e}')
		return 'error: Cannot get Iptables Input chain'

	try:
		in_public_allow = ssh_command(server_ip, cmd1, raw=1)
	except Exception as e:
		roxywi_common.logging(server_ip, f'error: Cannot get Iptables IN_public_allow chain: {e}')
		return 'error: Cannot get Iptables IN_public_allow chain'

	try:
		output_chain = ssh_command(server_ip, cmd2, raw=1)
	except Exception as e:
		roxywi_common.logging(server_ip, f'error: Cannot get Iptables OUTPUT chain: {e}')
		return 'error: Cannot get Iptables OUTPUT chain'

	for each_line in input_chain:
		input_chain2.append(each_line.strip('\n'))

	lang = roxywi_common.get_user_lang_for_flask()
	return render_template('ajax/firewall_rules.html', input_chain=input_chain2, IN_public_allow=in_public_allow, output_chain=output_chain, lang=lang)


def create_server(**kwargs) -> int:
	last_id = server_sql.add_server(**kwargs)
	return last_id


def update_server_after_creating(hostname: str, ip: str) -> None:
	try:
		checker_sql.insert_new_checker_setting_for_server(ip)
	except Exception as e:
		raise Exception(f'Cannot insert Checker settings for {hostname}: {e}')
	try:
		nginx_config_path = sql.get_setting('nginx_config_path')
		haproxy_config_path = sql.get_setting('haproxy_config_path')
		haproxy_dir = sql.get_setting('haproxy_dir')
		apache_config_path = sql.get_setting('apache_config_path')
		keepalived_config_path = sql.get_setting('keepalived_config_path')

		if is_file_exists(ip, nginx_config_path):
			service_sql.update_nginx(ip)

		if is_file_exists(ip, haproxy_config_path):
			service_sql.update_haproxy(ip)

		if is_file_exists(ip, keepalived_config_path):
			service_sql.update_keepalived(ip)

		if is_file_exists(ip, apache_config_path):
			service_sql.update_apache(ip)

		if is_file_exists(ip, haproxy_dir + '/waf/bin/modsecurity'):
			waf_sql.insert_waf_metrics_enable(ip, "0")
			waf_sql.insert_waf_rules(ip)

		if is_service_active(ip, 'firewalld'):
			server_sql.update_firewall(ip)

	except Exception as e:
		raise Exception(f'Cannot get scan the server {hostname}: {e}')

	try:
		get_system_info(ip)
	except Exception as e:
		raise Exception(f'Cannot get information from {hostname}: {e}')


def delete_server(server_id: int) -> None:
	server = server_sql.get_server_by_id(server_id)

	if backup_sql.check_exists_backup(server.ip, 'fs'):
		raise 'warning: Delete the backups first'
	if backup_sql.check_exists_backup(server.ip, 's3'):
		raise 'warning: Delete the S3 backups first'
	if server_sql.delete_server(server_id):
		waf_sql.delete_waf_server(server_id)
		ps_sql.delete_port_scanner_settings(server_id)
		waf_sql.delete_waf_rules(server.ip)
		history_sql.delete_action_history(server_id)
		server_sql.delete_system_info(server_id)
		service_sql.delete_service_settings(server_id)
		roxywi_common.logging(server.ip, f'The server {server.hostname} has been deleted', roxywi=1, login=1)


def server_is_up(server_ip: str) -> str:
	cmd = f'if ping -c 1 -W 1 {server_ip} >> /dev/null; then echo up; else echo down; fi'
	server_status, stderr = subprocess_execute(cmd)
	return server_status[0]


def show_server_services(server_id: int) -> str:
	server = server_sql.select_servers(id=server_id)
	lang = roxywi_common.get_user_lang_for_flask()
	return render_template('ajax/show_server_services.html', server=server, lang=lang)


def change_server_services(server_id: int, server_name: str, server_services: dict) -> str:
	services = service_sql.select_services()
	services_status = {}

	for k, v in server_services.items():
		for service in services:
			if service.service_id == int(k):
				services_status[service.service_id] = v

	try:
		if service_sql.update_server_services(server_id, services_status[1], services_status[2], services_status[4], services_status[3]):
			roxywi_common.logging('Roxy-WI server', f'Active services have been updated for {server_name}', roxywi=1, login=1)
			return 'ok'
	except Exception as e:
		return f'error: {e}'


def start_ssh_agent() -> dict:
	"""
	Start SSH agent
	:return: Dict of SSH agent socket and pid
	"""
	agent_settings = {}
	cmd = "ssh-agent -s"
	output, stderr = subprocess_execute(cmd)

	for out in output:
		if 'SSH_AUTH_SOCK=' in out:
			agent_settings.setdefault('socket', out.split('=')[1].split(';')[0])
		if 'SSH_AGENT_PID=' in out:
			agent_settings.setdefault('pid', out.split('=')[1].split(';')[0])
	if 'error' in stderr:
		raise Exception(f'error: Cannot start SSH agent: {stderr}')
	return agent_settings


def add_key_to_agent(ssh_settings: dict, agent_pid: dict) -> None:
	"""
	Add key to SSH agent
	:return: None
	"""
	cmd = f'export SSH_AGENT_PID={agent_pid["pid"]} && export SSH_AUTH_SOCK={agent_pid["socket"]} && '

	if ssh_settings['passphrase']:
		cmd += f"{{ sleep .1; echo {ssh_settings['passphrase']}; }} | script -q /dev/null -c 'ssh-add {ssh_settings['key']}'"
	else:
		cmd += f'ssh-add {ssh_settings["key"]}'
	output, stderr = subprocess_execute(cmd)
	if 'error' in stderr:
		raise Exception(f'error: Cannot add the key {ssh_settings["key"]} to SSH agent: {stderr}')


def stop_ssh_agent(agent_pid: dict) -> None:
	"""
	Stop SSH agent
	:return: None
	"""

	cmd = f'export SSH_AGENT_PID={agent_pid["pid"]} && ssh-agent -k'
	output, stderr = subprocess_execute(cmd)

	if 'error' in stderr:
		raise Exception(f'error: Cannot stop SSH agent: {stderr}')
