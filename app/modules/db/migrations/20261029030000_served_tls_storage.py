from peewee import SqliteDatabase
from app.modules.db.db_model import ServedTlsMonitor


def up():
    database=ServedTlsMonitor._meta.database
    if not isinstance(database,SqliteDatabase):
        database.execute_sql('ALTER TABLE served_tls_monitors MODIFY configuration LONGTEXT NOT NULL')


def down():
    # Never truncate existing encrypted evidence during a downgrade.
    pass
