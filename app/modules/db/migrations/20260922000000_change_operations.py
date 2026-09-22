from peewee import SqliteDatabase
from playhouse.migrate import migrate, SqliteMigrator, MySQLMigrator

from app.modules.db.db_model import ConfigChange


def up():
    database = ConfigChange._meta.database
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    columns = {column.name for column in database.get_columns('config_changes')}
    for name in ('active_task_id', 'last_task_id', 'scheduled_by'):
        if name not in columns:
            migrate(migrator.add_column('config_changes', name, ConfigChange._meta.fields[name]))
    if not any(index.columns == ['active_task_id'] for index in database.get_indexes('config_changes')):
        migrate(migrator.add_index('config_changes', ('active_task_id',), False))


def down():
    raise RuntimeError('Drain Change Center operations before rolling back this migration')
