import os
import json
from packaging import version

import ansible
import ansible_runner

import app.modules.db.sql as sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.service.common as service_common
import app.modules.common.common as common
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
from app.modules.server.ssh import return_ssh_keys_path


def show_installation_output(error: str, output: list, service: str, rc=0):
	if error and "WARNING" not in error:
		roxywi_common.logging('Roxy-WI server', error, roxywi=1)
		raise Exception('error: ' + error)
	else:
		if rc != 0:
			for line in output:
				if any(s in line for s in ("Traceback", "FAILED", "error", "ERROR", "UNREACHABLE")):
					try:
						correct_out = line.split('=>')
						correct_out = json.loads(correct_out[1])
					except Exception:
						raise Exception(f'error: {output} for {service}')
					else:
						raise Exception(f'error: {correct_out["msg"]} for {service}')
	return True


def generate_geoip_inv(server_ip: str, installed_service: str, geoip_update: int) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []

	inv['server']['hosts'][server_ip] = {
		'service_dir': common.return_nice_path(sql.get_setting(f'{installed_service}_dir')),
		'maxmind_key': sql.get_setting('maxmind_key'),
		'UPDATE': geoip_update

	}
	server_ips.append(server_ip)

	return inv, server_ips


def generate_grafana_inv() -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []
	inv['server']['hosts']['localhost'] = {}
	server_ips.append('localhost')

	return inv, server_ips


def generate_kp_inv(json_data: json, installed_service) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []
	cluster_id = int(json_data['cluster_id'])
	haproxy = json_data['services']['haproxy']['enabled']
	nginx = json_data['services']['nginx']['enabled']
	apache = json_data['services']['apache']['enabled']
	keepalived_path_logs = sql.get_setting('keepalived_path_logs')
	syn_flood_protect = str(json_data['syn_flood'])
	routers = {}
	vips = ha_sql.select_cluster_vips(cluster_id)

	for vip in vips:
		router_id = str(vip.router_id)
		routers[router_id] = {}
		routers[router_id].setdefault('return_master', vip.return_master)
		routers[router_id].setdefault('vip', vip.vip)
		slaves = ha_sql.select_cluster_slaves_for_inv(router_id)
		for slave in slaves:
			slave_ip = server_sql.select_server_ip_by_id(str(slave.server_id))
			routers[router_id].setdefault(slave_ip, dict())
			routers[router_id][slave_ip].setdefault('master', slave.master)
			routers[router_id][slave_ip].setdefault('eth', slave.eth)

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


def generate_waf_inv(server_ip: str, installed_service: str) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []

	inv['server']['hosts'][server_ip] = {
		'SERVICE_PATH': common.return_nice_path(sql.get_setting(f'{installed_service}_dir'))
	}
	server_ips.append(server_ip)

	return inv, server_ips


def generate_haproxy_inv(json_data: json, installed_service: str) -> object:
	inv = {"server": {"hosts": {}}}
	slaves = []
	server_ips = []
	master_ip = 0
	hap_sock_p = str(sql.get_setting('haproxy_sock_port'))
	stats_port = str(sql.get_setting('haproxy_stats_port'))
	server_state_file = sql.get_setting('server_state_file')
	stats_user = sql.get_setting('haproxy_stats_user')
	stats_password = sql.get_setting('haproxy_stats_password')
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


def generate_service_inv(json_data: json, installed_service: str) -> object:
	inv = {"server": {"hosts": {}}}
	server_ips = []
	stats_user = sql.get_setting(f'{installed_service}_stats_user')
	stats_password = sql.get_setting(f'{installed_service}_stats_password')
	stats_port = str(sql.get_setting(f'{installed_service}_stats_port'))
	stats_page = sql.get_setting(f'{installed_service}_stats_page')
	config_path = sql.get_setting(f'{installed_service}_config_path')
	service_dir = sql.get_setting(f'{installed_service}_dir')
	container_name = sql.get_setting(f'{installed_service}_container_name')
	is_docker = json_data['services'][installed_service]['docker']

	if installed_service == 'nginx' and not os.path.isdir('/var/www/haproxy-wi/app/scripts/ansible/roles/nginxinc.nginx'):
		os.system('ansible-galaxy install nginxinc.nginx,0.23.2 --roles-path /var/www/haproxy-wi/app/scripts/ansible/roles/')

	for k, v in json_data['servers'].items():
		server_ip = v['ip']
		if installed_service == 'apache':
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
			"service": installed_service,
		}
		server_ips.append(server_ip)

	return inv, server_ips


def run_ansible(inv: dict, server_ips: str, ansible_role: str) -> object:
	inventory_path = '/var/www/haproxy-wi/app/scripts/ansible/inventory'
	inventory = f'{inventory_path}/{ansible_role}.json'
	proxy = sql.get_setting('proxy')
	proxy_serv = ''
	tags = ''
	try:
		agent_pid = server_mod.start_ssh_agent()
	except Exception as e:
		raise Exception(f'{e}')

	try:
		_install_ansible_collections()
	except Exception as e:
		raise Exception(f'{e}')

	for server_ip in server_ips:
		ssh_settings = return_ssh_keys_path(server_ip)
		if ssh_settings['enabled']:
			inv['server']['hosts'][server_ip]['ansible_ssh_private_key_file'] = ssh_settings['key']
		inv['server']['hosts'][server_ip]['ansible_password'] = ssh_settings['password']
		inv['server']['hosts'][server_ip]['ansible_user'] = ssh_settings['user']
		inv['server']['hosts'][server_ip]['ansible_port'] = ssh_settings['port']
		inv['server']['hosts'][server_ip]['ansible_become'] = True

		if ssh_settings['enabled']:
			try:
				server_mod.add_key_to_agent(ssh_settings, agent_pid)
			except Exception as e:
				server_mod.stop_ssh_agent(agent_pid)
				raise Exception(f'{e}')

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
		'SSH_AUTH_PID': agent_pid['pid'],
		'SSH_AUTH_SOCK': agent_pid['socket'],
		'ANSIBLE_PYTHON_INTERPRETER': '/usr/bin/python3'
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
		server_mod.stop_ssh_agent(agent_pid)
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot save inventory file', roxywi=1)

	try:
		result = ansible_runner.run(**kwargs)
	except Exception as e:
		server_mod.stop_ssh_agent(agent_pid)
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot run Ansible', roxywi=1)

	try:
		server_mod.stop_ssh_agent(agent_pid)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot stop SSH agent {e}', roxywi=1)

	os.remove(inventory)

	if result.rc != 0:
		raise Exception('Something wrong with installation, check <a href="/app/logs/internal?log_file=roxy-wi.error.log" target="_blank" class="link">Apache logs</a> for details')

	return result.stats


def service_actions_after_install(server_ips: str, service: str, json_data) -> None:
	is_docker = None
	update_functions = {
		'haproxy': service_sql.update_haproxy,
		'nginx': service_sql.update_nginx,
		'apache': service_sql.update_apache,
		'keepalived': service_sql.update_keepalived,
	}

	for server_ip in server_ips:
		server_id = server_sql.select_server_id_by_ip(server_ip)
		try:
			update_functions[service](server_ip)
		except Exception as e:
			roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot activate {service} on server {server_ip}', roxywi=1)

		if service != 'keepalived':
			is_docker = json_data['services'][service]['docker']

		if is_docker == '1' and service != 'keepalived':
			service_sql.insert_or_update_service_setting(server_id, service, 'dockerized', '1')
			service_sql.insert_or_update_service_setting(server_id, service, 'restart', '1')


def install_service(service: str, json_data: str) -> object:
	try:
		json_data = json.loads(json_data)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot parse JSON', roxywi=1)

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
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot install {service}', roxywi=1)


def _install_ansible_collections():
	old_ansible_server = ''
	collections = ('community.general', 'ansible.posix', 'community.docker', 'community.grafana')
	trouble_link = 'Read <a href="https://roxy-wi.org/troubleshooting#ansible_collection" target="_blank" class="link">troubleshooting</a>'
	for collection in collections:
		if not os.path.isdir(f'/usr/share/httpd/.ansible/collections/ansible_collections/{collection.replace(".", "/")}'):
			try:
				if version.parse(ansible.__version__) < version.parse('2.13.9'):
					old_ansible_server = '--server https://old-galaxy.ansible.com/'
				exit_code = os.system(f'ansible-galaxy collection install {collection} {old_ansible_server}')
			except Exception as e:
				roxywi_common.handle_exceptions(e,
												'Roxy-WI server',
												f'Cannot install as collection. {trouble_link}',
												roxywi=1)
			else:
				if exit_code != 0:
					raise Exception(f'error: Ansible collection installation was not successful: {exit_code}. {trouble_link}')
