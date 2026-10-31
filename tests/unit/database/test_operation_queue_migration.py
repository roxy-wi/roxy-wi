"""Upgrade databases created before the durable operation queue existed."""

import importlib

import pytest
from peewee import OperationalError, SqliteDatabase
from playhouse.migrate import SqliteMigrator

from app.modules.db.db_model import Groups, InstallationTasks, User


@pytest.fixture
def migration_database(tmp_path, monkeypatch):
    migration = importlib.import_module(
        'app.modules.db.migrations.20260903000000_add_operation_queue'
    )
    database = SqliteDatabase(tmp_path / 'migration.db', pragmas={'foreign_keys': 1})

    def connect(get_migrator=None):
        return SqliteMigrator(database) if get_migrator else database

    monkeypatch.setattr(migration, 'connect', connect)
    with database.bind_ctx([Groups, User, InstallationTasks], bind_backrefs=False):
        database.create_tables([Groups, User])
        try:
            yield migration, database
        finally:
            database.close()


def test_queue_migration_creates_missing_table_and_can_be_repeated(migration_database):
    migration, database = migration_database
    assert not database.table_exists('installation_tasks')

    migration.up()
    task = InstallationTasks.create(service_name='haproxy', operation_id='operation-1')
    migration.up()

    stored = InstallationTasks.get_by_id(task.id)
    assert stored.operation_id == 'operation-1'
    assert stored.attempts == 0
    assert stored.status == 'created'
    assert stored.updated_at is not None
    assert stored.published_at is None
    assert InstallationTasks.select().count() == 1


@pytest.mark.parametrize('partial', [False, True])
def test_queue_migration_preserves_existing_tasks(migration_database, partial):
    migration, database = migration_database
    database.execute_sql(
        'CREATE TABLE installation_tasks ('
        'id INTEGER PRIMARY KEY, service_name VARCHAR(255), '
        'status VARCHAR(255), error VARCHAR(255))'
    )
    database.execute_sql(
        'INSERT INTO installation_tasks VALUES (1, ?, ?, ?)',
        ('haproxy', 'error', 'Existing installation failure'),
    )
    if partial:
        database.execute_sql('ALTER TABLE installation_tasks ADD COLUMN operation_id VARCHAR(64)')
        database.execute_sql("UPDATE installation_tasks SET operation_id = 'existing-operation'")

    migration.up()
    migration.up()

    row = database.execute_sql(
        'SELECT service_name, status, error, operation_id, operation_type, '
        'operation_payload, attempts, updated_at, published_at FROM installation_tasks'
    ).fetchone()
    assert row == (
        'haproxy', 'error', 'Existing installation failure',
        'existing-operation' if partial else None, None, None, 0, None, None,
    )


def test_queue_migration_propagates_creation_failure(migration_database, monkeypatch):
    migration, database = migration_database

    def fail(*args, **kwargs):
        raise OperationalError('database is locked')

    monkeypatch.setattr(database, 'create_tables', fail)
    with pytest.raises(OperationalError, match='database is locked'):
        migration.up()
    assert not database.table_exists('installation_tasks')
