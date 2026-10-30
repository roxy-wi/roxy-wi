"""Upgrades create current identities without guessing ownership of old evidence."""
import importlib

import pytest
from peewee import IntegrityError, SqliteDatabase
from playhouse.migrate import SqliteMigrator, migrate

from app.modules.db.db_model import Server, OperationalAssessment
from app.modules.db import server as server_sql


def test_registration_migration_is_idempotent_and_leaves_legacy_reports_unbound():
    migration = importlib.import_module('app.modules.db.migrations.20261030010000_proxy_registration_identity')
    database = SqliteDatabase(':memory:')
    with database.bind_ctx([Server, OperationalAssessment], bind_refs=False, bind_backrefs=False):
        database.create_tables([Server, OperationalAssessment])
        one = Server.create(hostname='Original one', ip='192.0.2.1', group_id='1')
        two = Server.create(hostname='Original two', ip='192.0.2.2', group_id='1')
        # Service/HA pages consume these established positional tuples.
        assert list(server_sql.select_servers(server=one.ip))[0][:3] == (one.server_id, one.hostname, one.ip)
        assert list(server_sql.get_dick_permit(1, disable=0, virt=True))[0][2] == one.ip
        report = OperationalAssessment.create(group_id=1, user_id=1, kind='proxy-diagnostics',
            subject=f'haproxy:{one.server_id}', result='historical encrypted bytes')
        migrator = SqliteMigrator(database)
        for index in database.get_indexes('servers'):
            if tuple(index.columns) == ('registration_key',):
                migrate(migrator.drop_index('servers', index.name))
        migrate(migrator.drop_column('servers', 'registration_key'))
        migrate(migrator.drop_column('operational_assessments', 'server_registration_key'))
        migration.up()
        keys = {row.server_id: row.registration_key for row in Server.select()}
        assert len(set(keys.values())) == 2 and all(len(key) == 32 for key in keys.values())
        assert OperationalAssessment.get_by_id(report.id).server_registration_key == ''
        assert OperationalAssessment.get_by_id(report.id).result == 'historical encrypted bytes'
        migration.up()
        assert {row.server_id: row.registration_key for row in Server.select()} == keys
        with pytest.raises(IntegrityError):
            Server.create(hostname='Duplicate identity', ip='192.0.2.3', group_id='1', registration_key=keys[one.server_id])
        Server.delete_by_id(two.server_id)
        replacement = Server.create(hostname='Replacement two', ip='192.0.2.2', group_id='1')
        assert replacement.server_id == two.server_id
        assert replacement.registration_key not in keys.values()
        with pytest.raises(RuntimeError, match='retained'):
            migration.down()
    database.close()
