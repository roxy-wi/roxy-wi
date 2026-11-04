"""Bounded read-only probes alongside the operations executor, on their own queue."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import threading

import pika
from pydantic import ValidationError

from app.modules.db.db_model import Server, ServiceAssignment, close_database_connection
from app.modules.integrations.keepalived_contract import KeepalivedProbeRequest, KeepalivedProbeResult
from app.modules.integrations.service_commands import RabbitPublisherSettings
from app.modules.roxywi import logger
from app.modules.service.keepalived import collect
from app.modules.subscription.access import MANAGED_SERVICES, is_feature_available


ROUTING_KEY = 'keepalived.probe.request'
CAPACITY = 4


def assignment_server(request: KeepalivedProbeRequest) -> Server | None:
    """Resolve only a current, enabled assignment; never accept an SSH target."""
    if not is_feature_available(MANAGED_SERVICES):
        return None
    assignment = ServiceAssignment.get_or_none(
        (ServiceAssignment.assignment_id == request.assignment_id)
        & (ServiceAssignment.target_service == 'checker')
        & (ServiceAssignment.service == 'keepalived')
        & (ServiceAssignment.user_group == request.group_id)
        & (ServiceAssignment.revision == request.revision)
        & (ServiceAssignment.desired_state == 'running')
    )
    if assignment is None:
        return None
    server = Server.get_or_none(
        (Server.server_id == assignment.server_id)
        & (Server.group_id == str(request.group_id))
        & (Server.enabled == 1) & (Server.keepalived == 1) & (Server.keepalived_alert == 1)
    )
    if server is None:
        return None
    target = json.loads(assignment.payload)['target']
    if (target.get('address') != server.ip or target.get('server_id') != server.server_id
            or target.get('service') != 'keepalived'):
        return None
    return server


def execute_probe(request: KeepalivedProbeRequest) -> KeepalivedProbeResult:
    """Return only states or a safe error code, even when SSH fails."""
    result = dict(request_id=request.request_id, assignment_id=request.assignment_id,
                  revision=request.revision, lease_epoch=request.lease_epoch)
    try:
        remaining = (request.expires_at - datetime.now(timezone.utc)).total_seconds()
        if not 0 < remaining <= 95:
            return KeepalivedProbeResult(**result, error='expired')
        server = assignment_server(request)
        if server is None:
            return KeepalivedProbeResult(**result, error='assignment_unavailable')
        snapshot = collect(server)
        current = assignment_server(request)
        if current is None or current.ip != server.ip or current.cred_id != server.cred_id:
            return KeepalivedProbeResult(**result, error='assignment_unavailable')
        if request.expires_at <= datetime.now(timezone.utc):
            return KeepalivedProbeResult(**result, error='expired')
        return KeepalivedProbeResult(**result, snapshot=snapshot)
    except Exception as error:
        # Neither SSH exceptions nor raw stdout/stderr belong in broker messages.
        logger.warning(f'Keepalived probe {request.request_id} failed ({type(error).__name__})')
        return KeepalivedProbeResult(**result, error='probe_failed')
    finally:
        close_database_connection()


class KeepalivedProbeConsumer:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.settings = RabbitPublisherSettings.load()
        self.queue = os.environ.get('ROXYWI_KEEPALIVED_PROBES_QUEUE', 'roxy-wi.keepalived-probes')

    def consume_once(self, executor: ThreadPoolExecutor) -> None:
        settings = self.settings
        parameters = pika.ConnectionParameters(
            host=settings.host, port=settings.port, virtual_host=settings.vhost,
            credentials=pika.PlainCredentials(settings.username, settings.password),
            heartbeat=30, blocked_connection_timeout=5, socket_timeout=5, stack_timeout=10,
        )
        connection = pika.BlockingConnection(parameters)
        pending = {}
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=settings.exchange, exchange_type='topic', durable=True)
            arguments = {'x-message-ttl': 90000, 'x-max-length': 1000}
            if settings.queue_type == 'quorum':
                arguments['x-queue-type'] = 'quorum'
            channel.queue_declare(queue=self.queue, durable=True, arguments=arguments)
            channel.queue_bind(exchange=settings.exchange, queue=self.queue, routing_key=ROUTING_KEY)
            channel.confirm_delivery()
            while not self.stop_event.is_set() or pending:
                for future in list(pending):
                    if not future.done():
                        continue
                    method, properties = pending.pop(future)
                    response = future.result()
                    try:
                        channel.basic_publish(
                            exchange='', routing_key=properties.reply_to,
                            body=response.model_dump_json().encode('utf-8'), mandatory=True,
                            properties=pika.BasicProperties(
                                content_type='application/json', correlation_id=str(response.request_id),
                                type=response.type, expiration='90000',
                            ),
                        )
                    except pika.exceptions.UnroutableError:
                        # The requesting runner stopped/timed out; a fresh poll
                        # will retry. Never resurrect an expired reply queue.
                        logger.debug(f'Keepalived probe {response.request_id} requester disconnected')
                    channel.basic_ack(method.delivery_tag)
                if not self.stop_event.is_set() and len(pending) < CAPACITY:
                    method, properties, body = channel.basic_get(queue=self.queue, auto_ack=False)
                    if method is not None:
                        if self.stop_event.is_set():
                            channel.basic_nack(method.delivery_tag, requeue=True)
                            continue
                        try:
                            if len(body) > 4096:
                                raise ValueError('Oversized probe request')
                            request = KeepalivedProbeRequest.model_validate_json(body)
                            if (properties.correlation_id != str(request.request_id)
                                    or properties.reply_to != f'roxy-checker.probe.{request.request_id}'):
                                raise ValueError('Invalid probe reply queue')
                        except (ValidationError, ValueError):
                            logger.warning('Rejected invalid Keepalived probe request')
                            channel.basic_reject(method.delivery_tag, requeue=False)
                            continue
                        pending[executor.submit(execute_probe, request)] = method, properties
                        continue
                connection.process_data_events(time_limit=0.2)
        finally:
            if connection.is_open:
                connection.close()
            # Do not overlap old and redelivered probes after a disconnect.
            for future in pending:
                future.result()

    def run(self) -> None:
        delay = 1
        with ThreadPoolExecutor(max_workers=CAPACITY, thread_name_prefix='keepalived-probe') as executor:
            while not self.stop_event.is_set():
                try:
                    self.consume_once(executor)
                    delay = 1
                except Exception as error:
                    if self.stop_event.is_set():
                        break
                    logger.error(f'Keepalived probe consumer disconnected ({type(error).__name__}); retrying in {delay}s')
                    self.stop_event.wait(delay)
                    delay = min(delay * 2, 30)
