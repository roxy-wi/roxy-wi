from typing import Union

import requests
from flask import render_template

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.db.service as service_sql
import app.modules.server.server as server_mod
import app.modules.roxywi.common as roxywi_common
import app.modules.config.section as section_mod
import app.modules.config.common as config_common
from app.modules.roxywi.exception import RoxywiResourceNotFound


def get_correct_service_name(service: str, server_id: int) -> str:
	"""
	:param service: The name of the service.
	:param server_id: The ID of the server.
	:return: The correct service name based on the provided parameters.

	This method takes a service name and server ID as input and returns the correct service name based on the given parameters. If the service name is 'haproxy', it checks if haproxy_enter
	*prise is set to '1' in the database for the given server ID. If true, it returns "hapee-2.0-lb". If the service name is 'apache', it calls the get_correct_apache_service_name() method
	* with parameters 0 and the server ID to get the correct apache service name. If none of the conditions match, it will return the original service name.
	"""
	if service == 'apache':
		return get_correct_apache_service_name(0, server_id)

	return service


def is_protected(server_ip: str, action: str) -> None:
	"""
	Check if the server is protected and the user has the required role.

	:param server_ip: The IP address of the server.
	:param action: The action to be performed on the server.
	:return: None
	:raises: Exception if the server is protected and the user role is not high enough.
	"""
	claims = roxywi_common.get_jwt_token_claims()
	user_role = user_sql.get_user_role_in_group(claims['user_id'], claims['group'])

	if server_sql.is_serv_protected(server_ip) and int(user_role) > 2:
		raise Exception(f'error: This server is protected. You cannot {action} it')


def is_not_allowed_to_restart(server_id: int, service: str, action: str) -> int:
	"""
	:param server_id: The ID of the server.
	:param service: The name of the service.
	:param action: The action to perform on the service.
	:return: An integer indicating whether the restart is allowed or not.

	This method checks if the given service is not allowed to be restarted based on the provided server ID, service name, and action. It returns `0` if the restart is not allowed, otherwise
	* it returns `1`.
	"""
	is_restart = 0
	if service != 'waf' and action == 'restart':
		try:
			is_restart = int(service_sql.select_service_setting(server_id, service, 'restart'))
		except Exception as e:
			roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot get restart settings for service {service}')

	return is_restart


def get_exp_version(server_ip: str, service_name: str) -> str:
	if service_name == 'haproxy':
		command = "/opt/prometheus/exporters/haproxy_exporter --version 2>&1 |head -1|awk '{print $3}'"
	elif service_name == 'nginx':
		command = "/opt/prometheus/exporters/nginx_exporter --version 2>&1 |head -1 |awk -F\"version\" '{print $2}'|awk '{print $1}'"
	elif service_name == 'node':
		command = "node_exporter --version 2>&1 |head -1|awk '{print $3}'"
	elif service_name == 'apache':
		command = "/opt/prometheus/exporters/apache_exporter --version 2>&1 |head -1|awk '{print $3}'"
	elif service_name == 'keepalived':
		command = "keepalived_exporter --version 2>&1 |head -1|awk '{print $2}'"

	ver = server_mod.ssh_command(server_ip, command)

	if ver != '':
		return ver
	else:
		return 'no'


def get_correct_apache_service_name(server_ip=None, server_id=None) -> str:
	if server_id is None:
		server_id = server_sql.get_server_by_ip(server_ip).server_id

	try:
		os_info = server_sql.select_os_info(server_id)
	except RoxywiResourceNotFound:
		raise RoxywiResourceNotFound('Cannot find system information')
	except Exception as e:
		raise Exception(f'error: cannot get server info: {e}')

	if "CentOS" in os_info or "Redhat" in os_info:
		return 'httpd'
	else:
		return 'apache2'


def server_status(stdout):
	proc_count = ""

	for line in stdout:
		if "Ncat: " not in line:
			for k in line:
				try:
					proc_count = k.split(":")[1]
				except Exception:
					proc_count = 1
		else:
			proc_count = 0
	return proc_count


def check_service_config(server_ip: str, server_id: int, service: str) -> None:
	"""
	:param server_ip: The IP address of the server to check the service configuration for.
	:param server_id: The unique identifier of the server.
	:param service: The name of the service to check the configuration for.
	:return: True if the service configuration is valid, False otherwise.

	This method checks the configuration of a given service on a server. It first retrieves the value of the "dockerized" setting for the service and the container name from the database
	*. Then, it constructs the command to check the configuration based on the service type and dockerization status.

	The command depends on the service type and can be one of the following:
	- For haproxy:
	    - If not dockerized: `haproxy -c -f {config_path}`
	    - If dockerized: `sudo docker exec -it {container_name} haproxy -c -f {config_path}`
	- For nginx:
	    - If not dockerized: `sudo nginx -q -t -p {config_path}`
	    - If dockerized: `sudo docker exec -it {container_name} nginx -t`
	- For apache:
	    - If not dockerized: `sudo apachectl -t`
	    - If dockerized: `sudo docker exec -it {container_name} apachectl -t`
	- For keepalived:
	    - If not dockerized: `keepalived -t -f {config_path}`
	    - If dockerized: empty string ` ` (no command needed)

	The method then tries to execute the generated command on the server using the server_mod.ssh_command method. If any exception occurs during the process, it is re-ra
	*ised with an appropriate error message.

	"""
	is_dockerized = service_sql.select_service_setting(server_id, service, 'dockerized')
	container_name = sql.get_setting(f'{service}_container_name')
	command_for_docker = f'sudo docker exec -it {container_name}'
	config_path = ''

	if service in ('haproxy', 'keepalived'):
		config_path = sql.get_setting(f'{service}_config_path')

	command = {
		'haproxy': {'0': f'haproxy -c -f {config_path} ', '1': f'{command_for_docker} haproxy -c -f {config_path} '},
		'nginx': {'0': 'sudo nginx -q -t ', '1': f'{command_for_docker} nginx -t '},
		'apache': {'0': 'sudo apachectl -t ', '1': f'{command_for_docker} apachectl -t '},
		'keepalived': {'0': f'keepalived -t -f {config_path} ', '1': ' '}
	}

	try:
		check_config = command[service][is_dockerized]
	except Exception as e:
		raise Exception(f'error: Cannot generate command: {e}')

	try:
		server_mod.ssh_command(server_ip, check_config)
	except Exception as e:
		raise Exception(e)


def overview_backends(server_ip: str, service: str) -> Union[str, dict]:
	import app.modules.config.config as config_mod

	if service not in ('nginx', 'apache'):
		format_file = config_common.get_file_format(service)
		config_dir = config_common.get_config_dir(service)

		try:
			config_file = roxywi_common.get_files(config_dir, format_file, server_ip)
			if len(config_file) == 0:
				raise 'there is no config file'
			sections = section_mod.get_sections(config_dir + config_file[0], service=service)
		except Exception as e:
			cfg = config_common.generate_config_path(service, server_ip)
			roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

			try:
				config_mod.get_config(server_ip, cfg, service=service)
			except Exception as e:
				raise Exception('Cannot get config file: ' + str(e))
			try:
				sections = section_mod.get_sections(cfg, service=service)
			except Exception as e:
				raise Exception(f'Cannot get sections: {e}')
	else:
		sections = {}
		try:
			sections_not_formated = section_mod.get_remote_sections(server_ip, service)
		except Exception as e:
			raise Exception(f'Cannot format backends: {e}')

		for section in sections_not_formated.split('\r'):
			if section == '\n':
				continue
			back_path = section.split(":")[0]
			back_name = section.split(":")[1]
			back_name = back_name.strip().replace('\n', '').replace('\r', '').replace(';', '')
			back_path = back_path.strip().replace('/', '92').replace(':', '')
			sections[back_path] = back_name

	return sections


def get_overview_last_edit(server_ip: str, service: str) -> str:
	config_path = sql.get_setting(f'{service}_config_path')
	command = "ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % config_path
	try:
		return server_mod.ssh_command(server_ip, command)
	except Exception as e:
		return f'error: Cannot get last date {e} for server {server_ip}'


def get_stat_page(server_ip: str, service: str, group_id: int) -> str:
	stats_user = sql.get_setting(f'{service}_stats_user', group_id=group_id)
	stats_pass = sql.get_setting(f'{service}_stats_password', group_id=group_id)
	stats_pass = stats_pass.replace("'", "")
	stats_port = sql.get_setting(f'{service}_stats_port', group_id=group_id)
	stats_page = sql.get_setting(f'{service}_stats_page', group_id=group_id)

	try:
		response = requests.get(f'http://{server_ip}:{stats_port}/{stats_page}', auth=(stats_user, stats_pass), timeout=5)
	except requests.exceptions.ConnectTimeout:
		return 'error: Connection timeout occurred!'
	except requests.exceptions.ReadTimeout:
		return 'error: Read timeout occurred'
	except requests.exceptions.HTTPError as errh:
		return f'error: Http Error: {errh}'
	except requests.exceptions.ConnectionError as errc:
		if "Max retries exceeded" in str(errc):
			raise Exception(f"error: Max retries exceeded")
		return f'error: Error Connecting: {errc}'
	except requests.exceptions.Timeout as errt:
		return f'error: Timeout Error: {errt}'
	except requests.exceptions.RequestException as err:
		return f'error: Something Else {err}'

	data = response.content
	if service == 'nginx':
		lang = roxywi_common.get_user_lang_for_flask()
		servers_with_status = list()
		out1 = []
		for k in data.decode('utf-8').split():
			out1.append(k)
		h = (out1,)
		servers_with_status.append(h)

		return render_template('ajax/nginx_stats.html', out=servers_with_status, lang=lang)
	else:
		return data.decode('utf-8')
