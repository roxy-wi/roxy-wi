import re
import cgi

form = cgi.FieldStorage()
error_mess = 'error: All fields must be completed'


def is_ip_or_dns(server_from_request: str) -> str:
	ip_regex = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
	dns_regex = "^(?!-)[A-Za-z0-9-]+([\\-\\.]{1}[a-z0-9]+)*\\.[A-Za-z]{2,6}$"
	try:
		server_from_request = server_from_request.strip()
	except Exception:
		pass
	try:
		if server_from_request in (
			'roxy-wi-checker', 'roxy-wi-keep_alive', 'roxy-wi-keep-alive', 'roxy-wi-metrics',
			'roxy-wi-portscanner', 'roxy-wi-smon', 'roxy-wi-socket', 'roxy-wi-prometheus-exporter',
			'prometheus', 'fail2ban', 'all', 'grafana-server', 'rabbitmq-server'
		):
			return server_from_request
		if re.match(ip_regex, server_from_request):
			return server_from_request
		else:
			if re.match(dns_regex, server_from_request):
				return server_from_request
			else:
				return ''
	except Exception:
		return ''


def checkAjaxInput(ajax_input: str):
	if not ajax_input: return ''
	pattern = re.compile('[&;|$`]')
	if pattern.search(ajax_input):
		print('error: nice try')
		return
	else:
		from shlex import quote
		return quote(ajax_input.rstrip())


def check_is_service_folder(service_path: str) -> bool:
	if (
			'nginx' not in service_path
			and 'haproxy' not in service_path
			and 'apache2' not in service_path
			and 'httpd' not in service_path
			and 'keepalived' not in service_path
	) or '..' in service_path:
		return False
	else:
		return True


def return_nice_path(return_path: str) -> str:
	if not check_is_service_folder(return_path):
		return 'error: The path must contain the name of the service. Check it in Roxy-WI settings'

	if return_path[-1] != '/':
		return_path += '/'

	return return_path


def check_is_conf(config_path: str) -> bool:
	if check_is_service_folder(config_path):
		if 'conf' in config_path or 'cfg' in config_path:
			return True

	return False


def string_to_dict(dict_string) -> dict:
	from ast import literal_eval
	return literal_eval(dict_string)


def get_key(item):
	return item[0]


def is_tool(name):
	from shutil import which
	is_tool_installed = which(name)

	return True if is_tool_installed is not None else False
