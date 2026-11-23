"""VRID reservations survive upgrades, concurrency and primary-key growth."""
from concurrent.futures import ThreadPoolExecutor
import importlib
from threading import Barrier

from peewee import IntegrityError, SqliteDatabase
import pytest

from app.modules.db import ha_cluster
from app.modules.db.db_model import (
    HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip, Server,
)
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiValidationError, RoxywiResourceNotFound


MIGRATION = importlib.import_module('app.modules.db.migrations.20261121000000_keepalived_vrid')


@pytest.fixture
def database(tmp_path):
    db = SqliteDatabase(tmp_path / 'vrid.db', pragmas={'foreign_keys': 1}, timeout=10)
    models = [HaCluster, HaClusterRouter, HaClusterSlave, HaClusterVip, Server]
    with db.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        db.create_tables(models)
        yield db
        db.close()


def cluster(group=1):
    return HaCluster.create(name=f'Cluster {group}', group_id=group, description='VRID test')


def legacy_schema(database):
    """Remove only the new column/index to exercise an actual schema upgrade."""
    for index in database.get_indexes('ha_cluster_routers'):
        if 'vrid' in index.columns:
            database.execute_sql(f'DROP INDEX "{index.name}"')
    database.execute_sql('ALTER TABLE ha_cluster_routers DROP COLUMN vrid')


def test_primary_key_growth_and_groups_do_not_affect_vrid_allocation(database):
    first, second = cluster(), cluster(2)
    old = HaClusterRouter.create(id=1000, cluster_id=first, vrid=1)
    created = ha_cluster.create_ha_router(second.id, default=1)
    router = HaClusterRouter.get_by_id(created)
    assert router.id == 1001 and router.vrid == 1 and router.default == 1
    old.delete_instance()
    following = HaClusterRouter.get_by_id(ha_cluster.create_ha_router(first.id))
    assert following.id == 1002 and following.vrid == 1
    assert HaClusterRouter.get_by_id(created).vrid == 1


def test_exhaustion_does_not_create_a_router_and_retry_uses_released_value(database):
    owner = cluster()
    HaClusterRouter.insert_many([
        {'cluster_id': owner.id, 'vrid': vrid} for vrid in range(1, 256)
    ]).execute()
    with pytest.raises(RoxywiConflictError, match='No free Keepalived VRID'):
        ha_cluster.create_ha_router(owner.id)
    assert HaClusterRouter.select().count() == 255
    HaClusterRouter.delete().where(HaClusterRouter.vrid == 100).execute()
    created = ha_cluster.create_ha_router(owner.id)
    assert HaClusterRouter.get_by_id(created).vrid == 100


@pytest.mark.parametrize('vrid', (0, -1, 256))
def test_database_rejects_out_of_range_vrid(database, vrid):
    with pytest.raises(IntegrityError):
        HaClusterRouter.create(cluster_id=cluster(), vrid=vrid)


@pytest.mark.parametrize('group', (1, 2))
def test_database_enforces_uniqueness_only_within_cluster(database, group):
    owner = cluster()
    HaClusterRouter.create(cluster_id=owner, vrid=17)
    with pytest.raises(IntegrityError):
        HaClusterRouter.create(cluster_id=owner, vrid=17)
    HaClusterRouter.create(cluster_id=cluster(group), vrid=17)


@pytest.mark.parametrize('reserved', (0, 254))
@pytest.mark.parametrize('manual', (False, True))
def test_concurrent_reservations_are_unique(database, reserved, manual):
    owner = cluster()
    if reserved:
        HaClusterRouter.insert_many([
            {'cluster_id': owner.id, 'vrid': vrid} for vrid in range(1, reserved + 1)
        ]).execute()
    barrier = Barrier(8)

    def create(_index):
        try:
            barrier.wait(timeout=10)
            return ha_cluster.create_ha_router(owner.id, vrid=255 if manual else None)
        except RoxywiConflictError:
            return None
        finally:
            database.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        identifiers = list(pool.map(create, range(8)))
    successful = [ident for ident in identifiers if ident is not None]
    expected = 1 if manual else min(8, 255 - reserved)
    assert len(successful) == len(set(successful)) == expected
    expected_values = set(range(1, reserved + 1)) | {255} if manual else set(range(1, reserved + expected + 1))
    assert {row.vrid for row in HaClusterRouter.select()} == expected_values


@pytest.mark.parametrize('vrid', (1, 255))
def test_manual_reservation_is_honoured_by_automatic_allocation(database, vrid):
    owner = cluster()
    manual = ha_cluster.create_ha_router(owner.id, vrid=vrid)
    automatic = ha_cluster.create_ha_router(owner.id)
    assert HaClusterRouter.get_by_id(manual).vrid == vrid
    assert HaClusterRouter.get_by_id(automatic).vrid == (2 if vrid == 1 else 1)
    with pytest.raises(RoxywiConflictError, match='already used in this cluster'):
        ha_cluster.create_ha_router(owner.id, vrid=vrid)


@pytest.mark.parametrize('vrid', (0, 256, -1, True, '42', 42.0))
def test_manual_value_validation_applies_to_direct_writers(database, vrid):
    owner = cluster()
    with pytest.raises(RoxywiValidationError, match='integer between'):
        ha_cluster.create_ha_router(owner.id, vrid=vrid)
    assert HaClusterRouter.select().count() == 0


def test_edit_preserves_omitted_value_and_checks_scope_and_duplicates(database):
    owner, other = cluster(), cluster(2)
    first = ha_cluster.create_ha_router(owner.id, vrid=10)
    ha_cluster.create_ha_router(owner.id, vrid=20)
    for vrid in (None, 10):
        ha_cluster.update_router_vrid(owner.id, first, vrid)
        assert HaClusterRouter.get_by_id(first).vrid == 10
    with pytest.raises(RoxywiConflictError, match='already used'):
        ha_cluster.update_router_vrid(owner.id, first, 20)
    with pytest.raises(RoxywiResourceNotFound):
        ha_cluster.update_router_vrid(other.id, first, 30)
    assert HaClusterRouter.get_by_id(first).vrid == 10
    ha_cluster.update_router_vrid(owner.id, first, 30)
    assert HaClusterRouter.get_by_id(first).vrid == 30


def test_migration_preserves_live_ids_and_children_and_is_repeatable(database):
    owner = cluster()
    node = Server.create(hostname='Node', ip='192.0.2.11', group_id='1')
    routers = [HaClusterRouter.create(id=ident, cluster_id=owner) for ident in (1, 200, 255, 256, 1000)]
    vip = HaClusterVip.create(cluster_id=owner, router_id=routers[-1], vip='192.0.2.100')
    member = HaClusterSlave.create(cluster_id=owner, router_id=routers[-1], server_id=node)
    legacy_schema(database)

    MIGRATION.up()
    expected = {1: 1, 200: 200, 255: 255, 256: 2, 1000: 3}
    assert {row.id: row.vrid for row in HaClusterRouter.select()} == expected
    assert HaClusterVip.get_by_id(vip.id).router_id_id == 1000
    assert HaClusterSlave.get_by_id(member.id).router_id_id == 1000
    assert database.execute_sql('PRAGMA foreign_key_check').fetchall() == []
    MIGRATION.up()
    assert {row.id: row.vrid for row in HaClusterRouter.select()} == expected
    with pytest.raises(IntegrityError):
        HaClusterRouter.create(cluster_id=owner, vrid=2)
    with pytest.raises(IntegrityError):
        HaClusterRouter.create(cluster_id=owner, vrid=256)
    with pytest.raises(RuntimeError, match='retained'):
        MIGRATION.down()


def test_exhausted_migration_does_not_partially_assign_vrids(database):
    owner = cluster()
    HaClusterRouter.insert_many([
        {'id': ident, 'cluster_id': owner.id} for ident in range(1, 257)
    ]).execute()
    legacy_schema(database)
    with pytest.raises(RuntimeError, match='more than 255'):
        MIGRATION.up()
    assert {row.vrid for row in HaClusterRouter.select()} == {None}
    HaClusterRouter.delete_by_id(256)
    MIGRATION.up()
    assert all(row.vrid == row.id for row in HaClusterRouter.select())


def test_migration_preserves_assigned_vrids_and_refuses_legacy_conflict(database):
    owner = cluster()
    HaClusterRouter.create(id=300, cluster_id=owner, vrid=5)
    legacy = HaClusterRouter.create(id=5, cluster_id=owner)
    with pytest.raises(RuntimeError, match='conflicts with a legacy'):
        MIGRATION.up()
    assert HaClusterRouter.get_by_id(300).vrid == 5
    assert HaClusterRouter.get_by_id(legacy.id).vrid is None


def test_migration_supports_more_than_255_routers_across_clusters(database):
    first, second = cluster(), cluster()
    HaClusterRouter.insert_many([
        {'id': ident, 'cluster_id': first.id if ident <= 255 else second.id}
        for ident in range(1, 511)
    ]).execute()
    legacy_schema(database)
    MIGRATION.up()
    for owner in (first, second):
        values = {row.vrid for row in HaClusterRouter.select().where(HaClusterRouter.cluster_id == owner.id)}
        assert values == set(range(1, 256))
    MIGRATION.up()
    assert HaClusterRouter.select().count() == 510


def test_migration_replaces_global_index_without_changing_existing_assignments(database):
    first, second = cluster(), cluster()
    one = HaClusterRouter.create(id=300, cluster_id=first, vrid=40)
    two = HaClusterRouter.create(id=301, cluster_id=second, vrid=41)
    database.execute_sql('CREATE UNIQUE INDEX haclusterrouter_vrid ON ha_cluster_routers (vrid)')
    MIGRATION.up()
    assert HaClusterRouter.get_by_id(one.id).vrid == 40
    assert HaClusterRouter.get_by_id(two.id).vrid == 41
    HaClusterRouter.create(cluster_id=second, vrid=40)
    MIGRATION.up()
    assert not any(index.unique and tuple(index.columns) == ('vrid',)
                   for index in database.get_indexes('ha_cluster_routers'))
