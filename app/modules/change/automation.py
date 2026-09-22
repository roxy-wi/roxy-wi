"""Automation, timeline, notifications and drift monitoring for Change Center."""

from __future__ import annotations

import csv
import difflib
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import requests

import app.modules.config.config as config_mod
from app.modules.common.time import as_naive_utc as normalize_datetime
from app.modules.common.time import utc_iso, utc_now
import app.modules.db.change as change_sql
import app.modules.db.channel as channel_sql
import app.modules.db.user as user_sql
import app.modules.tools.alerting as alerting
from app.modules.db.db_model import (
    ConfigChange,
    ConfigChangeTarget,
    close_database_connection,
)
from app.modules.roxywi import logger
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiPermissionError,
    RoxywiValidationError,
)
from app.modules.subscription.access import CHANGE_CENTER, require_feature


NOTIFIABLE_EVENTS = {
    'change.scheduled': 'info',
    'schedule.missed': 'warning',
    'deployment.succeeded': 'info',
    'deployment.failed': 'critical',
    'rollback.succeeded': 'info',
    'rollback.failed': 'critical',
    'drift.detected': 'warning',
    'drift.resolved': 'info',
    'drift.check_failed': 'warning',
}
DELIVERY_ATTEMPTS = 5
DELIVERY_RETRY_MINUTES = (1, 2, 5, 15, 30)
NOTIFICATION_CHANNEL_LABELS = {
    'email': 'Email',
    'telegram': 'Telegram',
    'slack': 'Slack',
    'mm': 'Mattermost',
    'pd': 'PagerDuty',
}

def _json_loads(value: str | None, default):
    try:
        loaded = json.loads(value or '')
    except (TypeError, ValueError):
        return default
    return loaded


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), default=str)


def _destination_values(destination) -> tuple[str, int]:
    if isinstance(destination, dict):
        channel = destination.get('channel')
        recipient_id = destination.get('recipient_id')
    else:
        channel = getattr(destination, 'channel', None)
        recipient_id = getattr(destination, 'recipient_id', None)
    try:
        recipient_id = int(recipient_id)
    except (TypeError, ValueError) as exc:
        raise RoxywiValidationError('Notification recipient ID must be a positive integer') from exc
    if channel not in NOTIFICATION_CHANNEL_LABELS or recipient_id < 1:
        raise RoxywiValidationError('Unsupported notification destination')
    return channel, recipient_id


def validate_notification_destinations(destinations, group_id: int) -> list[dict]:
    """Normalize recipients and ensure every ID belongs to the active group."""
    normalized = []
    seen = set()
    for destination in destinations or []:
        channel, recipient_id = _destination_values(destination)
        key = (channel, recipient_id)
        if key in seen:
            raise RoxywiValidationError('Notification destinations must not contain duplicates')
        try:
            if channel == 'email':
                user_sql.get_notification_user_with_group(recipient_id, group_id)
            else:
                channel_sql.get_receiver_with_group(channel, recipient_id, group_id)
        except Exception as exc:
            raise RoxywiValidationError(
                f'{NOTIFICATION_CHANNEL_LABELS[channel]} recipient is not available for the active group'
            ) from exc
        normalized.append({'channel': channel, 'recipient_id': recipient_id})
        seen.add(key)
    return normalized


def list_notification_destinations(group_id: int) -> list[dict]:
    """Return selectable group recipients without exposing integration secrets."""
    destinations = []
    for user in user_sql.select_notification_users_by_group_id(group_id):
        destinations.append({
            'channel': 'email',
            'channel_label': NOTIFICATION_CHANNEL_LABELS['email'],
            'recipient_id': user.user_id,
            'label': user.username,
            'destination': user.email,
        })
    for channel in ('telegram', 'slack', 'mm', 'pd'):
        for receiver in channel_sql.get_user_receiver_by_group(channel, group_id):
            destinations.append({
                'channel': channel,
                'channel_label': NOTIFICATION_CHANNEL_LABELS[channel],
                'recipient_id': receiver.id,
                'label': receiver.chanel_name,
                'destination': receiver.chanel_name,
            })
    return destinations


def _actor_name(actor_id: int | None) -> str | None:
    if not actor_id:
        return None
    try:
        return user_sql.get_user_id(actor_id).username
    except Exception:
        return None


def serialize_event(event) -> dict:
    target = event.target if event.target_id else None
    return {
        'id': event.id,
        'change_id': event.change_id,
        'change_title': event.change.title,
        'service': event.change.service,
        'target_id': event.target_id,
        'target_name': target.server_name if target else None,
        'target_ip': target.server_ip if target else None,
        'event_type': event.event_type,
        'status': event.status,
        'message': event.message,
        'details': _json_loads(event.details, event.details) if event.details else None,
        'actor_id': event.actor_id,
        'actor_name': _actor_name(event.actor_id),
        'created_at': utc_iso(event.created_at),
    }


def _event_payload(event, change, target=None) -> dict:
    return {
        'version': '1',
        'id': event.id,
        'type': event.event_type,
        'occurred_at': utc_iso(event.created_at or utc_now()),
        'change': {
            'id': change.id,
            'title': change.title,
            'service': change.service,
            'status': change.status,
            'server_id': change.server_id,
            'group_id': change.group_id,
            'remote_path': change.remote_path,
        },
        'target': None if target is None else {
            'id': target.id,
            'server_id': target.server_id,
            'name': target.server_name,
            'ip': target.server_ip,
            'status': target.status,
            'batch': target.batch,
        },
        'message': event.message,
        'details': _json_loads(event.details, event.details) if event.details else None,
    }


def _queue_event_deliveries(event, change, target=None) -> None:
    payload = _event_payload(event, change, target)
    rows = []
    for webhook in change_sql.list_webhooks(change.group_id, enabled_only=True):
        events = set(_json_loads(webhook.events, []))
        if '*' in events or event.event_type in events:
            rows.append({
                'change': change.id,
                'event': event.id,
                'destination_type': 'webhook',
                'destination_id': webhook.id,
                'payload': _json_dumps(payload),
            })

    level = NOTIFIABLE_EVENTS.get(event.event_type)
    explicit_destinations = _json_loads(
        getattr(change, 'notification_destinations', '[]'), []
    )
    channels = set(_json_loads(change.notification_channels, []))
    if level and (explicit_destinations or channels):
        notification = {
            'subject': f'Change Center #{change.id}: {change.title}',
            'message': event.message,
            'level': level,
            'group_id': change.group_id,
            'server_ip': target.server_ip if target else None,
            'service': change.service,
            'change_id': change.id,
            'event_type': event.event_type,
        }
        if explicit_destinations:
            queued = set()
            for destination in explicit_destinations:
                try:
                    normalized = validate_notification_destinations(
                        [destination], change.group_id
                    )[0]
                except Exception as exc:
                    logger.warning(
                        f'Cannot queue Change Center notification: {exc}',
                        service=change.service,
                    )
                    continue
                key = (normalized['channel'], normalized['recipient_id'])
                if key in queued:
                    continue
                rows.append({
                    'change': change.id,
                    'event': event.id,
                    'destination_type': normalized['channel'],
                    'destination_id': normalized['recipient_id'],
                    'payload': _json_dumps(notification),
                })
                queued.add(key)
        else:
            # Compatibility for changes created before concrete recipients were stored.
            for channel in sorted(channels):
                if channel == 'email':
                    rows.append({
                        'change': change.id,
                        'event': event.id,
                        'destination_type': channel,
                        'destination_id': None,
                        'payload': _json_dumps(notification),
                    })
                    continue
                try:
                    receivers = channel_sql.get_user_receiver_by_group(channel, change.group_id)
                except Exception as exc:
                    logger.warning(
                        f'Cannot queue Change Center {channel} notification: {exc}',
                        service=change.service,
                    )
                    continue
                for receiver in receivers:
                    rows.append({
                        'change': change.id,
                        'event': event.id,
                        'destination_type': channel,
                        'destination_id': receiver.id,
                        'payload': _json_dumps(notification),
                    })
    change_sql.create_deliveries(rows)


def record_event(
    change_id: int,
    event_type: str,
    message: str,
    *,
    status: str | None = None,
    target_id: int | None = None,
    actor_id: int | None = None,
    details=None,
):
    """Append an event and enqueue integrations without failing the workflow."""
    try:
        change = change_sql.get_change(change_id)
        target = change_sql.get_change_target(change_id, target_id) if target_id else None
        event = change_sql.create_event(
            change=change_id,
            target=target_id,
            event_type=event_type,
            status=status or change.status,
            message=str(message)[:255],
            details=_json_dumps(details) if details is not None else None,
            actor_id=actor_id,
            created_at=utc_now(),
        )
        _queue_event_deliveries(event, change, target)
        return event
    except Exception as exc:
        logger.error(
            f'Cannot record Change Center timeline event {event_type}: {exc}',
            exception=exc,
        )
        return None


def list_audit_events(group_id: int, query, *, change_id: int | None = None) -> list[dict]:
    events = change_sql.list_events(
        group_id,
        change_id=change_id,
        service=getattr(query, 'service', None),
        event_type=getattr(query, 'event_type', None),
        status=getattr(query, 'status', None),
        search=getattr(query, 'q', None),
        date_from=normalize_datetime(query.date_from) if getattr(query, 'date_from', None) else None,
        date_to=normalize_datetime(query.date_to) if getattr(query, 'date_to', None) else None,
        after_id=getattr(query, 'after_id', None),
        limit=getattr(query, 'limit', 200),
    )
    return [serialize_event(event) for event in events]


def serialize_webhook(webhook) -> dict:
    return {
        'id': webhook.id,
        'name': webhook.name,
        'url': webhook.url,
        'events': _json_loads(webhook.events, []),
        'enabled': bool(webhook.enabled),
        'verify_tls': bool(webhook.verify_tls),
        'secret_configured': bool(webhook.secret_encrypted),
        'created_at': webhook.created_at.isoformat() if webhook.created_at else None,
        'updated_at': webhook.updated_at.isoformat() if webhook.updated_at else None,
    }


def _webhook_values(body, *, existing=None) -> dict:
    values = body.model_dump(exclude_unset=True)
    secret_supplied = 'secret' in body.model_fields_set
    secret = values.pop('secret', None)
    if 'events' in values:
        values['events'] = _json_dumps(values['events'])
    for field in ('enabled', 'verify_tls'):
        if field in values:
            values[field] = int(values[field])
    if secret_supplied:
        if secret:
            from app.modules.server.ssh import crypt_password
            values['secret_encrypted'] = crypt_password(secret).decode('ascii')
        else:
            values['secret_encrypted'] = None
    elif existing is None:
        values['secret_encrypted'] = None
    return values


def create_webhook(body, user_id: int, group_id: int):
    require_feature(CHANGE_CENTER)
    return change_sql.create_webhook(
        group_id=group_id,
        created_by=user_id,
        **_webhook_values(body),
    )


def update_webhook(webhook_id: int, body, group_id: int):
    require_feature(CHANGE_CENTER)
    webhook = change_sql.get_webhook(webhook_id, group_id)
    return change_sql.update_webhook(
        webhook_id,
        group_id,
        **_webhook_values(body, existing=webhook),
    )


def delete_webhook(webhook_id: int, group_id: int) -> None:
    require_feature(CHANGE_CENTER)
    change_sql.delete_webhook(webhook_id, group_id)


def _validate_webhook_destination(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise RoxywiValidationError('Webhook URL must be an absolute HTTP(S) URL')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except OSError as exc:
        logger.warning(
            f'Cannot resolve Change Center webhook host {parsed.hostname}: {exc}',
            exception=exc,
        )
        raise RoxywiValidationError('Webhook host cannot be resolved') from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise RoxywiPermissionError('Webhook destination resolves to a prohibited address')


def _send_webhook(delivery, payload: dict) -> int:
    webhook = change_sql.get_webhook(delivery.destination_id)
    if not webhook.enabled:
        raise RoxywiConflictError('Webhook is disabled')
    _validate_webhook_destination(webhook.url)
    body = _json_dumps(payload).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Roxy-WI-Change-Center/1.0',
        'X-Roxy-WI-Event': payload.get('type', 'unknown'),
        'X-Roxy-WI-Delivery': str(delivery.id),
    }
    if webhook.secret_encrypted:
        from app.modules.server.ssh import decrypt_password
        secret = decrypt_password(webhook.secret_encrypted).encode('utf-8')
        headers['X-Roxy-WI-Signature'] = 'sha256=' + hmac.new(
            secret, body, hashlib.sha256
        ).hexdigest()
    with requests.post(
        webhook.url,
        data=body,
        headers=headers,
        timeout=5,
        allow_redirects=False,
        verify=bool(webhook.verify_tls),
        stream=True,
    ) as response:
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f'Webhook returned HTTP {response.status_code}')
        return response.status_code


def _send_notification(delivery, payload: dict) -> None:
    destination_type = delivery.destination_type
    channel_id = delivery.destination_id
    message = payload['message']
    level = payload['level']
    if destination_type == 'email':
        if channel_id is None:
            alerting.send_email_to_server_group(
                payload['subject'], message, level, payload['group_id']
            )
        else:
            user = user_sql.get_notification_user_with_group(channel_id, payload['group_id'])
            alerting.send_email(user.email, payload['subject'], f'{level}: {message}')
    elif destination_type == 'telegram':
        channel_sql.get_receiver_with_group('telegram', channel_id, payload['group_id'])
        alerting.telegram_send_mess(message, level, channel_id=channel_id)
    elif destination_type == 'slack':
        channel_sql.get_receiver_with_group('slack', channel_id, payload['group_id'])
        alerting.slack_send_mess(message, level, channel_id=channel_id)
    elif destination_type == 'mm':
        channel_sql.get_receiver_with_group('mm', channel_id, payload['group_id'])
        alerting.mm_send_mess(
            message,
            level,
            payload.get('server_ip'),
            payload['change_id'],
            'change-center',
            channel_id=channel_id,
        )
    elif destination_type == 'pd':
        channel_sql.get_receiver_with_group('pd', channel_id, payload['group_id'])
        alerting.pd_send_mess(
            message,
            level,
            payload.get('server_ip'),
            payload['change_id'],
            'change-center',
            channel_id=channel_id,
        )
    else:
        raise RoxywiValidationError(f'Unsupported delivery type: {destination_type}')


def process_pending_deliveries(*, limit: int = 50) -> dict:
    """Deliver queued integrations with bounded retries."""
    processed = delivered = failed = 0
    now = utc_now()
    deliveries = change_sql.claim_due_deliveries(now, limit=limit)
    for delivery in deliveries:
        processed += 1
        response_code = None
        try:
            payload = _json_loads(delivery.payload, {})
            if delivery.destination_type == 'webhook':
                response_code = _send_webhook(delivery, payload)
            else:
                _send_notification(delivery, payload)
            delivery.status = 'delivered'
            delivery.delivered_at = utc_now()
            delivery.response_code = response_code
            delivery.error = None
            delivered += 1
        except Exception as exc:
            attempts = int(delivery.attempts or 1)
            terminal = attempts >= DELIVERY_ATTEMPTS
            retry_index = min(attempts - 1, len(DELIVERY_RETRY_MINUTES) - 1)
            delivery.status = 'abandoned' if terminal else 'failed'
            delivery.delivered_at = None
            delivery.next_attempt_at = (
                utc_now() + timedelta(minutes=DELIVERY_RETRY_MINUTES[retry_index])
            )
            delivery.response_code = response_code
            delivery.error = str(exc)[:4000]
            logger.warning(
                f'Change Center delivery #{delivery.id} failed: {exc}',
                service=delivery.change.service if delivery.change_id else 'change-center',
            )
            failed += 1
    change_sql.update_deliveries(deliveries)
    return {'processed': processed, 'delivered': delivered, 'failed': failed}


def queue_webhook_test(webhook_id: int, group_id: int, user_id: int):
    webhook = change_sql.get_webhook(webhook_id, group_id)
    payload = {
        'version': '1',
        'id': f'test-{webhook.id}-{int(utc_now().timestamp())}',
        'type': 'webhook.test',
        'occurred_at': utc_iso(utc_now()),
        'change': None,
        'target': None,
        'message': f'Test delivery requested by {_actor_name(user_id) or user_id}',
        'details': {'test': True},
    }
    change_sql.create_deliveries([{
        'change': None,
        'event': None,
        'destination_type': 'webhook',
        'destination_id': webhook.id,
        'payload': _json_dumps(payload),
    }])
    return webhook


def schedule_change(change_id: int, body, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    if int(change.group_id) != int(group_id):
        raise RoxywiPermissionError('Change does not belong to the active group')
    ready_status = 'approved' if change.requires_approval else 'validated'
    if change.status not in (ready_status, 'schedule_missed'):
        raise RoxywiConflictError('Only a deployment-ready change can be scheduled')
    scheduled_at = normalize_datetime(body.scheduled_at)
    window_end = (
        normalize_datetime(body.maintenance_window_end)
        if body.maintenance_window_end else None
    )
    now = utc_now()
    if scheduled_at < now - timedelta(minutes=1):
        raise RoxywiValidationError('Scheduled deployment time must not be in the past')
    if scheduled_at > now + timedelta(days=366):
        raise RoxywiValidationError('Scheduled deployment time must be within one year')
    if window_end and window_end <= max(now, scheduled_at):
        raise RoxywiValidationError('Maintenance window must end after deployment starts')
    change = change_sql.transition_change(
        change.id,
        (change.status,),
        'scheduled',
        scheduled_at=scheduled_at,
        scheduled_by=actor_id,
        maintenance_window_end=window_end,
        schedule_base_status=ready_status,
        finished_at=None,
    )
    record_event(
        change.id,
        'change.scheduled',
        f'Deployment scheduled for {scheduled_at.isoformat()}',
        actor_id=actor_id,
        details={
            'scheduled_at': scheduled_at.isoformat(),
            'maintenance_window_end': window_end.isoformat() if window_end else None,
        },
    )
    return change


def cancel_schedule(change_id: int, group_id: int, actor_id: int | None = None):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    if int(change.group_id) != int(group_id):
        raise RoxywiPermissionError('Change does not belong to the active group')
    if change.status != 'scheduled':
        raise RoxywiConflictError('Only a scheduled change can have its schedule cancelled')
    restore_status = change.schedule_base_status or (
        'approved' if change.requires_approval else 'validated'
    )
    scheduled_at = change.scheduled_at
    change = change_sql.transition_change(
        change.id,
        ('scheduled',),
        restore_status,
        scheduled_at=None,
        scheduled_by=None,
        maintenance_window_end=None,
        schedule_base_status=None,
    )
    record_event(
        change.id,
        'change.schedule_cancelled',
        'Scheduled deployment was cancelled',
        actor_id=actor_id,
        details={'scheduled_at': scheduled_at.isoformat() if scheduled_at else None},
    )
    return change


def run_due_scheduled_changes(*, limit: int = 10) -> dict:
    """Atomically enqueue due deployments; the Scheduler never performs SSH."""
    from app.modules.change import operations

    now = utc_now()
    queued = missed = failed = 0
    for candidate in change_sql.list_due_scheduled(now, limit=limit):
        try:
            with operations.locked_change(candidate.id, candidate.group_id) as change:
                if change.status != 'scheduled' or change.scheduled_at > now:
                    continue
                if change.maintenance_window_end and change.maintenance_window_end < now:
                    change_sql.transition_change(
                        change.id, ('scheduled',), 'schedule_missed', finished_at=now,
                        deployment_output='Maintenance window expired before deployment could start.',
                    )
                    record_event(change.id, 'schedule.missed', 'Maintenance window expired before deployment could start')
                    missed += 1
                else:
                    operations.enqueue(change.id, 'deploy', change.group_id, None, scheduled=True)
                    queued += 1
        except RoxywiConflictError:
            continue  # Another Scheduler or an interactive request claimed it.
        except Exception as exc:
            failed += 1
            logger.error(f'Cannot queue scheduled change #{candidate.id} ({type(exc).__name__})')
    return {'queued': queued, 'missed': missed, 'failed': failed}


def _drift_target(change, target) -> dict:
    descriptor, temporary_name = tempfile.mkstemp(prefix='roxy-wi-drift-', suffix='.cfg')
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        config_mod.get_config(
            target.server_ip,
            str(temporary),
            service=change.service,
            config_file_name=change.remote_path,
        )
        baseline = Path(change.draft_path).read_text(encoding='utf-8', errors='replace')
        current = temporary.read_text(encoding='utf-8', errors='replace')
        if baseline == current:
            return {'status': 'in_sync', 'diff': ''}
        diff = '\n'.join(difflib.unified_diff(
            baseline.splitlines(),
            current.splitlines(),
            fromfile=f'change-{change.id}-baseline',
            tofile=f'{target.server_name}-current',
            lineterm='',
        ))
        return {'status': 'drifted', 'diff': diff[:200000]}
    except Exception as exc:
        return {'status': 'check_failed', 'diff': str(exc)[:4000]}
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        close_database_connection()


def check_change_drift(
    change_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    require_feature(CHANGE_CENTER)
    change = change_sql.get_change(change_id)
    if int(change.group_id) != int(group_id):
        raise RoxywiPermissionError('Change does not belong to the active group')
    if change.status != 'deployed':
        raise RoxywiConflictError('Drift can only be checked for a deployed change')
    targets = [
        target for target in change_sql.list_targets(change.id)
        if not target.excluded and target.status == 'deployed'
    ]
    if not targets:
        raise RoxywiConflictError('No deployed targets are available for drift detection')
    checked_at = utc_now()
    results = {}
    worker_count = min(4, len(targets))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='change-drift') as executor:
        futures = {executor.submit(copy_context().run, _drift_target, change, target): target for target in targets}
        for future in as_completed(futures):
            results[futures[future].id] = future.result()
    aggregate_parts = []
    statuses = []
    for target in targets:
        result = results[target.id]
        statuses.append(result['status'])
        target.drift_status = result['status']
        target.drift_checked_at = checked_at
        target.drift_diff = result['diff'] or None
        if result['diff']:
            aggregate_parts.append(f'{target.server_name} ({target.server_ip})\n{result["diff"]}')
    aggregate_status = (
        'drifted' if 'drifted' in statuses
        else 'check_failed' if 'check_failed' in statuses
        else 'in_sync'
    )
    previous_status = change.drift_status or 'unknown'
    change = change_sql.update_drift_results(
        change.id,
        targets,
        drift_status=aggregate_status,
        drift_checked_at=checked_at,
        drift_diff='\n\n'.join(aggregate_parts) or None,
    )
    if aggregate_status != previous_status:
        if aggregate_status == 'drifted':
            event_type = 'drift.detected'
            message = 'Configuration drift was detected on one or more rollout targets'
        elif aggregate_status == 'in_sync':
            event_type = 'drift.resolved'
            message = 'All deployed rollout targets match the approved configuration'
        else:
            event_type = 'drift.check_failed'
            message = 'Configuration drift check failed on one or more rollout targets'
        record_event(
            change.id,
            event_type,
            message,
            actor_id=actor_id,
            details={'previous_status': previous_status, 'drift_status': aggregate_status},
        )
    return change


def run_continuous_drift_scan(*, limit: int = 100) -> dict:
    from app.modules.change import operations

    queued = failed = 0
    for change in change_sql.list_latest_deployed_changes(limit=limit):
        try:
            operations.enqueue(change.id, 'drift', change.group_id, None)
            queued += 1
        except RoxywiConflictError:
            continue  # Only one pending or running command per change.
        except Exception as exc:
            failed += 1
            logger.warning(f'Cannot queue drift check for change #{change.id} ({type(exc).__name__})')
    return {'queued': queued, 'failed': failed}


def deployment_statistics(
    group_id: int,
    days: int = 30,
    *,
    services: list[str] | None = None,
) -> dict:
    cutoff = utc_now() - timedelta(days=days)
    condition = (
        (ConfigChange.group_id == group_id) &
        (ConfigChange.started_at.is_null(False)) &
        (ConfigChange.started_at >= cutoff)
    )
    if services is not None:
        condition &= ConfigChange.service.in_(services or ('',))
    changes = list(ConfigChange.select().where(condition))
    terminal = [change for change in changes if change.finished_at]
    successful = [change for change in terminal if change.status == 'deployed']
    durations = [
        max(0.0, (change.finished_at - change.started_at).total_seconds())
        for change in terminal
    ]
    drift_condition = (
        (ConfigChange.group_id == group_id) &
        (ConfigChangeTarget.drift_status == 'drifted')
    )
    scheduled_condition = (
        (ConfigChange.group_id == group_id) &
        (ConfigChange.status == 'scheduled')
    )
    if services is not None:
        permitted = services or ('',)
        drift_condition &= ConfigChange.service.in_(permitted)
        scheduled_condition &= ConfigChange.service.in_(permitted)
    drifted_targets = (
        ConfigChangeTarget.select()
        .join(ConfigChange)
        .where(drift_condition)
        .count()
    )
    scheduled = (
        ConfigChange.select()
        .where(scheduled_condition)
        .count()
    )
    return {
        'period_days': days,
        'deployments': len(terminal),
        'successful': len(successful),
        'failed': len(terminal) - len(successful),
        'success_rate': round((len(successful) / len(terminal) * 100), 1) if terminal else 0.0,
        'average_duration_seconds': round(sum(durations) / len(durations), 1) if durations else 0.0,
        'scheduled': scheduled,
        'drifted_targets': drifted_targets,
    }


def build_change_report(change, *, as_csv: bool = False):
    targets = change_sql.list_targets(change.id)
    events = change_sql.list_events(change.group_id, change_id=change.id, limit=500)
    deliveries = change_sql.list_change_deliveries(change.id)
    duration = None
    if change.started_at and change.finished_at:
        duration = max(0.0, (change.finished_at - change.started_at).total_seconds())
    report = {
        'change': {
            'id': change.id,
            'title': change.title,
            'service': change.service,
            'status': change.status,
            'server_id': change.server_id,
            'group_id': change.group_id,
            'created_by': _actor_name(change.user_id),
            'approved_by': _actor_name(change.approved_by),
            'remote_path': change.remote_path,
            'scheduled_at': utc_iso(change.scheduled_at),
            'started_at': utc_iso(change.started_at),
            'finished_at': utc_iso(change.finished_at),
            'duration_seconds': duration,
            'drift_status': change.drift_status,
        },
        'targets': [{
            'id': target.id,
            'server': target.server_name,
            'ip': target.server_ip,
            'role': target.role,
            'batch': target.batch,
            'status': target.status,
            'drift_status': target.drift_status,
            'deployed_at': target.deployed_at.isoformat() if target.deployed_at else None,
            'validation_output': target.validation_output,
            'deployment_output': target.deployment_output,
            'health_output': target.health_output,
            'rollback_output': target.rollback_output,
            'drift_diff': target.drift_diff,
        } for target in targets],
        'timeline': [serialize_event(event) for event in reversed(events)],
        'deliveries': [{
            'id': delivery.id,
            'type': delivery.destination_type,
            'status': delivery.status,
            'attempts': delivery.attempts,
            'response_code': delivery.response_code,
            'error': delivery.error,
            'created_at': delivery.created_at.isoformat() if delivery.created_at else None,
            'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        } for delivery in deliveries],
    }
    if not as_csv:
        return report
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([
        'change_id', 'title', 'service', 'change_status', 'server', 'ip', 'role',
        'batch', 'target_status', 'drift_status', 'deployed_at', 'duration_seconds',
        'validation_output', 'deployment_output', 'health_output', 'rollback_output',
    ])
    for target in report['targets']:
        writer.writerow([
            change.id, change.title, change.service, change.status, target['server'],
            target['ip'], target['role'], target['batch'], target['status'],
            target['drift_status'], target['deployed_at'], duration,
            target['validation_output'], target['deployment_output'], target['health_output'],
            target['rollback_output'],
        ])
    return output.getvalue()
