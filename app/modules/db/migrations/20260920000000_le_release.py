from peewee import SqliteDatabase
from playhouse.migrate import migrate, SqliteMigrator, MySQLMigrator

from app.modules.db.db_model import LetsEncryptState, LetsEncryptDnsProfile


def up():
    database = LetsEncryptState._meta.database
    database.create_tables([LetsEncryptDnsProfile], safe=True)
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    columns = {column.name for column in database.get_columns('lets_encrypt_state')}
    for name in ('deployment', 'last_error_code', 'dns_profile_id', 'draft', 'preflight', 'notification_state'):
        if name not in columns:
            migrate(migrator.add_column('lets_encrypt_state', name, LetsEncryptState._meta.fields[name]))


def down():
    raise RuntimeError('Finish certificate recovery and export DNS profiles before rolling back LE')
