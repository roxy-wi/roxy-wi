from app.modules.db.db_model import (
    AuditEvent, AuditDestination, AuditDestinationRevision, AuditDelivery, AuditState,
)


def up():
    AuditEvent._meta.database.create_tables([
        AuditEvent, AuditDestination, AuditDestinationRevision, AuditDelivery, AuditState,
    ], safe=True)
    AuditState.get_or_create(id=1)


def down():
    raise RuntimeError('Preserve audit records, receiver credentials and queued deliveries before rollback')
