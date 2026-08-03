import os
import base64
from cryptography.fernet import Fernet

from flask import render_template
from playhouse.shortcuts import model_to_dict

import app.modules.db.cred as cred_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
from app.modules.server import ssh_connection
from app.modules.db.db_model import Cred
import app.modules.roxywi.common as roxywi_common
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi import logger
from app.modules.roxywi.class_models import IdResponse, IdDataResponse, CredRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound

get_config = roxy_wi_tools.GetConfigVar()


def _get_fernet_key() -> str:
	environment_key = os.environ.get('ROXYWI_SECRET_PHRASE')
	if environment_key:
		key = environment_key.strip()
		source = 'ROXYWI_SECRET_PHRASE'
	else:
		# Do not use the module-level configuration snapshot for credentials. The
		# config file may be created or updated after application modules have been
		# imported (for example, during an upgrade or first installation).
		credential_config = roxy_wi_tools.GetConfigVar()
		key = credential_config.get_config_var('main', 'secret_phrase')
		key = key.strip() if key else ''
		source = f'[main] secret_phrase in {credential_config.path_config}'

	if not key:
		raise RuntimeError(
			f'Credential encryption key from {source} is empty. Configure a unique secret_phrase'
		)
	if key == 'CHANGE_ME':
		raise RuntimeError(
			f'Credential encryption key from {source} is set to CHANGE_ME. '
			'Configure a unique secret_phrase'
		)
	try:
		Fernet(key.encode('ascii'))
	except (ValueError, UnicodeEncodeError) as e:
		raise RuntimeError(
			f'Credential encryption key from {source} is not a valid Fernet key'
		) from e
	return key


def return_ssh_keys_path(server_ip: str, cred_id: int = None) -> dict:
	ssh_settings = {}
	try:
		server = server_sql.get_server_by_ip(server_ip)
	except Exception as e:
		raise Exception(f'error: Cannot get server SSH settings: {e}')

	if cred_id is not None:
		# A caller may select credentials only from the server's tenant or from
		# credentials explicitly shared across tenants.
		sshs = list(cred_sql.select_ssh(group=server.group_id, cred_id=cred_id, not_shared=True))
	else:
		sshs = list(cred_sql.select_ssh(serv=server_ip))
	if not sshs:
		raise RoxywiResourceNotFound

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

		if ssh.private_key:
			ssh_key = _return_correct_ssh_file(ssh)
		else:
			ssh_key = None
		ssh_settings.setdefault('enabled', ssh.key_enabled)
		ssh_settings.setdefault('user', ssh.username)
		ssh_settings.setdefault('password', password)
		ssh_settings.setdefault('key', ssh_key)
		ssh_settings.setdefault('passphrase', passphrase)

	ssh_settings.setdefault('port', server.port)

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
		kwargs = {
			'groups': group_sql.select_groups(),
			'sshs': cred_sql.select_ssh(name=name),
			'lang': lang,
			'adding': 1
		}
		data = render_template('ajax/new_ssh.html', **kwargs)
		return IdDataResponse(id=last_id, data=data).model_dump(mode='json')


def upload_ssh_key(ssh_id: int, key: str, passphrase: str) -> None:
	key = key.replace("'", "")
	key = crypt_password(key)

	try:
		cred_sql.update_private_key(ssh_id, key)
	except Exception as e:
		raise e

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

	roxywi_common.logging("Roxy-WI server", "A new SSH cert has been uploaded", roxywi=1, login=1)


def update_ssh_key(body: CredRequest, group_id: int, ssh_id: int) -> None:
	if body.password != '' and body.password is not None:
		try:
			body.password = crypt_password(body.password)
		except Exception as e:
			raise Exception(e)

	try:
		cred_sql.update_ssh(ssh_id, body.name, body.key_enabled, group_id, body.username, body.password, body.shared)
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {body.name} has been updated ', roxywi=1, login=1)
	except Exception as e:
		raise Exception(e)


def delete_ssh_key(ssh_id: int) -> None:
	sshs = cred_sql.get_ssh(ssh_id)

	if sshs.key_enabled == 1:
		ssh_key_name = _return_correct_ssh_file(sshs)
		try:
			os.remove(ssh_key_name)
		except Exception:
			pass
	try:
		cred_sql.delete_ssh(ssh_id)
		roxywi_common.logging('Roxy-WI server', f'The SSH credentials {sshs.name} has deleted', roxywi=1, login=1)
	except Exception as e:
		raise e


def crypt_password(password: str) -> bytes:
	"""
	Crypt password
	:param password: plain password
	:return: crypted text
	"""
	salt = _get_fernet_key()
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
	salt = _get_fernet_key()
	fernet = Fernet(salt.encode())
	try:
		decrypted_pass = fernet.decrypt(password.encode()).decode()
		decrypted_pass = decrypted_pass.replace("'", "")
	except Exception as e:
		raise Exception(f'error: Cannot decrypt password: {e}')
	return decrypted_pass


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
			for credential_field in ('password', 'passphrase'):
				if not cred_dict[credential_field]:
					continue
				try:
					cred_dict[credential_field] = decrypt_password(cred_dict[credential_field])
				except RuntimeError:
					# A missing/invalid application key affects every credential and must
					# remain visible to the operator instead of rendering all fields empty.
					raise
				except Exception as e:
					# One stale or damaged credential must not make the complete admin
					# page unavailable or expose encrypted values in its response.
					cred_dict[credential_field] = ''
					logger.warning(
						'Cannot decrypt an SSH credential field',
						credential_id=cred.id,
						credential_field=credential_field,
						exception=e
					)
		cred_dict['name'] = cred_dict['name'].replace("'", "")
		cred_dict['private_key'] = ''

		if cred.key_enabled == 1 and group_id == cred.group_id:
			if cred.private_key:
				cred_dict['private_key'] = base64.b64encode(cred.private_key.encode()).decode('utf-8')
		json_data.append(cred_dict)
	return json_data


def _return_correct_ssh_file(cred: CredRequest, ssh_id: int = None) -> str:
	lib_path = get_config.get_config_var('main', 'lib_path')
	group_name = group_sql.get_group(cred.group_id).name
	if group_name not in cred.name:
		key_file = f'{lib_path}/keys/{cred.name}_{group_name}.pem'
	else:
		key_file = f'{lib_path}/keys/{cred.name}.pem'

	if not ssh_id:
		ssh_id = cred.id

	try:
		private_key = cred_sql.get_ssh(ssh_id).private_key
		private_key = decrypt_password(private_key)
		private_key = private_key.strip()
		private_key = f'{private_key}\n'
	except Exception as e:
		raise e

	with open(key_file, 'wb') as key:
		key.write(private_key.encode())

	try:
		os.chmod(key_file, 0o600)
	except IOError as e:
		raise Exception(e)

	return key_file
