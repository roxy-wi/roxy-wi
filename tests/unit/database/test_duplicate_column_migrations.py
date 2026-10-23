import importlib

import pytest
from peewee import OperationalError

MIGRATIONS = [
    ('app.modules.db.migrations.20230101000012_add_private_key_to_cred', 'private_key', 'cred'),
    ('app.modules.db.migrations.20230101000013_add_is_checker_to_udp_balancers', 'is_checker', 'udp_balancers'),
]


def raising(error):
    def migrate(*operations):
        raise error
    return migrate


@pytest.mark.parametrize(('module_name', 'column', 'table'), MIGRATIONS)
def test_existing_column_is_tolerated(module_name, column, table, monkeypatch, capsys):
    migration = importlib.import_module(module_name)
    errors = [
        OperationalError(f'duplicate column name: {column}'),
        # psycopg2 ends its message with a newline
        OperationalError(f'column "{column}" of relation "{table}" already exists\n'),
    ]
    for error in errors:
        monkeypatch.setattr(migration, 'migrate', raising(error))
        migration.up()
        assert 'Column already exists' in capsys.readouterr().out


@pytest.mark.parametrize(('module_name', 'column', 'table'), MIGRATIONS)
def test_other_errors_are_not_swallowed(module_name, column, table, monkeypatch):
    migration = importlib.import_module(module_name)
    monkeypatch.setattr(migration, 'migrate', raising(OperationalError('database is locked')))

    with pytest.raises(OperationalError, match='database is locked'):
        migration.up()
