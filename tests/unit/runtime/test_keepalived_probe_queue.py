from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
import threading
from types import SimpleNamespace
from uuid import uuid4

import pika
import pytest

from app.modules.integrations import keepalived_probes as probes
from app.modules.integrations.keepalived_contract import KeepalivedProbeRequest, KeepalivedProbeResult
from app.modules.integrations.service_commands import RabbitPublisherSettings


class Broker:
    def __init__(self, worker, requests, unroutable=False):
        self.worker = worker
        self.requests = requests
        self.unroutable = unroutable
        self.pending = []
        self.acked = []
        self.rejected = []
        self.sent = []
        self.is_open = True
        self.inflight_max = 0
        self.arguments = None

    def channel(self):
        return self

    def exchange_declare(self, **kw):
        pass

    def queue_declare(self, **kw):
        self.arguments = kw['arguments']

    def queue_bind(self, **kw):
        assert kw['routing_key'] == 'keepalived.probe.request'

    def confirm_delivery(self):
        pass

    def basic_get(self, **kw):
        if not self.requests:
            return None, None, None
        request, reply_to = self.requests.pop(0)
        return (SimpleNamespace(delivery_tag=str(request.request_id)),
                SimpleNamespace(correlation_id=str(request.request_id), reply_to=reply_to),
                request.model_dump_json().encode())

    def submit(self, function, request):
        future = Future()
        self.pending.append((future, request))
        self.inflight_max = max(self.inflight_max, len(self.pending))
        return future

    def process_data_events(self, **kw):
        for future, request in self.pending:
            future.set_result(KeepalivedProbeResult(request_id=request.request_id,
                assignment_id=request.assignment_id, revision=request.revision,
                lease_epoch=request.lease_epoch, error='probe_failed'))
        self.pending.clear()
        if not self.requests:
            self.worker.stop_event.set()

    def basic_publish(self, **kw):
        self.sent.append(kw)
        if self.unroutable:
            raise pika.exceptions.UnroutableError([])

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_reject(self, tag, **kw):
        assert kw['requeue'] is False
        self.rejected.append(tag)

    def close(self):
        self.is_open = False


@pytest.mark.parametrize('unroutable', [False, True])
def test_probe_queue_bounds_concurrency_drains_and_handles_disconnected_requester(monkeypatch, unroutable):
    monkeypatch.setattr(probes.RabbitPublisherSettings, 'load', lambda: RabbitPublisherSettings(
        'broker', 5672, '/', 'user', 'password'))
    worker = probes.KeepalivedProbeConsumer(threading.Event())
    requests = [KeepalivedProbeRequest(request_id=uuid4(), assignment_id='keepalived:server-11',
                revision=1, lease_epoch=1, group_id=1,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=90)) for _ in range(9)]
    deliveries = [(request, f'roxy-checker.probe.{request.request_id}') for request in requests]
    deliveries[0] = requests[0], 'arbitrary-queue'
    broker = Broker(worker, deliveries, unroutable)
    monkeypatch.setattr(probes.pika, 'BlockingConnection', lambda settings: broker)
    worker.consume_once(broker)
    assert broker.inflight_max == 4
    assert broker.rejected == [str(requests[0].request_id)]
    assert len(broker.acked) == 8 and len(broker.sent) == 8
    assert not broker.is_open
    assert broker.arguments == {'x-message-ttl': 90000, 'x-max-length': 1000}
    assert all(message['exchange'] == '' and message['mandatory'] for message in broker.sent)
