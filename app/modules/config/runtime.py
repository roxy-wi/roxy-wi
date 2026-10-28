import json
from pathlib import Path, PurePosixPath
import re
import shlex

from flask import render_template, jsonify
from werkzeug.utils import secure_filename

import app.modules.db.sql as sql
import app.modules.config.common as config_common
from app.modules.config.viewer import haproxy_sections
from app.modules.service.haproxy import _haproxy_line_tokens
from app.modules.service.haproxy_runtime import execute_runtime_command
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.error_handler import safe_error_message
from app.modules.roxywi.exception import RoxywiInputError

get_config_var = roxy_wi_tools.GetConfigVar()


def _runtime_command(server: str, port: int, command: str) -> tuple[list[str], str]:
	try:
		response = execute_runtime_command(server, int(port), command)
	except Exception as exception:
		return [''], safe_error_message(exception)
	lines = response.splitlines()
	return lines or [''], ''


SERVER_LINE = re.compile(r'^(\s*server\s+)(\S+)(\s+)(\S+)([^\r\n]*)(\r?\n)?$')


def _runtime_config_path(config_path: str) -> Path:
	"""Return a sanitized HAProxy work-file path inside its configured directory."""
	config_directory = Path(config_common.get_config_dir('haproxy')).resolve()
	requested_path = Path(config_path)
	config_filename = secure_filename(requested_path.name)
	if not config_filename or config_filename != requested_path.name:
		raise RoxywiInputError('Invalid runtime configuration filename')
	safe_path = (config_directory / config_filename).resolve()
	if safe_path.parent != config_directory or requested_path.resolve() != safe_path:
		raise RoxywiInputError('Runtime configuration is outside of the HAProxy configuration directory')
	return safe_path


def read_config_lines(config_path: str) -> list[str]:
	safe_path = _runtime_config_path(config_path)
	return safe_path.read_bytes().decode('utf-8').splitlines(keepends=True)


def _write_config_lines(config_path: str, lines: list[str]) -> None:
	safe_path = _runtime_config_path(config_path)
	safe_path.write_bytes(''.join(lines).encode('utf-8'))


def find_section(lines: list[str], section_types, section_name: str = '', *, required=True) -> tuple[int, int] | None:
	if isinstance(section_types, str):
		section_types = (section_types,)
	matches = [section for section in haproxy_sections(''.join(lines))
		if section['kind'] in section_types and (not section_name or section['name'] == section_name)]
	if len(matches) > 1:
		raise RuntimeError(f'Ambiguous configuration section: {section_name}')
	if matches:
		return matches[0]['header'], matches[0]['end']
	if not required:
		return None
	raise RuntimeError(f'Cannot find configuration section: {section_name or "/".join(section_types)}')


def server_line(lines, section, server) -> tuple[int, re.Match]:
	start, end = section[:2]
	matches = [(index, SERVER_LINE.fullmatch(lines[index])) for index in range(start + 1, end)
		if _haproxy_line_tokens(lines[index])[:2] == ['server', server]]
	if len(matches) != 1 or matches[0][1] is None:
		raise RuntimeError(f'Cannot identify server {server} in configuration')
	return matches[0]


def server_endpoint(address: str, port: int) -> str:
	return f'[{address}]:{port}' if ':' in address else f'{address}:{port}'


def replace_server_address(config_path: str, backend: str, server: str, address: str, port: int) -> None:
	lines = read_config_lines(config_path)
	index, match = server_line(lines, find_section(lines, ('backend', 'listen'), backend), server)
	lines[index] = ''.join([match[1], match[2], match[3], server_endpoint(address, port), match[5], match[6] or ''])
	_write_config_lines(config_path, lines)


def _insert_section_line(lines, section, line) -> None:
	start, end = section
	identity = ' '.join(_haproxy_line_tokens(lines[start])[:2])
	marker = f'# END Roxy-WI MANAGED {identity} do not edit it directly'
	markers = [index for index in range(start + 1, end) if lines[index].strip() == marker]
	if len(markers) > 1:
		raise RuntimeError('Ambiguous managed section marker')
	if markers:
		end = markers[0]
	if end and not lines[end - 1].endswith(('\n', '\r')):
		lines[end - 1] += '\n'
	lines.insert(end, f'    {line}\n')


def insert_server(config_path: str, backend: str, server_line: str) -> None:
	lines = read_config_lines(config_path)
	section = find_section(lines, ('backend', 'listen'), backend)
	name = _haproxy_line_tokens(server_line)[1]
	for line in lines[section[0] + 1:section[1]]:
		tokens = _haproxy_line_tokens(line)
		if tokens and (tokens[0] == 'server-template' or tokens[:2] == ['server', name]):
			raise RuntimeError('Server already exists or uses a server template')
	_insert_section_line(lines, section, server_line)
	_write_config_lines(config_path, lines)


def server_default_options(sources, backend: str) -> str:
	"""Resolve default-server options in configuration load order for dynamic adds."""
	defaults, current = {}, ''
	for lines in sources:
		for section in haproxy_sections(''.join(lines)):
			kind = section['kind']
			if kind not in ('defaults', 'backend', 'listen'):
				continue
			tokens = _haproxy_line_tokens(lines[section['header']])
			parent = tokens[tokens.index('from') + 1] if 'from' in tokens else None
			if parent is not None and parent not in defaults:
				raise RuntimeError('Cannot resolve inherited default-server options')
			options = defaults[parent] if parent is not None else '' if kind == 'defaults' else current
			for line in lines[section['header'] + 1:section['end']]:
				values = _haproxy_line_tokens(line)
				if values[:1] == ['default-server']:
					# CLI words use backslash escaping, not configuration-file quotes.
					options += ' ' + ' '.join(re.sub(r'([\\ \t])', r'\\\1', value) for value in values[1:])
			if kind == 'defaults':
				current = options
				defaults[section['name']] = options
			elif section['name'] == backend:
				return options.strip()
	raise RuntimeError('Cannot resolve backend default-server options')


def delete_server(config_path: str, backend: str, server: str) -> None:
	lines = read_config_lines(config_path)
	index, _match = server_line(lines, find_section(lines, ('backend', 'listen'), backend), server)
	del lines[index]
	_write_config_lines(config_path, lines)


def _server_command(server_ip: str, sock_port: int, command: str, success_pattern: str = '') -> str:
	# These commands are composed from validated identifiers and configuration options.
	if any(char in command for char in ';\r\n\x00'):
		raise RoxywiInputError('Invalid runtime server command')
	response = execute_runtime_command(server_ip, int(sock_port), command).strip()
	if response and (not success_pattern or not re.fullmatch(success_pattern, response)):
		raise RuntimeError('HAProxy rejected the server command')
	return response


def change_ip_and_port(serv, backend_backend, backend_server, backend_ip, backend_port, *, sock_port) -> str:
	"""Apply to one node; the caller coordinates validation, persistence and replicas."""
	return _server_command(serv, sock_port,
		f'set server {backend_backend}/{backend_server} addr {backend_ip} port {backend_port}',
		r"(?:(?:IP changed from '[^'\r\n]+' to '[^'\r\n]+'|no need to change the addr)(?:, )?)?"
		r"(?:port changed from '[^'\r\n]+' to '[^'\r\n]+'|no need to change the port)?(?: by 'stats socket command')?\.?",
	)


def add_server(
	server_ip: str, backend: str, server: str, backend_ip: str, backend_port: int, check: int, port_check: int,
	*, sock_port: int, options: str = ''
) -> str:
	"""Register, enable checks and enable traffic, stopping at the first failed command."""
	target = f'{backend}/{server}'
	options = options or f'{"check" if check else ""} port {port_check}'
	response = _server_command(server_ip, sock_port,
		f'add server {target} {server_endpoint(backend_ip, backend_port)} {options}',
		r'(?:\[NOTICE\][^\r\n]* : )?New server registered\.',
	)
	if check:
		_server_command(server_ip, sock_port, f'enable health {target}')
	# A default-server 'disabled' must remain disabled after a later reload too.
	states = [token for token in shlex.split(options) if token in ('enabled', 'disabled')]
	if not states or states[-1] == 'enabled':
		_server_command(server_ip, sock_port, f'set server {target} state ready')
	return response


def set_section_maxconn(config_path: str, section_type: str, section_name: str, maxconn: int) -> None:
	lines = read_config_lines(config_path)
	start, end = find_section(lines, section_type, section_name)
	maxconn_pattern = re.compile(r'^(\s*maxconn\s+)\d+(.*)$')
	for index in range(start + 1, end):
		match = maxconn_pattern.match(lines[index].rstrip('\r\n'))
		if match:
			newline = '\n' if lines[index].endswith('\n') else ''
			lines[index] = f'{match.group(1)}{maxconn}{match.group(2)}{newline}'
			_write_config_lines(config_path, lines)
			return
	_insert_section_line(lines, (start, end), f'maxconn {maxconn}')
	_write_config_lines(config_path, lines)


def set_server_maxconn(config_path: str, backend: str, server: str, maxconn: int) -> None:
	lines = read_config_lines(config_path)
	start, end = find_section(lines, ('backend', 'listen'), backend)
	server_pattern = re.compile(rf'^(\s*server\s+{re.escape(server)}\s+\S+)(.*)$')
	for index in range(start + 1, end):
		line = lines[index].rstrip('\r\n')
		match = server_pattern.match(line)
		if not match:
			continue
		options, separator, comment = match.group(2).partition(' #')
		if re.search(r'\bmaxconn\s+\d+', options):
			options = re.sub(r'\bmaxconn\s+\d+', f'maxconn {maxconn}', options, count=1)
		else:
			options = f'{options.rstrip()} maxconn {maxconn}'
		newline = '\n' if lines[index].endswith('\n') else ''
		lines[index] = f'{match.group(1)}{options}{separator}{comment}{newline}'
		_write_config_lines(config_path, lines)
		return
	raise RuntimeError(f'Cannot find server {backend}/{server} in configuration')


def _list_file_path(lib_path: str, user_group: int, list_name: str) -> Path:
	if not isinstance(list_name, str) or '\\' in list_name or '\x00' in list_name:
		raise RoxywiInputError('Invalid list filename')
	parts = PurePosixPath(list_name).parts
	if len(parts) != 2 or parts[0] not in ('white', 'black'):
		raise RoxywiInputError('List file must belong to the white or black list directory')
	list_filename = secure_filename(parts[1])
	if not list_filename or list_filename != parts[1] or not list_filename.endswith('.lst'):
		raise RoxywiInputError('Invalid list filename')

	base_path = (Path(lib_path) / 'lists' / str(int(user_group))).resolve()
	list_directory = (base_path / parts[0]).resolve()
	if list_directory.parent != base_path:
		raise RoxywiInputError('List file is outside of the group directory')
	list_path = (list_directory / list_filename).resolve()
	if list_path.parent != list_directory:
		raise RoxywiInputError('List file is outside of the group directory')
	return list_path


def escape_runtime_argument(value: str) -> str:
	"""Escape a single CLI argument, including command separators."""
	return ''.join('\\' + char if char in '\\; \t' else char for char in value)


def get_all_stick_table(serv: str, *, sock_port: int) -> str:
	return execute_runtime_command(serv, int(sock_port), 'show table')


def get_stick_table(serv: str, table: str, *, sock_port: int) -> str:
	return execute_runtime_command(serv, int(sock_port), f'show table {escape_runtime_argument(table)}')


def show_backends(server_ip, **kwargs):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	output, stderr = _runtime_command(server_ip, hap_sock_p, 'show backend')
	lines = ''
	if stderr:
		roxywi_common.logging('Roxy-WI server', ' ' + stderr, roxywi=1)
	if kwargs.get('ret'):
		ret = list()
	else:
		ret = ""
	for line in output:
		if any(s in line for s in ('#', 'stats', 'MASTER', '<')):
			continue
		if len(line) > 1:
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret.append(back[1])
			else:
				lines += back[1] + "<br>"

	if kwargs.get('ret'):
		return ret

	return lines


def clear_stick_table(serv: str, table: str, *, sock_port: int, key: str | None = None) -> str:
	"""Clear a table or one entry and preserve HAProxy's reply for the caller."""
	command = f'clear table {escape_runtime_argument(table)}'
	if key is not None:
		command += f' key {escape_runtime_argument(key)}'
	return execute_runtime_command(serv, int(sock_port), command)


def list_of_lists(serv) -> dict:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	output, _stderr = _runtime_command(serv, haproxy_sock_port, 'show acl')
	acl_lists = [
		' '.join(line.split()[:2])
		for line in output
		if 'loaded from' in line
	]
	return jsonify(acl_lists)


def show_lists(serv, list_id, color, list_name) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	output, _stderr = _runtime_command(serv, haproxy_sock_port, f'show acl #{list_id}')

	return render_template('ajax/list.html', list=output, list_id=list_id, color=color, list_name=list_name)


def delete_ip_from_list(serv, ip_id, ip, list_id, list_name) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	user_group = roxywi_common.get_user_group(id=1)
	list_path = _list_file_path(lib_path, user_group, list_name)
	list_entries = [
		line for line in list_path.read_text(encoding='utf-8', errors='replace').splitlines()
		if line.strip() and line.strip() != ip
	]
	content = '\n'.join(list_entries)
	list_path.write_text(f'{content}\n' if content else '', encoding='utf-8')

	output, stderr = _runtime_command(serv, haproxy_sock_port, f'del acl #{list_id} #{ip_id}')

	roxywi_common.logging(serv, f'{ip_id} has been delete from list {list_id}', keep_history=1, service='haproxy')
	if output[0] != '':
		return f'error: {output[0]}'
	if stderr != '':
		return f'error: {stderr}'

	return 'ok'


def add_ip_to_list(serv, ip, list_id, list_name) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	user_group = roxywi_common.get_user_group(id=1)
	output, stderr = _runtime_command(serv, haproxy_sock_port, f'add acl #{list_id} {ip}')
	if output[0]:
		return f'error: {output[0]}'
	if stderr:
		return f'error: {stderr}'

	if 'is not a valid IPv4 or IPv6 address' not in output[0]:
		list_path = _list_file_path(lib_path, user_group, list_name)
		with list_path.open('a', encoding='utf-8') as list_file:
			list_file.write(f'{ip}\n')
		roxywi_common.logging(serv, f'{ip} has been added to list {list_id}', keep_history=1, service='haproxy')
	return 'ok'


def select_session(server_ip: str, *, sock_port: int) -> str:
	return execute_runtime_command(server_ip, sock_port, 'show sess')


def show_session(server_ip: str, sess_id: str, *, sock_port: int) -> str:
	return execute_runtime_command(server_ip, sock_port, f'show sess {sess_id}')


def delete_session(server_ip: str, sess_id: str, *, sock_port: int) -> str:
	return execute_runtime_command(server_ip, sock_port, f'shutdown session {sess_id}')
