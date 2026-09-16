"""Shared transaction, identity and retention rules for service event sinks."""

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta

from peewee import IntegrityError, SqliteDatabase

from app.modules.common.time import as_naive_utc, utc_now
from app.modules.db.db_model import (
    Alerts, ApacheMetrics, Metrics, MetricsHttpStatus, NginxMetrics,
    PortScannerHistory, ServiceEventPosition, ServiceEventRetention, WafMetrics,
)


METRIC_MODELS = {'haproxy': Metrics, 'nginx': NginxMetrics, 'apache': ApacheMetrics, 'waf': WafMetrics}
HISTORY_MODELS = {
    'metrics': (Metrics, MetricsHttpStatus, NginxMetrics, ApacheMetrics, WafMetrics),
    'checker': (Alerts,),
    'portscanner': (PortScannerHistory,),
}


def event_key(data):
    identity = [data['assignment_id'], data['assignment_revision'], data['lease_epoch'], data['sequence']]
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


def event_order(data):
    return data['assignment_revision'], data['lease_epoch'], data['sequence']


@contextmanager
def write_transaction():
    database = ServiceEventPosition._meta.database
    # Acquire the writer before reading in SQLite; deferred upgrades can fail
    # immediately with BUSY even with busy_timeout set.
    transaction_args = ('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ()
    with database.atomic(*transaction_args):
        yield


def _current_read(query):
    if not isinstance(query.model._meta.database, SqliteDatabase):
        query = query.for_update()
    return query


def current_exists(query):
    # A locking read also avoids stale snapshots under MySQL REPEATABLE READ
    # after waiting for another consumer's transaction to commit.
    return _current_read(query).exists()


def _lock_or_create(model, key, defaults=None):
    query = _current_read(model.select().filter(**key))
    row = query.get_or_none()
    if row is not None:
        return row
    try:
        with model._meta.database.atomic():
            return model.create(**key, **(defaults or {}))
    except IntegrityError:
        row = query.get_or_none()
        if row is None:
            raise
        return row


def lock_retention(category):
    return _lock_or_create(ServiceEventRetention, {'category': category}, {'cutoff': datetime(1970, 1, 1)})


def lock_position(data):
    return _lock_or_create(ServiceEventPosition, {'assignment_id': data['assignment_id']})


def advance_position(position, data):
    if event_order(data) <= (position.assignment_revision, position.lease_epoch, position.sequence):
        return False
    ServiceEventPosition.update(
        assignment_revision=data['assignment_revision'], lease_epoch=data['lease_epoch'],
        sequence=data['sequence'], event_id=data['event_id'],
        observed_at=as_naive_utc(data['observed_at']),
    ).where(ServiceEventPosition.assignment_id == data['assignment_id']).execute()
    return True


def has_identity(model, data):
    return current_exists(model.select().where(
        (model.event_id == data['event_id']) | (model.event_key == event_key(data))
    ))


def prune_history(category, retention_days, models=None):
    """Advance replay boundary and prune its sinks together, even across HA consumers."""
    if retention_days < 1:
        raise ValueError('history retention must be at least one day')
    deleted = 0
    with write_transaction():
        boundary = lock_retention(category)
        cutoff = max(boundary.cutoff, utc_now() - timedelta(days=retention_days))
        ServiceEventRetention.update(cutoff=cutoff).where(
            ServiceEventRetention.category == category
        ).execute()
        for model in models or HISTORY_MODELS[category]:
            query = model.delete().where(model.date < cutoff)
            if model is Alerts:
                query = query.where(Alerts.service == 'Checker')
            deleted += query.execute()
    return deleted
