import os
import glob
from typing import Any, Union

from flask import request, g
from flask_jwt_extended import get_jwt
from flask_jwt_extended import verify_jwt_in_request

import app.modules.db.udp as udp_sql
import app.modules.db.ha_cluster as ha_sql
import app.modules.db.roxy as roxy_sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.history as history_sql
import app.modules.roxy_wi_tools as roxy_wi_tools
from app.modules.roxywi.class_models import ErrorResponse
from app.modules.roxywi.exception import RoxywiGroupMismatch
from app.modules.roxywi.error_handler import handle_exception, log_error
from app.modules.roxywi import logger

get_config_var = roxy_wi_tools.GetConfigVar()


def get_jwt_token_claims() -> dict:
	verify_jwt_in_request()
	claims = get_jwt()
	claim = {'user_id': claims['user_id'], 'group': claims['group']}
	return claim


def get_user_group(**kwargs) -> int:
	try:
		claims = get_jwt_token_claims()
		user_group_id = claims['group']
		group = group_sql.get_group(user_group_id)
		if group.group_id == int(user_group_id):
			if kwargs.get('id'):
				user_group = group.group_id
			else:
				user_group = group.name
		else:
			user_group = ''
	except Exception as e:
		raise Exception(f'error: {e}')
	return user_group


def check_user_group_for_flask() -> bool:
	claims = get_jwt_token_claims()
	user_id = claims['user_id']
	group_id = claims['group']

	if user_sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('Roxy-WI server', 'warning: has tried to actions in not his group')
	return False


def check_user_group_for_socket(user_id: int, group_id: int) -> bool:
	if user_sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('Roxy-WI server', 'warning: has tried to actions in not his group')
		return False


def check_is_server_in_group(server_ip: str) -> bool:
	group_id = get_user_group(id=1)
	server = server_sql.get_server_by_ip(server_ip)
	if (server.ip == server_ip and int(server.group_id) == int(group_id)) or group_id == 1:
		return True
	else:
		logging('Roxy-WI server', 'warning: has tried to actions in not his group server')
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
	"""
	Log an action with detailed information.

	Args:
		server_ip: The IP of the server where the action occurred
		action: The action that was performed
		**kwargs: Additional arguments, including:
			keep_history: Whether to keep the action in the history
			service: The service where the action occurred
	"""
	try:
		# JWT validation and extracting user's information
		claims = get_jwt_token_claims()
		user_id = claims['user_id']
		user = user_sql.get_user_id(user_id=user_id)
		user_group = get_user_group()
		ip = request.remote_addr

		# Determine log level and clean up action string
		if 'error' in action:
			log_level = logger.ERROR
			action = action.replace('error: : ', '')
			action = action.replace('error: ', '')
		elif 'warning' in action:
			log_level = logger.WARNING
			action = action.replace('warning: ', '')
		else:
			log_level = logger.INFO

		# Log the message with structured context
		logger.log(
			log_level,
			action,
			server_ip=server_ip,
			user_id=user.user_id,
			username=user.username,
			user_group=user_group,
			client_ip=ip,
			service=kwargs.get('service')
		)

		# Keep action history if requested
		if kwargs.get('keep_history'):
			try:
				keep_action_history(kwargs.get('service'), action, server_ip, user.user_id, ip)
			except Exception as e:
				logger.error(f'Cannot save history: {e}', server_ip=server_ip)
	except Exception as e:
		# Fallback logging if we can't get user information
		logger.error(f'Error in logging function: {e}', server_ip=server_ip)


def keep_action_history(service: str, action: str, server_ip: str, user_id: int, user_ip: str):
	"""
	Keep a history of actions in the database.

	Args:
		service: The service where the action occurred
		action: The action that was performed
		server_ip: The IP of the server where the action occurred
		user_id: The ID of the user who performed the action
		user_ip: The IP of the user who performed the action
	"""
	if user_ip == '':
		user_ip = 'localhost'

	if service == 'HA cluster':
		try:
			server_id = server_ip
			hostname = ha_sql.select_cluster_name(int(server_id))
		except Exception as e:
			logger.error(
				f'Cannot get info about cluster {server_ip} for history',
				server_ip='Roxy-WI server',
				exception=e
			)
			return
	elif service == 'UDP listener':
		try:
			server_id = int(server_ip)
			listener = udp_sql.get_listener(server_id)
			hostname = listener.name
		except Exception as e:
			logger.error(
				f'Cannot get info about Listener {server_ip} for history',
				server_ip='Roxy-WI server',
				exception=e
			)
			return
	else:
		try:
			server = server_sql.get_server_by_ip(server_ip)
			server_id = server.server_id
			hostname = server.hostname
		except Exception as e:
			logger.error(
				f'Cannot get info about {server_ip} for history',
				server_ip='Roxy-WI server',
				exception=e
			)
			return

	try:
		history_sql.insert_action_history(service, action, server_id, user_id, user_ip, server_ip, hostname)
	except Exception as e:
		logger.error(
			'Cannot save a history',
			server_ip='Roxy-WI server',
			exception=e,
			service=service,
			action=action
		)


def get_dick_permit(**kwargs):
	group_id = get_user_group(id=1)
	if check_user_group_for_flask():
		try:
			servers = server_sql.get_dick_permit(group_id, **kwargs)
		except Exception as e:
			raise Exception(e)
		else:
			return servers
	else:
		logging('Roxy-WI server', 'warning: has tried to actions in not his group')
		return []


def get_users_params(**kwargs):
	user_data = get_jwt_token_claims()

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
	user_subscription.setdefault('user_status', roxy_sql.get_user().Status)
	user_subscription.setdefault('user_plan', roxy_sql.get_user().Plan)

	return user_subscription


def return_unsubscribed_user_status() -> dict:
	user_subscription = {'user_status': 0, 'user_plan': 0}

	return user_subscription


def return_user_subscription():
	try:
		user_subscription = return_user_status()
	except Exception as e:
		user_subscription = return_unsubscribed_user_status()
		logging('Roxy-WI server', f'Cannot get a user plan: {e}')

	return user_subscription


def handle_exceptions(ex: Exception, server_ip: str, message: str, **kwargs: Any) -> None:
	"""
	:param server_ip:
	:param ex: The exception that was caught
	:param message: The error message to be logged and raised
	:param kwargs: Additional keyword arguments to be passed to the logging function
	:return: None
	"""
	log_error(ex, server_ip, message, kwargs.get('keep_history', False), kwargs.get('service'))
	raise Exception(f'{message}: {ex}')


def is_user_has_access_to_its_group(user_id: int) -> None:
	if not user_sql.check_user_group(user_id, g.user_params['group_id']) and g.user_params['role'] != 1:
		raise RoxywiGroupMismatch


def is_user_has_access_to_group(user_id: int, group_id: int) -> None:
	if not user_sql.check_user_group(user_id, group_id) and g.user_params['role'] != 1:
		raise RoxywiGroupMismatch


def handle_json_exceptions(ex: Exception, message: str, server_ip='Roxy-WI server') -> dict:
	"""
	Handle an exception and return a JSON error response.

	Args:
		ex: The exception that was raised
		message: Additional information to include in the response
		server_ip: The IP of the server where the error occurred

	Returns:
		A dictionary containing the error response
	"""
	log_error(ex, server_ip, message)
	return ErrorResponse(error=f'{message}: {ex}').model_dump(mode='json')


def handler_exceptions_for_json_data(ex: Exception, main_ex_mes: str = '') -> tuple[dict, int]:
	"""
	Handle an exception and return a JSON error response with an appropriate HTTP status code.

	Args:
		ex: The exception that was raised
		main_ex_mes: Additional information to include in the response

	Returns:
		A tuple containing the error response and HTTP status code
	"""

	# If main_ex_mes is provided, use it as additional_info
	additional_info = main_ex_mes if main_ex_mes else ""

	# Use the centralized error handler
	return handle_exception(ex, additional_info=additional_info)
