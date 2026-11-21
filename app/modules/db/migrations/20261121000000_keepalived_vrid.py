"""Separate VRRP wire identifiers from router primary keys without renumbering live VIPs."""
from peewee import SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate

from app.modules.db.db_model import HaClusterRouter


def up():
    """Preserve valid legacy identifiers and allocate unused values for larger IDs."""
    database = HaClusterRouter._meta.database
    table = HaClusterRouter._meta.table_name
    if 'vrid' not in {column.name for column in database.get_columns(table)}:
        # Adding a nullable column avoids a SQLite table rebuild and cascading
        # deletion of registered members/VIPs. MySQL DDL commits independently.
        database.execute_sql(
            'ALTER TABLE ha_cluster_routers ADD COLUMN vrid INTEGER '
            'CHECK (vrid BETWEEN 1 AND 255)'
        )
    indexes = database.get_indexes(table)
    if not any(index.unique and tuple(index.columns) == ('cluster_id', 'vrid')
               for index in indexes):
        database.execute_sql(
            'CREATE UNIQUE INDEX haclusterrouter_cluster_id_vrid '
            'ON ha_cluster_routers (cluster_id, vrid)'
        )
    # Also accept an installation that ran the unreleased global-pool migration.
    # Establish the scoped constraint before removing the broader constraint.
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    for index in indexes:
        if index.unique and tuple(index.columns) == ('vrid',):
            migrate(migrator.drop_index(table, index.name))
    transaction_args = ('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ()
    with database.atomic(*transaction_args):
        routers = list(HaClusterRouter.select().order_by(HaClusterRouter.id))
        used = {router.cluster_id_id: set() for router in routers}
        assignments = {}
        for router in routers:
            pool = used[router.cluster_id_id]
            if router.vrid is not None:
                if not 1 <= router.vrid <= 255 or router.vrid in pool:
                    raise RuntimeError('Invalid or duplicate stored Keepalived VRID')
                pool.add(router.vrid)
        # Reserve every existing valid wire ID before allocating new values.
        for router in routers:
            pool = used[router.cluster_id_id]
            if router.vrid is None and 1 <= router.id <= 255:
                if router.id in pool:
                    raise RuntimeError('Stored VRID conflicts with a legacy Keepalived router')
                assignments[router.id] = router.id
                pool.add(router.id)
        for router in routers:
            pool = used[router.cluster_id_id]
            if router.vrid is None and router.id not in assignments:
                vrid = next((value for value in range(1, 256) if value not in pool), None)
                if vrid is None:
                    raise RuntimeError('No free Keepalived VRID: more than 255 routers in one cluster')
                assignments[router.id] = vrid
                pool.add(vrid)
        for ident, vrid in assignments.items():
            HaClusterRouter.update(vrid=vrid).where(HaClusterRouter.id == ident).execute()


def down():
    """Retain assigned wire identifiers so a downgrade cannot change VRRP identity."""
    raise RuntimeError('Keepalived VRID assignments must be retained')
