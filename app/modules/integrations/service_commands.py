from __future__ import annotations

import os
from dataclasses import dataclass

import pika

from app.modules.common.time import utc_now
import app.modules.db.service_command as command_sql
from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings


@dataclass(frozen=True)
class RabbitPublisherSettings:
    host: str
    port: int
    vhost: str
    username: str
    password: str
    exchange: str = 'roxy.commands'
    queue: str = 'roxy-checker.commands'
    metrics_queue: str = 'roxy-metrics.commands'
    portscanner_queue: str = 'roxy-portscanner.commands'
    dead_letter_exchange: str = 'roxy.commands.dlx'
    dead_letter_queue: str = 'roxy-checker.commands.dlq'
    metrics_dead_letter_queue: str = 'roxy-metrics.commands.dlq'
    portscanner_dead_letter_queue: str = 'roxy-portscanner.commands.dlq'
    queue_type: str = 'classic'

    @classmethod
    def load(cls) -> 'RabbitPublisherSettings':
        connection = RabbitConnectionSettings.load()
        return cls(
            host=connection.host,
            port=connection.port,
            vhost=connection.vhost,
            username=connection.username,
            password=connection.password,
            exchange=os.environ.get('ROXYWI_COMMANDS_EXCHANGE', 'roxy.commands'),
            queue=os.environ.get('ROXYWI_CHECKER_COMMANDS_QUEUE', 'roxy-checker.commands'),
            metrics_queue=os.environ.get('ROXYWI_METRICS_COMMANDS_QUEUE', 'roxy-metrics.commands'),
            portscanner_queue=os.environ.get(
                'ROXYWI_PORTSCANNER_COMMANDS_QUEUE', 'roxy-portscanner.commands'
            ),
            dead_letter_exchange=os.environ.get('ROXYWI_COMMANDS_DLX', 'roxy.commands.dlx'),
            dead_letter_queue=os.environ.get('ROXYWI_CHECKER_COMMANDS_DLQ', 'roxy-checker.commands.dlq'),
            metrics_dead_letter_queue=os.environ.get(
                'ROXYWI_METRICS_COMMANDS_DLQ', 'roxy-metrics.commands.dlq'
            ),
            portscanner_dead_letter_queue=os.environ.get(
                'ROXYWI_PORTSCANNER_COMMANDS_DLQ', 'roxy-portscanner.commands.dlq'
            ),
            queue_type=os.environ.get('ROXYWI_RABBITMQ_QUEUE_TYPE', 'classic'),
        )


def declare_command_topology(channel, settings: RabbitPublisherSettings) -> None:
    if settings.queue_type not in {'classic', 'quorum'}:
        raise ValueError('ROXYWI_RABBITMQ_QUEUE_TYPE must be classic or quorum')
    channel.exchange_declare(exchange=settings.exchange, exchange_type='topic', durable=True)
    channel.exchange_declare(
        exchange=settings.dead_letter_exchange,
        exchange_type='topic',
        durable=True,
    )
    queue_arguments = {'x-dead-letter-exchange': settings.dead_letter_exchange}
    dead_letter_arguments = None
    if settings.queue_type == 'quorum':
        queue_arguments['x-queue-type'] = 'quorum'
        dead_letter_arguments = {'x-queue-type': 'quorum'}
    for queue, routing_key, dead_letter_queue in (
        (settings.queue, 'checker.assignment.apply', settings.dead_letter_queue),
        (settings.metrics_queue, 'metrics.assignment.apply', settings.metrics_dead_letter_queue),
        (
            settings.portscanner_queue,
            'portscanner.assignment.apply',
            settings.portscanner_dead_letter_queue,
        ),
    ):
        channel.queue_declare(queue=queue, durable=True, arguments=queue_arguments)
        channel.queue_bind(exchange=settings.exchange, queue=queue, routing_key=routing_key)
        channel.queue_declare(
            queue=dead_letter_queue,
            durable=True,
            arguments=dead_letter_arguments,
        )
        channel.queue_bind(
            exchange=settings.dead_letter_exchange,
            queue=dead_letter_queue,
            routing_key='#',
        )


def publish_pending_commands(
        limit: int = 100,
        settings: RabbitPublisherSettings | None = None,
) -> int:
    commands = command_sql.pending_commands(limit=limit)
    if not commands:
        return 0

    settings = settings or RabbitPublisherSettings.load()
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=settings.host,
        port=settings.port,
        virtual_host=settings.vhost,
        credentials=pika.PlainCredentials(settings.username, settings.password),
        heartbeat=30,
        blocked_connection_timeout=30,
    ))
    published = 0
    try:
        channel = connection.channel()
        declare_command_topology(channel, settings)
        channel.confirm_delivery()
        for command in commands:
            try:
                confirmed = channel.basic_publish(
                    exchange=settings.exchange,
                    routing_key=command.routing_key,
                    body=command.payload.encode('utf-8'),
                    properties=pika.BasicProperties(
                        app_id='roxy-wi',
                        content_type='application/json',
                        content_encoding='utf-8',
                        delivery_mode=2,
                        message_id=command.command_id,
                        type=command.command_type,
                    ),
                    mandatory=True,
                )
                if confirmed is False:
                    raise RuntimeError('RabbitMQ did not confirm the command')
            except Exception as exc:
                command_sql.mark_failed(command.command_id, str(exc), utc_now())
            else:
                command_sql.mark_published(command.command_id, utc_now())
                published += 1
    finally:
        if connection.is_open:
            connection.close()
    return published
