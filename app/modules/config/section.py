import re

import app.modules.db.sql as sql
import app.modules.server.server as server_mod
from app.modules.common.common import return_nice_path


SECTION_NAMES = (
    'global', 'listen', 'frontend', 'backend', 'cache', 'defaults', '#HideBlockStart',
    '#HideBlockEnd', 'peers', 'resolvers', 'userlist', 'http-errors'
)


def _extract_section_name(line: str):
	"""
	Extracts the section name from the given line.

	:param line: The line to extract the section name from.
	:return: The extracted section name as a string if it starts with one of the SECTION_NAMES,
	         None otherwise.
	"""
	line = line.strip()
	if line.startswith(SECTION_NAMES):
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
				ip_pattern = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
				find_ip = re.findall(ip_pattern, line)
				if find_ip:
					return_config.append(find_ip[0])
			else:
				if _extract_section_name(line):
					line = line.strip()
					return_config.append(line)

	return return_config


def get_section_from_config(config: str, section) -> tuple:
	"""
	:param config: The path to the configuration file.
	:param section: The section name to retrieve from the configuration file.
	:return: A tuple containing the starting line number, ending line number, and the content of the specified section.
	"""
	record = False
	start_line = ""
	end_line = ""
	return_config = ""
	with open(config, 'r') as f:
		for index, line in enumerate(f):
			if line.startswith(section + '\n'):
				start_line = index
				return_config += line
				record = True
				continue
			if record:
				if _extract_section_name(line):
					record = False
					end_line = index
					end_line = end_line - 1
				else:
					return_config += line

	if end_line == "":
		f = open(config, "r")
		line_list = f.readlines()
		end_line = len(line_list)

	return start_line, end_line, return_config


def rewrite_section(start_line: str, end_line: str, config: str, section: str) -> str:
	"""
	:param start_line: The line number where the section to be rewritten starts.
	:param end_line: The line number where the section to be rewritten ends.
	:param config: The path to the configuration file.
	:param section: The new section to be inserted in place of the existing section.
	:return: The modified configuration with the section rewritten.
	"""
	record = False
	start_line = int(start_line)
	end_line = int(end_line)
	return_config = ""
	with open(config, 'r') as f:
		for index, line in enumerate(f):
			index = int(index)
			if index == start_line:
				record = True
				return_config += section
				return_config += "\n"
				continue
			if index == end_line:
				record = False
				continue
			if record:
				continue

			return_config += line

	return return_config


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

	commands = [f"sudo grep {section_name} {config_dir}*/*.conf -R |grep -v '${{}}\|#'|awk '{{print $1, $3}}'"]

	backends = server_mod.ssh_command(server_ip, commands)

	return backends
