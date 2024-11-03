import os
import base64
from cryptography.fernet import Fernet

import paramiko
from flask import render_template
from playhouse.shortcuts import model_to_dict

import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.common.common as common
from app.modules.server import ssh_connection
from app.modules.db.db_model import Cred
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.class_models import IdResponse, IdDataResponse, CredRequest

error_mess = common.error_mess
get_config = roxy_wi_tools.GetConfigVar()


def return_ssh_keys_path(server_ip: str, cred_id: int = None) -> dict:
	ssh_settings = {}
	if cred_id:
		sshs = cred_sql.select_ssh(id=cred_id)
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

		ssh_key = _return_correct_ssh_file(ssh)
		ssh_settings.setdefault('enabled', ssh.key_enabled)
		ssh_settings.setdefault('user', ssh.username)
		ssh_settings.setdefault('password', password)
		ssh_settings.setdefault('key', ssh_key)
		ssh_settings.setdefault('passphrase', passphrase)

	try:
		server = server_sql.get_server_by_ip(server_ip)
		ssh_settings.setdefault('port', server.port)
	except Exception as e:
		raise Exception(f'error: Cannot get SSH port: {e}')

	return ssh_settings


def ssh_connect(server_ip):
	ssh_settings = return_ssh_keys_path(server_ip)
	ssh = ssh_connection.SshConnection(server_ip, ssh_settings)

	return ssh


def create_ssh_cred(name: str, password: str, group: int, username: str, enable: int, is_api: int, shared: int) -> dict:
	lang = roxywi_common.get_user_lang_for_flask()
	if password and password != "''":
		try:
			password = crypt_password(password)
		except Exception as e:
			raise Exception(e)
	else:
		password = ''

	try:
		last_id = cred_sql.insert_new_ssh(name, enable, group, username, password, shared)
	except Exception as e:
		return roxywi_common.handle_json_exceptions(e, 'Cannot create new SSH credentials')
	roxywi_common.logging('Roxy-WI server', f'New SSH credentials {name} has been created', roxywi=1, login=1)

	if is_api:
		return IdResponse(id=last_id).model_dump(mode='json')
	else:
		data = render_template('ajax/new_ssh.html',
							   groups=group_sql.select_groups(), sshs=cred_sql.select_ssh(name=name), lang=lang, adding=1)
		return IdDataResponse(id=last_id, data=data).model_dump(mode='json')


def upload_ssh_key(ssh_id: int, key: str, passphrase: str) -> None:
	key = key.replace("'", "")
	ssh = cred_sql.get_ssh(ssh_id)
	group_name = group_sql.get_group_name_by_id(ssh.group_id)
	lib_path = get_config.get_config_var('main', 'lib_path')
	full_dir = f'{lib_path}/keys/'
	name = ssh.name
	ssh_keys = f'{full_dir}{name}_{group_name}.pem'

	if key == '':
		raise ValueError('Private key cannot be empty')
	try:
		key = paramiko.pkey.load_private_key(key, password=passphrase)
	except Exception as e:
		raise e

	try:
		key.write_private_key_file(ssh_keys)
	except Exception as e:
		raise e

	try:
		os.chmod(ssh_keys, 0o600)
	except IOError as e:
		raise Exception(e)

	if passphrase:
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

	roxywi_common.logging("Roxy-WI server", f"A new SSH cert has been uploaded {ssh_keys}", roxywi=1, login=1)


def update_ssh_key(body: CredRequest, group_id: int, ssh_id: int) -> None:
	ssh = cred_sql.get_ssh(ssh_id)
	ssh_key_name = _return_correct_ssh_file(ssh)

	if body.password != '' and body.password is not None:
		try:
			body.password = crypt_password(body.password)
		except Exception as e:
			raise Exception(e)

	if os.path.isfile(ssh_key_name):
		new_ssh_key_name = _return_correct_ssh_file(body)
		os.rename(ssh_key_name, new_ssh_key_name)
		os.chmod(new_ssh_key_name, 0o600)

	try:
		cred_sql.update_ssh(ssh_id, body.name, body.key_enabled, group_id, body.username, body.password, body.shared)
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {body.name} has been updated ', roxywi=1, login=1)
	except Exception as e:
		raise Exception(e)


def delete_ssh_key(ssh_id) -> None:
	name = ''

	for sshs in cred_sql.select_ssh(id=ssh_id):
		name = sshs.name

		if sshs.key_enabled == 1:
			ssh_key_name = _return_correct_ssh_file(sshs)
			try:
				os.remove(ssh_key_name)
			except Exception:
				pass
	try:
		cred_sql.delete_ssh(ssh_id)
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {name} has deleted', roxywi=1, login=1)
	except Exception as e:
		raise e


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


def get_creds(group_id: int = None, cred_id: int = None, not_shared: bool = False) -> list:
	json_data = []

	if group_id and cred_id:
		creds = cred_sql.select_ssh(group=group_id, cred_id=cred_id, not_shared=not_shared)
	elif group_id:
		creds = cred_sql.select_ssh(group=group_id)
	else:
		creds = cred_sql.select_ssh()

	for cred in creds:
		if cred.shared and group_id != cred.group_id:
			cred_dict = model_to_dict(cred, exclude={Cred.password, Cred.passphrase})
		else:
			cred_dict = model_to_dict(cred)
			if cred_dict['password']:
				try:
					cred_dict['password'] = decrypt_password(cred_dict['password'])
				except Exception:
					pass
			if cred_dict['passphrase']:
				cred_dict['passphrase'] = decrypt_password(cred_dict['passphrase'])
		cred_dict['name'] = cred_dict['name'].replace("'", "")

		if cred.key_enabled == 1 and group_id == cred.group_id:
			ssh_key_file = _return_correct_ssh_file(cred)
			if os.path.isfile(ssh_key_file):
				with open(ssh_key_file, 'rb') as key:
					cred_dict['private_key'] = base64.b64encode(key.read()).decode('utf-8')
			else:
				cred_dict['private_key'] = ''
		else:
			cred_dict['private_key'] = ''
		json_data.append(cred_dict)
	return json_data


def _return_correct_ssh_file(cred: CredRequest) -> str:
	lib_path = get_config.get_config_var('main', 'lib_path')
	group_name = group_sql.get_group_name_by_id(cred.group_id)
	if group_name not in cred.name:
		return f'{lib_path}/keys/{cred.name}_{group_name}.pem'
	else:
		return f'{lib_path}/keys/{cred.name}.pem'
