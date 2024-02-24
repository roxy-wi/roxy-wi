import os
from cryptography.fernet import Fernet

import paramiko
from flask import render_template, request

import app.modules.db.sql as sql
import app.modules.common.common as common
from app.modules.server import ssh_connection
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools

error_mess = common.error_mess
get_config = roxy_wi_tools.GetConfigVar()


def return_ssh_keys_path(server_ip: str, **kwargs) -> dict:
	lib_path = get_config.get_config_var('main', 'lib_path')
	ssh_settings = {}
	if kwargs.get('id'):
		sshs = sql.select_ssh(id=kwargs.get('id'))
	else:
		sshs = sql.select_ssh(serv=server_ip)

	for ssh in sshs:
		if ssh.password:
			try:
				password = decrypt_password(ssh.password)
			except Exception as e:
				raise Exception(e)
		else:
			password = ssh.password
		if ssh.passphrase:
			try:
				passphrase = decrypt_password(ssh.passphrase)
			except Exception as e:
				raise Exception(e)
		else:
			passphrase = ssh.passphrase

		ssh_settings.setdefault('enabled', ssh.enable)
		ssh_settings.setdefault('user', ssh.username)
		ssh_settings.setdefault('password', password)
		ssh_key = f'{lib_path}/keys/{ssh.name}.pem' if ssh.enable == 1 else ''
		ssh_settings.setdefault('key', ssh_key)
		ssh_settings.setdefault('passphrase', passphrase)

	try:
		ssh_port = [str(server[10]) for server in sql.select_servers(server=server_ip)]
		ssh_settings.setdefault('port', ssh_port[0])
	except Exception as e:
		raise Exception(f'error: Cannot get SSH settings: {e}')

	return ssh_settings


def ssh_connect(server_ip):
	ssh_settings = return_ssh_keys_path(server_ip)
	ssh = ssh_connection.SshConnection(server_ip, ssh_settings)

	return ssh


def create_ssh_cred() -> str:
	name = common.checkAjaxInput(request.form.get('new_ssh'))
	enable = common.checkAjaxInput(request.form.get('ssh_enable'))
	group = common.checkAjaxInput(request.form.get('new_group'))
	group_name = sql.get_group_name_by_id(group)
	username = common.checkAjaxInput(request.form.get('ssh_user'))
	password = common.checkAjaxInput(request.form.get('ssh_pass'))
	page = common.checkAjaxInput(request.form.get('page'))
	page = page.split("#")[0]
	lang = roxywi_common.get_user_lang_for_flask()
	name = f'{name}_{group_name}'

	if password != '':
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)

	if username is None or name is None:
		return error_mess
	else:
		try:
			sql.insert_new_ssh(name, enable, group, username, password)
		except Exception as e:
			roxywi_common.handle_exceptions(e, 'Roxy-WI server', 'Cannot create new SSH credentials', roxywi=1, login=1)
		roxywi_common.logging('Roxy-WI server', f'New SSH credentials {name} has been created', roxywi=1, login=1)
		return render_template('ajax/new_ssh.html', groups=sql.select_groups(), sshs=sql.select_ssh(name=name), page=page, lang=lang)


def create_ssh_cread_api(name: str, enable: str, group: str, username: str, password: str) -> bool:
	group_name = sql.get_group_name_by_id(group)
	name = common.checkAjaxInput(name)
	name = f'{name}_{group_name}'
	enable = common.checkAjaxInput(enable)
	username = common.checkAjaxInput(username)
	password = common.checkAjaxInput(password)

	if password != '':
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)

	if username is None or name is None:
		return False
	else:
		if sql.insert_new_ssh(name, enable, group, username, password):
			return True


def upload_ssh_key(name: str, user_group: str, key: str, passphrase: str) -> str:
	if '..' in name:
		raise Exception('error: nice try')

	if name == '':
		raise Exception('error: please select credentials first')

	try:
		key = paramiko.pkey.load_private_key(key, password=passphrase)
	except Exception as e:
		raise Exception(f'error: Cannot save SSH key file: {e}')

	lib_path = get_config.get_config_var('main', 'lib_path')
	full_dir = f'{lib_path}/keys/'
	ssh_keys = f'{name}.pem'

	try:
		_check_split = name.split('_')[1]
		split_name = True
	except Exception:
		split_name = False

	if not os.path.isfile(ssh_keys) and not split_name:
		name = f'{name}_{user_group}'

	if not os.path.exists(full_dir):
		os.makedirs(full_dir)

	ssh_keys = f'{full_dir}{name}.pem'

	try:
		key.write_private_key_file(ssh_keys)
	except Exception as e:
		raise Exception(f'error: Cannot save SSH key file: {e}')
	try:
		os.chmod(ssh_keys, 0o600)
	except IOError as e:
		roxywi_common.logging('Roxy-WI server', e.args[0], roxywi=1)
		raise Exception(f'error: something went wrong: {e}')

	if passphrase != '':
		try:
			passphrase = crypt_password(passphrase)
		except Exception as e:
			raise Exception(e)

	try:
		sql.update_ssh_passphrase(name, passphrase)
	except Exception as e:
		raise Exception(e)

	roxywi_common.logging("Roxy-WI server", f"A new SSH cert has been uploaded {ssh_keys}", roxywi=1, login=1)
	return f'success: SSH key has been saved into: {ssh_keys}'


def update_ssh_key() -> str:
	ssh_id = common.checkAjaxInput(request.form.get('id'))
	name = common.checkAjaxInput(request.form.get('name'))
	enable = common.checkAjaxInput(request.form.get('ssh_enable'))
	group = common.checkAjaxInput(request.form.get('group'))
	username = common.checkAjaxInput(request.form.get('ssh_user'))
	password = common.checkAjaxInput(request.form.get('ssh_pass'))
	new_ssh_key_name = ''
	ssh_key_name = ''
	ssh_enable = 0

	if password != '':
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)

	if username is None:
		return error_mess

	lib_path = get_config.get_config_var('main', 'lib_path')

	for sshs in sql.select_ssh(id=ssh_id):
		ssh_enable = sshs.enable
		ssh_key_name = f'{lib_path}/keys/{sshs.name}.pem'
		new_ssh_key_name = f'{lib_path}/keys/{name}.pem'

	if ssh_enable == 1:
		os.rename(ssh_key_name, new_ssh_key_name)
		os.chmod(new_ssh_key_name, 0o600)

	sql.update_ssh(ssh_id, name, enable, group, username, password)
	roxywi_common.logging('Roxy-WI server', f'The SSH credentials {name} has been updated ', roxywi=1, login=1)

	return 'ok'


def delete_ssh_key(ssh_id) -> str:
	lib_path = get_config.get_config_var('main', 'lib_path')
	name = ''
	ssh_enable = 0
	ssh_key_name = ''

	for sshs in sql.select_ssh(id=ssh_id):
		ssh_enable = sshs.enable
		name = sshs.name
		ssh_key_name = f'{lib_path}/keys/{sshs.name}.pem'

	if ssh_enable == 1:
		try:
			os.remove(ssh_key_name)
		except Exception:
			pass
	if sql.delete_ssh(ssh_id):
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {name} has deleted', roxywi=1, login=1)
		return 'ok'


def crypt_password(password: str) -> bytes:
	"""
	Crypt password
	:param password: plain password
	:return: crypted text
	"""
	salt = get_config.get_config_var('main', 'secret_phrase')
	fernet = Fernet(salt.encode())
	try:
		crypted_pass = fernet.encrypt(password.encode())
	except Exception as e:
		raise Exception(f'error: Cannot crypt password: {e}')
	return crypted_pass


def decrypt_password(password: str) -> str:
	"""
	Decrypt password
	:param password: crypted password
	:return: plain text
	"""
	salt = get_config.get_config_var('main', 'secret_phrase')
	fernet = Fernet(salt.encode())
	try:
		decryp_pass = fernet.decrypt(password.encode()).decode()
	except Exception as e:
		raise Exception(f'error: Cannot decrypt password: {e}')
	return decryp_pass
