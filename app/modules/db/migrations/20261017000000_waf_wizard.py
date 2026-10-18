from peewee import SqliteDatabase
from playhouse.migrate import MySQLMigrator, migrate

from app.modules.db.db_model import WafRules


def up():
    database = WafRules._meta.database
    if 'wizard' not in {column.name for column in database.get_columns('waf_rules')}:
        if isinstance(database, SqliteDatabase):
            # A constant default permits native ADD COLUMN without Peewee's
            # table rebuild, which misparses the legacy table-level UNIQUE.
            database.execute_sql('ALTER TABLE "waf_rules" ADD COLUMN "wizard" INTEGER NOT NULL DEFAULT 0')
        else:
            migrate(MySQLMigrator(database).add_column('waf_rules', 'wizard', WafRules.wizard))


def down():
    raise RuntimeError('Managed WAF rules must retain their editor ownership')
