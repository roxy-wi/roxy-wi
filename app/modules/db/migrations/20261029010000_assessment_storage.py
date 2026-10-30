from peewee import SqliteDatabase
from app.modules.db.db_model import OperationalAssessment


def up():
    database=OperationalAssessment._meta.database
    if not isinstance(database,SqliteDatabase):
        database.execute_sql('ALTER TABLE operational_assessments MODIFY result LONGTEXT NOT NULL')


def down():
    # Never truncate existing encrypted evidence during a downgrade.
    pass
