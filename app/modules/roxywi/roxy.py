import os
import re

import distro

import modules.db.sql as sql
import modules.common.common as common
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common


def is_docker() -> bool:
	path = "/proc/self/cgroup"
	if not os.path.isfile(path):
		return False
	with open(path) as f:
		for line in f:
			if re.match("\d+:[\w=]+:/docker(-[ce]e)?/\w+", line):
				return True
		return False


def update_roxy_wi(service):
	restart_service = ''

	if distro.id() == 'ubuntu':
		try:
			if service == 'roxy-wi-keep_alive':
				service = 'roxy-wi-keep-alive'
		except Exception:
			pass

		if service != 'roxy-wi':
			restart_service = f'&& sudo systemctl restart {service}'

		cmd = f'sudo -S apt-get update && sudo apt-get install {service} {restart_service}'
	else:
		if service != 'roxy-wi':
			restart_service = f'&& sudo systemctl restart {service}'
		cmd = f'sudo -S yum -y install {service} {restart_service}'

	output, stderr = server_mod.subprocess_execute(cmd)
	print(output)
	print(stderr)


def check_ver():
	return sql.get_ver()


def versions():
	try:
		current_ver = check_ver()
		current_ver_without_dots = current_ver.split('.')
		current_ver_without_dots = ''.join(current_ver_without_dots)
		current_ver_without_dots = current_ver_without_dots.replace('\n', '')
		if len(current_ver_without_dots) == 2:
			current_ver_without_dots += '00'
		if len(current_ver_without_dots) == 3:
			current_ver_without_dots += '0'
		current_ver_without_dots = int(current_ver_without_dots)
	except Exception:
		current_ver = "Sorry cannot get current version"
		current_ver_without_dots = 0

	try:
		new_ver = check_new_version('roxy-wi')
		new_ver_without_dots = new_ver.split('.')
		new_ver_without_dots = ''.join(new_ver_without_dots)
		new_ver_without_dots = new_ver_without_dots.replace('\n', '')
		if len(new_ver_without_dots) == 2:
			new_ver_without_dots += '00'
		if len(new_ver_without_dots) == 3:
			new_ver_without_dots += '0'
		new_ver_without_dots = int(new_ver_without_dots)
	except Exception as e:
		new_ver = "Cannot get a new version"
		new_ver_without_dots = 0
		roxywi_common.logging('Roxy-WI server', f' {e}', roxywi=1)

	return current_ver, new_ver, current_ver_without_dots, new_ver_without_dots


def get_services_status():
	services = []
	is_in_docker = is_docker()
	services_name = {
		'roxy-wi-checker': 'Checker is designed for monitoring HAProxy, NGINX, Apache and Keepalived services as well as HAProxy backends and maxconn',
		'roxy-wi-keep_alive': '	The Auto Start service allows to restart the HAProxy, NGINX, Apache and Keepalived services if they are down',
		'roxy-wi-metrics': 'Collects number of connections for HAProxy, NGINX, Apache and HAProxy WAF services',
		'roxy-wi-portscanner': 'Probes and saves a server or host for open ports',
		'roxy-wi-smon': 'SMON stands for <b>S</b>imple <b>MON</b>itoring',
		'roxy-wi-socket': 'Socket is a service for sending alerts and notifications',
		'roxy-wi-prometheus-exporter': 'Prometheus exporter',
		'prometheus': 'Prometheus service',
		'grafana-server': 'Grafana service',
		'fail2ban': 'Fail2ban service',
		'rabbitmq-server': 'Message broker service'
	}
	for s, v in services_name.items():
		if is_in_docker:
			cmd = f"sudo supervisorctl status {s}|awk '{{print $2}}'"
		else:
			cmd = f"systemctl is-active {s}"

		status, stderr = server_mod.subprocess_execute(cmd)

		if s != 'roxy-wi-keep_alive':
			service_name = s.split('_')[0]
			if s == 'grafana-server':
				service_name = 'grafana'
		elif s == 'roxy-wi-keep_alive' and distro.id() == 'ubuntu':
			service_name = 'roxy-wi-keep-alive'
		else:
			service_name = s

		if service_name == 'prometheus':
			cmd = "prometheus --version 2>&1 |grep prometheus|awk '{print $3}'"
		else:
			if distro.id() == 'ubuntu':
				cmd = f"apt list --installed 2>&1 |grep {service_name}|awk '{{print $2}}'|sed 's/-/./'"
			else:
				cmd = f"rpm -q {service_name}|awk -F\"{service_name}\" '{{print $2}}' |awk -F\".noa\" '{{print $1}}' |sed 's/-//1' |sed 's/-/./'"
		service_ver, stderr = server_mod.subprocess_execute(cmd)

		try:
			if service_ver[0] == 'command' or service_ver[0] == 'prometheus:':
				service_ver[0] = ''
		except Exception:
			pass

		try:
			services.append([s, status, v, service_ver[0]])
		except Exception:
			services.append([s, status, v, ''])

	return services


def check_new_version(service):
	import requests
	from requests.adapters import HTTPAdapter
	from requests.packages.urllib3.util.retry import Retry

	current_ver = check_ver()
	proxy = sql.get_setting('proxy')
	res = ''
	user_name = sql.select_user_name()
	retry_strategy = Retry(
		total=3,
		status_forcelist=[429, 500, 502, 503, 504],
		method_whitelist=["HEAD", "GET", "OPTIONS"]
	)
	adapter = HTTPAdapter(max_retries=retry_strategy)
	roxy_wi_get_plan = requests.Session()
	roxy_wi_get_plan.mount("https://", adapter)

	try:
		if proxy is not None and proxy != '' and proxy != 'None':
			proxy_dict = {"https": proxy, "http": proxy}
			response = requests.get(f'https://roxy-wi.org/version/get/{service}', timeout=1, proxies=proxy_dict)
			if service == 'roxy-wi':
				requests.get(f'https://roxy-wi.org/version/send/{current_ver}', timeout=1, proxies=proxy_dict)
				roxy_wi_get_plan = requests.get(f'https://roxy-wi.org/user-name/{user_name}', timeout=1, proxies=proxy_dict)
		else:
			response = requests.get(f'https://roxy-wi.org/version/get/{service}', timeout=1)
			if service == 'roxy-wi':
				requests.get(f'https://roxy-wi.org/version/send/{current_ver}', timeout=1)
				roxy_wi_get_plan = requests.get(f'https://roxy-wi.org/user-name/{user_name}', timeout=1)

		res = response.content.decode(encoding='UTF-8')
		if service == 'roxy-wi':
			try:
				status = roxy_wi_get_plan.content.decode(encoding='UTF-8')
				status = status.split(' ')
				sql.update_user_status(status[0], status[1].strip(), status[2].strip())
			except Exception:
				pass
	except requests.exceptions.RequestException as e:
		roxywi_common.logging('Roxy-WI server', f' {e}', roxywi=1)

	return res


def action_service(action: str, service: str) -> None:
	if action not in ('start', 'stop', 'restart'):
		print('error: wrong action')
		return

	is_in_docker = is_docker()
	if action == 'stop':
		cmd = f"sudo systemctl disable {service} --now"
	elif action in ("start", "restart"):
		cmd = f"sudo systemctl {action} {service} --now"
		if not sql.select_user_status():
			print(
				'warning: The service is disabled because you are not subscribed. Read <a href="https://roxy-wi.org/pricing" '
				'title="Roxy-WI pricing" target="_blank">here</a> about subscriptions')
			sys.exit()
	if is_in_docker:
		cmd = f"sudo supervisorctl {action} {service}"
	os.system(cmd)
	roxywi_common.logging('Roxy-WI server', f' The service {service} has been {action}ed', roxywi=1, login=1)
