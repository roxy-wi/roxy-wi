import os
import re
from packaging import version

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

import app.modules.db.sql as sql
import app.modules.db.roxy as roxy_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
import app.modules.server.server as server_mod


def is_docker() -> bool:
	path = "/proc/self/cgroup"
	if not os.path.isfile(path):
		return False
	with open(path) as f:
		for line in f:
			if re.match("\d+:[\w=]+:/docker(-[ce]e)?/\w+", line):
				return True
	return_out = server_mod.subprocess_execute_with_rc('systemctl status rsyslog')
	if return_out['rc']:
		return True
	return False


def check_ver():
	return roxy_sql.get_ver()


def versions():
	json_data = {
		'need_update': 0
	}
	try:
		current_ver = roxy_sql.get_ver()
		json_data['current_ver'] = roxy_sql.get_ver()
	except Exception as e:
		raise Exception(f'Cannot get current version: {e}')

	try:
		new_ver = check_new_version('roxy-wi')
		json_data['new_ver'] = new_ver
	except Exception as e:
		raise Exception(f'Cannot get new version: {e}')

	try:
		if version.parse(current_ver) < version.parse(new_ver):
			json_data['need_update'] = 1
	except version.InvalidVersion as e:
		roxywi_common.handle_json_exceptions(e, 'Cannot check new version')

	return json_data


def check_new_version(service):
	current_ver = check_ver()
	res = ''
	proxy_dict = common.return_proxy_dict()

	try:
		response = requests.get(f'https://roxy-wi.org/version/get/{service}', timeout=5, proxies=proxy_dict)
		if service == 'roxy-wi':
			requests.get(f'https://roxy-wi.org/version/send/{current_ver}', timeout=5, proxies=proxy_dict)

		res = response.content.decode(encoding='UTF-8')
	except requests.exceptions.RequestException as e:
		roxywi_common.logging('Roxy-WI server', f' {e}', roxywi=1)

	return res


def update_user_status() -> None:
	user_license = sql.get_setting('license')
	proxy_dict = common.return_proxy_dict()
	retry_strategy = Retry(
		total=3,
		status_forcelist=[429, 500, 502, 503, 504]
	)
	adapter = HTTPAdapter(max_retries=retry_strategy)
	roxy_wi_get_plan = requests.Session()
	roxy_wi_get_plan.mount("https://", adapter)
	json_body = {'license': user_license}
	roxy_wi_get_plan = requests.post('https://roxy-wi.org/user/license', timeout=5, proxies=proxy_dict, json=json_body)
	try:
		status = roxy_wi_get_plan.json()
		roxy_sql.update_user_status(status['status'], status['plan'], status['method'])
		roxywi_common.logging('Roxy-WI server', 'Update Roxy-WI user status', roxywi=1)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot get Roxy-WI user status {e}', roxywi=1)


def action_service(action: str, service: str) -> str:
	is_in_docker = is_docker()
	actions = {
		'start': 'enable --now',
		'stop': 'disable --now',
		'restart': 'restart',
	}
	if not re.match(r'^[a-zA-Z0-9\.\-]+$', service):
			return f"Invalid service name: {service}. Only alphanumeric characters, dots, and hyphens are allowed."
	cmd = f"sudo systemctl {actions[action]} {service}"
	if not roxy_sql.select_user_status():
		return 'warning: The service is disabled because you are not subscribed. Read <a href="https://roxy-wi.org/pricing" ' \
				   'title="Roxy-WI pricing" target="_blank">here</a> about subscriptions'
	if is_in_docker:
		cmd = f"sudo supervisorctl {action} {service}"
	os.system(cmd)
	roxywi_common.logging('Roxy-WI server', f' The service {service} has been {action}ed', roxywi=1, login=1)
	return 'ok'


def update_plan():
	roxy_sql.insert_user_name('user')
	update_user_status()
