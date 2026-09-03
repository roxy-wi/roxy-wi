from app.modules.db.db_model import (
    ServiceAssignment,
    ServiceCommand,
    ServiceEvent,
    ServiceEventDelivery,
    WorkerState,
    connect,
)


def up():
    """Create durable service-event, notification-outbox and worker-state tables."""
    connect().create_tables(
        [ServiceEvent, ServiceEventDelivery, WorkerState, ServiceAssignment, ServiceCommand],
        safe=True,
    )


def down():
    """Remove service integration persistence."""
    connect().drop_tables(
        [ServiceCommand, ServiceAssignment, ServiceEventDelivery, ServiceEvent, WorkerState],
        safe=True,
    )
