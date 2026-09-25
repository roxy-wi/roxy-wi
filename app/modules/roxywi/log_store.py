"""Small, shared-volume log journal; each process owns its own segments."""
import logging
import os
import re
import socket
import time
import uuid
from pathlib import Path

from app.modules.roxy_wi_tools import GetConfigVar

SEGMENT_BYTES = 5 * 1024 * 1024
RETENTION_DAYS = 7


def store_path():
    config = GetConfigVar()
    mode = config.get_config_var('main', 'deployment_mode', 'package')
    enabled = config.get_config_var('logs', 'log_store_enabled', '0' if mode == 'package' else '1')
    if str(enabled).lower() not in {'1', 'true', 'yes', 'on'}:
        return None
    root = config.get_config_var('main', 'lib_path', '/var/lib/roxy-wi')
    return Path(config.get_config_var('logs', 'log_store_path', str(Path(root) / 'logs')))


class JournalHandler(logging.Handler):
    """No file shared by Gunicorn workers, no persistent handles across cleanup.

    Segments have immutable names, allowing readers to finish a rotated segment.
    Logging failures go through logging.handleError, never back into this logger.
    """

    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pid = None
        self.segment = None
        self.cleanup_at = 0

    def emit(self, record):
        try:
            now = time.time()
            day = int(now // 86400)
            if self.pid != os.getpid() or self.segment is None or self.day != day or self.size >= SEGMENT_BYTES:
                self.pid = os.getpid()
                role = re.sub(r'[^a-zA-Z0-9_-]', '_', os.getenv('ROXYWI_PROCESS_ROLE', 'web'))[:40]
                host = re.sub(r'[^a-zA-Z0-9_-]', '_', socket.gethostname())[:64]
                self.segment = self.directory / f'rwi-{role}-{host}-{self.pid}-{uuid.uuid4().hex}.log'
                self.day, self.size = day, 0
            data = (self.format(record) + '\n').encode('utf-8')
            # Opening per record also survives removal of an old, idle segment.
            fd = os.open(self.segment, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'ab') as stream:
                stream.write(data)
            self.size += len(data)
            if now >= self.cleanup_at:
                self.cleanup_at = now + 3600
                for path in self.directory.glob('rwi-*.log'):
                    try:
                        if path != self.segment and not path.is_symlink() and path.stat().st_mtime < now - RETENTION_DAYS * 86400:
                            path.unlink()
                    except FileNotFoundError:
                        # Another process can clean the same expired segment.
                        continue
        except Exception:
            self.handleError(record)
