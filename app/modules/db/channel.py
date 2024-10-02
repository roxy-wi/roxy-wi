from app.modules.db.db_model import Telegram, Slack, PD, Server, MM
from app.modules.db.common import out_error
from app.modules.roxywi.exception import RoxywiResourceNotFound

models = {
		'telegram': Telegram,
		'slack': Slack,
		'pd': PD,
		'mm': MM
	}


def get_user_receiver_by_group(receiver: str, group: int):
	model = models[receiver]
	try:
		return model.select().where(model.group_id == group).execute()
	except Exception as e:
		out_error(e)


def get_receiver_by_ip(receiver: str, ip: str):
	model = models[receiver]
	try:
		return model.select().join(Server, on=(Server.group_id == model.group_id)).where(Server.ip == ip).execute()
	except Exception as e:
		out_error(e)


def get_receiver_by_id(receiver: str, channel_id: str):
	model = models[receiver]
	try:
		return model.select().where(model.id == channel_id).execute()
	except Exception as e:
		out_error(e)


def select_receiver(receiver: str, channel_id: str):
	model = models[receiver]
	try:
		return model.get(model.id == channel_id)
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def insert_new_receiver(receiver: str, token: str, channel: str, group: str):
	model = models[receiver]
	try:
		return model.insert(token=token, chanel_name=channel, group_id=group).execute()
	except Exception as e:
		out_error(e)


def update_receiver(receiver: str, token: str, channel: str, group: str, channel_id: int) -> None:
	model = models[receiver]
	try:
		model.update(token=token, chanel_name=channel, group_id=group).where(model.id == channel_id).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def delete_receiver(receiver: str, channel_id: int) -> None:
	model = models[receiver]
	try:
		model.delete().where(model.id == channel_id).execute()
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)


def get_receiver_with_group(receiver: str, channel_id: int, group_id: int):
	try:
		model = models[receiver]
		return model.get((model.id == channel_id) & (model.group_id == group_id))
	except model.DoesNotExist:
		raise RoxywiResourceNotFound
	except Exception as e:
		out_error(e)
