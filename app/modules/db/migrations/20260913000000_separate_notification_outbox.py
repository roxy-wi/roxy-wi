import json

from app.modules.db.db_model import ServiceEvent, ServiceEventDelivery, ServiceNotification
from app.modules.db.service_event import notification_payload
from app.modules.db.service_event_storage import event_key


def up():
    """Copy delivery work before diagnostics can expire, in resumable batches."""
    database = ServiceNotification._meta.database
    database.create_tables([ServiceNotification], safe=True)
    last_id = 0
    while True:
        rows = list(ServiceEventDelivery.select(
            ServiceEventDelivery, ServiceEvent.payload.alias('event_payload')
        ).join(ServiceEvent).where(ServiceEventDelivery.id > last_id)
                    .order_by(ServiceEventDelivery.id).limit(500).dicts())
        if not rows:
            break
        with database.atomic():
            for row in rows:
                if not ServiceNotification.select().where(
                    ServiceNotification.event_id == row['event_id']
                ).exists():
                    event = json.loads(row['event_payload'])
                    ServiceNotification.create(
                        event_id=row['event_id'],
                        event_key=event_key(event),
                        category=event['source'],
                        observed_at=ServiceEvent.get_by_id(row['event_id']).observed_at,
                        payload=notification_payload(event),
                        status=row['status'],
                        attempts=row['attempts'],
                        last_error=row['last_error'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at'],
                        delivered_at=row['delivered_at'],
                    )
        last_id = rows[-1]['id']


def down():
    raise RuntimeError('Notification outbox rollback requires preserving undelivered notifications')
