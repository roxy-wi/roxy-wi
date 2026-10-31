"""Upgrades remove unbound proxy reports without deleting other assessments."""
import importlib

import pytest
from peewee import IntegrityError, SqliteDatabase
from playhouse.migrate import SqliteMigrator, migrate

from app.modules.db.db_model import Server, OperationalAssessment, HaproxySection, LetsEncrypt
from app.modules.db import server as server_sql


def test_registration_migration_is_idempotent_and_removes_only_unbound_proxy_reports():
    migration = importlib.import_module('app.modules.db.migrations.20261030010000_proxy_registration_identity')
    database = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
    models = [Server, OperationalAssessment, HaproxySection, LetsEncrypt]
    with database.bind_ctx(models, bind_refs=False, bind_backrefs=False):
        database.create_tables(models)
        one = Server.create(hostname='Original one', ip='192.0.2.1', group_id='1')
        two = Server.create(hostname='Original two', ip='192.0.2.2', group_id='1')
        section = HaproxySection.create(server_id=one, type='backend', name='web', config={'maxconn': 100})
        certificate = LetsEncrypt.create(server_id=one, domains='example.test', email='admin@example.test',
            api_key='', api_token='', type='http', description='Certificate linked to the server')
        # Service/HA pages consume these established positional tuples.
        assert list(server_sql.select_servers(server=one.ip))[0][:3] == (one.server_id, one.hostname, one.ip)
        assert list(server_sql.get_dick_permit(1, disable=0, virt=True))[0][2] == one.ip
        report = OperationalAssessment.create(group_id=1, user_id=1, kind='proxy-diagnostics',
            subject=f'haproxy:{one.server_id}', result='historical encrypted bytes')
        unrelated = [OperationalAssessment.create(group_id=1, user_id=1, kind=kind,
            subject=f'haproxy:{one.server_id}', result='other encrypted bytes')
            for kind in ('ha-readiness', 'ha-maintenance', 'served-tls')]
        migrator = SqliteMigrator(database)
        for index in database.get_indexes('servers'):
            if tuple(index.columns) == ('registration_key',):
                migrate(migrator.drop_index('servers', index.name))
        database.execute_sql('ALTER TABLE servers DROP COLUMN registration_key')
        database.execute_sql('ALTER TABLE operational_assessments DROP COLUMN server_registration_key')
        migration.up()
        keys = {row.server_id: row.registration_key for row in Server.select()}
        assert len(set(keys.values())) == 2 and all(len(key) == 32 for key in keys.values())
        assert OperationalAssessment.get_or_none(OperationalAssessment.id == report.id) is None
        for row in unrelated:
            assert OperationalAssessment.get_by_id(row.id).result == 'other encrypted bytes'
        bound = OperationalAssessment.create(group_id=1, user_id=1, kind='proxy-diagnostics',
            subject=f'haproxy:{one.server_id}', server_registration_key=keys[one.server_id],
            result='current encrypted bytes')
        queued = OperationalAssessment.create(group_id=2, user_id=2, kind='proxy-diagnostics',
            subject='nginx:99', result='')
        migration.up()
        assert {row.server_id: row.registration_key for row in Server.select()} == keys
        assert HaproxySection.get_by_id(section.id).config == {'maxconn': 100}
        assert LetsEncrypt.get_by_id(certificate.id).server_id_id == one.server_id
        assert database.execute_sql('PRAGMA foreign_keys').fetchone() == (1,)
        assert database.execute_sql('PRAGMA foreign_key_check').fetchall() == []
        assert OperationalAssessment.get_by_id(bound.id).result == 'current encrypted bytes'
        assert OperationalAssessment.get_or_none(OperationalAssessment.id == queued.id) is None
        with pytest.raises(IntegrityError):
            Server.create(hostname='Duplicate identity', ip='192.0.2.3', group_id='1', registration_key=keys[one.server_id])
        Server.delete_by_id(two.server_id)
        replacement = Server.create(hostname='Replacement two', ip='192.0.2.2', group_id='1')
        assert replacement.server_id == two.server_id
        assert replacement.registration_key not in keys.values()
        with pytest.raises(RuntimeError, match='retained'):
            migration.down()
    database.close()
