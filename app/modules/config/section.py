import re

import modules.db.sql as sql
import modules.server.server as server_mod
from modules.common.common import return_nice_path


def get_sections(config, **kwargs):
	return_config = list()
	with open(config, 'r') as f:
		for line in f:
			if kwargs.get('service') == 'keepalived':
				ip_pattern = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
				find_ip = re.findall(ip_pattern, line)
				if find_ip:
					return_config.append(find_ip[0])
			else:
				if line.startswith((
					'global', 'listen', 'frontend', 'backend', 'cache', 'defaults', '#HideBlockStart',
					'#HideBlockEnd', 'peers', 'resolvers', 'userlist', 'http-errors'
				)):
					line = line.strip()
					return_config.append(line)

	return return_config


def get_section_from_config(config, section):
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
				if line.startswith((
					'global', 'listen', 'frontend', 'backend', 'cache', 'defaults', '#HideBlockStart',
					'#HideBlockEnd', 'peers', 'resolvers', 'userlist', 'http-errors'
				)):
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


def rewrite_section(start_line, end_line, config, section):
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
	remote_dir = service + '_dir'
	config_dir = sql.get_setting(remote_dir)
	config_dir = return_nice_path(config_dir)
	section_name = 'server_name'

	if service == 'apache':
		section_name = 'ServerName'

	commands = [f"sudo grep {section_name} {config_dir}*/*.conf -R |grep -v '${{}}\|#'|awk '{{print $1, $3}}'"]

	backends = server_mod.ssh_command(server_ip, commands)

	return backends
