"""Lease renewal accepts a verified no-op, never stale ownership or a short lease."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.db.db_model import PacemakerCluster
from app.modules.pacemaker import service
from app.modules.roxywi.exception import RoxywiConflictError


NOW = datetime(2026, 10, 30, 12, 0, 0, 750000)
TOKEN = '0123456789abcdef0123456789abcdef'


@pytest.fixture
def lease(monkeypatch):
    monkeypatch.setattr(service, 'utc_now', lambda: NOW)
    row = PacemakerCluster.create(name='renew-'+uuid4().hex, group_id=1,
        lock_token=TOKEN, lock_until=NOW+timedelta(minutes=10))
    yield row
    row.delete_instance()


def report_no_changed_rows(monkeypatch):
    # Simulate the documented MySQL changed-row result with real read-back data.
    # The actual MariaDB regression runs this path with the real UPDATE driver.
    monkeypatch.setattr(PacemakerCluster, 'update', lambda **_values: SimpleNamespace(
        where=lambda *_predicates: SimpleNamespace(execute=lambda: 0)))


@pytest.mark.parametrize('precision', ['microseconds', 'seconds'])
def test_unchanged_renewal_rechecks_owner_and_requested_expiry(lease, monkeypatch, precision):
    if precision == 'seconds':
        PacemakerCluster.update(lock_until=(NOW+timedelta(minutes=10)).replace(microsecond=0)).where(
            PacemakerCluster.id == lease.id).execute()
    report_no_changed_rows(monkeypatch)
    service.renew_lock(lease, TOKEN)
    current = PacemakerCluster.get_by_id(lease.id)
    assert current.lock_token == TOKEN
    assert current.lock_until >= (NOW+timedelta(minutes=10)).replace(microsecond=0)


@pytest.mark.parametrize('state', ['wrong-token', 'released', 'expired', 'too-short', 'missing'])
def test_zero_rows_cannot_hide_lost_ownership_or_unrenewed_expiry(lease, monkeypatch, state):
    if state == 'missing':
        lease.delete_instance()
    elif state in ('wrong-token', 'released'):
        PacemakerCluster.update(lock_token='f'*32 if state == 'wrong-token' else None).where(
            PacemakerCluster.id == lease.id).execute()
    else:
        expiry = NOW-timedelta(seconds=1) if state == 'expired' else NOW+timedelta(seconds=1)
        PacemakerCluster.update(lock_until=expiry).where(PacemakerCluster.id == lease.id).execute()
    before = PacemakerCluster.get_or_none(PacemakerCluster.id == lease.id)
    report_no_changed_rows(monkeypatch)
    with pytest.raises(RoxywiConflictError, match='lock was lost'):
        service.renew_lock(lease, TOKEN)
    current = PacemakerCluster.get_or_none(PacemakerCluster.id == lease.id)
    if before is None:
        assert current is None
    else:
        assert (current.lock_token, current.lock_until) == (before.lock_token, before.lock_until)


def test_changed_renewal_extends_the_existing_owned_lease(lease):
    PacemakerCluster.update(lock_until=NOW+timedelta(seconds=1)).where(PacemakerCluster.id == lease.id).execute()
    service.renew_lock(lease, TOKEN)
    current = PacemakerCluster.get_by_id(lease.id)
    requested = NOW+timedelta(minutes=10)
    assert current.lock_token == TOKEN
    assert requested.replace(microsecond=0) <= current.lock_until <= requested


@pytest.mark.parametrize('token', [None, '', b'bytes', 1])
def test_invalid_token_cannot_renew_an_unowned_row(lease, token):
    PacemakerCluster.update(lock_token=None).where(PacemakerCluster.id == lease.id).execute()
    previous = PacemakerCluster.get_by_id(lease.id).lock_until
    with pytest.raises(RoxywiConflictError, match='lock was lost'):
        service.renew_lock(lease, token)
    current = PacemakerCluster.get_by_id(lease.id)
    assert current.lock_token is None and current.lock_until == previous
