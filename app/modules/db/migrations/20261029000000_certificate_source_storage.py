from peewee import SqliteDatabase
from app.modules.db.db_model import CertificateSource


def up():
    database=CertificateSource._meta.database
    if not isinstance(database,SqliteDatabase):
        database.execute_sql('ALTER TABLE certificate_sources MODIFY configuration LONGTEXT NOT NULL')
        database.execute_sql('ALTER TABLE installation_tasks MODIFY operation_payload LONGTEXT NULL')


def down():
    # Narrowing an encrypted column can truncate existing data.
    pass
