import os
import json

from flask import render_template
import ansible_runner

import modules.db.sql as sql
import modules.service.common as service_common
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
from modules.server.ssh import return_ssh_keys_path


def show_installation_output(error: str, output: str, service: str, rc=0):
	if error and "WARNING" not in error:
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
		raise Exception('error: ' + error)
	else:
		if rc != 0:
			for line in output.read():
				if any(s in line for s in ("Traceback", "FAILED", "error", "ERROR", "UNREACHABLE")):
					try:
						correct_out = line.split('=>')
						correct_out = json.loads(correct_out[1])
					except Exception:
						raise Exception(f'error: {output} for {service}')
					else:
						raise Exception(f'error: {correct_out["msg"]} for {service}')
	return True


def show_success_installation(service):
	lang = roxywi_common.get_user_lang_for_flask()
	return render_template('include/show_success_installation.html', service=service, lang=lang)


def waf_install(server_ip: str):
	script = "waf.sh"
	proxy = sql.get_setting('proxy')
	haproxy_dir = sql.get_setting('haproxy_dir')
	ver = service_common.check_haproxy_version(server_ip)
	service = ' WAF'
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)
	full_path = '/var/www/haproxy-wi/app'

	os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	commands = [
		f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} HAPROXY_PATH={haproxy_dir} VERSION='{ver}' "
		f"SSH_PORT={ssh_settings['port']} HOST={server_ip} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' "
		f"KEY={ssh_settings['key']}"
	]

	return_out = server_mod.subprocess_execute_with_rc(commands[0])

	try:
		show_installation_output(return_out['error'], return_out['output'], service, rc=return_out['rc'])
	except Exception as e:
		raise Exception(e)

	try:
		sql.insert_waf_metrics_enable(server_ip, "0")
		sql.insert_waf_rules(server_ip)
	except Exception as e:
		return str(e)

	os.remove(f'{full_path}/{script}')

	return show_success_installation(service)


def waf_nginx_install(server_ip: str):
	script = "waf_nginx.sh"
	proxy = sql.get_setting('proxy')
	nginx_dir = sql.get_setting('nginx_dir')
	service = ' WAF'
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(server_ip)
	full_path = '/var/www/haproxy-wi/app'

	os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	commands = [
		f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} NGINX_PATH={nginx_dir} SSH_PORT={ssh_settings['port']} "
		f"HOST={server_ip} USER={ssh_settings['user']} PASS='{ssh_settings['password']}' KEY={ssh_settings['key']}"
	]

	return_out = server_mod.subprocess_execute_with_rc(commands[0])

	try:
		show_installation_output(return_out['error'], return_out['output'], service, rc=return_out['rc'])
	except Exception as e:
		raise Exception(e)

	try:
		sql.insert_nginx_waf_rules(server_ip)
		sql.insert_waf_nginx_server(server_ip)
	except Exception as e:
		return str(e)

	os.remove(f'{full_path}/{script}')

	return show_success_installation(service)


def geoip_installation(serv, geoip_update, service):
	proxy = sql.get_setting('proxy')
	maxmind_key = sql.get_setting('maxmind_key')
	proxy_serv = ''
	ssh_settings = return_ssh_keys_path(serv)
	full_path = '/var/www/haproxy-wi/app'

	if service in ('haproxy', 'nginx'):
		service_dir = common.return_nice_path(sql.get_setting(f'{service}_dir'))
		script = f'install_{service}_geoip.sh'
	else:
		raise Exception('warning: select a server and service first')

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	try:
		os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")
	except Exception as e:
		raise Exception(f'error: {e}')

	commands = [
		f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv} SSH_PORT={ssh_settings['port']} UPDATE={geoip_update} "
		f"maxmind_key={maxmind_key} service_dir={service_dir} HOST={serv} USER={ssh_settings['user']} "
		f"PASS={ssh_settings['password']} KEY={ssh_settings['key']}"
	]

	return_out = server_mod.subprocess_execute_with_rc(commands[0])

	try:
		show_installation_output(return_out['error'], return_out['output'], 'GeoLite2 Database', rc=return_out['rc'])
	except Exception as e:
		raise Exception(e)

	os.remove(f'{full_path}/{script}')

	return show_success_installation('GeoLite2 Database')


def grafana_install():
	script = "install_grafana.sh"
	proxy = sql.get_setting('proxy')
	proxy_serv = ''
	host = os.environ.get('HTTP_HOST', '')
	full_path = '/var/www/haproxy-wi/app'

	try:
		os.system(f"cp {full_path}/scripts/{script} {full_path}/{script}")
	except Exception as e:
		raise Exception(f'error: {e}')

	if proxy is not None and proxy != '' and proxy != 'None':
		proxy_serv = proxy

	cmd = f"chmod +x {full_path}/{script} && {full_path}/{script} PROXY={proxy_serv}"
	output, error = server_mod.subprocess_execute(cmd)

	if error:
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
	else:
		for line in output:
			if any(s in line for s in ("Traceback", "FAILED")):
				try:
					return line
				except Exception:
					return output

	os.remove(f'{full_path}/{script}')

	return f'success: Grafana and Prometheus servers were installed. You can find Grafana on http://{host}:3000<br>'


def generate_kp_inv(json_data: json, install_service) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []
	cluster_id = int(json_data['cluster_id'])
	haproxy = json_data['services']['haproxy']['enabled']
	nginx = json_data['services']['nginx']['enabled']
	# apache = json_data['apache']
	apache = 0
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	syn_flood_protect = str(json_data['syn_flood'])
	routers = {}
	vips = sql.select_cluster_vips(cluster_id)

	for vip in vips:
		router_id = str(vip.router_id)
		routers[router_id] = {vip.vip: {}}
		routers[router_id][vip.vip].setdefault('return_master', vip.return_master)
		routers[router_id][vip.vip].setdefault('vip', vip.vip)
		slaves = sql.select_cluster_slaves_for_inv(router_id)
		for slave in slaves:
			routers[router_id][vip.vip].setdefault('master', slave.master)
			routers[router_id][vip.vip].setdefault('eth', slave.eth)

	for k, v in json_data['servers'].items():
		server_ip = v['ip']
		inv['server']['hosts'][server_ip] = {
			"HAPROXY": haproxy,
			"NGINX": nginx,
			"APACHE": apache,
			"RESTART": 1,
			"SYN_FLOOD": syn_flood_protect,
			"keepalived_path_logs": keepalived_path_logs,
			"routers": routers
		}
		server_ips.append(server_ip)

	return inv, server_ips


def generate_haproxy_inv(json_data: json, install_service: str) -> object:
	inv = {"server": {"hosts": {}}}
	slaves = []
	server_ips = []
	master_ip = 0
	hap_sock_p = str(sql.get_setting('haproxy_sock_port'))
	stats_port = str(sql.get_setting('stats_port'))
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('stats_user')
	stats_password = sql.get_setting('stats_password')
	haproxy_dir = sql.get_setting('haproxy_dir')
	container_name = sql.get_setting('haproxy_container_name')
	haproxy_ver = ''
	is_docker = json_data['services']['haproxy']['docker']

	if haproxy_ver == '':
		haproxy_ver = '2.8.1-1'

	for k, v in json_data['servers'].items():
		if not v['master']:
			slaves.append(v['ip'])
		else:
			master_ip = v['ip']

	for k, v in json_data['servers'].items():
		server_ip = v['ip']
		is_master = v['master']

		if 'version' in v:
			haproxy_ver = v['version']

		inv['server']['hosts'][server_ip] = {
			"SOCK_PORT": hap_sock_p,
			"STAT_PORT": stats_port,
			"STAT_FILE": server_state_file,
			"STATS_USER": stats_user,
			"CONT_NAME": container_name,
			"HAP_DIR": haproxy_dir,
			"STATS_PASS": stats_password,
			"HAPVER": haproxy_ver,
			"SYN_FLOOD": '0',
			"M_OR_S": is_master,
			"MASTER": master_ip,
			"slaves": slaves,
			"DOCKER": is_docker
		}
		server_ips.append(server_ip)

	return inv, server_ips


def generate_service_inv(json_data: json, install_service: str) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []
	stats_user = sql.get_setting(f'{install_service}_stats_user')
	stats_password = sql.get_setting(f'{install_service}_stats_password')
	stats_port = str(sql.get_setting(f'{install_service}_stats_port'))
	stats_page = sql.get_setting(f'{install_service}_stats_page')
	config_path = sql.get_setting(f'{install_service}_config_path')
	service_dir = sql.get_setting(f'{install_service}_dir')
	container_name = sql.get_setting(f'{install_service}_container_name')
	is_docker = json_data['services'][install_service]['docker']

	if install_service == 'nginx':
		os.system('ansible-galaxy collection install community.general')
		os.system('ansible-galaxy install nginxinc.nginx,0.23.2 --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/')

	for k, v in json_data['servers'].items():
		server_ip = v['ip']
		if install_service == 'apache':
			correct_service_name = service_common.get_correct_apache_service_name(server_ip=server_ip, server_id=None)
			if service_dir == '/etc/httpd' and correct_service_name == 'apache2':
				service_dir = '/etc/apache2'
			elif service_dir == '/etc/apache2' and correct_service_name == 'httpd':
				service_dir = '/etc/httpd'

		inv['server']['hosts'][server_ip] = {
			"STAT_PORT": stats_port,
			"DOCKER": is_docker,
			"STATS_USER": stats_user,
			"CONT_NAME": container_name,
			"STATS_PASS": stats_password,
			"service_dir": service_dir,
			"SYN_FLOOD": "0",
			"CONFIG_PATH": config_path,
			"STAT_PAGE": stats_page,
			"service": install_service,
		}
		server_ips.append(server_ip)

	return inv, server_ips


def run_ansible(inv: object, server_ips: str, ansible_role: str) -> object:
	inventory_path = '/var/www/haproxy-wi/app/scripts/ansible/inventory'
	inventory = f'{inventory_path}/{ansible_role}.json'
	proxy = sql.get_setting('proxy')
	proxy_serv = ''
	tags = ''
	for server_ip in server_ips:
		ssh_settings = return_ssh_keys_path(server_ip)
		inv['server']['hosts'][server_ip]['ansible_ssh_private_key_file'] = ssh_settings['key']
		inv['server']['hosts'][server_ip]['ansible_password'] = ssh_settings['password']
		inv['server']['hosts'][server_ip]['ansible_user'] = ssh_settings['user']
		inv['server']['hosts'][server_ip]['ansible_port'] = ssh_settings['port']
		inv['server']['hosts'][server_ip]['ansible_become'] = True

		if proxy is not None and proxy != '' and proxy != 'None':
			proxy_serv = proxy

		inv['server']['hosts'][server_ip]['PROXY'] = proxy_serv

		if 'DOCKER' in inv['server']['hosts'][server_ip]:
			if inv['server']['hosts'][server_ip]['DOCKER']:
				tags = 'docker'
			else:
				tags = 'system'

	envvars = {
		'ANSIBLE_DISPLAY_OK_HOSTS': 'no',
		'ANSIBLE_SHOW_CUSTOM_STATS': 'no',
		'ANSIBLE_DISPLAY_SKIPPED_HOSTS': "no",
		'ANSIBLE_DEPRECATION_WARNINGS': "no",
		'ANSIBLE_HOST_KEY_CHECKING': "no",
		'ACTION_WARNINGS': "no",
		'LOCALHOST_WARNING': "no",
		'COMMAND_WARNINGS': "no",
		'AWX_DISPLAY': False,
	}

	kwargs = {
		'private_data_dir': '/var/www/haproxy-wi/app/scripts/ansible/',
		'inventory': inventory,
		'envvars': envvars,
		'playbook': f'/var/www/haproxy-wi/app/scripts/ansible/roles/{ansible_role}.yml',
		'tags': tags
	}

	if os.path.isfile(inventory):
		os.remove(inventory)

	if not os.path.isdir(inventory_path):
		os.makedirs(inventory_path)

	try:
		with open(inventory, 'a') as invent:
			invent.write(str(inv))
	except Exception as e:
		raise Exception(f'error: Cannot save inventory file: {e}')

	result = ansible_runner.run(**kwargs)
	stats = result.stats

	os.remove(inventory)
	return stats


def service_actions_after_install(server_ips: str, service: str, json_data) -> None:
	is_docker = None
	update_functions = {
		'haproxy': sql.update_haproxy,
		'nginx': sql.update_nginx,
		'apache': sql.update_apache,
		'keepalived': sql.update_keepalived,
	}

	for server_ip in server_ips:
		server_id = sql.select_server_id_by_ip(server_ip)
		try:
			update_functions[service](server_ip)
		except Exception as e:
			raise Exception(f'error: Cannot activate {service} on server {server_ip}: {e}')

		if service != 'keepalived':
			is_docker = json_data['services'][service]['docker']

		if is_docker == '1' and service != 'keepalived':
			sql.insert_or_update_service_setting(server_id, service, 'dockerized', '1')
			sql.insert_or_update_service_setting(server_id, service, 'restart', '1')


def install_service(service: str, json_data: str) -> object:
	try:
		json_data = json.loads(json_data)
	except Exception as e:
		raise Exception(f'error: Cannot parse JSON: {e}')

	generate_functions = {
		'haproxy': generate_haproxy_inv,
		'nginx': generate_service_inv,
		'apache': generate_service_inv,
		'keepalived': generate_kp_inv,
	}

	try:
		inv, server_ips = generate_functions[service](json_data, service)
		service_actions_after_install(server_ips, service, json_data)
		return run_ansible(inv, server_ips, service), 201
	except Exception as e:
		raise Exception(f'error: Cannot install {service}: {e}')
