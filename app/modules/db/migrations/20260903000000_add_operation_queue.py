from peewee import CharField, DateTimeField, IntegerField, TextField
from playhouse.migrate import migrate

from app.modules.db.db_model import connect


def _column_names(database):
    return {column.name for column in database.get_columns('installation_tasks')}


def up():
    """Add the durable outbox fields used by the operations worker."""
    database = connect()
    migrator = connect(get_migrator=1)
    existing = _column_names(database)
    changes = []
    fields = {
        'operation_id': CharField(null=True, max_length=64),
        'operation_type': CharField(null=True, max_length=64),
        'operation_payload': TextField(null=True),
        'attempts': IntegerField(default=0),
        'updated_at': DateTimeField(null=True),
        'published_at': DateTimeField(null=True),
    }
    for name, field in fields.items():
        if name not in existing:
            changes.append(migrator.add_column('installation_tasks', name, field))
    if changes:
        migrate(*changes)


def down():
    database = connect()
    migrator = connect(get_migrator=1)
    existing = _column_names(database)
    changes = [
        migrator.drop_column('installation_tasks', name)
        for name in (
            'published_at', 'updated_at', 'attempts', 'operation_payload',
            'operation_type', 'operation_id',
        )
        if name in existing
    ]
    if changes:
        migrate(*changes)
