"""Retain old reports unbound; numeric server IDs cannot establish provenance."""
from uuid import uuid4
from peewee import CharField, SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate
from app.modules.db.db_model import Server, OperationalAssessment


def up():
    database = Server._meta.database
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    for model, field in ((Server, 'registration_key'), (OperationalAssessment, 'server_registration_key')):
        table = model._meta.table_name
        if field not in {column.name for column in database.get_columns(table)}:
            migrate(migrator.add_column(table, field, CharField(max_length=32, default='')))
    for row in Server.select(Server.server_id).where((Server.registration_key == '') | Server.registration_key.is_null()):
        Server.update(registration_key=uuid4().hex).where(
            (Server.server_id == row.server_id) & ((Server.registration_key == '') | Server.registration_key.is_null())).execute()
    table = Server._meta.table_name
    if not any(index.unique and tuple(index.columns) == ('registration_key',) for index in database.get_indexes(table)):
        migrate(migrator.add_index(table, ('registration_key',), unique=True))
    # Never attach an existing assessment to a current server merely because its
    # ID/IP matches. Old proxy tasks without the new identity must be resubmitted.


def down():
    raise RuntimeError('Server registration identities and report provenance must be retained')
