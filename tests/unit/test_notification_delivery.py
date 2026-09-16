from types import SimpleNamespace

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
