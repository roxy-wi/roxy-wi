"""Bind evidence to registration lifetimes, never reusable numeric primary keys."""
from uuid import uuid4
from peewee import CharField, SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate
from app.modules.db.db_model import HaCluster, PacemakerCluster, HaReadinessProfile


def up():
    database=HaCluster._meta.database
    fields=[(HaCluster,'readiness_key'),(PacemakerCluster,'readiness_key'),
            (HaReadinessProfile,'registration_key')]
    missing=[(model._meta.table_name,field) for model,field in fields
             if field not in {c.name for c in database.get_columns(model._meta.table_name)}]
    # Legacy plans cannot be safely attached to a newly generated registration.
    # Abort before any DDL so their approved return remains usable on the old code.
    if missing and 'ha_maintenance_plans' in database.get_tables():
        busy=database.execute_sql(
            "SELECT 1 FROM ha_maintenance_plans WHERE active_task_id IS NOT NULL "
            "OR status IN ('draining','ready','unknown','resuming','return-reviewed') LIMIT 1"
        ).fetchone()
        if busy:
            raise RuntimeError('Finish or recover every active HA maintenance plan through its approved return before upgrading')
    migrator=SqliteMigrator(database) if isinstance(database,SqliteDatabase) else MySQLMigrator(database)
    for table,field in missing:
        if isinstance(database, SqliteDatabase):
            # Peewee rebuilds the parent table for NOT NULL, cascading deletes
            # into its children when foreign_keys is enabled.
            database.execute_sql(
                f'ALTER TABLE "{table}" ADD COLUMN "{field}" ' "VARCHAR(32) NOT NULL DEFAULT ''"
            )
        else:
            migrate(migrator.add_column(table,field,CharField(max_length=32,default='')))
    for model in (HaCluster,PacemakerCluster):
        for row in model.select().where(model.readiness_key==''):
            model.update(readiness_key=uuid4().hex).where((model.id==row.id)&(model.readiness_key=='')).execute()
    table=HaReadinessProfile._meta.table_name
    for index in database.get_indexes(table):
        if index.unique and tuple(index.columns)==('group_id','provider','cluster_id'):
            migrate(migrator.drop_index(table,index.name))
    columns=('group_id','provider','cluster_id','registration_key')
    if not any(tuple(i.columns)==columns and i.unique for i in database.get_indexes(table)):
        migrate(migrator.add_index(table,columns,unique=True))
    # Legacy profiles/reports remain stored but unbound: their provenance cannot
    # distinguish a deleted/reused registration and must not be guessed.


def down():
    raise RuntimeError('Readiness registration identity must be retained')
