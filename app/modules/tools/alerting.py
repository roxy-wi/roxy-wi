import json

import pika
import pdpyras
import requests
import telebot
from telebot import apihelper
from flask import render_template, request, abort

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.channel as channel_sql
import app.modules.db.checker as checker_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common

error_mess = common.error_mess


def send_message_to_rabbit(message: str, **kwargs) -> None:
	rabbit_user = sql.get_setting('rabbitmq_user')
	rabbit_password = sql.get_setting('rabbitmq_password')
	rabbit_host = sql.get_setting('rabbitmq_host')
	rabbit_port = sql.get_setting('rabbitmq_port')
	rabbit_vhost = sql.get_setting('rabbitmq_vhost')
	if kwargs.get('rabbit_queue'):
		rabbit_queue = kwargs.get('rabbit_queue')
	else:
		rabbit_queue = sql.get_setting('rabbitmq_queue')

	credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
	try:
		parameters = pika.ConnectionParameters(
			rabbit_host,
			rabbit_port,
			rabbit_vhost,
			credentials
		)
		connection = pika.BlockingConnection(parameters)
		channel = connection.channel()
	except Exception as e:
		raise Exception(f'RabbitMQ connection error {e}')

	channel.queue_declare(queue=rabbit_queue)
	channel.basic_publish(exchange='', routing_key=rabbit_queue, body=message)

	connection.close()


def alert_routing(
	server_ip: str, service_id: int, group_id: int, level: str, mes: str, alert_type: str
) -> None:
	subject: str = level + ': ' + mes
	server_id: int = server_sql.select_server_id_by_ip(server_ip)
	checker_settings = checker_sql.select_checker_settings_for_server(service_id, server_id)

	try:
		json_for_sending = {"user_group": group_id, "message": subject}
		send_message_to_rabbit(json.dumps(json_for_sending))
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: unable to send message: {e}', roxywi=1)

	for setting in checker_settings:
		if alert_type == 'service' and setting.service_alert:
			try:
				telegram_send_mess(mes, level, channel_id=setting.telegram_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Telegram: {e}', roxywi=1)
			try:
				slack_send_mess(mes, level, channel_id=setting.slack_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Slack: {e}', roxywi=1)
			try:
				pd_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.pd_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to PagerDuty: {e}', roxywi=1)
			try:
				mm_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.mm_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Mattermost: {e}', roxywi=1)

			if setting.email:
				send_email_to_server_group(subject, mes, level, group_id)

		if alert_type == 'backend' and setting.backend_alert:
			try:
				telegram_send_mess(mes, level, channel_id=setting.telegram_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Telegram: {e}', roxywi=1)
			try:
				slack_send_mess(mes, level, channel_id=setting.slack_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Slack: {e}', roxywi=1)
			try:
				pd_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.pd_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to PagerDuty: {e}', roxywi=1)
			try:
				mm_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.mm_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Mattermost: {e}', roxywi=1)

			if setting.email:
				send_email_to_server_group(subject, mes, level, group_id)

		if alert_type == 'maxconn' and setting.maxconn_alert:
			try:
				telegram_send_mess(mes, level, channel_id=setting.telegram_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Telegram: {e}', roxywi=1)
			try:
				slack_send_mess(mes, level, channel_id=setting.slack_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Slack: {e}', roxywi=1)
			try:
				pd_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.pd_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to PagerDuty: {e}', roxywi=1)
			try:
				mm_send_mess(mes, level, server_ip, service_id, alert_type, channel_id=setting.mm_id)
			except Exception as e:
				roxywi_common.logging('Roxy-WI server', f'error: unable to send message to Mattermost: {e}', roxywi=1)

			if setting.email:
				send_email_to_server_group(subject, mes, level, group_id)


def send_email_to_server_group(subject: str, mes: str, level: str, group_id: int) -> None:
	try:
		users_email = user_sql.select_users_emails_by_group_id(group_id)

		for user_email in users_email:
			send_email(user_email.email, subject, f'{level}: {mes}')
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: unable to send email: {e}', roxywi=1)


def send_email(email_to: str, subject: str, message: str) -> None:
	from smtplib import SMTP

	try:
		from email.MIMEText import MIMEText
	except Exception:
		from email.mime.text import MIMEText

	mail_ssl = sql.get_setting('mail_ssl')
	mail_from = sql.get_setting('mail_from')
	mail_smtp_host = sql.get_setting('mail_smtp_host')
	mail_smtp_port = sql.get_setting('mail_smtp_port')
	mail_smtp_user = sql.get_setting('mail_smtp_user')
	mail_smtp_password = sql.get_setting('mail_smtp_password').replace("'", "")

	msg = MIMEText(message)
	msg['Subject'] = f'Roxy-WI: {subject}'
	msg['From'] = f'Roxy-WI <{mail_from}>'
	msg['To'] = email_to

	try:
		smtp_obj = SMTP(mail_smtp_host, mail_smtp_port)
		if mail_ssl:
			smtp_obj.starttls()
		smtp_obj.login(mail_smtp_user, mail_smtp_password)
		smtp_obj.send_message(msg)
		roxywi_common.logging('Roxy-WI server', f'An email has been sent to {email_to}', roxywi=1)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', f'error: unable to send email: {e}', roxywi=1)


def telegram_send_mess(mess, level, **kwargs):
	token_bot = ''
	channel_name = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		telegrams = channel_sql.get_telegram_by_id(kwargs.get('channel_id'))
	else:
		telegrams = channel_sql.get_telegram_by_ip(kwargs.get('ip'))

	proxy = sql.get_setting('proxy')

	for telegram in telegrams:
		token_bot = telegram.token
		channel_name = telegram.chanel_name

	if token_bot == '' or channel_name == '':
		mess = " Can't send message. Add Telegram channel before use alerting at this servers group"
		roxywi_common.logging('Roxy-WI server', mess, roxywi=1)

	if proxy is not None and proxy != '' and proxy != 'None':
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=f'{level}: {mess}')
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def slack_send_mess(mess, level, **kwargs):
	from slack_sdk import WebClient
	from slack_sdk.errors import SlackApiError
	slack_token = ''
	channel_name = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		slacks = channel_sql.get_slack_by_id(kwargs.get('channel_id'))
	else:
		slacks = channel_sql.get_slack_by_ip(kwargs.get('ip'))

	proxy = sql.get_setting('proxy')

	for slack in slacks:
		slack_token = slack.token
		channel_name = slack.chanel_name

	if proxy is not None and proxy != '' and proxy != 'None':
		proxies = dict(https=proxy, http=proxy)
		client = WebClient(token=slack_token, proxies=proxies)
	else:
		client = WebClient(token=slack_token)

	try:
		client.chat_postMessage(channel=f'#{channel_name}', text=f'{level}: {mess}')
	except SlackApiError as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def pd_send_mess(mess, level, server_ip=None, service_id=None, alert_type=None, **kwargs):
	token = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		try:
			pds = channel_sql.get_pd_by_id(kwargs.get('channel_id'))
		except Exception as e:
			print(e)
	else:
		try:
			pds = channel_sql.get_pd_by_ip(kwargs.get('ip'))
		except Exception as e:
			print(e)

	for pd in pds:
		token = pd.token

	try:
		proxy = sql.get_setting('proxy')
		session = pdpyras.EventsAPISession(token)
		dedup_key = f'{server_ip} {service_id} {alert_type}'
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)

	if proxy is not None and proxy != '' and proxy != 'None':
		proxies = dict(https=proxy, http=proxy)
		session.proxies.update(proxies)

	try:
		if level == 'info':
			session.resolve(dedup_key)
		else:
			session.trigger(mess, 'Roxy-WI', dedup_key=dedup_key, severity=level, custom_details={'server': server_ip, 'alert': mess})
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def mm_send_mess(mess, level, server_ip=None, service_id=None, alert_type=None, **kwargs):
	token = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		try:
			mms = channel_sql.get_mm_by_id(kwargs.get('channel_id'))
		except Exception as e:
			print(e)
	else:
		try:
			mms = channel_sql.get_mm_by_ip(kwargs.get('ip'))
		except Exception as e:
			print(e)

	for pd in mms:
		token = pd.token
		channel = pd.chanel_name

	headers = {'Content-Type': 'application/json'}
	if level == "info":
		color = "51A347"
	else:
		color = "c20707"
	attach = {
		"fallback": f"{alert_type}",
		"color": f"#{color}",
		"text": f"{mess}",
		"author_name": "Roxy-WI",
		"title": f"{level} alert",
		"fields": [
			{
				"short": "true",
				"title": "Level",
				"value": f"{level}",
			},
			{
				"short": "true",
				"title": "Server",
				"value": f"{server_ip}",
				},
			]
	}
	attach = str(json.dumps(attach))
	values = f'{{"channel": "{channel}", "username": "Roxy-WI", "attachments": [{attach}]}}'
	proxy_dict = common.return_proxy_dict()
	try:
		requests.post(token, headers=headers, data=str(values), proxies=proxy_dict)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def check_rabbit_alert() -> None:
	try:
		user_group_id = request.cookies.get('group')
	except Exception as e:
		raise Exception(f'Cannot get user group {e}')

	try:
		json_for_sending = {"user_group": user_group_id, "message": 'info: Test message'}
		send_message_to_rabbit(json.dumps(json_for_sending))
	except Exception as e:
		raise Exception(f'Cannot send message {e}')


def check_email_alert() -> None:
	subject = 'test message'
	message = 'Test message from Roxy-WI'

	try:
		user_uuid = request.cookies.get('uuid')
	except Exception as e:
		raise Exception(f'Cannot send a message {e}')

	try:
		user_email = user_sql.select_user_email_by_uuid(user_uuid)
	except Exception as e:
		raise Exception(f'Cannot get a user email: {e}')

	try:
		send_email(user_email, subject, message)
	except Exception as e:
		raise Exception('Cannot send a message {e}')


def add_telegram_channel(token: str, channel: str, group: str) -> str:
	if token is None or channel is None or group is None:
		return error_mess
	else:
		if channel_sql.insert_new_telegram(token, channel, group):
			lang = roxywi_common.get_user_lang_for_flask()
			channels = channel_sql.select_telegram(token=token)
			groups = group_sql.select_groups()
			roxywi_common.logging('Roxy-WI server', f'A new Telegram channel {channel} has been created ', roxywi=1, login=1)

			return render_template('ajax/new_receiver.html', groups=groups, lang=lang, channels=channels, receiver='telegram')


def add_slack_channel(token: str, channel: str, group: str) -> str:
	if token is None or channel is None or group is None:
		return error_mess
	else:
		if channel_sql.insert_new_slack(token, channel, group):
			lang = roxywi_common.get_user_lang_for_flask()
			channels = channel_sql.select_slack(token=token)
			groups = group_sql.select_groups()
			roxywi_common.logging('Roxy-WI server', f'A new Slack channel {channel} has been created ', roxywi=1, login=1)
			return render_template('ajax/new_receiver.html', groups=groups, lang=lang, channels=channels, receiver='slack')


def add_pd_channel(token: str, channel: str, group: str) -> str:
	if token is None or channel is None or group is None:
		return error_mess
	else:
		if channel_sql.insert_new_pd(token, channel, group):
			lang = roxywi_common.get_user_lang_for_flask()
			channels = channel_sql.select_pd(token=token)
			groups = group_sql.select_groups()
			roxywi_common.logging('Roxy-WI server', f'A new PagerDuty channel {channel} has been created ', roxywi=1, login=1)
			return render_template('ajax/new_receiver.html', groups=groups, lang=lang, channels=channels, receiver='pd')


def add_mm_channel(token: str, channel: str, group: str) -> str:
	if token is None or channel is None or group is None:
		return error_mess
	else:
		if channel_sql.insert_new_mm(token, channel, group):
			lang = roxywi_common.get_user_lang_for_flask()
			channels = channel_sql.select_mm(token=token)
			groups = group_sql.select_groups()
			roxywi_common.logging('Roxy-WI server', f'A new Mattermost channel {channel} has been created ', roxywi=1, login=1)
			return render_template('ajax/new_receiver.html', groups=groups, lang=lang, channels=channels, receiver='mm')


def delete_telegram_channel(channel_id) -> str:
	telegram = channel_sql.select_telegram(id=channel_id)
	channel_name = ''
	for t in telegram:
		channel_name = t.token
	if channel_sql.delete_telegram(channel_id):
		roxywi_common.logging('Roxy-WI server', f'The Telegram channel {channel_name} has been deleted ', roxywi=1, login=1)
		return 'ok'


def delete_slack_channel(channel_id) -> None:
	slack = channel_sql.select_slack(id=channel_id)
	channel_name = ''
	for t in slack:
		channel_name = t.chanel_name
	if channel_sql.delete_slack(channel_id):
		roxywi_common.logging('Roxy-WI server', f'The Slack channel {channel_name} has been deleted ', roxywi=1, login=1)


def delete_pd_channel(channel_id) -> None:
	pd = channel_sql.select_pd(id=channel_id)
	channel_name = ''
	for t in pd:
		channel_name = t.chanel_name
	if channel_sql.delete_pd(channel_id):
		roxywi_common.logging('Roxy-WI server', f'The PageDuty channel {channel_name} has been deleted ', roxywi=1, login=1)


def delete_mm_channel(channel_id) -> None:
	pd = channel_sql.select_mm(id=channel_id)
	channel_name = ''
	for t in pd:
		channel_name = t.chanel_name
	if channel_sql.delete_mm(channel_id):
		roxywi_common.logging('Roxy-WI server', f'The Mattermost channel {channel_name} has been deleted ', roxywi=1, login=1)


def update_telegram(token: str, channel: str, group: int, user_id: int) -> None:
	channel_sql.update_telegram(token, channel, group, user_id)
	roxywi_common.logging(f'group {group}', f'The Telegram token has been updated for channel: {channel}', roxywi=1, login=1)


def update_slack(token: str, channel: str, group: int, user_id: int) -> None:
	channel_sql.update_slack(token, channel, group, user_id)
	roxywi_common.logging(f'group {group}', f'The Slack token has been updated for channel: {channel}', roxywi=1, login=1)


def update_pd(token: str, channel: str, group: int, user_id: int) -> None:
	channel_sql.update_pd(token, channel, group, user_id)
	roxywi_common.logging(f'group {group}', f'The PagerDuty token has been updated for channel: {channel}', roxywi=1, login=1)


def update_mm(token: str, channel: str, group: int, user_id: int) -> None:
	channel_sql.update_mm(token, channel, group, user_id)
	roxywi_common.logging(f'group {group}', f'The Mattermost token has been updated for channel: {channel}', roxywi=1, login=1)


def delete_receiver_channel(channel_id: int, receiver_name: str) -> None:
	delete_functions = {
		"telegram": delete_telegram_channel,
		"slack": delete_slack_channel,
		"pd": delete_pd_channel,
		"mm": delete_mm_channel,
	}
	return delete_functions[receiver_name](channel_id)


def add_receiver_channel(receiver_name: str, token: str, channel: str, group: id) -> str:
	add_functions = {
		"telegram": add_telegram_channel,
		"slack": add_slack_channel,
		"pd": add_pd_channel,
		"mm": add_mm_channel,
	}

	try:
		return add_functions[receiver_name](token, channel, group)
	except Exception as e:
		raise Exception(e)


def update_receiver_channel(receiver_name: str, token: str, channel: str, group: id, user_id: int) -> None:
	update_functions = {
		"telegram": update_telegram,
		"slack": update_slack,
		"pd": update_pd,
		"mm": update_mm,
	}
	return update_functions[receiver_name](token, channel, group, user_id)


def check_receiver(channel_id: int, receiver_name: str) -> None:
	functions = {
		"telegram": telegram_send_mess,
		"slack": slack_send_mess,
		"pd": pd_send_mess,
		"mm": mm_send_mess,
	}
	mess = 'Test message from Roxy-WI'

	if receiver_name == 'pd':
		level = 'warning'
	else:
		level = 'info'

	try:
		functions[receiver_name](mess, level, channel_id=channel_id)
	except Exception as e:
		raise Exception(e)


def load_channels():
	try:
		user_subscription = roxywi_common.return_user_status()
	except Exception as e:
		user_subscription = roxywi_common.return_unsubscribed_user_status()
		roxywi_common.logging('Roxy-WI server', f'Cannot get a user plan: {e}', roxywi=1)

	try:
		user_params = roxywi_common.get_users_params()
	except Exception:
		abort(403)

	kwargs = {
		'user_subscription': user_subscription,
		'user_params': user_params,
		'lang': user_params['lang']
	}

	if user_subscription['user_status']:
		user_group = roxywi_common.get_user_group(id=1)
		kwargs.setdefault('telegrams', channel_sql.get_user_telegram_by_group(user_group))
		kwargs.setdefault('pds', channel_sql.get_user_pd_by_group(user_group))
		kwargs.setdefault('mms', channel_sql.get_user_mm_by_group(user_group))
		kwargs.setdefault('groups', group_sql.select_groups())
		kwargs.setdefault('slacks', channel_sql.get_user_slack_by_group(user_group))
		kwargs.setdefault('user_subscription', user_subscription)
		kwargs.setdefault('user_params', user_params)
		kwargs.setdefault('lang', user_params['lang'])

	return render_template('ajax/channels.html', **kwargs)
