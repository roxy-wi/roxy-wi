import os
import json
import http.cookies

import pika
from jinja2 import Environment, FileSystemLoader

import modules.db.sql as sql
import modules.common.common as common
import modules.roxywi.common as roxywi_common

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
	parameters = pika.ConnectionParameters(
		rabbit_host,
		rabbit_port,
		rabbit_vhost,
		credentials
	)

	connection = pika.BlockingConnection(parameters)
	channel = connection.channel()
	channel.queue_declare(queue=rabbit_queue)
	channel.basic_publish(exchange='', routing_key=rabbit_queue, body=message)

	connection.close()


def alert_routing(
	server_ip: str, service_id: int, group_id: int, level: str, mes: str, alert_type: str
) -> None:
	subject: str = level + ': ' + mes
	server_id: int = sql.select_server_id_by_ip(server_ip)
	checker_settings = sql.select_checker_settings_for_server(service_id, server_id)

	try:
		json_for_sending = {"user_group": group_id, "message": subject}
		send_message_to_rabbit(json.dumps(json_for_sending))
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', 'error: unable to send message: ' + str(e), roxywi=1)

	for setting in checker_settings:
		if alert_type == 'service' and setting.service_alert:
			telegram_send_mess(mes, telegram_channel_id=setting.telegram_id)
			slack_send_mess(mes, slack_channel_id=setting.slack_id)

			if setting.email:
				send_email_to_server_group(subject, mes, group_id)

		if alert_type == 'backend' and setting.backend_alert:
			telegram_send_mess(mes, telegram_channel_id=setting.telegram_id)
			slack_send_mess(mes, slack_channel_id=setting.slack_id)

			if setting.email:
				send_email_to_server_group(subject, mes, group_id)

		if alert_type == 'maxconn' and setting.maxconn_alert:
			telegram_send_mess(mes, telegram_channel_id=setting.telegram_id)
			slack_send_mess(mes, slack_channel_id=setting.slack_id)

			if setting.email:
				send_email_to_server_group(subject, mes, group_id)


def send_email_to_server_group(subject: str, mes: str, group_id: int) -> None:
	try:
		users_email = sql.select_users_emails_by_group_id(group_id)

		for user_email in users_email:
			send_email(user_email.email, subject, mes)
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
	mail_smtp_password = sql.get_setting('mail_smtp_password')

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


def telegram_send_mess(mess, **kwargs):
	import telebot
	from telebot import apihelper
	token_bot = ''
	channel_name = ''

	if kwargs.get('telegram_channel_id') == 0:
		return

	if kwargs.get('telegram_channel_id'):
		telegrams = sql.get_telegram_by_id(kwargs.get('telegram_channel_id'))
	else:
		telegrams = sql.get_telegram_by_ip(kwargs.get('ip'))

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
		bot.send_message(chat_id=channel_name, text=mess)
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)


def slack_send_mess(mess, **kwargs):
	from slack_sdk import WebClient
	from slack_sdk.errors import SlackApiError
	slack_token = ''
	channel_name = ''

	if kwargs.get('slack_channel_id') == 0:
		return

	if kwargs.get('slack_channel_id'):
		slacks = sql.get_slack_by_id(kwargs.get('slack_channel_id'))
	else:
		slacks = sql.get_slack_by_ip(kwargs.get('ip'))

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
		client.chat_postMessage(channel=f'#{channel_name}', text=mess)
	except SlackApiError as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)


def check_rabbit_alert() -> None:
	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_group_id = cookie.get('group')
		user_group_id1 = user_group_id.value
	except Exception as e:
		print(f'error: Cannot send a message {e}')

	try:
		json_for_sending = {"user_group": user_group_id1, "message": 'info: Test message'}
		send_message_to_rabbit(json.dumps(json_for_sending))
	except Exception as e:
		print(f'error: Cannot send a message {e}')


def check_email_alert() -> None:
	subject = 'test message'
	message = 'Test message from Roxy-WI'

	try:
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_uuid = cookie.get('uuid')
		user_uuid_value = user_uuid.value
	except Exception as e:
		print(f'error: Cannot send a message {e}')

	try:
		user_email = sql.select_user_email_by_uuid(user_uuid_value)
	except Exception as e:
		print(f'error: Cannot get a user email: {e}')

	try:
		send_email(user_email, subject, message)
	except Exception as e:
		print(f'error: Cannot send a message {e}')


def add_telegram_channel(token: str, channel: str, group: str, page: str) -> None:
	if token is None or channel is None or group is None:
		print(error_mess)
	else:
		if sql.insert_new_telegram(token, channel, group):
			env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
			template = env.get_template('/new_telegram.html')
			output_from_parsed_template = template.render(groups=sql.select_groups(),
														  telegrams=sql.select_telegram(token=token), page=page)
			print(output_from_parsed_template)
			roxywi_common.logging('Roxy-WI server', f'A new Telegram channel {channel} has been created ', roxywi=1,
								  login=1)


def add_slack_channel(token: str, channel: str, group: str, page: str) -> None:
	if token is None or channel is None or group is None:
		print(error_mess)
	else:
		if sql.insert_new_slack(token, channel, group):
			env = Environment(loader=FileSystemLoader('templates/ajax'), autoescape=True)
			template = env.get_template('/new_slack.html')
			output_from_parsed_template = template.render(groups=sql.select_groups(),
														  slacks=sql.select_slack(token=token), page=page)
			print(output_from_parsed_template)
			roxywi_common.logging('Roxy-WI server', 'A new Slack channel ' + channel + ' has been created ', roxywi=1,
								  login=1)


def delete_telegram_channel(channel_id) -> None:
	telegram = sql.select_telegram(id=channel_id)
	for t in telegram:
		telegram_name = t.token
	if sql.delete_telegram(channel_id):
		print("Ok")
		roxywi_common.logging('Roxy-WI server', f'The Telegram channel {telegram_name} has been deleted ', roxywi=1, login=1)


def delete_slack_channel(channel_id) -> None:
	slack = sql.select_slack(id=channel_id)
	for t in slack:
		slack_name = t.chanel_name
	if sql.delete_slack(channel_id):
		print("Ok")
		roxywi_common.logging('Roxy-WI server', f'The Slack channel {slack_name} has been deleted ', roxywi=1, login=1)


def update_telegram(token: str, channel: str, group: str, user_id: int) -> None:
	sql.update_telegram(token, channel, group, user_id)
	roxywi_common.logging('group ' + group, f'The Telegram token has been updated for channel: {channel}', roxywi=1, login=1)


def update_slack(token: str, channel: str, group: str, user_id: int) -> None:
	sql.update_slack(token, channel, group, user_id)
	roxywi_common.logging(f'group {group}', f'The Slack token has been updated for channel: {channel}', roxywi=1, login=1)