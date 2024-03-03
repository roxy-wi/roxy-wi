import re
from datetime import datetime

from shlex import quote
from shutil import which
from pytz import timezone

error_mess = 'error: All fields must be completed'


def get_present_time():
	"""
	Returns the current time in UTC.

	:return: The current time in UTC.
	:rtype: datetime.datetime
	"""
	present = datetime.now(timezone('UTC'))
	formatted_present = present.strftime('%b %d %H:%M:%S %Y %Z')
	return datetime.strptime(formatted_present, '%b %d %H:%M:%S %Y %Z')


def is_ip_or_dns(server_from_request: str) -> str:
	"""
	:param server_from_request: The server name or IP address obtained from the request
	:return: The server name or IP address if it is valid. Otherwise, an empty string is returned.

	This method checks whether the given server name or IP address is valid.
	The method first strips any leading or trailing whitespace from the server_from_request parameter.
	Then, it checks if the server_from_request value is one of the specified special server names.
	If it is, the method immediately returns the server_from_request value.

	If the server_from_request is not a special server name, it then validates whether it is an IP address
	by matching it against the IP regular expression pattern (ip_regex).
	If it is a valid IP address, the method returns the server_from_request value.

	If the server_from_request is not an IP address, it checks if it is a valid DNS name
	by matching it against the DNS regular expression pattern (dns_regex).
	If it is a valid DNS name, the method returns the server_from_request value.

	If the server_from_request value does not match any of the above conditions, an empty string is returned.

	Note: This method uses regular expressions (re.match) to validate the server_from_request value,
	so the regular expression patterns used should follow the standard IP and DNS validation rules.
	"""
	ip_regex = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
	dns_regex = "^(?!-)[A-Za-z0-9-]+([\\-\\.]{1}[a-z0-9]+)*\\.[A-Za-z]{2,6}$"
	try:
		server_from_request = server_from_request.strip()
	except Exception:
		pass
	try:
		if server_from_request in (
			'roxy-wi-checker', 'roxy-wi-keep_alive', 'roxy-wi-keep-alive', 'roxy-wi-metrics', 'roxy-wi-portscanner',
			'roxy-wi-smon', 'roxy-wi-socket', 'roxy-wi-prometheus-exporter', 'prometheus', 'fail2ban', 'all', 'grafana-server', 'rabbitmq-server'
		):
			return server_from_request
		if re.match(ip_regex, server_from_request):
			return server_from_request
		if re.match(dns_regex, server_from_request):
			return server_from_request
		return ''
	except Exception:
		return ''


def checkAjaxInput(ajax_input: str):
	"""
	Checks if the provided `ajax_input` string contains any non-permitted characters and returns the modified string.

	:param ajax_input: The input string to be checked and modified.
	:return: The modified `ajax_input` string, or an empty string if the input was empty or contained non-permitted characters.
	"""
	if not ajax_input: return ''
	pattern = re.compile('[&;|$`]')
	if pattern.search(ajax_input):
		raise ValueError('Error: Non-permitted characters detected')
	else:
		return quote(ajax_input.rstrip())


def check_is_service_folder(service_path: str) -> bool:
	"""
	Check if the given `service_path` contains the name of a service folder.

	:param service_path: The path of the folder to be checked.
	:return: True if the `service_path` contains the name of a service folder, False otherwise.
	"""
	service_names = ['nginx', 'haproxy', 'apache2', 'httpd', 'keepalived']

	return any(service in service_path for service in service_names) and '..' not in service_path


def return_nice_path(return_path: str, is_service=1) -> str:
	"""
	Formats the given return path to make it a nice path.

	:param return_path: The return path that needs to be formatted.
	:param is_service: A flag indicating whether the return path must contain the name of the service.
	                   Defaults to 1.
	:return: The formatted nice path.

	"""
	if not check_is_service_folder(return_path) and is_service:
		return 'error: The path must contain the name of the service. Check it in Roxy-WI settings'

	if return_path[-1] != '/':
		return_path += '/'

	return return_path


def check_is_conf(config_path: str) -> bool:
	"""
	    Check if the config_path is a service folder and contains either 'conf' or 'cfg'.
	    Raise an exception if the check fails.

	    :param config_path: Path string to be checked.
	    :return: True if the path passes the checks, otherwise an exception is raised.
	    """
	if check_is_service_folder(config_path) and ('conf' in config_path or 'cfg' in config_path):
		return True
	raise ValueError(f'error: The provided path "{config_path}" is not a service folder or does not contain "conf" or "cfg"')


def get_key(item):
	return item[0]


def is_tool(name):
	is_tool_installed = which(name)

	return True if is_tool_installed is not None else False


def wrap_line(content: str, css_class: str="line") -> str:
	"""
	Wraps the provided content into a div HTML element with the given CSS class.
	"""
	return f'<div class="{css_class}">{content}</div>'


def highlight_word(line: str, word: str) -> str:
	"""
	Highlights the word in the line by making it bold and colored red.
	"""
	return line.replace(word, f'<span style="color: red; font-weight: bold;">{word}</span>')


def sanitize_input_word(word: str) -> str:
	"""
	Sanitizes the input word by removing certain characters.
	"""
	return re.sub(r'[?|$|!|^|*|\]|\[|,| |]', r'', word)
