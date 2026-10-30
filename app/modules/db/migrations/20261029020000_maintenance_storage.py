from peewee import SqliteDatabase
from app.modules.db.db_model import HaMaintenancePlan


def up():
    database=HaMaintenancePlan._meta.database
    if not isinstance(database,SqliteDatabase):
        database.execute_sql('ALTER TABLE ha_maintenance_plans MODIFY payload LONGTEXT NOT NULL')


def down():
    # Never truncate existing encrypted evidence during a downgrade.
    pass
