import json

import pytest

from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
from app.modules.integrations.socket_notifications import (
    SocketPublisherSettings,
    build_notification,
    publish_socket_notification,
)


class RecordingChannel:
    def __init__(self):
        self.calls = []

    def exchange_declare(self, **kwargs):
        self.calls.append(('exchange_declare', kwargs))

    def basic_publish(self, **kwargs):
        self.calls.append(('basic_publish', kwargs))

    def confirm_delivery(self):
        self.calls.append(('confirm_delivery', {}))


class RecordingConnection:
    def __init__(self, channel):
        self._channel = channel
        self.is_open = True

    def channel(self):
        return self._channel

    def close(self):
        self.is_open = False


def test_notification_contract_rejects_invalid_identity_or_message():
    with pytest.raises(ValueError, match='positive integer'):
        build_notification(0, 'hello')
    with pytest.raises(ValueError, match='non-empty'):
        build_notification(1, '  ')


def test_notification_is_published_to_group_topic(monkeypatch):
    channel = RecordingChannel()
    connection = RecordingConnection(channel)
    monkeypatch.setattr(
        'app.modules.integrations.socket_notifications.pika.BlockingConnection',
        lambda _parameters: connection,
    )
    settings = SocketPublisherSettings(
        connection=RabbitConnectionSettings(
            host='rabbitmq',
            port=5672,
            vhost='/',
            username='roxy-wi',
            password='secret',
        ),
        exchange='roxy.notifications',
    )

    publish_socket_notification(7, 'critical: HAProxy is down', settings)

    declaration = channel.calls[0]
    assert declaration == (
        'exchange_declare',
        {'exchange': 'roxy.notifications', 'exchange_type': 'topic', 'durable': True},
    )
    assert channel.calls[1] == ('confirm_delivery', {})
    publish = channel.calls[2][1]
    payload = json.loads(publish['body'])
    assert publish['exchange'] == 'roxy.notifications'
    assert publish['routing_key'] == 'group.7'
    assert publish['properties'].content_type == 'application/json'
    assert publish['properties'].delivery_mode == 2
    assert payload['type'] == 'socket.notification'
    assert payload['schema_version'] == 1
    assert payload['user_group'] == 7
    assert payload['message'] == 'critical: HAProxy is down'
    assert payload['created_at'].endswith('Z')
    assert connection.is_open is False
