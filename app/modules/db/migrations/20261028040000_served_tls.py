from app.modules.db.db_model import ServedTlsMonitor


def up():
    ServedTlsMonitor._meta.database.create_tables([ServedTlsMonitor], safe=True)


def down():
    ServedTlsMonitor._meta.database.drop_tables([ServedTlsMonitor], safe=True)
