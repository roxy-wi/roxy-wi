import json
from pathlib import Path, PurePosixPath
import re

from flask import render_template, jsonify
from werkzeug.utils import secure_filename

import app.modules.db.sql as sql
import app.modules.db.server as server_sql
import app.modules.config.config as config_mod
import app.modules.config.common as config_common
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


_SECTION_NAMES = {
	'global', 'listen', 'frontend', 'backend', 'cache', 'defaults', 'peers',
	'resolvers', 'userlist', 'http-errors', 'log-forward',
}


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


def _read_config_lines(config_path: str) -> list[str]:
	safe_path = _runtime_config_path(config_path)
	return safe_path.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)


def _write_config_lines(config_path: str, lines: list[str]) -> None:
	safe_path = _runtime_config_path(config_path)
	safe_path.write_text(''.join(lines), encoding='utf-8')


def _find_section(lines: list[str], section_types, section_name: str = '') -> tuple[int, int]:
	if isinstance(section_types, str):
		section_types = (section_types,)
	for start, line in enumerate(lines):
		parts = line.strip().split()
		if not parts or parts[0] not in section_types:
			continue
		if section_name and (len(parts) < 2 or parts[1] != section_name):
			continue
		for end in range(start + 1, len(lines)):
			candidate = lines[end].strip().split()
			if candidate and candidate[0] in _SECTION_NAMES:
				return start, end
		return start, len(lines)
	raise RuntimeError(f'Cannot find configuration section: {section_name or "/".join(section_types)}')


def _replace_server_address(config_path: str, backend: str, server: str, address: str, port: int) -> None:
	lines = _read_config_lines(config_path)
	start, end = _find_section(lines, ('backend', 'listen'), backend)
	server_pattern = re.compile(rf'^(\s*server\s+{re.escape(server)}\s+)\S+(.*)$')
	for index in range(start + 1, end):
		match = server_pattern.match(lines[index].rstrip('\r\n'))
		if match:
			newline = '\n' if lines[index].endswith('\n') else ''
			lines[index] = f'{match.group(1)}{address}:{port}{match.group(2)}{newline}'
			_write_config_lines(config_path, lines)
			return
	raise RuntimeError(f'Cannot find server {backend}/{server} in configuration')


def _insert_server(config_path: str, backend: str, server_line: str) -> None:
	lines = _read_config_lines(config_path)
	_start, end = _find_section(lines, ('backend', 'listen'), backend)
	lines.insert(end, f'    {server_line.rstrip()}\n')
	_write_config_lines(config_path, lines)


def _delete_server(config_path: str, backend: str, server: str) -> None:
	lines = _read_config_lines(config_path)
	start, end = _find_section(lines, ('backend', 'listen'), backend)
	server_pattern = re.compile(rf'^\s*server\s+{re.escape(server)}(?:\s|$)')
	for index in range(start + 1, end):
		if server_pattern.match(lines[index]):
			del lines[index]
			_write_config_lines(config_path, lines)
			return
	raise RuntimeError(f'Cannot find server {backend}/{server} in configuration')


def _set_section_maxconn(config_path: str, section_type: str, section_name: str, maxconn: int) -> None:
	lines = _read_config_lines(config_path)
	start, end = _find_section(lines, section_type, section_name)
	maxconn_pattern = re.compile(r'^(\s*maxconn\s+)\d+(.*)$')
	for index in range(start + 1, end):
		match = maxconn_pattern.match(lines[index].rstrip('\r\n'))
		if match:
			newline = '\n' if lines[index].endswith('\n') else ''
			lines[index] = f'{match.group(1)}{maxconn}{match.group(2)}{newline}'
			_write_config_lines(config_path, lines)
			return
	lines.insert(end, f'    maxconn {maxconn}\n')
	_write_config_lines(config_path, lines)


def _set_server_maxconn(config_path: str, backend: str, server: str, maxconn: int) -> None:
	lines = _read_config_lines(config_path)
	start, end = _find_section(lines, ('backend', 'listen'), backend)
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


def show_frontend_backend(serv: str, backend: str) -> str:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	output, _stderr = _runtime_command(serv, haproxy_sock_port, 'show servers state')
	lines = ''
	for line in output:
		if backend not in line:
			continue
		fields = line.split()
		if len(fields) > 3:
			lines += fields[3] + '<br>'
	return lines


def show_server(serv: str, backend: str, backend_server: str) -> str:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	output, _stderr = _runtime_command(serv, haproxy_sock_port, 'show servers state')
	for line in output:
		if backend not in line or backend_server not in line:
			continue
		fields = line.split()
		if len(fields) > 18:
			return f'{fields[4]}:{fields[18]}'
	return ''


def get_all_stick_table(serv: str):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	output, _stderr = _runtime_command(serv, hap_sock_p, 'show table')
	return ''.join(line.split()[2] for line in output if len(line.split()) > 2)


def get_stick_table(serv: str, table: str):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	output, _stderr = _runtime_command(serv, hap_sock_p, f'show table {table}')
	header = next((line.split('#', 1)[1] for line in output if '#' in line), '')
	tables_head = []
	for item in header.split(','):
		if ':' in item:
			tables_head.append(item.split(':', 1)[1])
	output = [line for line in output if '#' not in line]

	return tables_head, output


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


def change_ip_and_port(serv, backend_backend, backend_server, backend_ip, backend_port) -> str:
	if backend_ip is None:
		return 'error: Backend IP must be IP and not 0'

	if backend_port is None:
		return 'error: The backend port must be integer and not 0'

	lines = ''
	sock_port = sql.get_setting('haproxy_sock_port')
	masters = server_sql.is_master(serv)

	for master in masters:
		if master[0] is not None:
			command = (f'set server {backend_backend}/{backend_server} addr {backend_ip} port {backend_port} '
					   f'check-port {backend_port}')
			output, stderr = _runtime_command(master[0], sock_port, command)
			lines += output[0]
			roxywi_common.logging(
				master[0], f'IP address and port have been changed. On: {backend_backend}/{backend_server} to {backend_ip}:{backend_port}',
				keep_history=1, service='haproxy'
			)

	command = f'set server {backend_backend}/{backend_server} addr {backend_ip} port {backend_port} check-port {backend_port}'
	roxywi_common.logging(
		serv,
		f'IP address and port have been changed. On: {backend_backend}/{backend_server} to {backend_ip}:{backend_port}',
		keep_history=1, service='haproxy'
	)
	output, stderr = _runtime_command(serv, sock_port, command)

	if stderr != '':
		return f'error: {stderr}'

	lines += output[0]
	cfg = config_common.generate_config_path('haproxy', serv)

	config_mod.get_config(serv, cfg)
	_replace_server_address(cfg, backend_backend, backend_server, backend_ip, backend_port)
	config_mod.master_slave_upload_and_restart(serv, cfg, 'save', 'haproxy')

	return lines


def add_server_via_runtime(
		server_ip: str, backend: str, server: str, backend_ip: str, backend_port: int, check: int, port_check: int
) -> tuple:
	lines = ''
	stderr = ''
	check_cmd = ''
	sock_port = sql.get_setting('haproxy_sock_port')

	if check:
		check_cmd = 'check'

	commands = [f'add server {backend}/{server} {backend_ip}:{backend_port} {check_cmd}'.rstrip()]

	if check:
		commands.append(f'enable health {backend}/{server}')
		commands.append(f'set server {backend}/{server} check-addr {backend_ip} check-port {port_check}')

	commands.append(f'set server {backend}/{server} state ready')

	for command in commands:
		output, stderr = _runtime_command(server_ip, sock_port, command)
		lines += output[0]
	return lines, stderr


def delete_server_via_runtime(server_ip: str, backend: str, server: str) -> tuple:
	lines = ''
	stderr = ''
	sock_port = sql.get_setting('haproxy_sock_port')

	commands = [
		f'set server {backend}/{server} state maint',
		f'del server {backend}/{server}',
	]

	for command in commands:
		output, stderr = _runtime_command(server_ip, sock_port, command)
		lines += output[0]
	return lines, stderr


def add_server(
		server_ip: str, backend: str, server: str, backend_ip: str, backend_port: int, check: int, port_check: int
) -> str:
	lines = ''
	stderr = ''
	check_cfg = ''
	check = int(check)
	masters = server_sql.is_master(server_ip)

	for master in masters:
		if master[0] is not None:
			line, error = add_server_via_runtime(master[0], backend, server, backend_ip, backend_port, check, port_check)
			lines += f'{master[0]}: {line}<br />'
			stderr += error
			roxywi_common.logging(
				master[0], f'A new backend server has been add: {backend}/{server}', keep_history=1, service='haproxy'
			)

	line, error = add_server_via_runtime(server_ip, backend, server, backend_ip, backend_port, check, port_check)
	lines += f'{server_ip}: {line}<br />'
	stderr += error
	roxywi_common.logging(
		server_ip, f'A new backend server has been add: {backend}/{server}', keep_history=1, service='haproxy'
	)

	if 'Already exists a server' in lines:
		return f'error: {lines}'

	if stderr != '':
		return f'error: {stderr}'

	if check:
		check_cfg = f'check port {port_check}'

	cfg = config_common.generate_config_path('haproxy', server_ip)
	try:
		config_mod.get_config(server_ip, cfg)
	except Exception as e:
		raise Exception(f'error: Cannot config section: {e}')
	new_server_cfg = f'server {server} {backend_ip}:{backend_port} {check_cfg}'
	_insert_server(cfg, backend, new_server_cfg)
	try:
		config_mod.master_slave_upload_and_restart(server_ip, cfg, 'save', 'haproxy')
	except Exception as e:
		raise Exception(f'error: Cannot save a new config: {e}')

	return lines


def delete_server(server_ip: str, backend: str, server: str) -> str:
	lines = ''
	stderr = ''
	masters = server_sql.is_master(server_ip)

	for master in masters:
		if master[0] is not None:
			line, error = delete_server_via_runtime(master[0], backend, server)
			lines += f'{master[0]}: {line}<br />'
			stderr += error
			roxywi_common.logging(
				master[0], f'Server has been deleted: {backend}/{server}', keep_history=1, service='haproxy'
			)

	line, error = delete_server_via_runtime(server_ip, backend, server)
	lines += f'{server_ip}: {line}<br />'
	stderr += error
	roxywi_common.logging(
		server_ip, f'Server has been deleted: {backend}/{server}', keep_history=1, service='haproxy'
	)

	if stderr != '':
		return f'error: {stderr}'

	if 'No such server' in lines:
		return f'error: {lines}'

	cfg = config_common.generate_config_path('haproxy', server_ip)

	config_mod.get_config(server_ip, cfg)
	_delete_server(cfg, backend, server)
	config_mod.master_slave_upload_and_restart(server_ip, cfg, 'save', 'haproxy')

	return lines


def table_select(serv: str, table: str):
	lang = roxywi_common.get_user_lang_for_flask()

	if table == 'All':
		tables = get_all_stick_table(serv)
		table = []
		for t in tables.split(','):
			if t != '':
				table_id = []
				tables_head1, table1 = get_stick_table(serv, t)
				table_id.append(tables_head1)
				table_id.append(table1)
				table.append(table_id)

		return render_template('ajax/stick_tables.html', table=table, lang=lang)
	else:
		tables_head, table = get_stick_table(serv, table)
		return render_template('ajax/stick_table.html', tables_head=tables_head, table=table, lang=lang)


def delete_ip_from_stick_table(serv, ip, table) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	_output, stderr = _runtime_command(serv, haproxy_sock_port, f'clear table {table} key {ip}')
	if stderr != '':
		return f'error: {stderr}'
	return 'ok'


def clear_stick_table(serv, table) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	_output, stderr = _runtime_command(serv, haproxy_sock_port, f'clear table {table}')
	if stderr != '':
		return f'error: {stderr}'
	return 'ok'


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


def select_session(server_ip: str) -> str:
	lang = roxywi_common.get_user_lang_for_flask()
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	output, _stderr = _runtime_command(server_ip, haproxy_sock_port, 'show sess')

	return render_template('ajax/sessions_table.html', sessions=output, lang=lang)


def show_session(server_ip, sess_id) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	output, stderr = _runtime_command(server_ip, haproxy_sock_port, f'show sess {sess_id}')
	lines = ''

	if stderr:
		return f'error: {stderr}'
	else:
		for o in output:
			lines += f'{o}<br />'
		return lines


def delete_session(server_ip, sess_id) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	output, stderr = _runtime_command(server_ip, haproxy_sock_port, f'shutdown session {sess_id}')
	try:
		if output[0] != '':
			return 'error: ' + output[0]
	except Exception:
		pass
	if stderr:
		return f'error: {stderr}'

	return 'ok'
