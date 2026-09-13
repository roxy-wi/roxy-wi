from peewee import CharField, TextField
from playhouse.migrate import migrate

from app.modules.db.db_model import connect


def _error_column(database):
    return next(
        (column for column in database.get_columns('installation_tasks') if column.name == 'error'),
        None,
    )


def up():
    """Allow the operations worker to retain useful Ansible failure details."""
    database = connect()
    column = _error_column(database)
    if column is not None and 'text' not in column.data_type.lower():
        migrator = connect(get_migrator=1)
        migrate(migrator.alter_column_type('installation_tasks', 'error', TextField(null=True)))


def down():
    database = connect()
    column = _error_column(database)
    if column is not None and 'text' in column.data_type.lower():
        migrator = connect(get_migrator=1)
        migrate(migrator.alter_column_type('installation_tasks', 'error', CharField(null=True)))
