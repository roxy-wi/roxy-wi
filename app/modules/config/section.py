import re

import app.modules.db.sql as sql
import app.modules.server.server as server_mod
from app.modules.common.common import return_nice_path
from app.modules.config.viewer import HAPROXY_SECTIONS, haproxy_sections, source_lines


SECTION_NAMES = (
	'global', 'listen', 'frontend', 'backend', 'cache', 'defaults', '#HideBlockStart',
	'#HideBlockEnd', 'peers', 'resolvers', 'userlist', 'http-errors', 'log-forward'
)


def _extract_section_name(line: str):
	"""
	Extracts the section name from the given line.

	:param line: The line to extract the section name from.
	:return: The extracted section name as a string if it starts with one of the SECTION_NAMES,
			 None otherwise.
	"""
	line = line.strip()
	if line and (line.split()[0] in HAPROXY_SECTIONS or line in ('#HideBlockStart', '#HideBlockEnd')):
		return line
	return None


def get_sections(config: str, **kwargs) -> list:
	"""
	This method, `get_sections`, is used to extract sections from a configuration file. It takes two parameters: `config`, which is the path to the configuration file, and `kwargs`, which
	* is a variable-length keyword argument that can provide additional options.

	:param config: The path to the configuration file.
	:param kwargs: Additional options to customize the extraction.

	:return: A list containing the extracted sections.

	.. note:: The `service` option in `kwargs` can be used to specify a particular service to extract sections for. If the `service` option is not provided or is not equal to `'keepalived
	*'`, this method will extract all sections. Otherwise, it will only extract sections that contain an IP address.
	"""
	return_config = list()
	with open(config, 'r') as f:
		for line in f:
			if kwargs.get('service') == 'keepalived':
				ip_pattern = re.compile('\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}')
				find_ip = re.findall(ip_pattern, line)
				if find_ip:
					return_config.append(find_ip[0])
			else:
				if _extract_section_name(line):
					line = line.strip()
					return_config.append(line)

	return return_config


def get_section_from_config(config: str, section: str, section_line: int = None) -> tuple:
	"""Return inclusive, zero-based bounds and the exact section source.

	A viewer-supplied header line disambiguates duplicate section names. A stale
	line fails explicitly rather than opening a different section.
	"""
	with open(config, encoding='utf-8', newline='') as file:
		text = file.read()
	lines = source_lines(text)
	candidates = [
		item for item in haproxy_sections(text)
		if item['title'] == section.strip() and item['kind'] != 'preamble'
		and (section_line is None or item['header'] + 1 == section_line)
	]
	if len(candidates) != 1:
		raise ValueError('Section not found or ambiguous; reopen the configuration')
	selected = candidates[0]
	return selected['start'], selected['end'] - 1, ''.join(lines[selected['start']:selected['end']])


def rewrite_section(start_line: str, end_line: str, config: str, section: str) -> str:
	"""Replace an inclusive range without dropping adjacent lines or markers."""
	with open(config, encoding='utf-8', newline='') as file:
		lines = source_lines(file.read())
	start, end = int(start_line), int(end_line)
	# Older editor pages used len(lines) for the final section.
	if end == len(lines):
		end -= 1
	if start < 0 or end < start or end >= len(lines):
		raise ValueError('Invalid section line range')
	if not isinstance(section, str):
		raise ValueError('Section content must be text')
	newline = '\r\n' if lines[start].endswith('\r\n') else '\n'
	if section and not section.endswith('\n') and (end + 1 < len(lines) or lines[end].endswith('\n')):
		section += newline
	return ''.join(lines[:start]) + section + ''.join(lines[end + 1:])


def get_remote_sections(server_ip: str, service: str) -> str:
	"""
	Get the remote sections from a server.

	:param server_ip: The IP address of the server.
	:param service: The name of the service (e.g., apache).
	:return: The remote sections.
	"""
	config_dir = return_nice_path(sql.get_setting(f'{service}_dir'))
	section_name = 'server_name'

	if service == 'apache':
		section_name = 'ServerName'

	commands = f"sudo grep {section_name} {config_dir}*/*.conf -R |grep -v '${{}}\\|#'|awk '{{print $1, $3}}'"

	backends = server_mod.ssh_command(server_ip, commands)

	return backends
