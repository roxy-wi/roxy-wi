from typing import Union, Literal

from app.modules.db.db_model import SavedServer, Option, HaproxySection, NginxSection
from app.modules.db.common import out_error
from app.modules.roxywi.class_models import HaproxyConfigRequest, HaproxyGlobalRequest, HaproxyDefaultsRequest, NginxUpstreamRequest
from app.modules.roxywi.exception import RoxywiResourceNotFound

SectionModel = {
	'haproxy': HaproxySection,
	'nginx': NginxSection,
}


def update_saved_server(server, description, saved_id):
	try:
		SavedServer.update(server=server, description=description).where(SavedServer.id == saved_id).execute()
	except SavedServer.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_saved_server(saved_id):
	try:
		SavedServer.delete().where(SavedServer.id == saved_id).execute()
	except SavedServer.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_option(option_id):
	try:
		Option.delete().where(Option.id == option_id).execute()
	except Exception as e:
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
	if kwargs.get('option'):
		query = Option.select().where(Option.options == kwargs.get('option'))
	elif kwargs.get('group'):
		query = Option.select(Option.options).where(
			(Option.groups == kwargs.get('group')) & (Option.options.startswith(kwargs.get('term'))))
	else:
		query = Option.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def update_options(option, option_id):
	try:
		Option.update(options=option).where(Option.id == option_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_saved_servers(**kwargs):
	if kwargs.get('server'):
		query = SavedServer.select().where(SavedServer.server == kwargs.get('server'))
	elif kwargs.get('group'):
		query = SavedServer.select(SavedServer.server, SavedServer.description).where(
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
		service: Literal['haproxy', 'nginx'] = 'haproxy'
):
	model = SectionModel[service]
	try:
		return (model.insert(
			server_id=server_id,
			type=section_type,
			name=section_name,
			config=body.model_dump(mode='json')
		).execute())
	except Exception as e:
		out_error(e)


def insert_or_update_new_section(
		server_id: int,
		section_type: str,
		section_name: str,
		body: Union[HaproxyGlobalRequest, HaproxyDefaultsRequest]
):
	try:
		return (HaproxySection.insert(
			server_id=server_id,
			type=section_type,
			name=section_name,
			config=body.model_dump(mode='json')
		).on_conflict('replace').execute())
	except Exception as e:
		out_error(e)


def update_section(
		server_id: int,
		section_type: str,
		section_name: str,
		body: Union[HaproxyConfigRequest, NginxUpstreamRequest],
		service: Literal['haproxy', 'nginx'] = 'haproxy'
):
	model = SectionModel[service]
	try:
		model.update(
			config=body.model_dump(mode='json')
		).where(
			(model.server_id == server_id) & (model.type == section_type) & (model.name == section_name)
		).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def get_section(
		server_id: int,
		section_type: str,
		section_name: str,
		service: Literal['haproxy', 'nginx'] = 'haproxy'
) -> Union[HaproxySection, NginxSection]:
	model = SectionModel[service]
	try:
		return model.get(
			(model.server_id == server_id)
			& (model.type == section_type)
			& (model.name == section_name)
		)
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_section(server_id: int, section_type: str, section_name: str, service: Literal['haproxy', 'nginx'] = 'haproxy') -> None:
	model = SectionModel[service]
	try:
		model.delete().where(
			(model.server_id == server_id)
			& (model.type == section_type)
			& (model.name == section_name)
		).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
