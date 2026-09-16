import json

import pagerduty
import requests
import telebot
from telebot import apihelper
from flask import render_template, abort, g

import app.modules.db.sql as sql
import app.modules.db.user as user_sql
import app.modules.db.group as group_sql
import app.modules.db.server as server_sql
import app.modules.db.channel as channel_sql
import app.modules.db.checker as checker_sql
import app.modules.common.common as common
import app.modules.roxywi.common as roxywi_common
from app.modules.integrations.socket_notifications import publish_socket_notification


class NotificationDeliveryError(RuntimeError):
	pass


def _attempt_delivery(errors, channel, sender, *args, **kwargs):
	try:
		sender(*args, **kwargs)
	except Exception as exc:
		# Provider exceptions may contain token-bearing webhook URLs.
		errors.append(f'{channel} ({type(exc).__name__})')
		roxywi_common.logging('Roxy-WI server', f'error: notification delivery failed: {errors[-1]}', roxywi=1)


def _finish_delivery(errors, raise_on_error):
	if errors and raise_on_error:
		raise NotificationDeliveryError('Notification delivery failed: ' + ', '.join(errors))


def alert_routing(
	server_ip: str, service_id: int, group_id: int, level: str, mes: str, alert_type: str,
	raise_on_error: bool = False,
) -> None:
	subject = level + ': ' + mes
	checker_settings = []
	if service_id != 6:
		server_id = server_sql.get_server_by_ip(server_ip).server_id
		checker_settings = list(checker_sql.select_checker_settings_for_server(service_id, server_id))
	errors = []
	_attempt_delivery(errors, 'Socket', publish_socket_notification, group_id, subject)
	for setting in checker_settings:
		if not getattr(setting, f'{alert_type}_alert', False):
			continue
		for name, sender, channel_id, args in (
			('Telegram', telegram_send_mess, setting.telegram_id, ()),
			('Slack', slack_send_mess, setting.slack_id, ()),
			('PagerDuty', pd_send_mess, setting.pd_id, (server_ip, service_id, alert_type)),
			('Mattermost', mm_send_mess, setting.mm_id, (server_ip, service_id, alert_type)),
		):
			_attempt_delivery(errors, name, sender, mes, level, *args,
							  channel_id=channel_id, raise_on_error=raise_on_error)
		if setting.email:
			_attempt_delivery(errors, 'Email', send_email_to_server_group,
							  subject, mes, level, group_id, raise_on_error=raise_on_error)
	_finish_delivery(errors, raise_on_error)


def portscanner_alert_routing(
	server_ip: str, group_id: int, level: str, mes: str, raise_on_error: bool = False,
) -> None:
	"""Keep unsuccessful notification jobs retryable, while trying every configured channel."""
	errors = []
	_attempt_delivery(errors, 'Socket', publish_socket_notification, group_id, f'{level}: {mes}')
	for sender, name in ((telegram_send_mess, 'Telegram'), (slack_send_mess, 'Slack')):
		_attempt_delivery(errors, name, sender, mes, level, ip=server_ip, raise_on_error=raise_on_error)
	_finish_delivery(errors, raise_on_error)


def send_email_to_server_group(subject: str, mes: str, level: str, group_id: int, raise_on_error=False) -> None:
	try:
		users_email = user_sql.select_users_emails_by_group_id(group_id)
		errors = []
		for user_email in users_email:
			_attempt_delivery(errors, 'Email', send_email, user_email.email, subject,
							  f'{level}: {mes}', raise_on_error=raise_on_error)
		_finish_delivery(errors, raise_on_error)
	except Exception as e:
		if raise_on_error:
			raise NotificationDeliveryError('Email group delivery failed') from None
		roxywi_common.logging('Roxy-WI server', f'error: unable to send email: {e}', roxywi=1)


def send_email(email_to: str, subject: str, message: str, raise_on_error=False) -> None:
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
		with SMTP(mail_smtp_host, mail_smtp_port, timeout=15) as smtp_obj:
			if mail_ssl:
				smtp_obj.starttls()
			smtp_obj.login(mail_smtp_user, mail_smtp_password)
			smtp_obj.send_message(msg)
		roxywi_common.logging('Roxy-WI server', f'An email has been sent to {email_to}', roxywi=1)
	except Exception as e:
		if raise_on_error:
			raise NotificationDeliveryError('Email delivery failed') from None
		roxywi_common.logging('Roxy-WI server', f'error: unable to send email: {e}', roxywi=1)


def telegram_send_mess(mess, level, **kwargs):
	token_bot = ''
	channel_name = ''
	proxy = sql.get_setting('proxy')

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		telegrams = channel_sql.get_receiver_by_id('telegram', kwargs.get('channel_id'))
	else:
		telegrams = list(channel_sql.get_receiver_by_ip('telegram', kwargs.get('ip')))
		if not telegrams:
			return

	for telegram in telegrams:
		token_bot = telegram.token
		channel_name = telegram.chanel_name

	if token_bot == '' or channel_name == '':
		mess = "Can't send message. Add Telegram channel before use alerting at this servers group"
		roxywi_common.logging('Roxy-WI server', mess, roxywi=1)

	if proxy is not None and proxy != '' and proxy != 'None':
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=f'{level}: {mess}')
	except Exception as e:
		if kwargs.get('raise_on_error'):
			raise NotificationDeliveryError('Telegram delivery failed') from None
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
		slacks = channel_sql.get_receiver_by_id('slack', kwargs.get('channel_id'))
	else:
		slacks = list(channel_sql.get_receiver_by_ip('slack', kwargs.get('ip')))
		if not slacks:
			return

	proxy = sql.get_setting('proxy')

	for slack in slacks:
		slack_token = slack.token
		channel_name = slack.chanel_name

	if proxy is not None and proxy != '' and proxy != 'None':
		client = WebClient(token=slack_token, proxy=proxy)
	else:
		client = WebClient(token=slack_token)

	try:
		client.chat_postMessage(channel=f'#{channel_name}', text=f'{level}: {mess}')
	except SlackApiError as e:
		if kwargs.get('raise_on_error'):
			raise NotificationDeliveryError('Slack delivery failed') from None
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def pd_send_mess(mess, level, server_ip=None, service_id=None, alert_type=None, **kwargs):
	token = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		try:
			pds = channel_sql.get_receiver_by_id('pd', kwargs.get('channel_id'))
		except Exception:
			raise NotificationDeliveryError('Cannot load PagerDuty channel') from None
	else:
		try:
			pds = channel_sql.get_receiver_by_ip('pd', kwargs.get('ip'))
		except Exception:
			raise NotificationDeliveryError('Cannot load PagerDuty channel') from None

	for pd in pds:
		token = pd.token

	try:
		proxy = sql.get_setting('proxy')
		session = pagerduty.EventsApiV2Client(token)
		if server_ip:
			dedup_key = f'{server_ip} {service_id} {alert_type}'
		else:
			dedup_key = f'{level}: {mess}'
	except Exception as e:
		if kwargs.get('raise_on_error'):
			raise NotificationDeliveryError('PagerDuty setup failed') from None
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
		if kwargs.get('raise_on_error'):
			raise NotificationDeliveryError('PagerDuty delivery failed') from None
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def mm_send_mess(mess, level, server_ip=None, service_id=None, alert_type=None, **kwargs):
	token = ''

	if kwargs.get('channel_id') == 0:
		return

	if kwargs.get('channel_id'):
		try:
			mms = channel_sql.get_receiver_by_id('mm', kwargs.get('channel_id'))
		except Exception:
			raise NotificationDeliveryError('Cannot load Mattermost channel') from None
	else:
		try:
			mms = channel_sql.get_receiver_by_ip('mm', kwargs.get('ip'))
		except Exception:
			raise NotificationDeliveryError('Cannot load Mattermost channel') from None

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
		response = requests.post(token, headers=headers, data=str(values), proxies=proxy_dict, timeout=15, allow_redirects=False)
		if kwargs.get('raise_on_error') and not 200 <= response.status_code < 300:
			raise NotificationDeliveryError(f'Mattermost rejected notification (HTTP {response.status_code})')
	except Exception as e:
		if kwargs.get('raise_on_error'):
			raise NotificationDeliveryError('Mattermost delivery failed') from None
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		raise Exception(e)


def check_rabbit_alert() -> None:
	try:
		publish_socket_notification(g.user_params['group_id'], 'info: Test message')
	except Exception as e:
		raise Exception(f'Cannot send message {e}')


def check_email_alert() -> str:
	subject = 'test message'
	message = 'Test message from Roxy-WI'

	try:
		user = user_sql.get_user_id(g.user_params['user_id'])
	except Exception as e:
		return f'error: Cannot get a user email: {e}'

	try:
		send_email(user.email, subject, message)
	except Exception as e:
		return f'error: Cannot send a message {e}'

	return 'ok'


def add_receiver(receiver: str, token: str, channel: str, group: str, is_api=False) -> str:
	last_id = channel_sql.insert_new_receiver(receiver, token, channel, group)

	if is_api:
		return last_id
	else:
		lang = roxywi_common.get_user_lang_for_flask()
		new_channel = channel_sql.select_receiver(receiver, last_id)
		groups = group_sql.select_groups()
		roxywi_common.logging('Roxy-WI server', f'A new {receiver.title()} channel {channel} has been created ', roxywi=1, login=1)
		return render_template('ajax/new_receiver.html', groups=groups, lang=lang, channel=new_channel, receiver=receiver)


def delete_receiver_channel(channel_id: int, receiver_name: str) -> None:
	try:
		channel_sql.delete_receiver(receiver_name, channel_id)
	except Exception as e:
		raise e


def update_receiver_channel(receiver_name: str, token: str, channel: str, group: id, channel_id: int) -> None:
	try:
		channel_sql.update_receiver(receiver_name, token, channel, group, channel_id)
	except Exception as e:
		raise e


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
		kwargs.setdefault('telegrams', channel_sql.get_user_receiver_by_group('telegram', user_group))
		kwargs.setdefault('pds', channel_sql.get_user_receiver_by_group('pd', user_group))
		kwargs.setdefault('mms', channel_sql.get_user_receiver_by_group('mm', user_group))
		kwargs.setdefault('groups', group_sql.select_groups())
		kwargs.setdefault('slacks', channel_sql.get_user_receiver_by_group('slack', user_group))
		kwargs.setdefault('user_subscription', user_subscription)
		kwargs.setdefault('user_params', user_params)
		kwargs.setdefault('lang', user_params['lang'])

	return render_template('ajax/channels.html', **kwargs)
