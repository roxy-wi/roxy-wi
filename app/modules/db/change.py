from datetime import datetime, timedelta
from time import sleep
from threading import RLock

from peewee import JOIN, OperationalError

from app.modules.common.time import utc_now as _utc_now
from app.modules.db.common import out_error
from app.modules.db.db_model import (
    ConfigChange,
    ConfigChangeDelivery,
    ConfigChangeEvent,
    ConfigChangeTarget,
    ConfigChangeWebhook,
)
from app.modules.roxywi.exception import RoxywiConflictError, RoxywiResourceNotFound


_UPDATABLE_FIELDS = {
    'action', 'approved_by', 'batch_size', 'deployment_output', 'deployed_at', 'description',
    'diff', 'execution_mode', 'health_check_interval', 'health_check_mode',
    'health_check_retries', 'manual_promotion', 'max_parallel', 'pause_requested',
    'maintenance_window_end', 'notification_channels', 'notification_destinations', 'schedule_base_status',
    'scheduled_at', 'scheduled_by', 'drift_checked_at', 'drift_diff', 'drift_status', 'finished_at',
    'rollback_output', 'started_at', 'status', 'title', 'updated_at', 'validation_output',
}

_TARGET_UPDATABLE_FIELDS = {
    'batch', 'deployed_at', 'deployment_output', 'excluded', 'excluded_reason',
    'health_output', 'is_canary', 'rollback_output', 'status', 'updated_at',
    'validation_output', 'drift_checked_at', 'drift_diff', 'drift_status',
}

_LOCK_RETRY_DELAYS = (0.1, 0.25, 0.5, 1.0)
_WRITE_LOCK = RLock()

_CHANGE_CREATE_DEFAULTS = {
    'batch_size': 0,
    'max_parallel': 8,
    'manual_promotion': 0,
    'health_check_mode': 'full',
    'health_check_retries': 1,
    'health_check_interval': 0,
    'pause_requested': 0,
    'notification_channels': '[]',
    'notification_destinations': '[]',
    'drift_status': 'unknown',
}

_TARGET_CREATE_DEFAULTS = {
    'batch': 0,
    'is_canary': 0,
    'excluded': 0,
    'drift_status': 'unknown',
}

_WEBHOOK_UPDATABLE_FIELDS = {
    'enabled', 'events', 'name', 'secret_encrypted', 'updated_at', 'url', 'verify_tls',
}

_DELIVERY_UPDATABLE_FIELDS = {
    'attempts', 'delivered_at', 'error', 'next_attempt_at', 'response_code',
    'status', 'updated_at',
}

def _is_database_locked(exc: Exception) -> bool:
    return isinstance(exc, OperationalError) and 'database is locked' in str(exc).lower()


def _execute_write(operation):
    """Retry short Change Center writes when another SQLite writer is finishing."""
    with _WRITE_LOCK:
        for attempt in range(len(_LOCK_RETRY_DELAYS) + 1):
            try:
                return operation()
            except Exception as exc:
                if not _is_database_locked(exc):
                    raise
                if attempt == len(_LOCK_RETRY_DELAYS):
                    raise RoxywiConflictError(
                        'The database is busy with another Roxy-WI task. Wait a moment and retry.'
                    ) from exc
                sleep(_LOCK_RETRY_DELAYS[attempt])


def create_change(**values) -> ConfigChange:
    values = {**_CHANGE_CREATE_DEFAULTS, **values}
    try:
        return _execute_write(lambda: ConfigChange.create(**values))
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def get_change(change_id: int) -> ConfigChange:
    try:
        return ConfigChange.get(ConfigChange.id == change_id)
    except ConfigChange.DoesNotExist as exc:
        raise RoxywiResourceNotFound from exc
    except Exception as exc:
        return out_error(exc)


def list_changes(group_id: int, *, service: str | None = None, status: str | None = None):
    query = ConfigChange.select().where(ConfigChange.group_id == group_id)
    if service:
        query = query.where(ConfigChange.service == service)
    if status:
        query = query.where(ConfigChange.status == status)
    try:
        return query.order_by(ConfigChange.created_at.desc()).execute()
    except Exception as exc:
        return out_error(exc)


def update_change(change_id: int, **values) -> ConfigChange:
    invalid_fields = set(values) - _UPDATABLE_FIELDS
    if invalid_fields:
        raise ValueError(f'Unsupported change fields: {", ".join(sorted(invalid_fields))}')
    values['updated_at'] = datetime.now()
    try:
        _execute_write(
            lambda: ConfigChange.update(**values).where(ConfigChange.id == change_id).execute()
        )
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return get_change(change_id)


def transition_change(change_id: int, from_statuses: tuple[str, ...], status: str, **values) -> ConfigChange:
    """Atomically claim a workflow transition and reject concurrent actions."""
    invalid_fields = set(values) - _UPDATABLE_FIELDS
    if invalid_fields:
        raise ValueError(f'Unsupported change fields: {", ".join(sorted(invalid_fields))}')
    values.update(status=status, updated_at=datetime.now())
    try:
        updated = _execute_write(
            lambda: (
                ConfigChange.update(**values)
                .where((ConfigChange.id == change_id) & (ConfigChange.status.in_(from_statuses)))
                .execute()
            )
        )
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    if updated != 1:
        raise RoxywiConflictError('The change is no longer in a state that allows this operation')
    return get_change(change_id)


def create_targets(change_id: int, targets: list[dict]) -> list[ConfigChangeTarget]:
    """Persist an immutable rollout topology for a configuration change."""
    if not targets:
        return []
    values = [
        {**_TARGET_CREATE_DEFAULTS, **target, 'change': change_id}
        for target in targets
    ]
    database = ConfigChangeTarget._meta.database
    try:
        def insert_targets():
            with database.atomic():
                return ConfigChangeTarget.insert_many(values).execute()

        _execute_write(insert_targets)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return list_targets(change_id)


def list_targets(change_id: int) -> list[ConfigChangeTarget]:
    try:
        return list(
            ConfigChangeTarget.select()
            .where(ConfigChangeTarget.change == change_id)
            .order_by(ConfigChangeTarget.position.asc())
        )
    except Exception as exc:
        return out_error(exc)


def get_target(target_id: int) -> ConfigChangeTarget:
    try:
        return ConfigChangeTarget.get(ConfigChangeTarget.id == target_id)
    except ConfigChangeTarget.DoesNotExist as exc:
        raise RoxywiResourceNotFound from exc
    except Exception as exc:
        return out_error(exc)


def get_change_target(change_id: int, target_id: int) -> ConfigChangeTarget:
    try:
        return ConfigChangeTarget.get(
            (ConfigChangeTarget.id == target_id) &
            (ConfigChangeTarget.change == change_id)
        )
    except ConfigChangeTarget.DoesNotExist as exc:
        raise RoxywiResourceNotFound from exc
    except Exception as exc:
        return out_error(exc)


def update_target(target_id: int, **values) -> ConfigChangeTarget:
    invalid_fields = set(values) - _TARGET_UPDATABLE_FIELDS
    if invalid_fields:
        raise ValueError(f'Unsupported target fields: {", ".join(sorted(invalid_fields))}')
    updated_at = datetime.now()
    values['updated_at'] = updated_at
    target = get_target(target_id)
    database = ConfigChangeTarget._meta.database
    try:
        def update_with_heartbeat():
            with database.atomic():
                ConfigChangeTarget.update(**values).where(
                    ConfigChangeTarget.id == target_id
                ).execute()
                ConfigChange.update(updated_at=updated_at).where(
                    ConfigChange.id == target.change_id
                ).execute()

        _execute_write(update_with_heartbeat)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return get_target(target_id)


def update_drift_results(
    change_id: int,
    targets: list[ConfigChangeTarget],
    *,
    drift_status: str,
    drift_checked_at: datetime,
    drift_diff: str | None,
) -> ConfigChange:
    """Persist one drift scan as a single atomic database operation."""
    database = ConfigChangeTarget._meta.database
    for target in targets:
        target.updated_at = drift_checked_at

    try:
        def update_scan():
            with database.atomic():
                if targets:
                    ConfigChangeTarget.bulk_update(
                        targets,
                        fields=(
                            ConfigChangeTarget.drift_status,
                            ConfigChangeTarget.drift_checked_at,
                            ConfigChangeTarget.drift_diff,
                            ConfigChangeTarget.updated_at,
                        ),
                        batch_size=50,
                    )
                ConfigChange.update(
                    drift_status=drift_status,
                    drift_checked_at=drift_checked_at,
                    drift_diff=drift_diff,
                    updated_at=drift_checked_at,
                ).where(ConfigChange.id == change_id).execute()

        _execute_write(update_scan)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return get_change(change_id)


def reset_targets(change_id: int, *, status: str = 'pending') -> list[ConfigChangeTarget]:
    updated_at = datetime.now()
    database = ConfigChangeTarget._meta.database
    try:
        def reset_with_heartbeat():
            with database.atomic():
                (
                    ConfigChangeTarget.update(
                        status=status,
                        deployment_output=None,
                        health_output=None,
                        rollback_output=None,
                        drift_status='unknown',
                        drift_checked_at=None,
                        drift_diff=None,
                        deployed_at=None,
                        updated_at=updated_at,
                    )
                    .where(
                        (ConfigChangeTarget.change == change_id) &
                        (ConfigChangeTarget.excluded == 0)
                    )
                    .execute()
                )
                ConfigChange.update(updated_at=updated_at).where(
                    ConfigChange.id == change_id
                ).execute()

        _execute_write(reset_with_heartbeat)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return list_targets(change_id)


def create_event(**values) -> ConfigChangeEvent:
    values.setdefault('created_at', datetime.now())
    try:
        return _execute_write(lambda: ConfigChangeEvent.create(**values))
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def list_events(
    group_id: int,
    *,
    change_id: int | None = None,
    service: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    after_id: int | None = None,
    limit: int = 200,
) -> list[ConfigChangeEvent]:
    query = (
        ConfigChangeEvent.select(ConfigChangeEvent, ConfigChange, ConfigChangeTarget)
        .join(ConfigChange)
        .switch(ConfigChangeEvent)
        .join(ConfigChangeTarget, JOIN.LEFT_OUTER)
        .where(ConfigChange.group_id == group_id)
    )
    if change_id is not None:
        query = query.where(ConfigChangeEvent.change == change_id)
    if service:
        query = query.where(ConfigChange.service == service)
    if event_type:
        query = query.where(ConfigChangeEvent.event_type == event_type)
    if status:
        query = query.where(ConfigChangeEvent.status == status)
    if search:
        query = query.where(
            ConfigChangeEvent.message.contains(search) |
            ConfigChange.title.contains(search) |
            ConfigChangeTarget.server_name.contains(search) |
            ConfigChangeTarget.server_ip.contains(search)
        )
    if date_from:
        query = query.where(ConfigChangeEvent.created_at >= date_from)
    if date_to:
        query = query.where(ConfigChangeEvent.created_at <= date_to)
    if after_id:
        query = query.where(ConfigChangeEvent.id > after_id)
        query = query.order_by(ConfigChangeEvent.id.asc())
    else:
        query = query.order_by(ConfigChangeEvent.id.desc())
    try:
        return list(query.limit(limit))
    except Exception as exc:
        return out_error(exc)


def list_due_scheduled(now: datetime, limit: int = 10) -> list[ConfigChange]:
    try:
        return list(
            ConfigChange.select()
            .where(
                (ConfigChange.status == 'scheduled') &
                (ConfigChange.scheduled_at.is_null(False)) &
                (ConfigChange.scheduled_at <= now)
            )
            .order_by(ConfigChange.scheduled_at.asc())
            .limit(limit)
        )
    except Exception as exc:
        return out_error(exc)


def list_latest_deployed_changes(limit: int = 100) -> list[ConfigChange]:
    """Return the newest deployed baseline for every managed config path."""
    try:
        candidates = (
            ConfigChange.select()
            .where(ConfigChange.status == 'deployed')
            .order_by(ConfigChange.deployed_at.desc(), ConfigChange.id.desc())
            .iterator()
        )
    except Exception as exc:
        return out_error(exc)
    latest = []
    seen = set()
    for change in candidates:
        key = (change.group_id, change.server_id, change.service, change.remote_path)
        if key in seen:
            continue
        seen.add(key)
        latest.append(change)
        if len(latest) >= limit:
            break
    return latest


def create_webhook(**values) -> ConfigChangeWebhook:
    values.setdefault('created_at', datetime.now())
    values.setdefault('updated_at', datetime.now())
    try:
        return _execute_write(lambda: ConfigChangeWebhook.create(**values))
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def list_webhooks(group_id: int, *, enabled_only: bool = False) -> list[ConfigChangeWebhook]:
    query = ConfigChangeWebhook.select().where(ConfigChangeWebhook.group_id == group_id)
    if enabled_only:
        query = query.where(ConfigChangeWebhook.enabled == 1)
    try:
        return list(query.order_by(ConfigChangeWebhook.name.asc()))
    except Exception as exc:
        return out_error(exc)


def get_webhook(webhook_id: int, group_id: int | None = None) -> ConfigChangeWebhook:
    query = ConfigChangeWebhook.select().where(ConfigChangeWebhook.id == webhook_id)
    if group_id is not None:
        query = query.where(ConfigChangeWebhook.group_id == group_id)
    webhook = query.get_or_none()
    if not webhook:
        raise RoxywiResourceNotFound('Change Center webhook was not found')
    return webhook


def update_webhook(webhook_id: int, group_id: int, **values) -> ConfigChangeWebhook:
    invalid_fields = set(values) - _WEBHOOK_UPDATABLE_FIELDS
    if invalid_fields:
        raise ValueError(f'Unsupported webhook fields: {", ".join(sorted(invalid_fields))}')
    values['updated_at'] = datetime.now()
    try:
        updated = _execute_write(
            lambda: ConfigChangeWebhook.update(**values).where(
                (ConfigChangeWebhook.id == webhook_id) &
                (ConfigChangeWebhook.group_id == group_id)
            ).execute()
        )
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    if updated != 1:
        raise RoxywiResourceNotFound('Change Center webhook was not found')
    return get_webhook(webhook_id, group_id)


def delete_webhook(webhook_id: int, group_id: int) -> None:
    get_webhook(webhook_id, group_id)
    database = ConfigChangeWebhook._meta.database
    try:
        def delete_records():
            with database.atomic():
                ConfigChangeDelivery.delete().where(
                    (ConfigChangeDelivery.destination_type == 'webhook') &
                    (ConfigChangeDelivery.destination_id == webhook_id) &
                    (ConfigChangeDelivery.status.in_(('pending', 'failed', 'delivering')))
                ).execute()
                ConfigChangeWebhook.delete().where(
                    (ConfigChangeWebhook.id == webhook_id) &
                    (ConfigChangeWebhook.group_id == group_id)
                ).execute()

        _execute_write(delete_records)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def create_deliveries(values: list[dict]) -> None:
    if not values:
        return
    now = _utc_now()
    rows = [
        {
            'status': 'pending',
            'attempts': 0,
            'next_attempt_at': now,
            'created_at': now,
            'updated_at': now,
            **value,
        }
        for value in values
    ]
    try:
        _execute_write(lambda: ConfigChangeDelivery.insert_many(rows).execute())
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def list_due_deliveries(now: datetime, limit: int = 50) -> list[ConfigChangeDelivery]:
    stale = now - timedelta(minutes=5)
    try:
        return list(
            ConfigChangeDelivery.select()
            .where(
                (
                    ConfigChangeDelivery.status.in_(('pending', 'failed')) &
                    (ConfigChangeDelivery.next_attempt_at <= now)
                ) |
                (
                    (ConfigChangeDelivery.status == 'delivering') &
                    (ConfigChangeDelivery.updated_at <= stale)
                )
            )
            .order_by(ConfigChangeDelivery.next_attempt_at.asc())
            .limit(limit)
        )
    except Exception as exc:
        return out_error(exc)


def claim_due_deliveries(now: datetime, limit: int = 50) -> list[ConfigChangeDelivery]:
    """Claim a due delivery batch with one write instead of one write per row."""
    stale = now - timedelta(minutes=5)
    due_condition = (
        (
            ConfigChangeDelivery.status.in_(('pending', 'failed')) &
            (ConfigChangeDelivery.next_attempt_at <= now)
        ) |
        (
            (ConfigChangeDelivery.status == 'delivering') &
            (ConfigChangeDelivery.updated_at <= stale)
        )
    )
    database = ConfigChangeDelivery._meta.database
    try:
        def claim_batch():
            atomic = (
                database.atomic('IMMEDIATE')
                if database.__class__.__name__ == 'SqliteExtDatabase'
                else database.atomic()
            )
            with atomic:
                query = (
                    ConfigChangeDelivery.select()
                    .where(due_condition)
                    .order_by(ConfigChangeDelivery.next_attempt_at.asc())
                    .limit(limit)
                )
                if database.__class__.__name__ != 'SqliteExtDatabase':
                    query = query.for_update()
                deliveries = list(query)
                if not deliveries:
                    return []
                delivery_ids = [delivery.id for delivery in deliveries]
                claimed_at = _utc_now()
                ConfigChangeDelivery.update(
                    status='delivering',
                    attempts=ConfigChangeDelivery.attempts + 1,
                    updated_at=claimed_at,
                ).where(ConfigChangeDelivery.id.in_(delivery_ids)).execute()
                for delivery in deliveries:
                    delivery.status = 'delivering'
                    delivery.attempts = int(delivery.attempts or 0) + 1
                    delivery.updated_at = claimed_at
                return deliveries

        return _execute_write(claim_batch)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def get_delivery(delivery_id: int) -> ConfigChangeDelivery:
    delivery = ConfigChangeDelivery.get_or_none(ConfigChangeDelivery.id == delivery_id)
    if not delivery:
        raise RoxywiResourceNotFound('Change Center delivery was not found')
    return delivery


def claim_delivery(delivery_id: int) -> ConfigChangeDelivery | None:
    now = _utc_now()
    stale = now - timedelta(minutes=5)
    try:
        updated = _execute_write(
            lambda: ConfigChangeDelivery.update(
                status='delivering',
                attempts=ConfigChangeDelivery.attempts + 1,
                updated_at=now,
            ).where(
                (ConfigChangeDelivery.id == delivery_id) &
                (
                    ConfigChangeDelivery.status.in_(('pending', 'failed')) |
                    (
                        (ConfigChangeDelivery.status == 'delivering') &
                        (ConfigChangeDelivery.updated_at <= stale)
                    )
                )
            ).execute()
        )
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return get_delivery(delivery_id) if updated == 1 else None


def update_delivery(delivery_id: int, **values) -> ConfigChangeDelivery:
    invalid_fields = set(values) - _DELIVERY_UPDATABLE_FIELDS
    if invalid_fields:
        raise ValueError(f'Unsupported delivery fields: {", ".join(sorted(invalid_fields))}')
    values['updated_at'] = _utc_now()
    try:
        _execute_write(
            lambda: ConfigChangeDelivery.update(**values).where(
                ConfigChangeDelivery.id == delivery_id
            ).execute()
        )
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)
    return get_delivery(delivery_id)


def update_deliveries(deliveries: list[ConfigChangeDelivery]) -> None:
    """Persist delivery outcomes in one short transaction."""
    if not deliveries:
        return
    updated_at = _utc_now()
    for delivery in deliveries:
        delivery.updated_at = updated_at
    database = ConfigChangeDelivery._meta.database
    fields = (
        ConfigChangeDelivery.status,
        ConfigChangeDelivery.delivered_at,
        ConfigChangeDelivery.next_attempt_at,
        ConfigChangeDelivery.response_code,
        ConfigChangeDelivery.error,
        ConfigChangeDelivery.updated_at,
    )
    try:
        def update_batch():
            with database.atomic():
                ConfigChangeDelivery.bulk_update(
                    deliveries,
                    fields=fields,
                    batch_size=50,
                )

        _execute_write(update_batch)
    except RoxywiConflictError:
        raise
    except Exception as exc:
        return out_error(exc)


def list_change_deliveries(change_id: int) -> list[ConfigChangeDelivery]:
    try:
        return list(
            ConfigChangeDelivery.select()
            .where(ConfigChangeDelivery.change == change_id)
            .order_by(ConfigChangeDelivery.id.asc())
        )
    except Exception as exc:
        return out_error(exc)
