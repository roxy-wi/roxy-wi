import os
from cryptography.fernet import Fernet

import paramiko
from flask import render_template

import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
from app.modules.server import ssh_connection
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.class_models import IdResponse, IdDataResponse

error_mess = common.error_mess
get_config = roxy_wi_tools.GetConfigVar()


def return_ssh_keys_path(server_ip: str, **kwargs) -> dict:
	lib_path = get_config.get_config_var('main', 'lib_path')
	ssh_settings = {}
	if kwargs.get('id'):
		sshs = cred_sql.select_ssh(id=kwargs.get('id'))
	else:
		sshs = cred_sql.select_ssh(serv=server_ip)

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

		ssh_settings.setdefault('enabled', ssh.key_enabled)
		ssh_settings.setdefault('user', ssh.username)
		ssh_settings.setdefault('password', password)
		ssh_key = f'{lib_path}/keys/{ssh.name}.pem' if ssh.key_enabled == 1 else ''
		ssh_settings.setdefault('key', ssh_key)
		ssh_settings.setdefault('passphrase', passphrase)

	try:
		ssh_port = [str(server[10]) for server in server_sql.select_servers(server=server_ip)]
		ssh_settings.setdefault('port', ssh_port[0])
	except Exception as e:
		raise Exception(f'error: Cannot get SSH port: {e}')

	return ssh_settings


def ssh_connect(server_ip):
	ssh_settings = return_ssh_keys_path(server_ip)
	ssh = ssh_connection.SshConnection(server_ip, ssh_settings)

	return ssh


def create_ssh_cred(name: str, password: str, group: int, username: str, enable: int, is_api: int) -> dict:
	group_name = group_sql.get_group_name_by_id(group)
	lang = roxywi_common.get_user_lang_for_flask()
	name = f'{name}_{group_name}'
	if password and password != "''":
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)
	else:
		password = ''

	try:
		last_id = cred_sql.insert_new_ssh(name, enable, group, username, password)
	except Exception as e:
		return roxywi_common.handle_json_exceptions(e, 'Cannot create new SSH credentials')
	roxywi_common.logging('RMON server', f'New SSH credentials {name} has been created', roxywi=1, login=1)

	if is_api:
		return IdResponse(id=last_id).model_dump(mode='json')
	else:
		data = render_template('ajax/new_ssh.html', groups=group_sql.select_groups(), sshs=cred_sql.select_ssh(name=name), lang=lang)
		return IdDataResponse(id=last_id, data=data).model_dump(mode='json')


def create_ssh_cred_api(name: str, enable: str, group: str, username: str, password: str) -> bool:
	group_name = group_sql.get_group_name_by_id(group)
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
		try:
			cred_sql.insert_new_ssh(name, enable, group, username, password)
			roxywi_common.logging('Roxy-WI server', f'New SSH credentials {name} has been created', roxywi=1)
			return True
		except Exception as e:
			roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot create SSH credentials {name}', roxywi=1)


def upload_ssh_key(ssh_id: int, key: str, passphrase: str) -> None:
	key = key.replace("'", "")
	ssh = cred_sql.get_ssh(ssh_id)
	group_name = group_sql.get_group_name_by_id(ssh.group_id)
	lib_path = get_config.get_config_var('main', 'lib_path')
	full_dir = f'{lib_path}/keys/'
	name = ssh.name
	ssh_keys = f'{name}.pem'

	try:
		key = paramiko.pkey.load_private_key(key, password=passphrase)
	except Exception as e:
		raise Exception(e)

	try:
		_ = name.split('_')[1]
		split_name = True
	except Exception:
		split_name = False

	if not os.path.isfile(ssh_keys) and not split_name:
		name = f'{ssh.name}_{group_name}'

	if not os.path.exists(full_dir):
		os.makedirs(full_dir)

	ssh_keys = f'{full_dir}{name}.pem'

	try:
		key.write_private_key_file(ssh_keys)
	except Exception as e:
		raise Exception(e)

	try:
		os.chmod(ssh_keys, 0o600)
	except IOError as e:
		roxywi_common.logging('RMON server', e.args[0], roxywi=1)
		raise Exception(e)

	if passphrase != "''":
		try:
			passphrase = crypt_password(passphrase)
		except Exception as e:
			raise Exception(e)
	else:
		passphrase = ''

	try:
		cred_sql.update_ssh_passphrase(ssh_id, passphrase)
	except Exception as e:
		raise Exception(e)

	roxywi_common.logging("RMON server", f"A new SSH cert has been uploaded {ssh_keys}", roxywi=1, login=1)


def update_ssh_key(ssh_id: int, name: str, password: str, enable: int, username: str, group: int) -> None:
	lib_path = get_config.get_config_var('main', 'lib_path')
	ssh = cred_sql.get_ssh(ssh_id)
	ssh_key_name = f'{lib_path}/keys/{ssh.name}.pem'
	new_ssh_key_name = f'{lib_path}/keys/{name}.pem'

	if password != '':
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)

	if ssh.key_enabled == 1 and os.path.isfile(ssh_key_name):
		os.rename(ssh_key_name, new_ssh_key_name)
		os.chmod(new_ssh_key_name, 0o600)

	try:
		cred_sql.update_ssh(ssh_id, name, enable, group, username, password)
		roxywi_common.logging('RMON server', f'The SSH credentials {name} has been updated ', roxywi=1, login=1)
	except Exception as e:
		raise Exception(e)


def delete_ssh_key(ssh_id) -> str:
	lib_path = get_config.get_config_var('main', 'lib_path')
	name = ''
	ssh_enable = 0
	ssh_key_name = ''

	for sshs in cred_sql.select_ssh(id=ssh_id):
		ssh_enable = sshs.key_enabled
		name = sshs.name
		ssh_key_name = f'{lib_path}/keys/{sshs.name}.pem'

	if ssh_enable == 1:
		try:
			os.remove(ssh_key_name)
		except Exception:
			pass
	try:
		cred_sql.delete_ssh(ssh_id)
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {name} has deleted', roxywi=1, login=1)
		return 'ok'
	except Exception as e:
		roxywi_common.handle_exceptions(e, 'Roxy-WI server', f'Cannot delete SSH credentials {name}', roxywi=1, login=1)


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
