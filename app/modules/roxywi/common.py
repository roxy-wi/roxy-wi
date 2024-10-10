import os
import glob
from typing import Any, Union

from flask import request, g
from flask_jwt_extended import get_jwt
from flask_jwt_extended import verify_jwt_in_request

from app.modules.db.sql import get_setting
import app.modules.db.udp as udp_sql
import app.modules.db.roxy as roxy_sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.history as history_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.class_models import ErrorResponse
from app.modules.roxywi.exception import RoxywiResourceNotFound, RoxywiGroupMismatch, RoxywiGroupNotFound, \
	RoxywiPermissionError, RoxywiConflictError

get_config_var = roxy_wi_tools.GetConfigVar()


def return_error_message():
	return 'error: All fields must be completed'


def get_user_group(**kwargs) -> int:
	user_group = ''

	try:
		verify_jwt_in_request()
		claims = get_jwt()
		user_group_id = claims['group']
		groups = group_sql.select_groups(id=user_group_id)
		for group in groups:
			if group.group_id == int(user_group_id):
				if kwargs.get('id'):
					user_group = group.group_id
				else:
					user_group = group.name
	except Exception as e:
		raise Exception(f'error: {e}')
	return user_group


def check_user_group_for_flask(api_token: bool = False):
	if api_token:
		return True
	verify_jwt_in_request()
	claims = get_jwt()
	user_id = claims['user_id']
	group_id = claims['group']

	if user_sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('RMON server', 'has tried to actions in not his group', login=1)
		return False


def check_user_group_for_socket(user_id: int, group_id: int) -> bool:
	if user_sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('RMON server', 'has tried to actions in not his group', login=1)
		return False


def check_is_server_in_group(server_ip: str) -> bool:
	group_id = get_user_group(id=1)
	servers = server_sql.select_servers(server=server_ip)
	for s in servers:
		if (s[2] == server_ip and int(s[3]) == int(group_id)) or group_id == 1:
			return True
		else:
			logging('Roxy-WI server', 'has tried to actions in not his group server', roxywi=1, login=1)
			return False


def get_files(folder, file_format, server_ip=None) -> list:
	if file_format == 'log':
		file = []
	else:
		file = set()
	return_files = set()
	i = 0
	for files in sorted(glob.glob(os.path.join(folder, f'*.{file_format}*'))):
		if file_format == 'log':
			try:
				file += [(i, files.split('/')[4])]
			except Exception as e:
				print(e)
		else:
			file.add(files.split('/')[-1])
		i += 1
	files = file
	if file_format == 'cfg' or file_format == 'conf':
		for file in files:
			ip = file.split("-")
			if server_ip == ip[0]:
				return_files.add(file)
		return sorted(return_files, reverse=True)
	else:
		return file


def logging(server_ip: Union[str, int], action: str, **kwargs) -> None:
	get_date = roxy_wi_tools.GetDate(get_setting('time_zone'))
	cur_date_in_log = get_date.return_date('date_in_log')
	log_path = get_config_var.get_config_var('main', 'log_path')
	verify_jwt_in_request()
	claims = get_jwt()
	user_id = claims['user_id']
	login = user_sql.get_user_id(user_id=user_id)

	if not os.path.exists(log_path):
		os.makedirs(log_path)

	try:
		user_group = get_user_group()
	except Exception:
		user_group = ''

	try:
		ip = request.remote_addr
	except Exception:
		ip = ''

	if kwargs.get('roxywi') == 1:
		if kwargs.get('login'):
			mess = f"{cur_date_in_log} from {ip} user: {login.username}, group: {user_group}, {action} on: {server_ip}\n"
		else:
			mess = f"{cur_date_in_log} {action} from {ip}\n"
		log_file = f"{log_path}/roxy-wi.log"
	else:
		mess = f"{cur_date_in_log} from {ip} user: {login.username}, group: {user_group}, {action} on: {server_ip} {kwargs.get('service')}\n"
		log_file = f"{log_path}/config_edit.log"

	if kwargs.get('keep_history'):
		try:
			keep_action_history(kwargs.get('service'), action, server_ip, login.username, ip)
		except Exception as e:
			print(f'error: Cannot save history: {e}')

	try:
		with open(log_file, 'a') as log:
			log.write(mess)
	except IOError as e:
		print(f'Cannot write log. Please check log_path in config {e}')


def keep_action_history(service: str, action: str, server_ip: str, login: str, user_ip: str):
	if login != '':
		user = user_sql.get_user_id_by_username(login)
		user_id = user.user_id
	else:
		user_id = 0
	if user_ip == '':
		user_ip = 'localhost'

	if service == 'HA cluster':
		try:
			server_id = server_ip
			hostname = ha_sql.select_cluster_name(int(server_id))
		except Exception as e:
			logging('Roxy-WI server', f'Cannot get info about cluster {server_ip} for history: {e}', roxywi=1)
			return
	elif service == 'UDP listener':
		try:
			server_id = int(server_ip)
			listener = udp_sql.get_listener(server_id)
			hostname = listener.name
		except Exception as e:
			logging('Roxy-WI server', f'Cannot get info about Listener {server_ip} for history: {e}', roxywi=1)
			return
	else:
		try:
			server = server_sql.get_server_by_ip(server_ip)
			server_id = server.server_id
			hostname = server.hostname
		except Exception as e:
			logging('Roxy-WI server', f'Cannot get info about {server_ip} for history: {e}', roxywi=1)
			return

	try:
		history_sql.insert_action_history(service, action, server_id, user_id, user_ip, server_ip, hostname)
	except Exception as e:
		logging('Roxy-WI server', f'Cannot save a history: {e}', roxywi=1)


def get_dick_permit(**kwargs):
	api_token = kwargs.get('token')
	if not kwargs.get('group_id'):
		try:
			group_id = get_user_group(id=1)
		except Exception as e:
			return str(e)
	else:
		group_id = kwargs.pop('group_id')

	if check_user_group_for_flask(api_token=api_token):
		try:
			servers = server_sql.get_dick_permit(group_id, **kwargs)
		except Exception as e:
			raise Exception(e)
		else:
			return servers
	else:
		print('Atata!')


def get_users_params(**kwargs):
	verify_jwt_in_request()
	user_data = get_jwt()

	try:
		user_id = user_data['user_id']
		user = user_sql.get_user_id(user_id)
	except Exception:
		raise Exception('error: Cannot get user id')

	if int(user_data['group']) != int(user.group_id):
		raise Exception('error: Wrong active group')

	try:
		role = user_sql.get_role_id(user_id, user.group_id)
	except Exception as e:
		raise Exception(f'error: Cannot get user role {e}')

	try:
		user_services = user_sql.select_user_services(user_id)
	except Exception as e:
		raise Exception(f'error: Cannot get user services {e}')

	if kwargs.get('virt') and kwargs.get('service') == 'haproxy':
		servers = get_dick_permit(virt=1, haproxy=1)
	elif kwargs.get('virt'):
		servers = get_dick_permit(virt=1)
	elif kwargs.get('disable'):
		servers = get_dick_permit(disable=0)
	elif kwargs.get('service'):
		servers = get_dick_permit(service=kwargs.get('service'))
	else:
		servers = get_dick_permit()

	user_lang = get_user_lang_for_flask()

	user_params = {
		'user': user.username,
		'role': role,
		'servers': servers,
		'user_services': user_services,
		'lang': user_lang,
		'user_id': user_id,
		'group_id': user.group_id
	}

	return user_params


def get_user_lang_for_flask() -> str:
	try:
		user_lang = request.cookies.get('lang')
	except Exception:
		return 'en'

	if user_lang is None:
		user_lang = 'en'

	return user_lang


def return_user_status() -> dict:
	user_subscription = {}
	user_subscription.setdefault('user_status', roxy_sql.select_user_status())
	user_subscription.setdefault('user_plan', roxy_sql.select_user_plan())

	return user_subscription


def return_unsubscribed_user_status() -> dict:
	user_subscription = {'user_status': 0, 'user_plan': 0}

	return user_subscription


def return_user_subscription():
	try:
		user_subscription = return_user_status()
	except Exception as e:
		user_subscription = return_unsubscribed_user_status()
		logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

	return user_subscription


def handle_exceptions(ex: Exception, server_ip: str, message: str, **kwargs: Any) -> None:
	"""
	:param server_ip:
	:param ex: The exception that was caught
	:param message: The error message to be logged and raised
	:param kwargs: Additional keyword arguments to be passed to the logging function
	:return: None

	"""
	logging(server_ip, f'error: {message}: {ex}', **kwargs)
	raise Exception(f'{message}: {ex}')


def is_user_has_access_to_its_group(user_id: int) -> None:
	if not user_sql.check_user_group(user_id, g.user_params['group_id']) and g.user_params['role'] != 1:
		raise RoxywiGroupMismatch


def is_user_has_access_to_group(user_id: int, group_id: int) -> None:
	if not user_sql.check_user_group(user_id, group_id) and g.user_params['role'] != 1:
		raise RoxywiGroupMismatch


def handle_json_exceptions(ex: Exception, message: str, server_ip='Roxy-WI server') -> dict:
	logging(server_ip, f'{message}: {ex}', login=1, roxywi=1)
	return ErrorResponse(error=f'{message}: {ex}').model_dump(mode='json')


def handler_exceptions_for_json_data(ex: Exception, main_ex_mes: str) -> tuple[dict, int]:
	if isinstance(ex, KeyError):
		return handle_json_exceptions(ex, 'Missing key in JSON data'), 500
	elif isinstance(ex, ValueError):
		return handle_json_exceptions(ex, 'Wrong type or missing value in JSON data'), 500
	elif isinstance(ex, RoxywiResourceNotFound):
		return handle_json_exceptions(ex, 'Resource not found'), 404
	elif isinstance(ex, RoxywiGroupNotFound):
		return handle_json_exceptions(ex, 'Group not found'), 404
	elif isinstance(ex, RoxywiGroupMismatch):
		return handle_json_exceptions(ex, 'Resource not found in group'), 404
	elif isinstance(ex, RoxywiPermissionError):
		return handle_json_exceptions(ex, 'You cannot edit this resource'), 403
	elif isinstance(ex, RoxywiConflictError):
		return handle_json_exceptions(ex, 'Conflict'), 429
	else:
		return handle_json_exceptions(ex, main_ex_mes), 500
