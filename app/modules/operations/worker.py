import json
import signal
import threading
import time

import pika

from app.modules.common.time import utc_now
from app.modules.db.db_model import InstallationTasks, close_database_connection
from app.modules.operations.queue import (
    OperationQueueSettings,
    declare_operation_topology,
    deserialize_operation_payload,
)
from app.modules.roxywi import logger
from app.modules.process_heartbeat import set_process_heartbeat_status


def _success_callback(action: dict | None):
    if not action:
        return None
    action_type = action.get('type')
    if action_type == 'service-installed':
        def callback() -> None:
            from app.modules.service.installation import service_actions_after_install
            service_actions_after_install(
                action['server_ips'],
                action['service'],
                action['request'],
            )

        return callback
    if action_type == 'waf-installed':
        def callback() -> None:
            from app.modules.service.installation import waf_actions_after_install
            waf_actions_after_install(action['server_ip'], action['service'])

        return callback
    raise ValueError('Unsupported operation success action')


def execute_operation(operation_id: str, task_id: int) -> str:
    try:
        task = InstallationTasks.get(
            (InstallationTasks.id == task_id)
            & (InstallationTasks.operation_id == operation_id)
        )
        if task.status in {'completed', 'failed'}:
            return task.status
        if task.operation_type != 'ansible':
            raise ValueError(f'Unsupported operation type: {task.operation_type}')
        payload = deserialize_operation_payload(task.operation_payload)
        from app.modules.service.installation import run_installations
        run_installations(
            payload.get('inventory'),
            payload.get('server_ips'),
            payload.get('ansible_role'),
            task.id,
            _success_callback(payload.get('success_action')),
            already_running=True,
            run_locally=bool(payload.get('run_locally')),
            steps=payload.get('steps'),
        )
        return InstallationTasks.get_by_id(task.id).status
    finally:
        close_database_connection()


def claim_operation(operation_id: str, task_id: int) -> tuple[bool, str]:
    """Atomically claim a published task; duplicate deliveries become no-ops."""
    try:
        updated = (
            InstallationTasks.update(
                status='running',
                attempts=InstallationTasks.attempts + 1,
                error=None,
                updated_at=utc_now(),
            )
            .where(
                (InstallationTasks.id == task_id)
                & (InstallationTasks.operation_id == operation_id)
                & (InstallationTasks.status.in_(('created', 'published')))
            )
            .execute()
        )
        task = InstallationTasks.get(
            (InstallationTasks.id == task_id)
            & (InstallationTasks.operation_id == operation_id)
        )
        return updated == 1, task.status
    finally:
        close_database_connection()


class OperationWorker:
    def __init__(self, settings: OperationQueueSettings | None = None):
        self.settings = settings or OperationQueueSettings.load()
        self._stop_event = threading.Event()
        self._connection = None

    def stop(self, *_args) -> None:
        self._stop_event.set()

    @staticmethod
    def _decode(body: bytes) -> tuple[str, int]:
        message = json.loads(body.decode('utf-8'))
        operation_id = str(message['operation_id'])
        task_id = int(message['task_id'])
        if not operation_id or task_id <= 0:
            raise ValueError('Invalid operation message')
        return operation_id, task_id

    def consume_once(self) -> None:
        self._connection = pika.BlockingConnection(self.settings.parameters())
        try:
            channel = self._connection.channel()
            declare_operation_topology(channel, self.settings)
            set_process_heartbeat_status('running')
            while not self._stop_event.is_set():
                method, _properties, body = channel.basic_get(
                    queue=self.settings.queue,
                    auto_ack=False,
                )
                if method is None:
                    self._connection.process_data_events(time_limit=1)
                    continue
                try:
                    operation_id, task_id = self._decode(body)
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                    logger.warning(f'Rejecting invalid operation message: {error}')
                    channel.basic_reject(method.delivery_tag, requeue=False)
                    continue

                try:
                    claimed, task_status = claim_operation(operation_id, task_id)
                except Exception as error:
                    logger.error(f'Cannot claim operation {operation_id}: {error}')
                    channel.basic_nack(method.delivery_tag, requeue=True)
                    continue

                # RabbitMQ is a durable wake-up mechanism; the database is the
                # source of truth. Ack after the atomic claim so a connection
                # loss during a long Ansible run cannot execute it concurrently.
                try:
                    channel.basic_ack(method.delivery_tag)
                except Exception as error:
                    logger.warning(f'Cannot acknowledge claimed operation {operation_id}: {error}')
                if not claimed:
                    logger.info(
                        f'Ignoring duplicate operation {operation_id} with status {task_status}'
                    )
                    continue

                result: dict[str, object] = {}

                def execute() -> None:
                    try:
                        result['status'] = execute_operation(operation_id, task_id)
                    except Exception as error:  # pragma: no cover - final safety net
                        result['error'] = error

                operation_thread = threading.Thread(target=execute, daemon=False)
                operation_thread.start()
                last_heartbeat = time.monotonic()
                rabbit_connection_lost = False
                while operation_thread.is_alive():
                    if rabbit_connection_lost:
                        time.sleep(1)
                    else:
                        try:
                            self._connection.process_data_events(time_limit=1)
                        except Exception as error:
                            # The operation has already been acknowledged and remains
                            # durable in the DB. Let it finish and reconnect later.
                            rabbit_connection_lost = True
                            logger.warning(
                                f'RabbitMQ connection lost during operation {operation_id}: {error}'
                            )
                    if time.monotonic() - last_heartbeat >= 30:
                        try:
                            InstallationTasks.update(updated_at=utc_now()).where(
                                (InstallationTasks.id == task_id)
                                & (InstallationTasks.status == 'running')
                            ).execute()
                        except Exception as error:
                            logger.error(f'Cannot renew operation {operation_id} lease: {error}')
                        finally:
                            close_database_connection()
                        last_heartbeat = time.monotonic()
                operation_thread.join()

                if 'error' in result:
                    error = result['error']
                    logger.error(f'Operation {operation_id} crashed: {error}')
                    try:
                        InstallationTasks.update(
                            status='failed',
                            error=str(error),
                            finish_date=utc_now(),
                            updated_at=utc_now(),
                        ).where(InstallationTasks.id == task_id).execute()
                    finally:
                        close_database_connection()
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
            except Exception as error:
                if self._stop_event.is_set():
                    break
                set_process_heartbeat_status('degraded', last_error=str(error)[:500])
                logger.error(f'Operations worker disconnected: {error}; retrying in {delay}s')
                self._stop_event.wait(delay)
                delay = min(delay * 2, 30)


def run_worker() -> None:
    worker = OperationWorker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run()
