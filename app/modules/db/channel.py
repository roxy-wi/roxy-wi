from app.modules.db.db_model import Telegram, Slack, PD, Server
from app.modules.db.common import out_error


def get_user_telegram_by_group(group):
	try:
		return Telegram.select().where(Telegram.groups == group).execute()
	except Exception as e:
		out_error(e)


def get_telegram_by_ip(ip):
	try:
		return Telegram.select().join(Server, on=(Server.groups == Telegram.groups)).where(Server.ip == ip).execute()
	except Exception as e:
		out_error(e)


def get_telegram_by_id(telegram_id):
	try:
		return Telegram.select().where(Telegram.id == telegram_id).execute()
	except Exception as e:
		out_error(e)


def get_user_slack_by_group(group):
	try:
		return Slack.select().where(Slack.groups == group).execute()
	except Exception as e:
		out_error(e)


def get_slack_by_ip(ip):
	try:
		return Slack.select().join(Server, on=(Server.groups == Slack.groups)).where(Server.ip == ip).execute()
	except Exception as e:
		out_error(e)


def get_slack_by_id(slack_id):
	try:
		return Slack.select().where(Slack.id == slack_id).execute()
	except Exception as e:
		out_error(e)


def get_user_pd_by_group(group):
	try:
		return PD.select().where(PD.groups == group).execute()
	except Exception as e:
		out_error(e)


def get_pd_by_ip(ip):
	query = PD.select().join(Server, on=(Server.groups == PD.groups)).where(Server.ip == ip)
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def get_pd_by_id(pd_id):
	try:
		return PD.select().where(PD.id == pd_id).execute()
	except Exception as e:
		out_error(e)


def delete_telegram(telegram_id):
	query = Telegram.delete().where(Telegram.id == telegram_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_telegram(**kwargs):
	if kwargs.get('token'):
		query = Telegram.select().where(Telegram.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = Telegram.select().where(Telegram.id == kwargs.get('id'))
	else:
		query = Telegram.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_telegram(token, channel, group):
	try:
		Telegram.insert(token=token, chanel_name=channel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_telegram(token, channel, group, telegram_id):
	telegram_update = Telegram.update(token=token, chanel_name=channel, groups=group).where(Telegram.id == telegram_id)
	try:
		telegram_update.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def delete_slack(slack_id):
	query = Slack.delete().where(Slack.id == slack_id)
	try:
		query.execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_slack(**kwargs):
	if kwargs.get('token'):
		query = Slack.select().where(Slack.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = Slack.select().where(Slack.id == kwargs.get('id'))
	else:
		query = Slack.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_slack(token, chanel, group):
	try:
		Slack.insert(token=token, chanel_name=chanel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_slack(token, chanel, group, slack_id):
	try:
		return Slack.update(token=token, chanel_name=chanel, groups=group).where(Slack.id == slack_id).execute()
	except Exception as e:
		out_error(e)


def delete_pd(pd_id):
	try:
		PD.delete().where(PD.id == pd_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def select_pd(**kwargs):
	if kwargs.get('token'):
		query = PD.select().where(PD.token == kwargs.get('token'))
	elif kwargs.get('id'):
		query = PD.select().where(PD.id == kwargs.get('id'))
	else:
		query = PD.select()
	try:
		query_res = query.execute()
	except Exception as e:
		out_error(e)
	else:
		return query_res


def insert_new_pd(token, chanel, group):
	try:
		PD.insert(token=token, chanel_name=chanel, groups=group).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True


def update_pd(token, chanel, group, pd_id):
	try:
		PD.update(token=token, chanel_name=chanel, groups=group).where(PD.id == pd_id).execute()
	except Exception as e:
		out_error(e)
		return False
	else:
		return True
