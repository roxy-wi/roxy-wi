import os
import subprocess
from difflib import unified_diff
from pathlib import Path
from shlex import quote
from typing import Any
from uuid import uuid4

from flask import render_template, g

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.server as server_sql
import app.modules.db.config as config_sql
import app.modules.db.service as service_sql
import app.modules.server.ssh as mod_ssh
import app.modules.server.server as server_mod
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
from app.modules.roxywi import logger
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.service.common as service_common
import app.modules.service.action as service_action
import app.modules.config.common as config_common
import app.modules.config.deployment_policy as deployment_policy
from app.modules.config import haproxy_files
from app.modules.config.path_tokens import encode_file_path, decode_file_path
from app.modules.config.viewer import build_document

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def _replace_config_path_to_correct(config_path: str) -> str:
	"""Decode and validate a path; shell quoting belongs at command construction."""
	if config_path in (None, '', 'undefined'):
		return ''
	path = decode_file_path(config_path)
	common.checkAjaxInput(path)
	if '\x00' in path or '\\' in path:
		raise ValueError('Invalid configuration file path')
	return path


def get_config(server_ip, cfg, service='haproxy', **kwargs):
	"""Download the selected configuration to a local candidate/baseline file.

	HAProxy defaults to its main file and accepts .cfg files within haproxy_dir.
	NGINX/Apache retain their explicit paths; Keepalived uses its main file.
	WAF rules retain their separate directory resolution.
	"""
	config_path = ''

	if kwargs.get('waf'):
		config_path = common.resolve_waf_config_path(kwargs['waf'], kwargs.get('waf_rule_file'))
	elif service == 'haproxy':
		config_path = haproxy_files.resolve_path(kwargs.get('config_file_name'))
	elif service == 'keepalived':
		config_path = sql.get_setting(f'{service}_config_path')
	elif service in ('nginx', 'apache'):
		config_path = _replace_config_path_to_correct(kwargs.get('config_file_name'))
	if not kwargs.get('waf'):
		common.check_is_conf(config_path)

	try:
		if service == 'haproxy' and not kwargs.get('waf'):
			command = haproxy_files.read_path_command(config_path, missing_ok=kwargs.get('missing_ok', False))
			config_path = server_mod.ssh_command(server_ip, command, rc=1, error_context='Cannot read the selected HAProxy configuration file').strip()
			if kwargs.get('missing_ok') and config_path == '__ROXYWI_MISSING_CONFIG__':
				Path(cfg).write_text('', encoding='utf-8')
				return
			if not config_path.startswith('/'):
				raise ValueError('Cannot resolve the selected HAProxy configuration file')
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.get_sftp(config_path, cfg)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot get config in get config function')


def upload(server_ip: str, path: str, file: str) -> None:
	"""
	Uploads a file to a remote server using secure shell (SSH) protocol.

	:param server_ip: The IP address or hostname of the remote server.
	:param path: The remote path on the server where the file will be uploaded.
	:param file: The file to be uploaded.
	:return: None
	"""
	try:
		with mod_ssh.ssh_connect(server_ip) as ssh:
			ssh.put_sftp(file, path)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot upload {file} to {path} to server: {server_ip}')


def validate_candidate_config(server_ip: str, cfg: str, service: str, config_file_name: str = None) -> str:
	"""Validate a candidate without leaving it as the active on-disk configuration."""
	server_id = server_sql.get_server_by_ip(server_ip).server_id
	config_path = config_file_name
	if service != 'haproxy' and config_path and config_path != 'undefined':
		config_path = _replace_config_path_to_correct(config_path)
	if service == 'haproxy':
		config_path = haproxy_files.resolve_path(config_path)
	elif service == 'keepalived':
		config_path = sql.get_setting(f'{service}_config_path')
	common.check_is_conf(config_path)

	tmp_file = (
		f"{sql.get_setting('tmp_config_path')}/{uuid4().hex}."
		f"candidate.{config_common.get_file_format(service)}"
	)
	try:
		subprocess.run(['dos2unix', '-q', cfg], check=False)
	except OSError:
		# dos2unix is optional; the actual service validator is authoritative.
		pass
	is_dockerized = service_sql.select_service_setting(server_id, service, 'dockerized')
	container_name = sql.get_setting(f'{service}_container_name')
	if service == 'haproxy':
		command = haproxy_files.candidate_command(
			config_path, tmp_file, 'test', sources=haproxy_files.config_sources(server_ip, server_id),
			container=container_name if is_dockerized == '1' else ''
		)
		upload(server_ip, tmp_file, cfg)
		return str(server_mod.ssh_command(server_ip, command, rc=1, timeout=90,
			error_context='HAProxy configuration validation failed') or '').strip() or 'HAProxy configuration is valid'
	if is_dockerized == '1':
		checks = {
			'haproxy': f'sudo docker exec {quote(container_name)} haproxy -c -f {quote(config_path)}',
			'nginx': f'sudo docker exec {quote(container_name)} nginx -t',
			'apache': f'sudo docker exec {quote(container_name)} apachectl -t',
			'keepalived': f'sudo docker exec {quote(container_name)} keepalived -t -f {quote(config_path)}',
		}
	else:
		checks = {
			'haproxy': f'sudo haproxy -c -f {quote(tmp_file)}',
			'nginx': 'sudo nginx -t',
			'apache': 'sudo apachectl -t',
			'keepalived': f'sudo keepalived -t -f {quote(tmp_file)}',
		}

	check_command = checks[service]
	# NGINX and Apache validate the complete configuration tree. Dockerized
	# services also need the candidate at the mounted production path. Preserve
	# the original and restore it before returning, including on failure.
	stage_candidate = service in ('nginx', 'apache') or is_dockerized == '1'
	if stage_candidate:
		backup_file = f'{tmp_file}.before'
		command = (
			f'sudo cp -p {quote(config_path)} {quote(backup_file)} && '
			f'sudo mv -f {quote(tmp_file)} {quote(config_path)} && {check_command}; '
			f'validation_rc=$?; sudo mv -f {quote(backup_file)} {quote(config_path)}; exit $validation_rc'
		)
	else:
		command = (
			f'{check_command}; validation_rc=$?; sudo rm -f {quote(tmp_file)}; exit $validation_rc'
		)

	try:
		upload(server_ip, tmp_file, cfg)
		output = server_mod.ssh_command(server_ip, command, rc=1)
	except Exception as e:
		roxywi_common.handle_exceptions(e, server_ip, f'Cannot validate {service} candidate configuration')
	return str(output or '').strip() or f'{service.title()} configuration is valid'


def _generate_command(
	service: str, server_id: int, just_save: str, config_path: str, tmp_file: str, cfg: str, server_ip: str,
	waf_service: str = None
) -> str:
	"""
	:param service: The name of the service.
	:param server_id: The ID of the server.
	:param just_save: Indicates whether the configuration should only be saved or not. Possible values are 'test', 'save', 'restart' or 'reload'.
	:param config_path: The path to the configuration file.
	:param tmp_file: The temporary file path.
	:param cfg: The configuration object.
	:param server_ip: The IP address of the server.
	:param waf_service: The proxy owning the WAF rule, used to select its runtime service.
	:return: A list of commands.

	This method generates a list of commands based on the given parameters.
	"""
	validate_config_action(just_save)
	if service == 'waf':
		if waf_service not in ('haproxy', 'nginx') or just_save == 'test':
			raise ValueError('Unsupported WAF configuration action')
		action_service = 'nginx' if waf_service == 'nginx' else 'waf'
		if service_common.is_not_allowed_to_restart(server_id, action_service, just_save):
			raise ValueError('This server is not allowed to be restarted')
		command = f'sudo mv -f {quote(tmp_file)} {quote(config_path)}'
		if just_save in ('reload', 'restart'):
			command += f' && {service_action.get_action_command(action_service, just_save, server_id)}'
		return command
	container_name = sql.get_setting(f'{service}_container_name')
	is_dockerized = service_sql.select_service_setting(server_id, service, 'dockerized')
	if service == 'haproxy':
		if service_common.is_not_allowed_to_restart(server_id, service, just_save):
			raise Exception('error: This server is not allowed to be restarted')
		action_command = service_action.get_action_command(service, just_save, server_id) if just_save in ('reload', 'restart') else ''
		commands = haproxy_files.candidate_command(
			config_path, tmp_file, just_save, sources=haproxy_files.config_sources(server_ip, server_id),
			container=container_name if is_dockerized == '1' else '',
			reload_command=action_command
		)
		if just_save != 'test' and server_sql.return_firewall(server_ip):
			commands += _open_port_firewalld(cfg, server_ip, service)
		return commands
	reload_or_restart_command = ''
	if just_save in ('reload', 'restart'):
		reload_or_restart_command = f' && {service_action.get_action_command(service, just_save, server_id)}'
	move_config = f" sudo mv -f {quote(tmp_file)} {quote(config_path)}"
	command_for_docker = f'sudo docker exec -it {quote(container_name)}'
	command = {
		'haproxy': {'0': f'sudo haproxy -c -f {tmp_file} ', '1': f'{command_for_docker} haproxy -c -f {tmp_file} '},
		'nginx': {'0': 'sudo nginx -t ', '1': f'{command_for_docker} nginx -t '},
		'apache': {'0': 'sudo apachectl -t ', '1': f'{command_for_docker} apachectl -t '},
		'keepalived': {'0': f'keepalived -t -f {quote(tmp_file)} ', '1': ' '},
	}

	try:
		check_config = command[service][is_dockerized]
	except Exception as e:
		raise Exception(f'error: Cannot generate command: {e}')

	if just_save == 'test':
		return f"{check_config} && sudo rm -f {quote(tmp_file)}"
	elif just_save == 'save':
		reload_or_restart_command = ''
	else:
		if service_common.is_not_allowed_to_restart(server_id, service, just_save):
			raise Exception('error: This server is not allowed to be restarted')

	if service in ('nginx', 'apache'):
		commands = f'{move_config} && {check_config} {reload_or_restart_command}'
	else:
		commands = f'{check_config} && {move_config} {reload_or_restart_command}'

	if service in ('haproxy', 'nginx'):
		if server_sql.return_firewall(server_ip):
			commands += _open_port_firewalld(cfg, server_ip, service)
	return commands


def _prepare_config_version_diff(server_ip: str, service: str, config_path: str, cfg: str, old_cfg: str, tmp_file: str) -> str:
	"""
	Create a new version of the configuration file.

	:param server_id: The ID of the server.
	:param server_ip: The IP address of the server.
	:param service: The service name.
	:param config_path: The path to the configuration file.
	:param cfg: The new configuration string.
	:param old_cfg: The path to the old configuration file.
	:param tmp_file: A temporary file name.

	:return: None
	"""
	diff = ''

	if old_cfg:
		old_cfg = config_common.resolve_config_baseline(service, server_ip, old_cfg)
		path = Path(old_cfg)
	else:
		old_cfg = ''
		path = Path(old_cfg)

	if not path.is_file():
		if service == 'haproxy':
			old_cfg = f'{cfg}.old'
			get_config(server_ip, old_cfg, service=service, config_file_name=config_path, missing_ok=True)
			return diff_config(old_cfg, cfg)
		old_cfg = f'{tmp_file}.old'
		try:
			get_config(server_ip, old_cfg, service=service, config_file_name=config_path)
		except Exception:
			roxywi_common.logging('Roxy-WI server', 'Cannot download config for diff')
	try:
		diff = diff_config(old_cfg, cfg)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot create diff config version: {e}')

	return diff


def _create_config_version(
	server_id: int, service: str, config_path: str, user_id: int, cfg: str, diff: str, message: str = None
) -> None:
	try:
		config_sql.insert_config_version(server_id, user_id, service, cfg, config_path, diff, message=message)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot insert config version: {e}')


def normalize_config_file(cfg: str) -> None:
	"""Normalize a local candidate once before it is uploaded to one or more nodes."""
	try:
		subprocess.run(['dos2unix', '-q', cfg], check=False)
	except OSError as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'There is no dos2unix')


def validate_config_action(action: str) -> None:
	if action not in ('save', 'test', 'reload', 'restart'):
		raise ValueError('Unsupported configuration action')


def upload_and_restart(server_ip: str, cfg: str, just_save: str, service: str, **kwargs):
	"""
	:param server_ip: IP address of the server
	:param cfg: Path to the config file to be uploaded
	:param just_save: Option specifying whether to just save the config or perform an action such as reload or restart
	:param service: Service name for which the config is being uploaded
	:param kwargs: Additional keyword arguments

	:return: Error message or service title

	"""
	validate_config_action(just_save)
	if (kwargs.get('oldcfg') and service != 'waf' and kwargs.get('record_version', True)
		and not kwargs.get('slave') and just_save != 'test'):
		kwargs['oldcfg'] = config_common.resolve_config_baseline(service, server_ip, kwargs['oldcfg'])
	policy_service = kwargs.get('deployment_policy_service', service)
	if (
		policy_service in deployment_policy.SERVICES
		and not kwargs.get('deployment_policy_bypass', False)
	):
		deployment_policy.require_direct_deployment_for_server(
			server_ip, policy_service, action=just_save
		)

	config_path = kwargs.get('config_file_name')
	server_id = server_sql.get_server_by_ip(server_ip).server_id
	tmp_file = f"{sql.get_setting('tmp_config_path')}/{uuid4().hex}.{config_common.get_file_format(service)}"

	if service != 'haproxy' and config_path and config_path != 'undefined':
		config_path = _replace_config_path_to_correct(kwargs.get('config_file_name'))

	if service == 'haproxy':
		config_path = haproxy_files.resolve_path(config_path)
	elif service == 'keepalived':
		config_path = sql.get_setting(f'{service}_config_path')

	if service == 'waf':
		expected_path = common.resolve_waf_config_path(kwargs.get('waf'), (config_path or '').rsplit('/', 1)[-1])
		if config_path != expected_path:
			raise ValueError('Configuration path does not match the WAF service directory')
	else:
		common.check_is_conf(config_path)

	if kwargs.get('normalize_config', True):
		normalize_config_file(cfg)

	should_record_version = (
		not kwargs.get('slave')
		and kwargs.get('record_version', True)
		and service != 'waf'
		and just_save != 'test'
	)
	version_diff = ''
	version_user = None
	if should_record_version:
		user_id = kwargs.get('user_id')
		if user_id is None:
			user_id = g.user_params['user_id']
		version_user = user_sql.get_user_id(user_id)
		version_diff = _prepare_config_version_diff(
			server_ip, service, config_path, cfg, kwargs.get('oldcfg'), tmp_file
		)

	try:
		commands = _generate_command(service, server_id, just_save, config_path, tmp_file, cfg, server_ip, **(
			{'waf_service': kwargs.get('waf')} if service == 'waf' else {}
		))
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot generate command for service {service}')

	try:
		upload(server_ip, tmp_file, cfg)
		error = server_mod.ssh_command(server_ip, commands, rc=1, **(
			{'timeout': 90, 'error_context': 'HAProxy configuration validation or application failed'} if service == 'haproxy' else {}
		))
	except Exception as e:
		if service == 'waf':
			try:
				server_mod.ssh_command(server_ip, f'sudo rm -f -- {quote(tmp_file)}', rc=1)
			except Exception as cleanup_error:
				logger.exception('Cannot remove temporary WAF upload', exc=cleanup_error, server_ip=server_ip)
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot {just_save} {service}')

	# A saved version represents a successful remote operation, not merely an
	# upload attempt. Validation-only requests are intentionally not versions.
	if should_record_version:
		_create_config_version(
			server_id, service, config_path, version_user.user_id, cfg, version_diff,
			message=kwargs.get('version_message')
		)

	if just_save in ('reload', 'restart'):
		action_service = 'nginx' if service == 'waf' and kwargs.get('waf') == 'nginx' else service
		roxywi_common.logging(server_ip, f'Service {action_service.title()} has been {just_save}ed', keep_history=1, service=action_service)
	if just_save != 'test':
		roxywi_common.logging(server_ip, 'A new config file has been uploaded', keep_history=1, service=service)

	if error.strip() != 'haproxy' and error.strip() != 'nginx':
		return error.strip() or service.title()


def master_slave_upload_and_restart(server_ip: str, cfg: str, just_save: str, service: str, **kwargs: Any) -> str:
	"""

	This method `master_slave_upload_and_restart` performs the upload and restart operation on a master server and its
	associated slave servers. It takes the following parameters:

	:param server_ip: The IP address of the server to perform the operation on.
	:param cfg: The configuration file to upload and restart.
	:param just_save: A flag indicating whether to just save the configuration or also restart the server.
	:param service: The name of the service to restart.
	:param kwargs: Additional optional keyword arguments.

	:return: The output of the operation.

	"""
	validate_config_action(just_save)
	if kwargs.get('oldcfg') and service != 'waf' and kwargs.get('record_version', True) and just_save != 'test':
		kwargs['oldcfg'] = config_common.resolve_config_baseline(service, server_ip, kwargs['oldcfg'])
	masters = list(server_sql.is_master(server_ip))
	policy_service = kwargs.get('deployment_policy_service', service)
	policy_bypass = kwargs.get('deployment_policy_bypass', False)
	if policy_service in deployment_policy.SERVICES and not policy_bypass:
		# Check the complete propagation topology before the first remote write.
		deployment_policy.require_direct_deployment_for_server(
			server_ip, policy_service, action=just_save
		)
		for slave_ip, _slave_hostname in masters:
			if slave_ip:
				deployment_policy.require_direct_deployment_for_server(
					slave_ip, policy_service, action=just_save
				)

	slave_output = ''
	config_file_name = kwargs.get('config_file_name')
	old_cfg = kwargs.get('oldcfg')
	waf = kwargs.get('waf')
	server = server_sql.get_server_by_ip(server_ip)

	for master in masters:
		if master[0] is not None:
			try:
				slv_output = upload_and_restart(
					master[0], cfg, just_save, service, waf=waf, config_file_name=config_file_name, slave=1,
					record_version=kwargs.get('record_version', True), deployment_policy_bypass=True,
					deployment_policy_service=policy_service
				)
				slave_output += f'<br>slave_server:\n{slv_output}'
			except Exception as e:
				if service == 'waf':
					raise
				slave_output += f'<br>slave_server:\n error: {e}'
	try:
		output = upload_and_restart(
			server_ip, cfg, just_save, service, waf=waf, config_file_name=config_file_name, oldcfg=old_cfg,
			record_version=kwargs.get('record_version', True), version_message=kwargs.get('version_message'),
			deployment_policy_bypass=True, deployment_policy_service=policy_service
		)
	except Exception as e:
		if service == 'waf':
			raise
		output = f'error: {e}'

	output = server.hostname + ':\n' + output
	output = output + slave_output

	return output


def _open_port_firewalld(cfg: str, server_ip: str, service: str) -> str:
	"""
	:param cfg: The path to the configuration file for Firewalld.
	:param server_ip: The IP address of the server.
	:param service: The name of the service to open ports for (e.g., nginx).
	:return: The Firewalld commands to open the specified ports.

	This method reads the provided Service configuration file and opens ports based on the specified service. It returns the Firewalld commands as a string.

	"""
	firewalld_commands = ' &&'
	ports = ''

	try:
		conf = open(cfg, "r")
	except IOError as e:
		raise Exception(f'error: Cannot open config file for Firewalld {e}')

	for line in conf:
		if service == 'nginx':
			if "listen " in line and '#' not in line:
				try:
					listen = ' '.join(line.split())
					listen = listen.split(" ")[1]
					listen = listen.split(";")[0]
					try:
						listen = int(listen)
						ports += str(listen) + ' '
						firewalld_commands += f' sudo firewall-cmd --zone=public --add-port={listen}/tcp --permanent -q &&'
					except Exception:
						pass
				except Exception:
					pass
		else:
			if "bind" in line:
				try:
					bind = line.split(":")
					bind[1] = bind[1].strip(' ')
					bind = bind[1].split("ssl")
					bind = bind[0].strip(' \t\n\r')
					try:
						bind = int(bind)
						firewalld_commands += f' sudo firewall-cmd --zone=public --add-port={bind}/tcp --permanent -q &&'
						ports += str(bind) + ' '
					except Exception:
						pass
				except Exception:
					pass

	firewalld_commands += ' sudo firewall-cmd --reload -q'
	roxywi_common.logging(server_ip, f'Next ports have been opened: {ports}')
	return firewalld_commands


def diff_config(old_cfg, cfg) -> str:
	"""
	Compute the difference between two configuration files and return the result as a string.

	This function compares two configuration files in Python. The output
	contains the line-by-line difference between `old_cfg` and `cfg` using the
	unified diff format. This function is useful for auditing and comparing
	configuration changes.

	:param old_cfg: Path to the old configuration file to compare.
	:param cfg: Path to the new configuration file to compare.
	:return: Unified diff output showing the differences between `old_cfg` and `cfg`.
	"""
	try:
		with open(old_cfg, encoding='utf-8', errors='replace') as old_file:
			old_lines = old_file.readlines()
		with open(cfg, encoding='utf-8', errors='replace') as new_file:
			new_lines = new_file.readlines()
	except OSError as e:
		raise Exception(f'Cannot compare configuration files: {e}') from e

	return ''.join(unified_diff(old_lines, new_lines, fromfile=str(old_cfg), tofile=str(cfg)))


def _classify_line(line: str) -> str:
	"""
	Classifies the line as 'line' or 'line3' based on if it contains '--'.
	"""
	return "line" if '--' in line else "line3"


def show_finding_in_config(stdout: str, **kwargs) -> str:
	"""
	:param stdout: The stdout of a command execution.
	:param kwargs: Additional keyword arguments.
		:keyword grep: The word to find and highlight in the output. (Optional)
	:return: The output with highlighted lines and formatted dividers.

	This method takes the stdout of a command execution and additional keyword arguments. It searches for a word specified by the `grep` keyword argument in each line of the stdout and highlights
	* the word if found. It then classifies each line based on its content and wraps it in a line with appropriate CSS class. Finally, it adds formatted dividers before and after the output
	*.
	The formatted output string is returned.
	"""
	css_class_divider = common.wrap_line("--")
	output = css_class_divider
	word_to_find = kwargs.get('grep')

	if word_to_find:
		word_to_find = common.sanitize_input_word(word_to_find)

	for line in stdout:
		if word_to_find:
			line = common.sanitize_input_word(line)
			line = common.highlight_word(line, word_to_find)
		line_class = _classify_line(line)
		output += common.wrap_line(line, line_class)

	output += css_class_divider
	return output


def show_compare_config(server_ip: str, service: str) -> str:
	"""
	Display the comparison of configurations for a service.

	:param server_ip: The IP address of the server.
	:param service: The service name.
	:return: Returns the rendered template as a string.
	"""
	lang = roxywi_common.get_user_lang_for_flask()
	config_dir = Path(config_common.get_config_dir(service)).resolve()
	versions = config_sql.select_config_version(server_ip, service)
	return_files = sorted({
		Path(version.local_path).name for version in versions
		if Path(version.local_path).resolve().parent == config_dir and Path(version.local_path).is_file()
	}, reverse=True)

	return render_template('ajax/show_compare_configs.html', serv=server_ip, return_files=return_files, lang=lang)


def compare_config(service: str, server_ip: str, left: str, right: str) -> str:
	"""
	Compares the configuration files of a service.

	:param service: The name of the service.
	:param server_ip: The server that owns both saved configurations.
	:param left: The name of the left configuration file.
	:param right: The name of the right configuration file.
	:return: The rendered template with the diff output and the user language for Flask.
	"""
	left_path = config_common.resolve_saved_config_path(service, server_ip, left)
	right_path = config_common.resolve_saved_config_path(service, server_ip, right)
	return diff_config(left_path, right_path)


def show_config(server_ip: str, service: str, config_file_name: str, configver: str, claims: dict, edit_section: str) -> str:
	"""
	Get and display the configuration file for a given server.

	:param edit_section:
	:param claims:
	:param server_ip: The IP address of the server.
	:param service: The name of the service.
	:param config_file_name: The name of the configuration file.
	:param configver: The version of the configuration.

	:return: The rendered template for displaying the configuration.
	"""
	user_id = claims['user_id']
	group_id = claims['group']
	server = server_sql.get_server_by_ip(server_ip)
	if configver is None:
		remote_path = config_common.resolve_viewer_path(service, config_file_name)
		cfg = config_common.generate_config_path(service, server_ip)
		try:
			get_config(server_ip, cfg, service=service, config_file_name=remote_path)
			with open(cfg, encoding='utf-8', errors='replace', newline='') as file:
				text = file.read()
		finally:
			Path(cfg).unlink(missing_ok=True)
	else:
		cfg = config_common.resolve_saved_config_path(service, server_ip, configver)
		remote_path = config_sql.select_remote_path_from_version(server_ip, service, cfg)
		with open(cfg, encoding='utf-8', errors='replace', newline='') as file:
			text = file.read()
	role = user_sql.get_user_role_in_group(user_id, group_id)
	protected = server_sql.is_serv_protected(server_ip)
	remote_path = str(remote_path or sql.get_setting(f'{service}_config_path'))
	document = build_document(
		text, service, server_ip, remote_path, version=configver,
		editable=bool(role and role <= 3 and (not protected or role <= 2)),
		main_file=remote_path == str(sql.get_setting(f'{service}_config_path')),
	)
	kwargs = {
		'document': document,
		'serv': server_ip,
		'configver': configver,
		'role': role,
		'service': service,
		'config_file_name': document['source']['file_token'],
		'is_serv_protected': protected,
		'is_restart': service_sql.select_service_setting(server.server_id, service, 'restart'),
		'lang': roxywi_common.get_user_lang_for_flask(),
		'hostname': server.hostname,
		'edit_section': edit_section,
		'direct_deployment_allowed': (
			deployment_policy.direct_deployment_allowed(server.group_id, service)
			if service in deployment_policy.SERVICES else True
		)
	}

	return render_template('ajax/config_show.html', **kwargs)


def show_config_files(server_ip: str, service: str, config_file_name: str, edit_mode: bool = False) -> str:
	"""
	Displays the configuration files for a given server IP, service, and config file name.

	:param server_ip: The IP address of the server.
	:param service: The name of the service.
	:param config_file_name: The name of the config file.
	:return: The rendered template.
	"""
	service_config_dir = sql.get_setting(f'{service}_dir')
	discovery = None
	multiple_files = False
	if service == 'haproxy':
		server_id = server_sql.get_server_by_ip(server_ip).server_id
		multiple_files = haproxy_files.multiple_files_enabled(server_id)
		if multiple_files:
			discovery = haproxy_files.discover_sources(server_ip, server_id)
	files = ([haproxy_files.resolve_path()] if discovery and discovery['state'] == 'error'
		else list_config_files(server_ip, service))
	lang = roxywi_common.get_user_lang_for_flask()

	if service == 'haproxy' and config_file_name in (None, '', 'undefined') and files:
		main = haproxy_files.resolve_path()
		config_file_name = main if main in files else files[0]
	config_file_name = haproxy_files.resolve_path(config_file_name) if service == 'haproxy' else _replace_config_path_to_correct(config_file_name)
	if not config_file_name:
		config_file_name = sql.get_setting(f'{service}_config_path')

	return render_template(
		'ajax/show_configs_files.html', serv=server_ip, service=service, files=files, lang=lang,
		config_file_name=config_file_name, path_dir=service_config_dir, edit_mode=edit_mode,
		file_extension=config_common.get_file_format(service), encode_file_path=encode_file_path,
		discovery=discovery, multiple_files=multiple_files,
		server_id=server_id if service == 'haproxy' else None
	)


def list_config_files(server_ip: str, service: str) -> list[str]:
	main = str(sql.get_setting(f'{service}_config_path'))
	if service == 'keepalived':
		return [main]
	root = str(sql.get_setting(f'{service}_dir')).rstrip('/')
	if service == 'haproxy':
		server_id = server_sql.get_server_by_ip(server_ip).server_id
		if not haproxy_files.multiple_files_enabled(server_id):
			return [main]
		discovery = haproxy_files.discover_sources(server_ip, server_id)
		if discovery['state'] == 'error':
			raise ValueError('Cannot determine HAProxy configuration sources (%s)' % discovery['code'])
		return [haproxy_files.resolve_path(path) for path in discovery['files']]
	else:
		output = server_mod.get_remote_files(server_ip, root, 'conf')
		if 'error: ' in output:
			raise ValueError(output)
		files = [path for path in output.split('\x00') if path]
	return [main, *sorted(set(files) - {main})]


def list_of_versions(server_ip: str, service: str, configver: str, for_delver: int) -> str:
	"""
	Retrieve a list of versions for a given server IP, service, configuration version.

	:param server_ip: The IP address of the server.
	:param service: The service to retrieve versions for.
	:param configver: The configuration version to retrieve.
	:param for_delver: The delete version to use.
	:return: The rendered HTML template with the list of versions.
	"""
	users = user_sql.select_users()
	configs = list(config_sql.select_config_version(server_ip, service))
	lang = roxywi_common.get_user_lang_for_flask()
	action = f'/app/config/versions/{service}/{server_ip}'
	config_dir = Path(config_common.get_config_dir(service)).resolve()
	files = sorted({
		Path(version.local_path).name for version in configs
		if Path(version.local_path).resolve().parent == config_dir and Path(version.local_path).is_file()
	}, reverse=True)

	return render_template(
		'ajax/show_list_version.html', server_ip=server_ip, service=service, action=action, return_files=files,
		configver=configver, for_delver=for_delver, configs=configs, users=users, lang=lang
	)


def return_cfg(service: str, server_ip: str, config_file_name: str) -> str:
	"""Return a unique config path bound to the selected server.

	Remote filenames are retained in version metadata, not used to infer
	ownership of controller files.
	"""
	return config_common.generate_config_path(service, server_ip)
