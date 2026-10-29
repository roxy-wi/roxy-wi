"""Bind evidence to registration lifetimes, never reusable numeric primary keys."""
from uuid import uuid4
from peewee import CharField, SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate
from app.modules.db.db_model import HaCluster, PacemakerCluster, HaReadinessProfile


def up():
    database=HaCluster._meta.database
    migrator=SqliteMigrator(database) if isinstance(database,SqliteDatabase) else MySQLMigrator(database)
    for model, field in [(HaCluster,'readiness_key'),(PacemakerCluster,'readiness_key'),
                         (HaReadinessProfile,'registration_key')]:
        table=model._meta.table_name
        if field not in {c.name for c in database.get_columns(table)}:
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
