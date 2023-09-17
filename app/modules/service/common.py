import requests
from flask import render_template, request

import modules.db.sql as sql
import modules.server.ssh as mod_ssh
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools
import modules.config.section as section_mod

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config = roxy_wi_tools.GetConfigVar()


def check_haproxy_version(server_ip):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	ver = ""
	cmd = f"echo 'show info' |nc {server_ip} {hap_sock_p} |grep Version |awk '{{print $2}}'"
	output, stderr = server_mod.subprocess_execute(cmd)
	for line in output:
		ver = line

	return ver


def is_restarted(server_ip: str, action: str) -> None:
	user_uuid = request.cookies.get('uuid')
	group_id = request.cookies.get('group')
	group_id = int(group_id)
	user_role = sql.get_user_role_by_uuid(user_uuid, group_id)

	if sql.is_serv_protected(server_ip) and int(user_role) > 2:
		print(f'error: This server is protected. You cannot {action} it')
		return


def is_not_allowed_to_restart(server_id: int, service: str) -> None:
	if service != 'waf':
		is_restart = sql.select_service_setting(server_id, service, 'restart')
	else:
		is_restart = 0

	if int(is_restart) == 1:
		raise Exception('warning: This service is not allowed to be restarted')


def get_exp_version(server_ip: str, service_name: str) -> str:
	server_ip = common.is_ip_or_dns(server_ip)
	if service_name == 'haproxy':
		commands = ["/opt/prometheus/exporters/haproxy_exporter --version 2>&1 |head -1|awk '{print $3}'"]
	elif service_name == 'nginx':
		commands = ["/opt/prometheus/exporters/nginx_exporter 2>&1 |head -1 |awk -F\"=\" '{print $2}'|awk '{print $1}'"]
	elif service_name == 'node':
		commands = ["node_exporter --version 2>&1 |head -1|awk '{print $3}'"]
	elif service_name == 'apache':
		commands = ["/opt/prometheus/exporters/apache_exporter --version 2>&1 |head -1|awk '{print $3}'"]
	elif service_name == 'keepalived':
		commands = ["keepalived_exporter --version 2>&1 |head -1|awk '{print $2}'"]

	ver = server_mod.ssh_command(server_ip, commands)

	if ver != '':
		return ver
	else:
		return 'no'


def get_correct_apache_service_name(server_ip=None, server_id=None) -> str:
	if server_id is None:
		server_id = sql.select_server_id_by_ip(server_ip)

	try:
		os_info = sql.select_os_info(server_id)
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


def check_haproxy_config(server_ip):
	server_id = sql.select_server_id_by_ip(server_ip=server_ip)
	is_dockerized = sql.select_service_setting(server_id, 'haproxy', 'dockerized')
	config_path = sql.get_setting('haproxy_config_path')

	if is_dockerized == '1':
		container_name = sql.get_setting('haproxy_container_name')
		commands = [f"sudo docker exec -it {container_name} haproxy -q -c -f {config_path}"]
	else:
		commands = [f"haproxy  -q -c -f {config_path}"]

	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			for command in commands:
				stdin, stdout, stderr = ssh.run_command(command, timeout=5)
				if not stderr.read():
					return True
				else:
					return False
	except Exception as e:
		print(f'error: {e}')


def check_nginx_config(server_ip):
	commands = [f"nginx -q -t -p {sql.get_setting('nginx_dir')}"]

	with mod_ssh.ssh_connect(server_ip) as ssh:
		for command in commands:
			stdin, stdout, stderr = ssh.run_command(command)
			if not stderr.read():
				return True
			else:
				return False


def overview_backends(server_ip: str, service: str) -> None:
	import modules.config.config as config_mod

	lang = roxywi_common.get_user_lang_for_flask()
	format_file = 'cfg'

	if service == 'haproxy':
		configs_dir = get_config.get_config_var('configs', 'haproxy_save_configs_dir')
		format_file = 'cfg'
	elif service == 'keepalived':
		configs_dir = get_config.get_config_var('configs', 'keepalived_save_configs_dir')
		format_file = 'conf'

	if service != 'nginx' and service != 'apache':
		try:
			sections = section_mod.get_sections(configs_dir + roxywi_common.get_files(configs_dir, format_file)[0],
												service=service)
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)

			try:
				cfg = f"{configs_dir}{server_ip}-{get_date.return_date('config')}.{format_file}"
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f' Cannot generate a cfg path {e}', roxywi=1)
			try:
				if service == 'keepalived':
					config_mod.get_config(server_ip, cfg, keepalived=1)
				else:
					config_mod.get_config(server_ip, cfg)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f' Cannot download a config {e}', roxywi=1)
			try:
				sections = section_mod.get_sections(cfg, service=service)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f' Cannot get sections from config file {e}', roxywi=1)
				sections = 'Cannot get backends'
	else:
		sections = section_mod.get_remote_sections(server_ip, service)

	return render_template('ajax/haproxyservers_backends.html', backends=sections, serv=server_ip, service=service, lang=lang)


def get_overview_last_edit(server_ip: str, service: str) -> str:
	if service == 'nginx':
		config_path = sql.get_setting('nginx_config_path')
	elif service == 'keepalived':
		config_path = sql.get_setting('keepalived_config_path')
	else:
		config_path = sql.get_setting('haproxy_config_path')
	commands = ["ls -l %s |awk '{ print $6\" \"$7\" \"$8}'" % config_path]
	try:
		return server_mod.ssh_command(server_ip, commands)
	except Exception as e:
		return f'error: Cannot get last date {e} for server {server_ip}'


def get_stat_page(server_ip: str, service: str) -> str:
	if service in ('nginx', 'apache'):
		stats_user = sql.get_setting(f'{service}_stats_user')
		stats_pass = sql.get_setting(f'{service}_stats_password')
		stats_port = sql.get_setting(f'{service}_stats_port')
		stats_page = sql.get_setting(f'{service}_stats_page')
	else:
		stats_user = sql.get_setting('stats_user')
		stats_pass = sql.get_setting('stats_password')
		stats_port = sql.get_setting('stats_port')
		stats_page = sql.get_setting('stats_page')
	try:
		response = requests.get(f'http://{server_ip}:{stats_port}/{stats_page}', auth=(stats_user, stats_pass))
	except requests.exceptions.ConnectTimeout:
		return 'error: Oops. Connection timeout occurred!'
	except requests.exceptions.ReadTimeout:
		return 'error: Oops. Read timeout occurred'
	except requests.exceptions.HTTPError as errh:
		return f'error: Http Error: {errh}'
	except requests.exceptions.ConnectionError as errc:
		return f'error: Error Connecting: {errc}'
	except requests.exceptions.Timeout as errt:
		return f'error: Timeout Error: {errt}'
	except requests.exceptions.RequestException as err:
		return f'error: OOps: Something Else {err}'

	data = response.content
	if service == 'nginx':
		lang = roxywi_common.get_user_lang_for_flask()
		servers_with_status = list()
		h = ()
		out1 = []
		for k in data.decode('utf-8').split():
			out1.append(k)
		h = (out1,)
		servers_with_status.append(h)

		return render_template('ajax/nginx_stats.html', out=servers_with_status, lang=lang)
	else:
		return data.decode('utf-8')


def show_service_version(server_ip: str, service: str) -> None:
	if service == 'haproxy':
		return check_haproxy_version(server_ip)

	server_id = sql.select_server_id_by_ip(server_ip)
	service_name = service
	is_dockerized = sql.select_service_setting(server_id, service, 'dockerized')

	if service == 'apache':
		service_name = get_correct_apache_service_name(None, server_id)

	if is_dockerized == '1':
		container_name = sql.get_setting(f'{service}_container_name')
		if service == 'apache':
			cmd = [f'docker exec -it {container_name}  /usr/local/apache2/bin/httpd -v 2>&1|head -1|awk -F":" \'{{print $2}}\'']
		else:
			cmd = [f'docker exec -it {container_name}  /usr/sbin/{service_name} -v 2>&1|head -1|awk -F":" \'{{print $2}}\'']
	else:
		cmd = [f'sudo /usr/sbin/{service_name} -v|head -1|awk -F":" \'{{print $2}}\'']
	return server_mod.ssh_command(server_ip, cmd)
