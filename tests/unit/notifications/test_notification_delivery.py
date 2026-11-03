from types import SimpleNamespace
from smtplib import SMTPAuthenticationError

import pytest

from app.modules.tools import alerting


@pytest.fixture(autouse=True)
def quiet_delivery_logs(monkeypatch):
    monkeypatch.setattr(alerting.roxywi_common, 'logging', lambda *args, **kwargs: None)


@pytest.mark.parametrize('alert_type', ['service', 'backend', 'maxconn'])
def test_checker_attempts_other_channels_but_reports_any_failure(monkeypatch, alert_type):
    calls = []
    monkeypatch.setattr(alerting.server_sql, 'get_server_by_ip', lambda _address: SimpleNamespace(server_id=1))
    monkeypatch.setattr(alerting.checker_sql, 'select_checker_settings_for_server', lambda *_args: [
        SimpleNamespace(service_alert=True, backend_alert=True, maxconn_alert=True,
                        telegram_id=1, slack_id=2, pd_id=3, mm_id=4, email=True),
    ])
    monkeypatch.setattr(alerting, 'publish_socket_notification', lambda *_args: calls.append('socket'))

    def fail(*_args, **_kwargs):
        raise RuntimeError('do not expose token')

    monkeypatch.setattr(alerting, 'telegram_send_mess', fail)
    for name in ('slack_send_mess', 'pd_send_mess', 'mm_send_mess', 'send_email_to_server_group'):
        monkeypatch.setattr(alerting, name, lambda *args, _name=name, **kwargs: calls.append(_name))
    with pytest.raises(alerting.NotificationDeliveryError, match='Telegram') as error:
        alerting.alert_routing('192.0.2.1', 1, 1, 'critical', 'down', alert_type, raise_on_error=True)
    assert 'token' not in str(error.value)
    assert len(calls) == 5


def test_email_failure_is_reported_in_strict_mode(monkeypatch):
    settings = {'mail_ssl': False, 'mail_from': 'from@example.test', 'mail_smtp_host': 'smtp.example.test',
                'mail_smtp_port': 25, 'mail_smtp_user': 'mail', 'mail_smtp_password': 'secret-token'}
    monkeypatch.setattr(alerting.sql, 'get_setting', lambda name: settings[name])

    def fail(*_args, **_kwargs):
        raise OSError('server rejected secret-token')

    monkeypatch.setattr('smtplib.SMTP', fail)
    with pytest.raises(alerting.NotificationDeliveryError, match='Email delivery failed') as error:
        alerting.send_email('to@example.test', 'subject', 'body', raise_on_error=True)
    assert 'secret-token' not in str(error.value)


def test_email_group_continues_after_a_recipient_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(alerting.user_sql, 'select_users_emails_by_group_id', lambda _group: [
        SimpleNamespace(email='a@example.test'), SimpleNamespace(email='b@example.test'),
    ])

    def send(address, *_args, **_kwargs):
        calls.append(address)
        if address.startswith('a@'):
            raise RuntimeError('failed')

    monkeypatch.setattr(alerting, 'send_email', send)
    with pytest.raises(alerting.NotificationDeliveryError):
        alerting.send_email_to_server_group('subject', 'body', 'critical', 1, raise_on_error=True)
    assert calls == ['a@example.test', 'b@example.test']


def test_unconfigured_optional_portscanner_channels_are_not_failures(monkeypatch):
    monkeypatch.setattr(alerting.sql, 'get_setting', lambda _name: '')
    monkeypatch.setattr(alerting.channel_sql, 'get_receiver_by_ip', lambda *_args: [])
    monkeypatch.setattr(alerting, 'publish_socket_notification', lambda *_args: None)
    alerting.portscanner_alert_routing('192.0.2.1', 1, 'info', 'ports changed', raise_on_error=True)


def test_mattermost_http_rejection_is_retryable(monkeypatch):
    monkeypatch.setattr(alerting.channel_sql, 'get_receiver_by_id', lambda *_args: [
        SimpleNamespace(token='https://example.test/secret-token', chanel_name='test'),
    ])
    monkeypatch.setattr(alerting.common, 'return_proxy_dict', lambda: {})
    monkeypatch.setattr(alerting.requests, 'post', lambda *args, **kwargs: SimpleNamespace(status_code=503))
    with pytest.raises(alerting.NotificationDeliveryError, match='Mattermost delivery failed'):
        alerting.mm_send_mess('down', 'critical', channel_id=1, raise_on_error=True)


@pytest.fixture
def smtp_settings(monkeypatch):
    settings = {
        'mail_ssl': '0', 'mail_from': 'from@example.test',
        'mail_smtp_host': 'smtp.example.test', 'mail_smtp_port': '25',
        'mail_smtp_user': 'mail', 'mail_smtp_password': "secret'with'quotes",
    }
    monkeypatch.setattr(alerting.sql, 'get_setting', lambda name: settings[name])
    return settings


@pytest.mark.parametrize('tls', ['0', '1'])
@pytest.mark.parametrize('username', ['', 'mail'])
def test_email_respects_tls_and_optional_authentication(monkeypatch, smtp_settings, tls, username):
    smtp_settings.update(mail_ssl=tls, mail_smtp_user=username)
    calls = []

    class Smtp:
        def __init__(self, host, port, timeout):
            calls.append(('connect', host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            calls.append(('tls',))

        def login(self, user, password):
            calls.append(('login', user, password))

        def send_message(self, message):
            assert message['To'] == 'to@example.test'
            assert message['From'] == 'Roxy-WI <from@example.test>'
            calls.append(('send',))

    monkeypatch.setattr('smtplib.SMTP', Smtp)
    alerting.send_email('to@example.test', 'subject', 'body', raise_on_error=True)
    expected = [('connect', 'smtp.example.test', 25, 15)]
    if tls == '1':
        expected.append(('tls',))
    if username:
        expected.append(('login', username, "secret'with'quotes"))
    assert calls == expected + [('send',)]


@pytest.mark.parametrize('field,value', [
    ('mail_smtp_host', '  '), ('mail_from', ''),
    ('mail_smtp_port', 'invalid-secret'), ('mail_ssl', 'invalid-secret'),
])
def test_invalid_smtp_settings_fail_before_connecting(monkeypatch, smtp_settings, field, value):
    smtp_settings[field] = value
    monkeypatch.setattr('smtplib.SMTP', lambda *a, **k: pytest.fail('Invalid SMTP connection'))
    with pytest.raises(alerting.NotificationDeliveryError, match='Invalid SMTP settings') as error:
        alerting.send_email('to@example.test', 'subject', 'body', raise_on_error=True)
    assert field in str(error.value)
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('strict', [False, True])
def test_smtp_failure_keeps_safe_reason_and_code(monkeypatch, smtp_settings, strict):
    logs = []
    monkeypatch.setattr(alerting.roxywi_common, 'logging', lambda *a, **k: logs.append(a[1]))

    def fail(*args, **kwargs):
        raise SMTPAuthenticationError(535, b'Credentials rejected: secret-token')

    monkeypatch.setattr('smtplib.SMTP', fail)
    if strict:
        with pytest.raises(alerting.NotificationDeliveryError) as error:
            alerting.send_email('to@example.test', 'subject', 'body', raise_on_error=True)
        message = str(error.value)
        assert logs == []
    else:
        alerting.send_email('to@example.test', 'subject', 'body')
        assert len(logs) == 1
        message = logs[0]
    assert 'SMTPAuthenticationError (SMTP 535)' in message
    assert 'secret-token' not in message


def test_group_email_failure_is_logged_once_with_the_correct_settings(monkeypatch):
    from app.modules.common.execution_context import group_id

    logs = []
    monkeypatch.setattr(alerting.roxywi_common, 'logging', lambda *a, **k: logs.append(a[1]))
    monkeypatch.setattr(alerting.user_sql, 'select_users_emails_by_group_id', lambda _group: [
        SimpleNamespace(email='a@example.test'), SimpleNamespace(email='b@example.test'),
    ])
    previous_group = group_id.get()
    calls = []

    def send(address, *args, **kwargs):
        calls.append(address)
        assert group_id.get() == 42
        assert kwargs['raise_on_error'] is True
        raise alerting.NotificationDeliveryError('Email delivery failed: SMTPAuthenticationError (SMTP 535)')

    monkeypatch.setattr(alerting, 'send_email', send)
    alerting.send_email_to_server_group('subject', 'body', 'critical', 42)
    assert calls == ['a@example.test', 'b@example.test']
    assert group_id.get() == previous_group
    assert len(logs) == 1
    assert logs[0].count('SMTPAuthenticationError') == 1


def test_email_test_button_reports_delivery_failure(app, monkeypatch):
    from flask import g

    monkeypatch.setattr(alerting.user_sql, 'get_user_id', lambda _id: SimpleNamespace(email='to@example.test'))

    def send(*args, **kwargs):
        assert kwargs['raise_on_error'] is True
        raise alerting.NotificationDeliveryError('Email delivery failed: SMTPAuthenticationError (SMTP 535)')

    monkeypatch.setattr(alerting, 'send_email', send)
    with app.test_request_context():
        g.user_params = {'user_id': 1}
        result = alerting.check_email_alert()
    assert result.startswith('error:')
    assert 'SMTP 535' in result
