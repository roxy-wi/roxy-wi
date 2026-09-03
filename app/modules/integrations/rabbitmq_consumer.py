from __future__ import annotations

import os
import signal
import threading
from dataclasses import dataclass

import pika

from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
from app.modules.integrations.service_events import (
    SUPPORTED_WORKER_SERVICES,
    deliver_pending_notifications,
    process_event,
)
from app.modules.roxywi import logger


@dataclass(frozen=True)
class RabbitConsumerSettings:
    host: str
    port: int
    vhost: str
    username: str
    password: str
    exchange: str = 'roxy.events'
    queue: str = 'roxy-wi.service-events'
    dead_letter_exchange: str = 'roxy.events.dlx'
    dead_letter_queue: str = 'roxy-wi.service-events.dlq'
    queue_type: str = 'classic'
    prefetch: int = 50

    @classmethod
    def load(cls) -> 'RabbitConsumerSettings':
        connection = RabbitConnectionSettings.load()
        return cls(
            host=connection.host,
            port=connection.port,
            vhost=connection.vhost,
            username=connection.username,
            password=connection.password,
            exchange=os.environ.get('ROXYWI_EVENTS_EXCHANGE', 'roxy.events'),
            queue=os.environ.get('ROXYWI_EVENTS_QUEUE', 'roxy-wi.service-events'),
            dead_letter_exchange=os.environ.get('ROXYWI_EVENTS_DLX', 'roxy.events.dlx'),
            dead_letter_queue=os.environ.get('ROXYWI_EVENTS_DLQ', 'roxy-wi.service-events.dlq'),
            queue_type=os.environ.get('ROXYWI_RABBITMQ_QUEUE_TYPE', 'classic'),
            prefetch=int(os.environ.get('ROXYWI_EVENTS_PREFETCH', '50')),
        )


def declare_topology(channel, settings: RabbitConsumerSettings) -> None:
    if settings.queue_type not in {'classic', 'quorum'}:
        raise ValueError('ROXYWI_RABBITMQ_QUEUE_TYPE must be classic or quorum')

    channel.exchange_declare(exchange=settings.exchange, exchange_type='topic', durable=True)
    channel.exchange_declare(exchange=settings.dead_letter_exchange, exchange_type='topic', durable=True)
    queue_arguments = {'x-dead-letter-exchange': settings.dead_letter_exchange}
    dead_letter_arguments = {}
    if settings.queue_type == 'quorum':
        queue_arguments['x-queue-type'] = 'quorum'
        dead_letter_arguments['x-queue-type'] = 'quorum'
    channel.queue_declare(queue=settings.queue, durable=True, arguments=queue_arguments)
    channel.queue_declare(
        queue=settings.dead_letter_queue,
        durable=True,
        arguments=dead_letter_arguments or None,
    )
    channel.queue_bind(
        exchange=settings.dead_letter_exchange,
        queue=settings.dead_letter_queue,
        routing_key='#',
    )
    for service in sorted(SUPPORTED_WORKER_SERVICES):
        channel.queue_bind(exchange=settings.exchange, queue=settings.queue, routing_key=f'{service}.#')
    channel.basic_qos(prefetch_count=settings.prefetch)


class ServiceEventConsumer:
    def __init__(self, settings: RabbitConsumerSettings | None = None):
        self.settings = settings or RabbitConsumerSettings.load()
        self._stop_event = threading.Event()
        self._connection = None

    def stop(self, *_args) -> None:
        self._stop_event.set()
        connection = self._connection
        if connection is not None and connection.is_open:
            connection.add_callback_threadsafe(connection.close)

    def _parameters(self) -> pika.ConnectionParameters:
        credentials = pika.PlainCredentials(self.settings.username, self.settings.password)
        return pika.ConnectionParameters(
            host=self.settings.host,
            port=self.settings.port,
            virtual_host=self.settings.vhost,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=30,
        )

    def _message(self, channel, method, _properties, body) -> None:
        try:
            result = process_event(body)
        except (ValueError, UnicodeError) as exc:
            logger.warning(f'Rejecting invalid service event: {exc}')
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            return
        except Exception as exc:
            logger.error(f'Cannot persist service event: {exc}')
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return

        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f'Processed {result.kind} event (created={result.created})')
        try:
            deliver_pending_notifications(limit=20)
        except Exception as exc:
            logger.error(f'Cannot process service-event notification outbox: {exc}')

    def consume_once(self) -> None:
        self._connection = pika.BlockingConnection(self._parameters())
        try:
            channel = self._connection.channel()
            declare_topology(channel, self.settings)
            channel.basic_consume(
                queue=self.settings.queue,
                on_message_callback=self._message,
                auto_ack=False,
            )
            deliver_pending_notifications(limit=100)
            channel.start_consuming()
        finally:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
            self._connection = None

    def run(self) -> None:
        delay = 1
        while not self._stop_event.is_set():
            try:
                self.consume_once()
                delay = 1
            except KeyboardInterrupt:
                self.stop()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.error(f'Service-event consumer disconnected: {exc}; retrying in {delay}s')
                self._stop_event.wait(delay)
                delay = min(delay * 2, 30)


def run_consumer() -> None:
    consumer = ServiceEventConsumer()
    signal.signal(signal.SIGTERM, consumer.stop)
    signal.signal(signal.SIGINT, consumer.stop)
    consumer.run()
