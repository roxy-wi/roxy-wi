from peewee import MySQLDatabase

from app.modules.db.db_model import WorkerRun, connect


def up():
    database = connect()
    if isinstance(database, MySQLDatabase):
        database.execute_sql('ALTER TABLE worker_states MODIFY started_at DATETIME(6) NULL')
    database.create_tables([WorkerRun], safe=True)


def down():
    connect().drop_tables([WorkerRun], safe=True)
