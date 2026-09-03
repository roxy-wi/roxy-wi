from __future__ import annotations

import json
import os
from dataclasses import dataclass
from uuid import uuid4

import pika

from app.modules.common.time import utc_iso, utc_now
from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings


@dataclass(frozen=True)
class SocketPublisherSettings:
    connection: RabbitConnectionSettings
    exchange: str = 'roxy.notifications'

    @classmethod
    def load(cls) -> 'SocketPublisherSettings':
        return cls(
            connection=RabbitConnectionSettings.load(),
            exchange=os.environ.get(
                'ROXYWI_NOTIFICATIONS_EXCHANGE',
                'roxy.notifications',
            ),
        )


def build_notification(group_id: int, message: str) -> dict:
    normalized_group_id = int(group_id)
    if normalized_group_id <= 0:
        raise ValueError('group_id must be a positive integer')
    if not isinstance(message, str) or not message.strip():
        raise ValueError('message must be a non-empty string')
    return {
        'event_id': str(uuid4()),
        'type': 'socket.notification',
        'schema_version': 1,
        'source': 'roxy-wi',
        'user_group': normalized_group_id,
        'message': message,
        'created_at': utc_iso(utc_now()),
    }


def publish_socket_notification(
        group_id: int,
        message: str,
        settings: SocketPublisherSettings | None = None,
) -> None:
    settings = settings or SocketPublisherSettings.load()
    payload = build_notification(group_id, message)
    connection = pika.BlockingConnection(settings.connection.parameters())
    try:
        channel = connection.channel()
        channel.exchange_declare(
            exchange=settings.exchange,
            exchange_type='topic',
            durable=True,
        )
        channel.basic_publish(
            exchange=settings.exchange,
            routing_key=f'group.{payload["user_group"]}',
            body=json.dumps(payload, separators=(',', ':')).encode('utf-8'),
            properties=pika.BasicProperties(
                app_id='roxy-wi',
                content_type='application/json',
                content_encoding='utf-8',
                delivery_mode=2,
                message_id=payload['event_id'],
                type=payload['type'],
            ),
        )
    finally:
        if connection.is_open:
            connection.close()
