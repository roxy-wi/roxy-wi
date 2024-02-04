import os
import glob
from typing import Any

from flask import request

import app.modules.db.sql as sql
import modules.roxy_wi_tools as roxy_wi_tools

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def return_error_message():
	return 'error: All fields must be completed'


def get_user_group(**kwargs) -> str:
	user_group = ''

	try:
		user_group_id = request.cookies.get('group')
		groups = sql.select_groups(id=user_group_id)
		for g in groups:
			if g.group_id == int(user_group_id):
				if kwargs.get('id'):
					user_group = g.group_id
				else:
					user_group = g.name
	except Exception as e:
		raise Exception(f'error: {e}')
	return user_group


def check_user_group_for_flask(**kwargs):
	if kwargs.get('token') is not None:
		return True

	if kwargs.get('user_uuid'):
		group_id = kwargs.get('user_group_id')
		user_uuid = kwargs.get('user_uuid')
		user_id = sql.get_user_id_by_uuid(user_uuid)
	else:
		user_uuid = request.cookies.get('uuid')
		group_id = request.cookies.get('group')
		user_id = sql.get_user_id_by_uuid(user_uuid)

	if sql.check_user_group(user_id, group_id):
		return True
	else:
		logging('Roxy-WI server', ' has tried to actions in not his group ', roxywi=1, login=1)
		return False


def get_user_id(**kwargs):
	if kwargs.get('login'):
		return sql.get_user_id_by_username(kwargs.get('login'))

	user_uuid = request.cookies.get('uuid')

	if user_uuid is not None:
		user_id = sql.get_user_id_by_uuid(user_uuid)

		return user_id


def check_is_server_in_group(server_ip: str) -> bool:
	group_id = get_user_group(id=1)
	servers = sql.select_servers(server=server_ip)
	for s in servers:
		if (s[2] == server_ip and int(s[3]) == int(group_id)) or group_id == 1:
			return True
		else:
			logging('Roxy-WI server', ' has tried to actions in not his group server ', roxywi=1, login=1)
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


def logging(server_ip: str, action: str, **kwargs) -> None:
	login = ''
	cur_date = get_date.return_date('logs')
	cur_date_in_log = get_date.return_date('date_in_log')
	log_path = get_config_var.get_config_var('main', 'log_path')

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

	try:
		user_uuid = request.cookies.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid)
	except Exception:
		if kwargs.get('login'):
			login = kwargs.get('login')

	if kwargs.get('roxywi') == 1:
		if kwargs.get('login'):
			mess = f"{cur_date_in_log} from {ip} user: {login}, group: {user_group}, {action} on: {server_ip}\n"
		else:
			mess = f"{cur_date_in_log} {action} from {ip}\n"
		log_file = f"{log_path}/roxy-wi-{cur_date}.log"
	else:
		mess = f"{cur_date_in_log} from {ip} user: {login}, group: {user_group}, {action} on: {server_ip}\n"
		log_file = f"{log_path}/config_edit-{cur_date}.log"

	if kwargs.get('keep_history'):
		try:
			keep_action_history(kwargs.get('service'), action, server_ip, login, ip)
		except Exception as e:
			print(f'error: Cannot save history: {e}')

	try:
		with open(log_file, 'a') as log:
			log.write(mess)
	except IOError as e:
		print(f'<center><div class="alert alert-danger">Cannot write log. Please check log_path in config {e}</div></center>')


def keep_action_history(service: str, action: str, server_ip: str, login: str, user_ip: str):
	if login != '':
		user_id = sql.get_user_id_by_username(login)
	else:
		user_id = 0
	if user_ip == '':
		user_ip = 'localhost'

	if service == 'HA cluster':
		cluster_name = sql.select_cluster_name(server_ip)
		sql.insert_action_history(service, action, server_ip, user_id, user_ip, server_ip, cluster_name)
	else:
		try:
			server_id = sql.select_server_id_by_ip(server_ip=server_ip)
			hostname = sql.get_hostname_by_server_ip(server_ip)

			sql.insert_action_history(service, action, server_id, user_id, user_ip, server_ip, hostname)
		except Exception as e:
			logging('Roxy-WI server', f'Cannot save a history: {e}', roxywi=1)


def get_dick_permit(**kwargs):
	if kwargs.get('token'):
		token = kwargs.get('token')
	else:
		token = ''

	if not kwargs.get('group_id'):
		try:
			group_id = get_user_group(id=1)
		except Exception as e:
			return str(e)
	else:
		group_id = kwargs.pop('group_id')

	if check_user_group_for_flask(token=token):
		try:
			servers = sql.get_dick_permit(group_id, **kwargs)
		except Exception as e:
			raise Exception(e)
		else:
			return servers
	else:
		print('Atata!')


def get_users_params(**kwargs):
	try:
		user_uuid = request.cookies.get('uuid')
		user = sql.get_user_name_by_uuid(user_uuid)
	except Exception:
		raise Exception('error: Cannot get user UUID')

	try:
		group_id = int(request.cookies.get('group'))
	except Exception as e:
		raise Exception(f'error: Cannot get user group: {e}')

	try:
		role = sql.get_user_role_by_uuid(user_uuid, group_id)
	except Exception:
		raise Exception('error: Cannot get user role')

	try:
		user_id = sql.get_user_id_by_uuid(user_uuid)
	except Exception as e:
		raise Exception(f'error: Cannot get user id {e}')

	try:
		user_services = sql.select_user_services(user_id)
	except Exception as e:
		raise Exception(f'error: Cannot get user services {e}')

	try:
		token = sql.get_token(user_uuid)
	except Exception as e:
		raise Exception(f'error: Cannot get user token {e}')

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
		'user': user,
		'user_uuid': user_uuid,
		'role': role,
		'token': token,
		'servers': servers,
		'user_services': user_services,
		'lang': user_lang,
		'user_id': user_id,
		'group_id': group_id
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
	user_subscription.setdefault('user_status', sql.select_user_status())
	user_subscription.setdefault('user_plan', sql.select_user_plan())

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
	logging(server_ip, f'{message}: {ex}', **kwargs)
	raise Exception(f'{message}: {ex}')
