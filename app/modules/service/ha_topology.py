"""Serialize membership changes and server identities on shared controller storage."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
import os
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace

from app.modules.common.file_lock import file_lock
from app.modules.roxy_wi_tools import GetConfigVar
from app.modules.roxywi.exception import RoxywiConflictError


_held = ContextVar('ha_topology_lease', default=None)


def owned(lease):
    return lease is not None and lease.active and lease.owner == (os.getpid(), get_ident())


@contextmanager
def change_lock(path):
    with ExitStack() as stack:
        try:
            stack.enter_context(file_lock(path, blocking=False))
        except BlockingIOError:
            raise RoxywiConflictError('HA membership or another cluster operation is changing; retry the request') from None
        yield


@contextmanager
def topology_lock():
    if owned(_held.get()):
        yield
        return
    directory = Path(GetConfigVar().get_config_var('main', 'lib_path')) / 'ha-maintenance-locks'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with change_lock(directory / 'topology.lock'):
        lease = SimpleNamespace(owner=(os.getpid(), get_ident()), active=True)
        token = _held.set(lease)
        try:
            yield
        finally:
            # A copied same-thread Context must not outlive the actual lock.
            lease.active = False
            _held.reset(token)


def topology_guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with topology_lock():
            return function(*args, **kwargs)
    return wrapped
