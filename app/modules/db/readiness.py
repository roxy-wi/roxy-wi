from __future__ import annotations

import atexit
import logging
import threading
import time

from app.modules.db.db_model import BaseModel
from app.modules.db.migration_manager import Migration, get_migration_files


def database_schema_ready() -> tuple[bool, str]:
    database = BaseModel._meta.database
    try:
        with database.connection_context():
            database.execute_sql('SELECT 1')
            tables = set(database.get_tables())
            required_tables = {'user', 'servers', 'settings', 'migrations'}
            missing_tables = sorted(required_tables - tables)
            if missing_tables:
                return False, f'missing tables: {", ".join(missing_tables)}'
            applied = {migration.name for migration in Migration.select(Migration.name)}
            pending = sorted(set(get_migration_files()) - applied)
            if pending:
                return False, f'pending migrations: {len(pending)}'
    except Exception as error:
        return False, str(error)
    return True, 'ready'


class DatabaseReadinessMonitor:
    """Keep slow database/DNS checks out of the HTTP worker pool."""

    def __init__(self, check=database_schema_ready, interval=5, max_age=15):
        self.check = check
        self.interval = interval
        self.max_age = max_age
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._result = (False, 'database check pending')
        self._checked_at = None

    def start(self) -> None:
        """Start once in the serving process, after the web worker has forked."""
        with self._lock:
            if self._thread is None and not self._stop.is_set():
                self._thread = threading.Thread(target=self._run, name='database-readiness', daemon=True)
                self._thread.start()
                atexit.register(self.close)

    def get(self) -> tuple[bool, str]:
        # Keep lazy initialization for WSGI servers without lifecycle hooks.
        self.start()
        with self._lock:
            if self._stop.is_set():
                return False, 'database readiness monitor stopped'
            if self._checked_at is None or time.monotonic() - self._checked_at > self.max_age:
                return False, 'database check pending or expired'
            return self._result

    def _run(self):
        while not self._stop.is_set():
            started_at = time.monotonic()
            try:
                result = self.check()
            except Exception:
                logging.getLogger('roxy-wi').exception('Database readiness monitor failed')
                result = (False, 'database check failed')
            with self._lock:
                self._result, self._checked_at = result, started_at
            self._stop.wait(self.interval)

    def close(self):
        with self._lock:
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
        atexit.unregister(self.close)
