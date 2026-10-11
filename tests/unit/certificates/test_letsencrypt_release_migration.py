import importlib

from peewee import SqliteDatabase

from app.modules.db.db_model import LetsEncryptState, LetsEncryptDnsProfile


def test_release_migration_upgrades_existing_rows_and_is_repeatable(tmp_path):
    database = SqliteDatabase(tmp_path / 'migration.db')
    with database.bind_ctx([LetsEncryptState, LetsEncryptDnsProfile], bind_refs=False, bind_backrefs=False):
        database.execute_sql('CREATE TABLE lets_encrypt_state (id INTEGER PRIMARY KEY, le_id INTEGER, status TEXT)')
        database.execute_sql("INSERT INTO lets_encrypt_state VALUES (1, 42, 'active')")
        migration = importlib.import_module('app.modules.db.migrations.20260920000000_le_release')
        migration.up()
        migration.up()
        result = database.execute_sql('SELECT le_id, status, deployment, dns_profile_id, draft, preflight, '
                                      'last_error_code, notification_state FROM lets_encrypt_state').fetchone()
        assert result == (42, 'active', '{}', None, 0, '{}', None, '{}')
        assert LetsEncryptDnsProfile.table_exists()
        assert LetsEncryptDnsProfile.select().count() == 0
    database.close()
