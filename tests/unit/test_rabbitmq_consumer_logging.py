from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize('failure', [None, ValueError('invalid'), RuntimeError('database failed')])
def test_connection_is_released_before_ack_or_rejection(monkeypatch, failure):
    calls = []

    def process(_body):
        if failure:
            raise failure
        calls.append('commit')
        return SimpleNamespace(kind='metric_sample', created=True)

    monkeypatch.setattr(rabbitmq_consumer, 'process_event', process)
    monkeypatch.setattr(rabbitmq_consumer, 'close_database_connection', lambda: calls.append('close'))
    monkeypatch.setattr(rabbitmq_consumer, 'deliver_pending_notifications', lambda limit: None)
    monkeypatch.setattr(rabbitmq_consumer.local_health, 'dependency', lambda *_args: None)
    channel = SimpleNamespace(
        basic_ack=lambda **kwargs: calls.append(('ack', kwargs)),
        basic_reject=lambda **kwargs: calls.append(('reject', kwargs)),
        basic_nack=lambda **kwargs: calls.append(('nack', kwargs)),
    )
    consumer = rabbitmq_consumer.ServiceEventConsumer(
        rabbitmq_consumer.RabbitConsumerSettings('rabbit', 5672, '/', 'user', 'secret')
    )
    consumer._message(channel, SimpleNamespace(delivery_tag=42), None, b'{}')
    if failure is None:
        assert calls == ['commit', 'close', ('ack', {'delivery_tag': 42}), 'close']
    elif isinstance(failure, ValueError):
        assert calls == ['close', ('reject', {'delivery_tag': 42, 'requeue': False})]
    else:
        assert calls == ['close', ('nack', {'delivery_tag': 42, 'requeue': True})]
