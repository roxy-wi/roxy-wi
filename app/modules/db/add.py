from typing import Union, Literal
import hashlib

from app.modules.db.db_model import SavedServer, Option, HaproxySection, NginxSection
from app.modules.db.common import out_error
from app.modules.roxywi.class_models import HaproxyConfigRequest, HaproxyGlobalRequest, HaproxyDefaultsRequest, NginxUpstreamRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound

SectionModel = {
	'haproxy': HaproxySection,
	'nginx': NginxSection,
}


def _file_values(service, config_path):
	if service != 'haproxy':
		return {}
	from app.modules.config.haproxy_files import resolve_path
	path = resolve_path(config_path)
	return {'config_path': path, 'file_id': hashlib.sha256(path.encode()).hexdigest()}


def _section_identity(model, server_id, section_type, section_name, service, config_path):
	condition = (model.server_id == server_id) & (model.type == section_type) & (model.name == section_name)
	if service == 'haproxy':
		condition &= model.file_id == _file_values(service, config_path)['file_id']
	return condition


def update_saved_server(server, description, saved_id, group_id):
	try:
		updated = SavedServer.update(server=server, description=description).where(
			(SavedServer.id == saved_id) & (SavedServer.groups == group_id)
		).execute()
		if not updated:
			raise RoxywiResourceNotFound
	except Exception as e:
		if isinstance(e, RoxywiResourceNotFound):
			raise
		out_error(e)


def delete_saved_server(saved_id, group_id):
	try:
		deleted = SavedServer.delete().where(
			(SavedServer.id == saved_id) & (SavedServer.groups == group_id)
		).execute()
		if not deleted:
			raise RoxywiResourceNotFound
	except Exception as e:
		if isinstance(e, RoxywiResourceNotFound):
			raise
		out_error(e)


def delete_option(option_id, group_id):
	try:
		deleted = Option.delete().where((Option.id == option_id) & (Option.groups == group_id)).execute()
		if not deleted:
			raise RoxywiResourceNotFound
	except Exception as e:
		if isinstance(e, RoxywiResourceNotFound):
			raise
		out_error(e)


def insert_new_saved_server(server, description, group):
	try:
		SavedServer.insert(server=server, description=description, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def insert_new_option(saved_option, group):
	try:
		Option.insert(options=saved_option, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_options(**kwargs):
	if kwargs.get('option') and kwargs.get('group') is not None:
		query = Option.select().where(
			(Option.options == kwargs.get('option')) & (Option.groups == kwargs.get('group'))
		)
	elif kwargs.get('option'):
		query = Option.select().where(Option.options == kwargs.get('option'))
	elif kwargs.get('group'):
		query = Option.select().where(
			(Option.groups == kwargs.get('group')) & (Option.options.startswith(kwargs.get('term'))))
	else:
		query = Option.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_options(option, option_id, group_id):
	try:
		updated = Option.update(options=option).where(
			(Option.id == option_id) & (Option.groups == group_id)
		).execute()
		if not updated:
			raise RoxywiResourceNotFound
	except Exception as e:
		if isinstance(e, RoxywiResourceNotFound):
			raise
		out_error(e)
	return True


def select_saved_servers(**kwargs):
	if kwargs.get('server') and kwargs.get('group') is not None:
		query = SavedServer.select().where(
			(SavedServer.server == kwargs.get('server')) & (SavedServer.groups == kwargs.get('group'))
		)
	elif kwargs.get('server'):
		query = SavedServer.select().where(SavedServer.server == kwargs.get('server'))
	elif kwargs.get('group'):
		query = SavedServer.select().where(
			(SavedServer.groups == kwargs.get('group')) & (SavedServer.server.startswith(kwargs.get('term'))))
	else:
		query = SavedServer.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_section(
		server_id: int,
		section_type: str,
		section_name: str,
		body: Union[HaproxyConfigRequest, NginxUpstreamRequest],
		service: Literal['haproxy', 'nginx'] = 'haproxy', config_path: str = None
):
	model = SectionModel[service]
	try:
		return (model.insert(
			server_id=server_id,
			type=section_type,
			name=section_name,
			config=body.model_dump(mode='json'), **_file_values(service, config_path)
		).execute())
	except Exception as e:
		out_error(e)


def insert_or_update_new_section(
		server_id: int,
		section_type: str,
		section_name: str,
		body: Union[HaproxyGlobalRequest, HaproxyDefaultsRequest], config_path: str = None
):
	try:
		return (HaproxySection.insert(
			server_id=server_id,
			type=section_type,
			name=section_name,
			config=body.model_dump(mode='json'), **_file_values('haproxy', config_path)
		).on_conflict('replace').execute())
	except Exception as e:
		out_error(e)


def update_section(
		server_id: int,
		section_type: str,
		section_name: str,
		body: Union[HaproxyConfigRequest, NginxUpstreamRequest],
		service: Literal['haproxy', 'nginx'] = 'haproxy', config_path: str = None
):
	model = SectionModel[service]
	try:
		model.update(
			config=body.model_dump(mode='json')
		).where(
			_section_identity(model, server_id, section_type, section_name, service, config_path)
		).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def get_section(
		server_id: int,
		section_type: str,
		section_name: str,
		service: Literal['haproxy', 'nginx'] = 'haproxy', config_path: str = None
) -> Union[HaproxySection, NginxSection]:
	model = SectionModel[service]
	try:
		return model.get(
			_section_identity(model, server_id, section_type, section_name, service, config_path)
		)
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_section(server_id: int, section_type: str, section_name: str, service: Literal['haproxy', 'nginx'] = 'haproxy', config_path: str = None) -> None:
	model = SectionModel[service]
	try:
		model.delete().where(
			_section_identity(model, server_id, section_type, section_name, service, config_path)
		).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
