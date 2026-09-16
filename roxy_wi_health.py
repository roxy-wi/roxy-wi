"""Local process probes. Importing this module must never initialize Flask or DBs."""

import atexit
import hashlib
import http.client
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
import socket

import psutil


WORKER_ROLES = {'scheduler', 'service-events', 'operations'}
WRITE_INTERVAL = 5
_health = None


def health_directory() -> Path:
    # Local ephemeral state, never a shared data volume. Separate package users
    # as well as container PID namespaces; no changes to persistent/config paths.
    owner = hashlib.sha256(psutil.Process().username().encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f'roxy-wi-health-{owner}'


def _identity() -> dict:
    process = psutil.Process()
    return {'pid': process.pid, 'created_at': process.create_time()}


def _write(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.health-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(snapshot, stream)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def register_web() -> None:
    identity = _identity()
    _write(health_directory() / f'web-{identity["pid"]}.json', {
        **identity, 'role': 'web', 'bind': os.environ.get('ROXYWI_WEB_BIND', '0.0.0.0:8080'),
    })


class LocalProcessHealth:
    def __init__(self, role: str, *, live_timeout: int = 120, ready_timeout: int = 75):
        if role not in WORKER_ROLES:
            raise ValueError('Unsupported worker role')
        self.role = role
        self.identity = _identity()
        self.path = health_directory() / f'{role}-{self.identity["pid"]}.json'
        self.live_timeout = max(30, live_timeout)
        self.ready_timeout = max(15, ready_timeout)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._status = 'starting'
        self._progress_at = time.monotonic()
        self._dependencies = {}
        self._thread = None

    def pulse(self, rabbitmq: bool | None = None) -> None:
        """Called by the working loop, not by the background heartbeat thread."""
        with self._lock:
            self._progress_at = time.monotonic()
            if self._status not in {'draining', 'stopped'}:
                self._status = 'running'
            if rabbitmq is not None:
                self._dependencies['rabbitmq'] = (rabbitmq, time.monotonic())

    def dependency(self, name: str, ready: bool) -> None:
        with self._lock:
            self._dependencies[name] = (ready, time.monotonic())

    def status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def write(self) -> None:
        with self._lock:
            snapshot = {
                **self.identity,
                'role': self.role,
                'status': self._status,
                'sample_at': time.monotonic(),
                'progress_at': self._progress_at,
                'live_timeout': self.live_timeout,
                'ready_timeout': self.ready_timeout,
                'dependencies': dict(self._dependencies),
            }
        _write(self.path, snapshot)

    def _run(self) -> None:
        while not self._stop.wait(WRITE_INTERVAL):
            try:
                self.write()
            except OSError as error:
                # Old samples expire; a failed write must not keep a process green.
                logging.getLogger('roxy-wi').error('Cannot write local health: %s', type(error).__name__)

    def start(self) -> None:
        self.write()
        self._thread = threading.Thread(target=self._run, name='local-process-health', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.status('stopped')
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


def start(role: str, **kwargs) -> None:
    global _health
    if _health is None and role in WORKER_ROLES:
        _health = LocalProcessHealth(role, **kwargs)
        _health.start()
        atexit.register(_health.stop)


def pulse(rabbitmq: bool | None = None) -> None:
    if _health is not None:
        _health.pulse(rabbitmq)


def dependency(name: str, ready: bool) -> None:
    if _health is not None:
        _health.dependency(name, ready)


def draining() -> None:
    if _health is not None:
        _health.status('draining')


def _same_process(snapshot: dict) -> bool:
    try:
        process = psutil.Process(snapshot['pid'])
        return (process.create_time() == snapshot['created_at']
                and process.is_running()
                and process.status() not in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD})
    except (psutil.Error, KeyError, TypeError, ValueError):
        return False


def evaluate(snapshot: dict, check: str) -> tuple[bool, str]:
    now = time.monotonic()
    if snapshot['status'] == 'stopped':
        return False, 'process stopped'
    if not 0 <= now - snapshot['sample_at'] <= WRITE_INTERVAL * 3:
        return False, 'local heartbeat expired'
    if not 0 <= now - snapshot['progress_at'] <= snapshot['live_timeout']:
        return False, 'worker loop is not progressing'
    if check == 'live':
        return True, 'live'
    if snapshot['status'] != 'running':
        return False, 'worker is not ready'
    for name in ('database', 'rabbitmq'):
        ready, checked_at = snapshot['dependencies'].get(name, (False, 0))
        if not ready or not 0 <= now - checked_at <= snapshot['ready_timeout']:
            return False, f'{name} unavailable or check expired'
    return True, 'ready'


def _probe_web(bind: str, check: str) -> bool:
    if bind.startswith('unix:'):
        connection = http.client.HTTPConnection('localhost', timeout=2)
        try:
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(2)
            connection.sock.connect(bind.removeprefix('unix:'))
            connection.request('GET', f'/health/{check}')
            response = connection.getresponse()
            return response.status == 200 and json.loads(response.read(4096)).get('status') == 'ok'
        finally:
            connection.close()
    host, port = bind.rsplit(':', 1)
    host = {'0.0.0.0': '127.0.0.1', '[::]': '[::1]', '': '127.0.0.1'}.get(host, host)
    # Health traffic must not go through an HTTP_PROXY configured for remote
    # requests made by Roxy-WI.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{host}:{int(port)}/health/{check}', timeout=2) as response:
        return response.status == 200 and json.loads(response.read(4096)).get('status') == 'ok'


def probe(check: str = 'ready', role: str | None = None) -> tuple[bool, str]:
    """Read only this local process' state; never connect to DB/RabbitMQ here."""
    try:
        candidates = []
        for path in health_directory().glob('*.json'):
            snapshot = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(snapshot, dict):
                return False, 'invalid local health sample'
            if role is not None and snapshot.get('role') != role:
                continue
            if _same_process(snapshot):
                candidates.append(snapshot)
        if len(candidates) != 1:
            return False, 'expected one local process; specify --role when needed'
        snapshot = candidates[0]
        if snapshot['role'] == 'web':
            ready = _probe_web(snapshot['bind'], check)
            return ready, 'ready' if ready else 'web unavailable'
        if snapshot['role'] not in WORKER_ROLES:
            return False, 'unsupported process role'
        return evaluate(snapshot, check)
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        # Do not expose URLs, credentials or arbitrary exception text in probes.
        return False, f'health check failed ({type(error).__name__})'
