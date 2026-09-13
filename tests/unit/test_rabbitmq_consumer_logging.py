from types import SimpleNamespace

from app.modules.integrations import rabbitmq_consumer


class ChannelStub:
    def __init__(self):
        self.acknowledged = []

    def basic_ack(self, delivery_tag):
        self.acknowledged.append(delivery_tag)


def test_successful_service_event_is_logged_at_debug(monkeypatch):
    debug_messages = []
    channel = ChannelStub()
    consumer = rabbitmq_consumer.ServiceEventConsumer(
        rabbitmq_consumer.RabbitConsumerSettings(
            host='rabbitmq',
            port=5672,
            vhost='/',
            username='roxy-wi',
            password='secret',
        )
    )
    monkeypatch.setattr(
        rabbitmq_consumer,
        'process_event',
        lambda body: SimpleNamespace(kind='worker_heartbeat', created=True),
    )
    monkeypatch.setattr(
        rabbitmq_consumer,
        'deliver_pending_notifications',
        lambda limit: None,
    )
    monkeypatch.setattr(rabbitmq_consumer.logger, 'debug', debug_messages.append)
    monkeypatch.setattr(
        rabbitmq_consumer.logger,
        'info',
        lambda message: (_ for _ in ()).throw(
            AssertionError(f'Unexpected INFO log: {message}')
        ),
    )

    consumer._message(
        channel,
        SimpleNamespace(delivery_tag=42),
        None,
        b'{}',
    )

    assert channel.acknowledged == [42]
    assert debug_messages == ['Processed worker_heartbeat event (created=True)']
