import app.modules.db.sql as sql
import app.modules.db.config as config_sql
import app.modules.common.common as common
import app.modules.roxy_wi_tools as roxy_wi_tools
from pathlib import Path
import os
import re
from uuid import uuid4
from werkzeug.utils import secure_filename

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
	if service in ('haproxy', 'nginx', 'apache', 'keepalived'):
		return get_config_var.get_config_var('configs', f'{service}_save_configs_dir')
	else:
		raise Exception('error: Wrong service')


def resolve_config_version_path(service: str, version: str) -> str:
	"""Resolve a saved config path and guarantee it remains inside its service directory."""
	if not version:
		raise ValueError('Config version is required')
	config_dir = Path(get_config_dir(service)).resolve()
	candidate = os.path.realpath(os.path.join(config_dir, version))
	# Include the separator so sibling directories with the same prefix fail.
	if not candidate.startswith(os.path.join(str(config_dir), '')):
		raise ValueError('Config version is outside the allowed directory')
	return candidate


def resolve_config_baseline(service: str, server_ip: str, version: str) -> str:
	"""Constrain a browser-supplied baseline to this server's saved configs."""
	root = Path(get_config_dir(service)).resolve()
	if version:
		absolute = os.path.abspath(version)
		if absolute.startswith(os.path.join(str(root), '')):
			version = absolute
	candidate = Path(resolve_config_version_path(service, version))
	prefix = re.escape(secure_filename(str(server_ip)))
	extension = re.escape(get_file_format(service))
	# Match the complete generated name: a hostname prefix alone is ambiguous
	# with another server such as 192.0.2.10-prod.example.com.
	generated = re.fullmatch(
		prefix + r'-\d{4}-\d{2}-\d{2}\.\d{2}:?\d{2}:?\d{2}(?:-[0-9a-f]{32})?\.'
		+ extension + r'(?:\.old)?', candidate.name,
	)
	if candidate.parent != root:
		raise ValueError('Config baseline does not belong to the selected server')
	# Historical versions may include the remote filename. Their ownership is
	# recorded in the database; never infer it from a partial filename match.
	if not generated and not config_sql.config_version_exists(server_ip, service, str(candidate)):
		raise ValueError('Config baseline does not belong to the selected server')
	return str(candidate)


def resolve_saved_config_path(service: str, server_ip: str, version: str) -> str:
	"""Bind persisted versions to server_id, including after an address change."""
	candidate = resolve_config_version_path(service, version)
	stored = config_sql.get_config_version(server_ip, service, candidate)
	if stored is None:
		raise ValueError('Config version does not belong to the selected server')
	# Use the owned database record, rather than a browser-supplied path.
	return resolve_config_version_path(service, str(Path(stored.local_path).resolve()))


def generate_config_path(service: str, server_ip: str) -> str:
	"""
	:param service: Name of the service for which the configuration path needs to be generated.
	:param server_ip: IP address of the server for which the configuration path needs to be generated.
	:return: The generated configuration path as a string.

	This method generates the configuration path for a given service and server IP address. It combines the service name, server IP address, current date, and file format to create the path
	*. The file format is determined by calling the `get_file_format` method and the configuration directory is obtained using the `get_config_dir` method.
	"""
	server_ip = common.is_ip_or_dns(server_ip)
	file_format = get_file_format(service)
	config_dir = get_config_dir(service)
	config_filename = secure_filename(
		f"{server_ip}-{get_date.return_date('config')}-{uuid4().hex}.{file_format}"
	)
	if not config_filename:
		raise ValueError('Cannot generate a safe configuration filename')
	return str(Path(config_dir) / config_filename)
