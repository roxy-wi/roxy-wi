"""Real changed-row and repeatable-read controls, enabled on a MariaDB test DB."""
from datetime import timedelta
from threading import Thread

import pytest
from peewee import MySQLDatabase

from app.modules.db.db_model import PacemakerCluster
from app.modules.pacemaker import service
from app.modules.roxywi.exception import RoxywiConflictError
from tests.unit.pacemaker.test_lock_renewal import lease, NOW, TOKEN


@pytest.fixture
def mariadb_lease(lease):
    database = PacemakerCluster._meta.database
    if not isinstance(database, MySQLDatabase):
        pytest.skip('Requires the actual MariaDB test backend')
    if 'MariaDB' not in database.execute_sql('SELECT VERSION()').fetchone()[0]:
        pytest.skip('Requires the MariaDB changed-row/REPEATABLE-READ regression backend')
    return lease


def test_real_identical_datetime_renewal_keeps_owner_and_wrong_token_is_rejected(mariadb_lease):
    row = mariadb_lease
    until = (NOW+timedelta(minutes=10)).replace(microsecond=0)
    PacemakerCluster.update(lock_until=until).where(PacemakerCluster.id == row.id).execute()
    changed = PacemakerCluster.update(lock_until=until).where(
        (PacemakerCluster.id == row.id) & (PacemakerCluster.lock_token == TOKEN)).execute()
    if changed == 1:
        pytest.skip('Connection reports matched rows; changed-row fallback is not applicable')
    assert changed == 0
    service.renew_lock(row, TOKEN)
    service.renew_lock(row, TOKEN)
    current = PacemakerCluster.get_by_id(row.id)
    assert current.lock_token == TOKEN and current.lock_until >= until
    other = 'f'*32
    PacemakerCluster.update(lock_token=other).where(PacemakerCluster.id == row.id).execute()
    with pytest.raises(RoxywiConflictError, match='lock was lost'):
        service.renew_lock(row, TOKEN)
    after = PacemakerCluster.get_by_id(row.id)
    assert (after.lock_token, after.lock_until) == (other, current.lock_until)


def test_renewal_does_not_accept_a_replaced_owner_from_a_repeatable_read_snapshot(mariadb_lease):
    row = mariadb_lease
    database = PacemakerCluster._meta.database
    isolation = database.execute_sql('SELECT @@tx_isolation').fetchone()[0]
    if isolation.upper().replace('_', '-') != 'REPEATABLE-READ':
        pytest.skip('Requires REPEATABLE-READ to exercise a genuinely stale snapshot')
    errors = []
    other = 'f'*32
    def replace_owner():
        try:
            PacemakerCluster.update(lock_token=other).where(PacemakerCluster.id == row.id).execute()
        except Exception as error:
            errors.append(error)
        finally:
            database.close()
    thread = None
    try:
        with database.atomic():
            snapshot = PacemakerCluster.get_by_id(row.id)
            assert snapshot.lock_token == TOKEN
            thread = Thread(target=replace_owner, daemon=True)
            thread.start(); thread.join(timeout=5)
            assert not thread.is_alive() and not errors
            # A normal consistent read really still sees the earlier owner.
            assert PacemakerCluster.get_by_id(row.id).lock_token == TOKEN
            with pytest.raises(RoxywiConflictError, match='lock was lost'):
                service.renew_lock(row, TOKEN)
    finally:
        if thread is not None:
            thread.join(timeout=5)
    assert not errors and PacemakerCluster.get_by_id(row.id).lock_token == other
