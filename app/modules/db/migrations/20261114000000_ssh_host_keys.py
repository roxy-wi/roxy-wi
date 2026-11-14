"""Store explicitly approved SSH public host keys; never trust keys on upgrade."""
from peewee import SqliteDatabase, TextField
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate

from app.modules.db.db_model import Server


def up():
    """Add nullable storage without rebuilding servers or their child records."""
    database = Server._meta.database
    if 'ssh_host_key' not in {column.name for column in database.get_columns('servers')}:
        migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
        migrate(migrator.add_column('servers', 'ssh_host_key', TextField(null=True)))


def down():
    """Keep approved keys across a rollback."""
    raise RuntimeError('Approved SSH host keys must be retained')
