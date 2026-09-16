import json

from peewee import CharField, SQL, SqliteDatabase
from playhouse.migrate import MySQLMigrator, SqliteMigrator, migrate

from app.modules.db.db_model import (
    Alerts, Metrics, MetricsHttpStatus, PortScannerHistory,
    ServiceEvent, ServiceEventPosition, ServiceEventRetention,
)
from app.modules.db.service_event_storage import (
    METRIC_MODELS, advance_position, event_key, lock_position, write_transaction,
)


def _identify_one(model, condition, identity):
    condition &= model.event_id.is_null()
    if isinstance(model._meta.database, SqliteDatabase):
        # Legacy graph/history tables have no primary key. Select one identical
        # legacy row, without relying on SQLite's optional UPDATE LIMIT extension.
        condition = SQL('rowid').in_(model.select(SQL('rowid')).where(condition).limit(1))
        return model.update(**identity).where(condition).execute()
    return model.update(**identity).where(condition).limit(1).execute()


def _backfill(event):
    data = json.loads(event.payload)
    data['observed_at'] = event.observed_at
    identity = {'event_id': event.event_id, 'event_key': event_key(data)}
    position = lock_position(data)
    advance_position(position, data)
    if event.event_type == 'metrics.sample.collected':
        model = METRIC_MODELS[event.service]
        if model.select().where(model.event_id == event.event_id).exists():
            return
        values = data['values']
        condition = (model.serv == data['server_address']) & (model.date == event.observed_at)
        names = ('curr_con', 'cur_ssl_con', 'sess_rate', 'max_sess_rate') if model is Metrics else ('conn',)
        for name in names:
            condition &= getattr(model, name) == values[name]
        _identify_one(model, condition, identity)
        if model is Metrics:
            condition = ((MetricsHttpStatus.serv == data['server_address'])
                         & (MetricsHttpStatus.date == event.observed_at))
            for name, source in (
                ('ok_ans', 'http_2xx'), ('redir_ans', 'http_3xx'),
                ('not_found_ans', 'http_4xx'), ('err_ans', 'http_5xx'),
            ):
                condition &= getattr(MetricsHttpStatus, name) == values[source]
            _identify_one(MetricsHttpStatus, condition, identity)
    elif event.event_type == 'checker.status.changed':
        if not Alerts.select().where(Alerts.event_id == event.event_id).exists():
            _identify_one(Alerts, (
                (Alerts.ip == data['server_address']) & (Alerts.port == data.get('port', 0))
                & (Alerts.service == 'Checker') & (Alerts.user_group == event.user_group)
                & (Alerts.message == event.message) & (Alerts.level == event.level)
                & (Alerts.date == event.observed_at)
            ), identity)
    elif event.event_type == 'portscanner.scan.completed':
        # V1 snapshots are no longer accepted by the receiver. Existing human
        # history is preserved; the position also fences the first v2 delivery.
        return


def up():
    database = ServiceEvent._meta.database
    migrator = SqliteMigrator(database) if isinstance(database, SqliteDatabase) else MySQLMigrator(database)
    models = [*METRIC_MODELS.values(), MetricsHttpStatus, Alerts, PortScannerHistory]
    for model in models:
        table = model._meta.table_name
        columns = {column.name for column in database.get_columns(table)}
        for name in ('event_id', 'event_key'):
            if name not in columns:
                migrate(migrator.add_column(table, name, CharField(null=True, max_length=64)))
        indexes = {tuple(index.columns) for index in database.get_indexes(table)}
        definitions = [(('event_id',), model is not PortScannerHistory)]
        definitions.append((('event_key', 'port', 'status'), True) if model is PortScannerHistory
                           else (('event_key',), True))
        for columns, unique in definitions:
            if columns not in indexes:
                migrate(migrator.add_index(table, columns, unique=unique))

    database.create_tables([ServiceEventPosition, ServiceEventRetention], safe=True)
    last_id = ''
    while True:
        rows = list(ServiceEvent.select().where(ServiceEvent.event_id > last_id)
                    .order_by(ServiceEvent.event_id).limit(250))
        if not rows:
            break
        with write_transaction():
            for event in rows:
                if event.event_type in (
                    'checker.status.changed', 'metrics.sample.collected', 'portscanner.scan.completed'
                ):
                    _backfill(event)
        last_id = rows[-1].event_id

    retained_indexes = {
        ('event_id',), ('received_at',),
        ('assignment_id', 'assignment_revision', 'lease_epoch', 'sequence'),
    }
    for index in database.get_indexes('service_events'):
        if tuple(index.columns) not in retained_indexes:
            migrate(migrator.drop_index('service_events', index.name))


def down():
    raise RuntimeError('History identity rollback would remove delivery deduplication')
