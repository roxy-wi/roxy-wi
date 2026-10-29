from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pika
from cryptography.fernet import Fernet, InvalidToken

from app.modules.common.time import utc_now
from app.modules.db.db_model import CertificateSource, InstallationTasks
from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
from app.modules.server.ssh import _get_fernet_key


_ENCRYPTED_PAYLOAD_PREFIX = 'fernet:'


def serialize_operation_payload(payload: dict) -> str:
    plaintext = json.dumps(
        payload, sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')
    token = Fernet(_get_fernet_key().encode('ascii')).encrypt(plaintext).decode('ascii')
    return f'{_ENCRYPTED_PAYLOAD_PREFIX}{token}'


def deserialize_operation_payload(payload: str) -> dict:
    if payload.startswith(_ENCRYPTED_PAYLOAD_PREFIX):
        token = payload[len(_ENCRYPTED_PAYLOAD_PREFIX):].encode('ascii')
        try:
            plaintext = Fernet(_get_fernet_key().encode('ascii')).decrypt(token)
        except InvalidToken as error:
            raise ValueError('Operation payload cannot be decrypted') from error
        return json.loads(plaintext.decode('utf-8'))
    # Compatibility for tasks created by an early development build before
    # encrypted operation payloads were introduced.
    return json.loads(payload)


def source_owned_operation(task) -> bool:
    """Source deployments are private children, never independent queue jobs."""
    if task.operation_type != 'certificate':
        return False
    try:
        if deserialize_operation_payload(task.operation_payload).get('source_id') is not None:
            return True
    except (ValueError, TypeError, AttributeError):
        # An unreadable payload cannot execute a deployment either. Leave the
        # ordinary executor to report its bounded failure without blocking jobs.
        pass
    return CertificateSource.select().where(CertificateSource.deployment_task_id == task.id).exists()


def renew_operation_lease(operation_id: str, task_id: int) -> int:
    """Renew a live source and its current child together in one transaction."""
    database = InstallationTasks._meta.database
    from peewee import SqliteDatabase
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        now = utc_now()
        task = InstallationTasks.get_or_none((InstallationTasks.id == task_id) &
            (InstallationTasks.operation_id == operation_id) & (InstallationTasks.status == 'running'))
        if task is None:
            return 0
        updated = InstallationTasks.update(updated_at=now).where(
            (InstallationTasks.id == task.id) & (InstallationTasks.status == 'running')).execute()
        if updated and task.operation_type == 'certificate-source':
            row = CertificateSource.get_or_none((CertificateSource.active_task_id == task.id) &
                (CertificateSource.group_id == task.group_id_id))
            child = InstallationTasks.get_or_none((InstallationTasks.id == row.deployment_task_id) &
                (InstallationTasks.group_id == task.group_id_id) & (InstallationTasks.status == 'running')) if row and row.deployment_task_id else None
            if child and source_owned_operation(child):
                payload = deserialize_operation_payload(child.operation_payload)
                if payload.get('source_id') == row.id and payload.get('source_task_id', task.id) == task.id:
                    InstallationTasks.update(updated_at=now).where(
                        (InstallationTasks.id == child.id) & (InstallationTasks.status == 'running')).execute()
        return updated


@dataclass(frozen=True)
class OperationQueueSettings:
    host: str
    port: int
    vhost: str
    username: str
    password: str
    exchange: str = 'roxy.operations'
    queue: str = 'roxy-wi.operations'
    dead_letter_exchange: str = 'roxy.operations.dlx'
    dead_letter_queue: str = 'roxy-wi.operations.dlq'
    queue_type: str = 'classic'
    prefetch: int = 1

    @classmethod
    def load(cls) -> 'OperationQueueSettings':
        connection = RabbitConnectionSettings.load()
        return cls(
            host=connection.host,
            port=connection.port,
            vhost=connection.vhost,
            username=connection.username,
            password=connection.password,
            exchange=os.environ.get('ROXYWI_OPERATIONS_EXCHANGE', 'roxy.operations'),
            queue=os.environ.get('ROXYWI_OPERATIONS_QUEUE', 'roxy-wi.operations'),
            dead_letter_exchange=os.environ.get('ROXYWI_OPERATIONS_DLX', 'roxy.operations.dlx'),
            dead_letter_queue=os.environ.get('ROXYWI_OPERATIONS_DLQ', 'roxy-wi.operations.dlq'),
            queue_type=os.environ.get('ROXYWI_RABBITMQ_QUEUE_TYPE', 'classic'),
            prefetch=max(1, int(os.environ.get('ROXYWI_OPERATIONS_PREFETCH', '1'))),
        )

    def parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            virtual_host=self.vhost,
            credentials=pika.PlainCredentials(self.username, self.password),
            heartbeat=30,
            blocked_connection_timeout=30,
        )


def declare_operation_topology(channel, settings: OperationQueueSettings) -> None:
    if settings.queue_type not in {'classic', 'quorum'}:
        raise ValueError('ROXYWI_RABBITMQ_QUEUE_TYPE must be classic or quorum')
    channel.exchange_declare(exchange=settings.exchange, exchange_type='direct', durable=True)
    channel.exchange_declare(
        exchange=settings.dead_letter_exchange,
        exchange_type='direct',
        durable=True,
    )
    queue_arguments = {'x-dead-letter-exchange': settings.dead_letter_exchange}
    dead_letter_arguments = None
    if settings.queue_type == 'quorum':
        queue_arguments['x-queue-type'] = 'quorum'
        dead_letter_arguments = {'x-queue-type': 'quorum'}
    channel.queue_declare(queue=settings.queue, durable=True, arguments=queue_arguments)
    channel.queue_bind(exchange=settings.exchange, queue=settings.queue, routing_key='execute')
    channel.queue_declare(
        queue=settings.dead_letter_queue,
        durable=True,
        arguments=dead_letter_arguments,
    )
    channel.queue_bind(
        exchange=settings.dead_letter_exchange,
        queue=settings.dead_letter_queue,
        routing_key='execute',
    )
    channel.basic_qos(prefetch_count=settings.prefetch)


def create_ansible_task(
    *,
    service_name: str,
    server_ids: list[int],
    user_id: int | None,
    group_id: int | None,
    inventory: dict,
    server_ips: list[str],
    ansible_role: str,
    success_action: dict | None = None,
    run_locally: bool = False,
) -> int:
    operation_id = str(uuid4())
    payload = serialize_operation_payload({
        'inventory': inventory,
        'server_ips': server_ips,
        'ansible_role': ansible_role,
        'success_action': success_action,
        'run_locally': run_locally,
    })
    return InstallationTasks.insert(
        service_name=service_name,
        server_ids=server_ids,
        user_id=user_id,
        group_id=group_id,
        operation_id=operation_id,
        operation_type='ansible',
        operation_payload=payload,
        status='created',
        updated_at=utc_now(),
    ).execute()


def create_ansible_workflow_task(
    *,
    service_name: str,
    server_ids: list[int],
    user_id: int | None,
    group_id: int | None,
    steps: list[dict],
    success_action: dict | None = None,
) -> int:
    if not steps:
        raise ValueError('Ansible workflow must contain at least one step')
    operation_id = str(uuid4())
    payload = serialize_operation_payload({
        'steps': steps,
        'success_action': success_action,
    })
    return InstallationTasks.insert(
        service_name=service_name,
        server_ids=server_ids,
        user_id=user_id,
        group_id=group_id,
        operation_id=operation_id,
        operation_type='ansible',
        operation_payload=payload,
        status='created',
        updated_at=utc_now(),
    ).execute()


def publish_pending_operations(
    limit: int = 100,
    settings: OperationQueueSettings | None = None,
) -> int:
    recover_stale_operations()
    tasks = list(
        InstallationTasks.select()
        .where(
            (InstallationTasks.operation_id.is_null(False))
            & (InstallationTasks.status == 'created')
            & (InstallationTasks.id.not_in(CertificateSource.select(CertificateSource.deployment_task_id)
                .where(CertificateSource.deployment_task_id.is_null(False))))
        )
        .order_by(InstallationTasks.start_date)
        .limit(limit)
    )
    if not tasks:
        return 0

    settings = settings or OperationQueueSettings.load()
    connection = pika.BlockingConnection(settings.parameters())
    published = 0
    try:
        channel = connection.channel()
        declare_operation_topology(channel, settings)
        channel.confirm_delivery()
        for task in tasks:
            if source_owned_operation(task):
                continue
            message = json.dumps({
                'operation_id': task.operation_id,
                'task_id': task.id,
                'type': task.operation_type,
            }, sort_keys=True, separators=(',', ':'))
            try:
                confirmed = channel.basic_publish(
                    exchange=settings.exchange,
                    routing_key='execute',
                    body=message.encode('utf-8'),
                    properties=pika.BasicProperties(
                        app_id='roxy-wi',
                        content_type='application/json',
                        content_encoding='utf-8',
                        delivery_mode=2,
                        message_id=task.operation_id,
                        type=task.operation_type,
                    ),
                    mandatory=True,
                )
                if confirmed is False:
                    raise RuntimeError('RabbitMQ did not confirm the operation')
            except Exception as error:
                InstallationTasks.update(
                    attempts=InstallationTasks.attempts + 1,
                    error=str(error),
                    updated_at=utc_now(),
                ).where(InstallationTasks.id == task.id).execute()
            else:
                InstallationTasks.update(
                    status='published',
                    error=None,
                    published_at=utc_now(),
                    updated_at=utc_now(),
                ).where(
                    (InstallationTasks.id == task.id)
                    & (InstallationTasks.status == 'created')
                ).execute()
                published += 1
    finally:
        if connection.is_open:
            connection.close()
    return published


def recover_stale_operations() -> int:
    """Return jobs abandoned by a terminated worker to the durable outbox."""
    lease_seconds = max(60, int(os.environ.get('ROXYWI_OPERATIONS_LEASE_SECONDS', '300')))
    stale_before = utc_now() - timedelta(seconds=lease_seconds)
    stale = (InstallationTasks.operation_id.is_null(False) & (InstallationTasks.status == 'running') &
        (InstallationTasks.updated_at < stale_before))
    updates = dict(status='created', error='Operations worker lease expired; task queued again',
        published_at=None, updated_at=utc_now())
    recovered = InstallationTasks.update(**updates).where(stale &
        ((InstallationTasks.operation_type != 'certificate') | InstallationTasks.operation_type.is_null(True))).execute()
    # Only certificate payloads need ownership inspection; keep other recovery
    # types as a single SQL update and bound the certificate working set.
    last_id = 0
    while True:
        batch = list(InstallationTasks.select().where(stale & (InstallationTasks.operation_type == 'certificate') &
            (InstallationTasks.id > last_id)).order_by(InstallationTasks.id).limit(100))
        if not batch:
            break
        for task in batch:
            if not source_owned_operation(task):
                recovered += InstallationTasks.update(**updates).where(stale & (InstallationTasks.id == task.id)).execute()
        last_id = batch[-1].id
    return recovered
