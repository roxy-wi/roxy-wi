import app.modules.db.sql as sql
import app.modules.roxy_wi_tools as roxy_wi_tools

get_config_var = roxy_wi_tools.GetConfigVar()
time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)


def get_file_format(service: str) -> str:
	"""
	Get the file format based on the given service.

	:param service: the service name to check the file format for.
	:type service: str
	:return: the file format, either 'cfg' or 'conf'.
	:rtype: str
	"""
	return 'cfg' if service == 'haproxy' else 'conf'


def get_config_dir(service: str) -> str:
	"""
	Return the directory path of the configurations for the given service.

	:param service: The name of the service.
	:return: The directory path of the configurations.
	:raises Exception: If the service name is invalid.
	"""
	if service in ('haproxy', 'nginx', 'apache', 'keepalived', 'caddy'):
		return get_config_var.get_config_var('configs', f'{service}_save_configs_dir')
	else:
		raise Exception('error: Wrong service')


def generate_config_path(service: str, server_ip: str) -> str:
	"""
	:param service: Name of the service for which the configuration path needs to be generated.
	:param server_ip: IP address of the server for which the configuration path needs to be generated.
	:return: The generated configuration path as a string.

	This method generates the configuration path for a given service and server IP address. It combines the service name, server IP address, current date, and file format to create the path
	*. The file format is determined by calling the `get_file_format` method and the configuration directory is obtained using the `get_config_dir` method.
	"""
	file_format = get_file_format(service)
	config_dir = get_config_dir(service)
	return f"{config_dir}/{server_ip}-{get_date.return_date('config')}.{file_format}"
