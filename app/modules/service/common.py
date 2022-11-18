import os
import http.cookies

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod


def check_haproxy_version(server_ip):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	ver = ""
	cmd = f"echo 'show info' |nc {server_ip} {hap_sock_p} |grep Version |awk '{{print $2}}'"
	output, stderr = server_mod.subprocess_execute(cmd)
	for line in output:
		ver = line

	return ver


def is_restarted(server_ip: str, action: str) -> None:
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	user_role = sql.get_user_role_by_uuid(user_uuid.value)

	if sql.is_serv_protected(server_ip) and int(user_role) > 2:
		print(f'error: This server is protected. You cannot {action} it')
		return


def is_not_allowed_to_restart(server_id: int, service: str) -> None:
	is_restart = sql.select_service_setting(server_id, service, 'restart')

	if int(is_restart) == 1:
		print('warning: this service is not allowed to be restarted')
		return


def get_exp_version(server_ip: str, service_name: str) -> str:
	server_ip = common.is_ip_or_dns(server_ip)
	if service_name == 'haproxy_exporter':
		commands = ["/opt/prometheus/exporters/haproxy_exporter --version 2>&1 |head -1|awk '{print $3}'"]
	elif service_name == 'nginx_exporter':
		commands = ["/opt/prometheus/exporters/nginx_exporter 2>&1 |head -1 |awk -F\"=\" '{print $2}'|awk '{print $1}'"]
	elif service_name == 'node_exporter':
		commands = ["node_exporter --version 2>&1 |head -1|awk '{print $3}'"]
	elif service_name == 'apache_exporter':
		commands = ["/opt/prometheus/exporters/apache_exporter --version 2>&1 |head -1|awk '{print $3}'"]

	ver = server_mod.ssh_command(server_ip, commands)

	if ver != '':
		return ver
	else:
		return 'no'


def get_correct_apache_service_name(server_ip=None, server_id=0) -> str:
	if server_id is None:
		server_id = sql.select_server_id_by_ip(server_ip)

	try:
		os_info = sql.select_os_info(server_id)
	except Exception:
		return 'error: cannot get server info'

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

	with server_mod.ssh_connect(server_ip) as ssh:
		for command in commands:
			stdin, stdout, stderr = ssh.run_command(command)
			if not stderr.read():
				return True
			else:
				return False


def check_nginx_config(server_ip):
	commands = [f"nginx -q -t -p {sql.get_setting('nginx_dir')}"]

	with server_mod.ssh_connect(server_ip) as ssh:
		for command in commands:
			stdin, stdout, stderr = ssh.run_command(command)
			if not stderr.read():
				return True
			else:
				return False
