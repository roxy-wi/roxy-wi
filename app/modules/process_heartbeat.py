import atexit
import os
import socket
import threading
from datetime import timedelta

import roxy_wi_health as local_health

from app.modules.common.time import utc_now
from app.modules.db.db_model import close_database_connection
from app.modules.db.service_event import record_worker_heartbeat
from app.modules.roxywi import logger
from app.modules.roxy_wi_tools import GetConfigVar
from app.version import get_service_version


PROCESS_SERVICES = {
    'web': 'roxy-wi-web',
    'scheduler': 'roxy-wi-scheduler',
    'service-events': 'roxy-wi-service-events',
    'operations': 'roxy-wi-operations',
}


class ProcessHeartbeat:
    """Publish the liveness of a Roxy-WI process to the shared database."""

    def __init__(
        self,
        service: str,
        *,
        interval_seconds: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        process_config = GetConfigVar()
        self.service = service
        self.interval_seconds = max(
            5,
            interval_seconds or int(process_config.get_config_var(
                'main',
                'process_heartbeat_interval',
                '20',
            )),
        )
        self.ttl_seconds = max(
            self.interval_seconds * 2,
            ttl_seconds or int(process_config.get_config_var(
                'main',
                'process_heartbeat_ttl',
                '75',
            )),
        )
        self.hostname = socket.gethostname()
        self.instance_id = process_config.get_config_var('main', 'instance_id', self.hostname)
        self.worker_id = f'{self.service}:{self.instance_id}'
        self.started_at = utc_now()
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._status = 'running'
        self._metadata = {'kind': 'roxy-wi-process'}
        self._thread: threading.Thread | None = None

    def _record(self, status: str | None = None) -> None:
        with self._state_lock:
            current_status = status or self._status
            metadata = dict(self._metadata)
        heartbeat_at = utc_now()
        expires_at = heartbeat_at + timedelta(seconds=self.ttl_seconds)
        if current_status == 'stopped':
            expires_at = heartbeat_at
        try:
            record_worker_heartbeat({
                'worker_id': self.worker_id,
                'service': self.service,
                'instance_id': self.instance_id,
                'status': current_status,
                'hostname': self.hostname,
                'version': get_service_version(),
                'started_at': self.started_at,
                'heartbeat_at': heartbeat_at,
                'expires_at': expires_at,
                'active_assignments': 0,
                'group_ids': [],
                'metadata': metadata,
            })
            local_health.dependency('database', True)
        except Exception as error:
            local_health.dependency('database', False)
            logger.warning(f'Cannot record {self.service} heartbeat: {error}')
        finally:
            close_database_connection()

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self._record()
            if self.service == PROCESS_SERVICES['scheduler']:
                self._check_scheduler_broker()

    def _check_scheduler_broker(self) -> None:
        # Scheduler has short-lived publisher connections, unlike consumers.
        # Authenticate against the configured vhost; TCP alone is insufficient.
        from app.modules.integrations.rabbitmq_settings import RabbitConnectionSettings
        import pika

        try:
            parameters = RabbitConnectionSettings.load().parameters()
            parameters.socket_timeout = 2
            parameters.stack_timeout = 3
            parameters.blocked_connection_timeout = 3
            parameters.connection_attempts = 1
            connection = pika.BlockingConnection(parameters)
            try:
                connection.channel()
            finally:
                connection.close()
            local_health.dependency('rabbitmq', True)
        except Exception as error:
            local_health.dependency('rabbitmq', False)
            logger.debug(f'Scheduler RabbitMQ readiness failed: {type(error).__name__}')
        finally:
            close_database_connection()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._record('running')
        self._thread = threading.Thread(
            target=self._run,
            name=f'{self.service}-heartbeat',
            daemon=True,
        )
        self._thread.start()

    def set_status(self, status: str, **metadata) -> None:
        if status not in {'starting', 'running', 'degraded', 'draining'}:
            raise ValueError(f'Unsupported process heartbeat status: {status}')
        with self._state_lock:
            self._status = status
            self._metadata = {'kind': 'roxy-wi-process', **metadata}
        self._record()

    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._record('stopped')


_process_heartbeat: ProcessHeartbeat | None = None
_process_heartbeat_lock = threading.Lock()


def start_configured_process_heartbeat() -> ProcessHeartbeat | None:
    global _process_heartbeat

    role = os.environ.get('ROXYWI_PROCESS_ROLE', '').strip().lower()
    service = PROCESS_SERVICES.get(role)
    if service is None:
        return None
    with _process_heartbeat_lock:
        if _process_heartbeat is None:
            _process_heartbeat = ProcessHeartbeat(service)
            local_health.start(
                role,
                live_timeout=int(GetConfigVar().get_config_var('main', 'process_health_timeout', '120')),
                ready_timeout=_process_heartbeat.ttl_seconds,
            )
            _process_heartbeat.start()
            atexit.register(_process_heartbeat.stop)
        return _process_heartbeat


def set_process_heartbeat_status(status: str, **metadata) -> None:
    if _process_heartbeat is not None:
        _process_heartbeat.set_status(status, **metadata)
