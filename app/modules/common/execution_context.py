"""Group settings for background work, independent of Flask request state."""

from contextlib import contextmanager
from contextvars import ContextVar


group_id = ContextVar('operation_group_id', default=None)


@contextmanager
def group_settings(value):
    token = group_id.set(int(value))
    try:
        yield
    finally:
        group_id.reset(token)
