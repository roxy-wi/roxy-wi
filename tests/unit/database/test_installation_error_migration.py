import importlib

from peewee import SqliteDatabase
from playhouse.migrate import SqliteMigrator


def test_installation_error_column_is_expanded_to_text(tmp_path, monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260904000000_expand_installation_task_error'
    )
    database = SqliteDatabase(tmp_path / 'migration.db')
    database.connect()
    database.execute_sql(
        'CREATE TABLE installation_tasks ('
        'id INTEGER PRIMARY KEY, error VARCHAR(255) NULL)'
    )

    def connect(get_migrator=None):
        return SqliteMigrator(database) if get_migrator else database

    monkeypatch.setattr(migration, 'connect', connect)

    try:
        migration.up()
        error_column = next(
            column for column in database.get_columns('installation_tasks')
            if column.name == 'error'
        )
        assert error_column.data_type.upper() == 'TEXT'

        long_error = 'Ansible failure details: ' + ('x' * 4000)
        database.execute_sql(
            'INSERT INTO installation_tasks (error) VALUES (?)',
            (long_error,),
        )
        stored_error = database.execute_sql(
            'SELECT error FROM installation_tasks'
        ).fetchone()[0]
        assert stored_error == long_error
    finally:
        database.close()
