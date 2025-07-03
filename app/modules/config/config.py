import os
from pathlib import Path
from typing import Any

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
import app.modules.roxy_wi_tools as roxy_wi_tools
import app.modules.service.common as service_common
import app.modules.service.action as service_action
import app.modules.config.common as config_common

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def _replace_config_path_to_correct(config_path: str) -> str:
	"""
	Replace the characters '92' with '/' in the given config_path string.

	:param config_path: The config path to be sanitized.
	:return: The sanitized config path string.
	"""
	config_path = common.checkAjaxInput(config_path)
	try:
		return config_path.replace('92', '/')
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot sanitize config file')


def get_config(server_ip, cfg, service='haproxy', **kwargs):
	"""
	:param service: The service for what needed to get config. Valid values are 'haproxy', 'nginx', 'apache' and 'keepalived'.
	:param server_ip: The IP address of the server from which to retrieve the configuration.
	:param cfg: The name of the configuration file.
	:param kwargs: Additional keyword arguments.
		- service: The name of the service for which the configuration is retrieved.
		- config_file_name: The name of the configuration file for 'nginx' or 'apache' services.
		- waf: The name of the Web Application Firewall (WAF) service.
		- waf_rule_file: The name of the WAF rule file.

	:return: None

	Retrieves the configuration file for the specified service on the given server IP. The configuration file is stored in the provided 'cfg' variable.

	The method first determines the correct path for the configuration file based on the 'service' parameter:
	- If the service is 'keepalived' or 'haproxy', the method retrieves the configuration path from the SQL database using the service name appended with '_config_path'.
	- If the service is 'nginx' or 'apache', the method replaces the configuration file name with the correct path using the '_replace_config_path_to_correct' function and the 'config_file
	*_name' parameter.
	- If the 'waf' parameter is provided, the method retrieves the service directory from the SQL database using the 'waf' parameter appended with '_dir'. If the 'waf' parameter is 'hap
	*roxy' or 'nginx', the method constructs the configuration path by appending the service directory with '/waf/rules/' and the 'waf_rule_file' parameter.

	After determining the configuration path, the method validates that the configuration file exists using the 'common.check_is_conf' function.

	Finally, the method establishes an SSH connection to the server IP using the 'mod_ssh.ssh_connect' function and retrieves the configuration file using the 'ssh.get_sftp' function. Any
	* exceptions that occur during this process are handled by the 'roxywi_common.handle_exceptions' function, displaying an error message with the relevant details.
	"""
	config_path = ''

	if service in ('keepalived', 'haproxy') and not kwargs.get("waf"):
		config_path = sql.get_setting(f'{service}_config_path')
	elif service in ('nginx', 'apache'):
		config_path = _replace_config_path_to_correct(kwargs.get('config_file_name'))
	elif kwargs.get("waf"):
		service_dir = sql.get_setting(f"{kwargs.get('waf')}_dir")
		if kwargs.get("waf") in ('haproxy', 'nginx'):
			config_path = f'{service_dir}/waf/rules/{kwargs.get("waf_rule_file")}'
	common.check_is_conf(config_path)

	try:
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


def _generate_command(service: str, server_id: int, just_save: str, config_path: str, tmp_file: str, cfg: str, server_ip: str) -> str:
	"""
	:param service: The name of the service.
	:param server_id: The ID of the server.
	:param just_save: Indicates whether the configuration should only be saved or not. Possible values are 'test', 'save', 'restart' or 'reload'.
	:param config_path: The path to the configuration file.
	:param tmp_file: The temporary file path.
	:param cfg: The configuration object.
	:param server_ip: The IP address of the server.
	:return: A list of commands.

	This method generates a list of commands based on the given parameters.
	"""
	container_name = sql.get_setting(f'{service}_container_name')
	is_dockerized = service_sql.select_service_setting(server_id, service, 'dockerized')
	reload_or_restart_command = f' && {service_action.get_action_command(service, just_save, server_id)}'
	move_config = f" sudo mv -f {tmp_file} {config_path}"
	command_for_docker = f'sudo docker exec -it {container_name}'
	command = {
		'haproxy': {'0': f'sudo haproxy -c -f {tmp_file} ', '1': f'{command_for_docker} haproxy -c -f {tmp_file} '},
		'nginx': {'0': 'sudo nginx -t ', '1': f'{command_for_docker} nginx -t '},
		'apache': {'0': 'sudo apachectl -t ', '1': f'{command_for_docker} apachectl -t '},
		'keepalived': {'0': f'keepalived -t -f {tmp_file} ', '1': ' '},
		'waf': {'0': ' ', '1': ' '}
	}

	try:
		check_config = command[service][is_dockerized]
	except Exception as e:
		raise Exception(f'error: Cannot generate command: {e}')

	if just_save == 'test':
		return f"{check_config} && sudo rm -f {tmp_file}"
	elif just_save == 'save':
		reload_or_restart_command = ''
	else:
		if service_common.is_not_allowed_to_restart(server_id, service, just_save):
			raise Exception('error: This server is not allowed to be restarted')

	if service == 'waf':
		commands = f'{move_config} {reload_or_restart_command}'
	elif service in ('nginx', 'apache'):
		commands = f'{move_config} && {check_config} {reload_or_restart_command}'
	else:
		commands = f'{check_config} && {move_config} {reload_or_restart_command}'

	if service in ('haproxy', 'nginx'):
		if server_sql.return_firewall(server_ip):
			commands += _open_port_firewalld(cfg, server_ip, service)
	return commands


def _create_config_version(server_id: int, server_ip: str, service: str, config_path: str, user_id: int, cfg: str, old_cfg: str, tmp_file: str) -> None:
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
		path = Path(old_cfg)
	else:
		old_cfg = ''
		path = Path(old_cfg)

	if not path.is_file():
		old_cfg = f'{tmp_file}.old'
		try:
			get_config(server_ip, old_cfg, service=service, config_file_name=config_path)
		except Exception:
			roxywi_common.logging('Roxy-WI server', 'Cannot download config for diff')
	try:
		diff = diff_config(old_cfg, cfg)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot create diff config version: {e}')

	try:
		config_sql.insert_config_version(server_id, user_id, service, cfg, config_path, diff)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: Cannot insert config version: {e}')


def upload_and_restart(server_ip: str, cfg: str, just_save: str, service: str, **kwargs):
	"""
	:param server_ip: IP address of the server
	:param cfg: Path to the config file to be uploaded
	:param just_save: Option specifying whether to just save the config or perform an action such as reload or restart
	:param service: Service name for which the config is being uploaded
	:param kwargs: Additional keyword arguments

	:return: Error message or service title

	"""
	user = user_sql.get_user_id(g.user_params['user_id'])
	config_path = kwargs.get('config_file_name')
	server_id = server_sql.get_server_by_ip(server_ip).server_id
	tmp_file = f"{sql.get_setting('tmp_config_path')}/{get_date.return_date('config')}.{config_common.get_file_format(service)}"

	if config_path and config_path != 'undefined':
		config_path = _replace_config_path_to_correct(kwargs.get('config_file_name'))

	if service in ('haproxy', 'keepalived'):
		config_path = sql.get_setting(f'{service}_config_path')

	common.check_is_conf(config_path)

	try:
		os.system(f"dos2unix -q {cfg}")
	except OSError as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'There is no dos2unix')

	try:
		upload(server_ip, tmp_file, cfg)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot upload config')

	# If master then save a version of config in a new way
	if not kwargs.get('slave') and service != 'waf':
		_create_config_version(server_id, server_ip, service, config_path, user.user_id, cfg, kwargs.get('oldcfg'), tmp_file)

	try:
		commands = _generate_command(service, server_id, just_save, config_path, tmp_file, cfg, server_ip)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot generate command for service {service}')

	try:
		error = server_mod.ssh_command(server_ip, commands)
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot {just_save} {service}')

	if just_save in ('reload', 'restart'):
		roxywi_common.logging(server_ip, f'Service {service.title()} has been {just_save}ed', keep_history=1, service=service)
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
	slave_output = ''
	masters = server_sql.is_master(server_ip)
	config_file_name = kwargs.get('config_file_name')
	old_cfg = kwargs.get('oldcfg')
	waf = kwargs.get('waf')
	server = server_sql.get_server_by_ip(server_ip)

	for master in masters:
		if master[0] is not None:
			try:
				slv_output = upload_and_restart(
					master[0], cfg, just_save, service, waf=waf, config_file_name=config_file_name, slave=1
				)
				slave_output += f'<br>slave_server:\n{slv_output}'
			except Exception as e:
				slave_output += f'<br>slave_server:\n error: {e}'
	try:
		output = upload_and_restart(
			server_ip, cfg, just_save, service, waf=waf, config_file_name=config_file_name, oldcfg=old_cfg
		)
	except Exception as e:
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

	This function executes the `diff` command to compare two configuration files,
	specified by their paths, and retrieves the resulting differences. The output
	contains the line-by-line difference between `old_cfg` and `cfg` using the
	unified diff format. This function is useful for auditing and comparing
	configuration changes.

	:param old_cfg: Path to the old configuration file to compare.
	:param cfg: Path to the new configuration file to compare.
	:return: Unified diff output showing the differences between `old_cfg` and `cfg`.
	"""
	cmd = f"/bin/diff -ub {old_cfg} {cfg}"
	output, stderr = server_mod.subprocess_execute(cmd)
	output = '\n'.join(output)
	return output


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
	config_dir = config_common.get_config_dir(service)
	file_format = config_common.get_file_format(service)
	return_files = roxywi_common.get_files(config_dir, file_format, server_ip=server_ip)

	return render_template('ajax/show_compare_configs.html', serv=server_ip, return_files=return_files, lang=lang)


def compare_config(service: str, left: str, right: str) -> str:
	"""
	Compares the configuration files of a service.

	:param service: The name of the service.
	:param left: The name of the left configuration file.
	:param right: The name of the right configuration file.
	:return: The rendered template with the diff output and the user language for Flask.
	"""
	config_dir = config_common.get_config_dir(service)
	output = diff_config(f'{config_dir}{left}', f'{config_dir}{right}')
	return output


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
	configs_dir = config_common.get_config_dir(service)
	server = server_sql.get_server_by_ip(server_ip)

	if config_file_name != 'undefined':
		try:
			config_file_name = config_file_name.replace('/', '92')
		except Exception:
			config_file_name = ''
	else:
		config_file_name = ''

	if '..' in configs_dir:
		raise Exception('error: nice try')

	if configver is None:
		cfg = config_common.generate_config_path(service, server_ip)
		try:
			get_config(server_ip, cfg, service=service, config_file_name=config_file_name)
		except Exception as e:
			raise Exception(e)
	else:
		cfg = configs_dir + configver

	try:
		with open(cfg, 'r', encoding='utf-8', errors='replace') as file:
			conf = file.readlines()
	except Exception as e:
		raise Exception(f'error: Cannot read config file: {e}')

	if configver is None:
		os.remove(cfg)

	kwargs = {
		'conf': conf,
		'serv': server_ip,
		'configver': configver,
		'role': user_sql.get_user_role_in_group(user_id, group_id),
		'service': service,
		'config_file_name': config_file_name,
		'is_serv_protected': server_sql.is_serv_protected(server_ip),
		'is_restart': service_sql.select_service_setting(server.server_id, service, 'restart'),
		'lang': roxywi_common.get_user_lang_for_flask(),
		'hostname': server.hostname,
		'edit_section': edit_section
	}

	return render_template('ajax/config_show.html', **kwargs)


def show_config_files(server_ip: str, service: str, config_file_name: str) -> str:
	"""
	Displays the configuration files for a given server IP, service, and config file name.

	:param server_ip: The IP address of the server.
	:param service: The name of the service.
	:param config_file_name: The name of the config file.
	:return: The rendered template.
	"""
	service_config_dir = sql.get_setting(f'{service}_dir')
	return_files = server_mod.get_remote_files(server_ip, service_config_dir, 'conf')
	return_files += ' ' + sql.get_setting(f'{service}_config_path')
	lang = roxywi_common.get_user_lang_for_flask()

	if 'error: ' in return_files:
		raise Exception(return_files)

	try:
		config_file_name = _replace_config_path_to_correct(config_file_name)
	except Exception:
		config_file_name = ''

	return render_template(
		'ajax/show_configs_files.html', serv=server_ip, service=service, return_files=return_files, lang=lang,
		config_file_name=config_file_name, path_dir=service_config_dir
	)


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
	configs = config_sql.select_config_version(server_ip, service)
	lang = roxywi_common.get_user_lang_for_flask()
	action = f'/app/config/versions/{service}/{server_ip}'
	config_dir = config_common.get_config_dir(service)
	file_format = config_common.get_file_format(service)
	files = roxywi_common.get_files(config_dir, file_format, server_ip)

	return render_template(
		'ajax/show_list_version.html', server_ip=server_ip, service=service, action=action, return_files=files,
		configver=configver, for_delver=for_delver, configs=configs, users=users, lang=lang
	)


def return_cfg(service: str, server_ip: str, config_file_name: str) -> str:
	"""
	:param service: The name of the service (e.g., 'nginx', 'apache')
	:param server_ip: The IP address of the server
	:param config_file_name: The name of the configuration file
	:return: The path to the generated configuration file

	This method returns the path to the generated configuration file based on the provided parameters. The file format is determined by the service. If the service is 'nginx' or 'apache
	*', then the config_file_name is replaced with the correct path, and the resulting configuration file is named using the server_ip and the original file name. If the service is not '
	*nginx' or 'apache', then the resulting configuration file is named using the server_ip. The file format is determined by calling the config_common.get_file_format() method.

	Any existing old configuration files in the config_dir are removed before generating the new configuration file.

	Note: This method depends on the config_common.get_file_format(), config_common.get_config_dir(), and get_date.return_date() methods.
	"""
	file_format = config_common.get_file_format(service)
	config_dir = config_common.get_config_dir(service)

	if service in ('nginx', 'apache'):
		config_file_name = _replace_config_path_to_correct(config_file_name)
		conf_file_name_short = config_file_name.split('/')[-1]
		cfg = f"{config_dir}{server_ip}-{conf_file_name_short}-{get_date.return_date('config')}.{file_format}"
	else:
		cfg = config_common.generate_config_path(service, server_ip)

	try:
		os.remove(f'{config_dir}*.old')
	except Exception:
		pass

	return cfg
