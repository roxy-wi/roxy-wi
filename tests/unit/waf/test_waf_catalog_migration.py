import importlib

from peewee import SqliteDatabase

from app.modules.db.db_model import WafRules
from app.modules.db import waf as waf_sql
from app.modules.common.common import resolve_waf_config_path


def test_bundled_rule_filenames_are_valid(tmp_path, monkeypatch):
    database = SqliteDatabase(tmp_path / 'catalog.db')
    monkeypatch.setattr('app.modules.common.common.sql.get_setting', lambda _: '/etc/haproxy')
    with database.bind_ctx([WafRules], bind_refs=False, bind_backrefs=False):
        database.create_tables([WafRules])
        waf_sql.insert_waf_rules('192.0.2.1')
        rules = list(WafRules.select())
        assert rules
        for rule in rules:
            assert resolve_waf_config_path('haproxy', rule.rule_file).endswith('/rules/' + rule.rule_file)
    database.close()


def test_migration_repairs_known_legacy_filename_without_changing_other_rules(tmp_path):
    database = SqliteDatabase(tmp_path / 'legacy-catalog.db')
    with database.bind_ctx([WafRules], bind_refs=False, bind_backrefs=False):
        database.create_tables([WafRules])
        first = WafRules.create(serv='192.0.2.1', rule_name='Trojans Protections',
                               rule_file='modsecurity_crs_45_trojans.conf ', en=0, service='haproxy')
        second = WafRules.create(serv='192.0.2.2', rule_name='Trojans Protections',
                                rule_file='modsecurity_crs_45_trojans.conf ', en=1, service='haproxy')
        other = WafRules.create(serv='192.0.2.1', rule_name='Manual', rule_file='manual.conf',
                               en=1, service='nginx')
        migration = importlib.import_module('app.modules.db.migrations.20261017010000_fix_waf_rule_filename')
        migration.up()
        migration.up()
        assert WafRules.get_by_id(first.id).rule_file == 'modsecurity_crs_45_trojans.conf'
        assert WafRules.get_by_id(first.id).en == 0
        assert WafRules.get_by_id(second.id).rule_file == 'modsecurity_crs_45_trojans.conf'
        assert WafRules.get_by_id(second.id).en == 1
        assert WafRules.get_by_id(other.id).rule_file == 'manual.conf'
        assert WafRules.select().count() == 3
    database.close()
