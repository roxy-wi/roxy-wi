"""Index per-snapshot confirmation reads without rewriting stored evidence."""
from peewee import SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate
from app.modules.db.db_model import PublishedServiceConfirmation


def up():
    database = PublishedServiceConfirmation._meta.database
    table = PublishedServiceConfirmation._meta.table_name
    if any(tuple(index.columns) == ('assessment_id',) for index in database.get_indexes(table)):
        return
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    migrate(migrator.add_index(table, ('assessment_id',), unique=False))


def down():
    # Retaining a non-unique lookup index does not change confirmation semantics.
    pass
