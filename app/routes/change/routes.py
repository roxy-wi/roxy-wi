from functools import wraps

from flask import Response, abort, g, jsonify, render_template, request
from flask_jwt_extended import jwt_required
from flask_pydantic import validate
from werkzeug.exceptions import HTTPException

import app.modules.change.service as change_service
import app.modules.change.automation as change_automation
import app.modules.change.operations as change_operations
import app.modules.db.change as change_sql
import app.modules.roxywi.common as roxywi_common
import app.modules.roxywi.auth as roxywi_auth
from app.middleware import get_user_params, page_for_admin
from app.modules.change.access import change_center_subscription_required
from app.modules.change.schemas import (
    ConfigChangeCreate,
    ConfigChangeAuditQuery,
    ConfigChangeReportQuery,
    ConfigChangeSchedule,
    ConfigChangeStatisticsQuery,
    ConfigChangeTargetUpdate,
    ConfigChangeUpdate,
    ConfigChangeWebhookCreate,
    ConfigChangeWebhookUpdate,
)
from app.modules.roxywi.exception import (
    RoxywiConflictError,
    RoxywiPermissionError,
    RoxywiResourceNotFound,
    RoxywiValidationError,
)
from app.routes.change import bp


@bp.before_request
@jwt_required()
@get_user_params()
@page_for_admin(level=3)
def before_request():
    """Authenticate Change Center pages and endpoints."""
    pass


def _error_response(exc: Exception):
    if isinstance(exc, RoxywiResourceNotFound):
        status_code = 404
    elif isinstance(exc, RoxywiPermissionError):
        status_code = 403
    elif isinstance(exc, RoxywiConflictError):
        status_code = 409
    elif isinstance(exc, RoxywiValidationError):
        status_code = 400
    elif isinstance(exc, ValueError):
        roxywi_common.logging('Roxy-WI server', f'error: Invalid Change Center request: {exc}')
        return jsonify({'status': 'failed', 'error': 'Invalid request'}), 400
    else:
        roxywi_common.logging('Roxy-WI server', f'error: Change Center operation failed: {exc}')
        return jsonify({'status': 'failed', 'error': 'Internal server error'}), 500
    return jsonify({'status': 'failed', 'error': exc.public_message}), status_code


def _get_active_group_change(change_id: int):
    change = change_sql.get_change(change_id)
    if int(change.group_id) != int(g.user_params['group_id']):
        raise RoxywiPermissionError('Change does not belong to the active group')
    if not roxywi_auth.is_access_permit_to_service(change.service):
        raise RoxywiPermissionError(f'No access to {change.service.title()} changes')
    return change


def _idle_change_required(handler):
    @wraps(handler)
    def wrapped(change_id, *args, **kwargs):
        try:
            _get_active_group_change(change_id)
            with change_operations.locked_change(change_id, g.user_params['group_id']):
                return handler(change_id, *args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            return _error_response(exc)
    return wrapped


def _queue_action(change_id, action, *, target_id=None):
    try:
        _get_active_group_change(change_id)
        change = change_operations.enqueue(
            change_id, action, g.user_params['group_id'], g.user_params['user_id'],
            target_id=target_id,
        )
        return jsonify({
            'status': 'accepted', 'data': change_service.serialize_change(change),
            'tasks_ids': [change.active_task_id],
        }), 202
    except Exception as exc:
        return _error_response(exc)


@bp.get('')
def index():
    return render_template('change_center.html', lang=g.user_params['lang'])


@bp.get('/api')
@change_center_subscription_required
def list_changes():
    service = request.args.get('service') or None
    status = request.args.get('status') or None
    if service and service not in ('haproxy', 'nginx', 'apache', 'keepalived'):
        return _error_response(RoxywiValidationError('Unsupported service filter'))
    try:
        changes = change_sql.list_changes(g.user_params['group_id'], service=service, status=status)
        changes = [item for item in changes if roxywi_auth.is_access_permit_to_service(item.service)]
        return jsonify({'status': 'success', 'data': [change_service.serialize_change(item) for item in changes]})
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/rollout-preview')
@change_center_subscription_required
def rollout_preview():
    try:
        server_id = request.args.get('server_id', '').strip()
        service = request.args.get('service', '').strip()
        if not server_id:
            raise RoxywiValidationError('server_id is required')
        if service not in ('haproxy', 'nginx', 'apache', 'keepalived'):
            raise RoxywiValidationError('Unsupported service')
        if not roxywi_auth.is_access_permit_to_service(service):
            raise RoxywiPermissionError(f'No access to {service.title()} changes')
        data = change_service.rollout_preview(
            server_id,
            service,
            g.user_params['group_id'],
        )
        return jsonify({'status': 'success', 'data': data})
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/notification-destinations')
@change_center_subscription_required
def notification_destinations():
    try:
        return jsonify({
            'status': 'success',
            'data': change_automation.list_notification_destinations(
                g.user_params['group_id']
            ),
        })
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api')
@change_center_subscription_required
@validate(body=ConfigChangeCreate)
def create_change(body: ConfigChangeCreate):
    try:
        if not roxywi_auth.is_access_permit_to_service(body.service):
            raise RoxywiPermissionError(f'No access to {body.service.title()} changes')
        change = change_service.create_change(body, g.user_params['user_id'], g.user_params['group_id'])
        roxywi_common.logging(
            change.server_id,
            f'Configuration change #{change.id} has been created',
            service=change.service,
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)}), 201
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/<int:change_id>')
@change_center_subscription_required
def get_change(change_id: int):
    try:
        return jsonify({'status': 'success', 'data': change_service.serialize_change(
            _get_active_group_change(change_id)
        )})
    except Exception as exc:
        return _error_response(exc)


@bp.put('/api/<int:change_id>')
@change_center_subscription_required
@validate(body=ConfigChangeUpdate)
@_idle_change_required
def update_change(change_id: int, body: ConfigChangeUpdate):
    try:
        _get_active_group_change(change_id)
        change = change_service.update_change(
            change_id, body, g.user_params['group_id'], g.user_params['user_id']
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/validate')
@change_center_subscription_required
def validate_change(change_id: int):
    return _queue_action(change_id, 'validate')


@bp.post('/api/<int:change_id>/approve')
@change_center_subscription_required
def approve_change(change_id: int):
    if int(g.user_params['role']) > 2:
        abort(403, 'Only administrators can approve changes')
    try:
        _get_active_group_change(change_id)
        with change_operations.locked_change(change_id, g.user_params['group_id']):
            change = change_service.approve_change(
                change_id, g.user_params['user_id'], g.user_params['group_id']
            )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/deploy')
@change_center_subscription_required
def deploy_change(change_id: int):
    return _queue_action(change_id, 'deploy')


def _run_rollout_action(change_id: int, action: str):
    try:
        _get_active_group_change(change_id)
        with change_operations.locked_change(change_id, g.user_params['group_id'], idle=False) as current:
            if action == 'pause':
                change = change_service.pause_change(
                    change_id, g.user_params['group_id'], g.user_params['user_id']
                )
            elif action == 'resume' and current.status == 'pause_requested':
                # Cancel a pending pause without starting a second rollout.
                # Holding the row lock prevents falling through to remote work
                # if the worker has just reached the batch boundary.
                change = change_sql.transition_change(
                    change_id, ('pause_requested',), 'deploying', pause_requested=0,
                )
                change_automation.record_event(
                    change.id, 'deployment.pause_cancelled', 'Pending pause was cancelled',
                    actor_id=g.user_params['user_id'],
                )
            else:
                return _queue_action(change_id, action)
        roxywi_common.logging(
            change.server_id,
            f'Configuration change #{change.id}: {action}',
            service=change.service,
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/pause')
@change_center_subscription_required
def pause_change(change_id: int):
    return _run_rollout_action(change_id, 'pause')


@bp.post('/api/<int:change_id>/resume')
@change_center_subscription_required
def resume_change(change_id: int):
    return _run_rollout_action(change_id, 'resume')


@bp.post('/api/<int:change_id>/promote')
@change_center_subscription_required
def promote_change(change_id: int):
    return _run_rollout_action(change_id, 'promote')


@bp.post('/api/<int:change_id>/targets/<int:target_id>/<action>')
@change_center_subscription_required
def target_action(change_id: int, target_id: int, action: str):
    handlers = {
        'retry': change_service.retry_target,
        'rollback': change_service.rollback_target,
        'exclude': change_service.exclude_target,
        'include': change_service.include_target,
    }
    try:
        _get_active_group_change(change_id)
        if action not in handlers:
            raise RoxywiResourceNotFound
        if action == 'exclude':
            body = ConfigChangeTargetUpdate.model_validate(request.get_json(silent=True) or {})
            with change_operations.locked_change(change_id, g.user_params['group_id']):
                change = handlers[action](
                    change_id, target_id, g.user_params['group_id'],
                    body.reason, g.user_params['user_id'],
                )
        else:
            return _queue_action(change_id, action, target_id=target_id)
        roxywi_common.logging(
            change.server_id,
            f'Configuration change #{change.id}, target #{target_id}: {action}',
            service=change.service,
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/rollback')
@change_center_subscription_required
def rollback_change(change_id: int):
    return _queue_action(change_id, 'rollback')


@bp.post('/api/<int:change_id>/cancel')
@change_center_subscription_required
@_idle_change_required
def cancel_change(change_id: int):
    try:
        _get_active_group_change(change_id)
        change = change_service.cancel_change(
            change_id, g.user_params['group_id'], g.user_params['user_id']
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/recover')
@change_center_subscription_required
@_idle_change_required
def recover_change(change_id: int):
    try:
        _get_active_group_change(change_id)
        change = change_service.recover_change(
            change_id, g.user_params['group_id'], g.user_params['user_id']
        )
        roxywi_common.logging(
            change.server_id,
            f'Configuration change #{change.id} stale operation has been recovered',
            service=change.service,
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/schedule')
@change_center_subscription_required
@validate(body=ConfigChangeSchedule)
@_idle_change_required
def schedule_change(change_id: int, body: ConfigChangeSchedule):
    try:
        _get_active_group_change(change_id)
        change = change_automation.schedule_change(
            change_id, body, g.user_params['group_id'], g.user_params['user_id']
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/schedule/cancel')
@change_center_subscription_required
@_idle_change_required
def cancel_change_schedule(change_id: int):
    try:
        _get_active_group_change(change_id)
        change = change_automation.cancel_schedule(
            change_id, g.user_params['group_id'], g.user_params['user_id']
        )
        return jsonify({'status': 'success', 'data': change_service.serialize_change(change)})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/<int:change_id>/drift')
@change_center_subscription_required
def check_change_drift(change_id: int):
    return _queue_action(change_id, 'drift')


@bp.get('/api/<int:change_id>/events')
@change_center_subscription_required
@validate(query=ConfigChangeAuditQuery)
def change_events(change_id: int, query: ConfigChangeAuditQuery):
    try:
        _get_active_group_change(change_id)
        events = change_automation.list_audit_events(
            g.user_params['group_id'], query, change_id=change_id
        )
        return jsonify({'status': 'success', 'data': events})
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/audit')
@change_center_subscription_required
@validate(query=ConfigChangeAuditQuery)
def audit_history(query: ConfigChangeAuditQuery):
    try:
        if query.service and not roxywi_auth.is_access_permit_to_service(query.service):
            raise RoxywiPermissionError(f'No access to {query.service.title()} changes')
        events = change_automation.list_audit_events(g.user_params['group_id'], query)
        events = [
            event for event in events
            if roxywi_auth.is_access_permit_to_service(event['service'])
        ]
        return jsonify({'status': 'success', 'data': events})
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/statistics')
@change_center_subscription_required
@validate(query=ConfigChangeStatisticsQuery)
def deployment_statistics(query: ConfigChangeStatisticsQuery):
    try:
        services = [
            service for service in ('haproxy', 'nginx', 'apache', 'keepalived')
            if roxywi_auth.is_access_permit_to_service(service)
        ]
        data = change_automation.deployment_statistics(
            g.user_params['group_id'], query.days, services=services
        )
        return jsonify({'status': 'success', 'data': data})
    except Exception as exc:
        return _error_response(exc)


@bp.get('/api/<int:change_id>/report')
@change_center_subscription_required
@validate(query=ConfigChangeReportQuery)
def change_report(change_id: int, query: ConfigChangeReportQuery):
    try:
        change = _get_active_group_change(change_id)
        if query.format == 'csv':
            report = change_automation.build_change_report(change, as_csv=True)
            return Response(
                report,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename="change-{change.id}-report.csv"'
                },
            )
        return jsonify({
            'status': 'success',
            'data': change_automation.build_change_report(change),
        })
    except Exception as exc:
        return _error_response(exc)


def _webhook_admin_required():
    if int(g.user_params['role']) > 2:
        raise RoxywiPermissionError('Only administrators can manage Change Center webhooks')


@bp.get('/api/webhooks')
@change_center_subscription_required
def list_webhooks():
    try:
        _webhook_admin_required()
        data = [
            change_automation.serialize_webhook(webhook)
            for webhook in change_sql.list_webhooks(g.user_params['group_id'])
        ]
        return jsonify({'status': 'success', 'data': data})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/webhooks')
@change_center_subscription_required
@validate(body=ConfigChangeWebhookCreate)
def create_webhook(body: ConfigChangeWebhookCreate):
    try:
        _webhook_admin_required()
        webhook = change_automation.create_webhook(
            body, g.user_params['user_id'], g.user_params['group_id']
        )
        return jsonify({
            'status': 'success',
            'data': change_automation.serialize_webhook(webhook),
        }), 201
    except Exception as exc:
        return _error_response(exc)


@bp.put('/api/webhooks/<int:webhook_id>')
@change_center_subscription_required
@validate(body=ConfigChangeWebhookUpdate)
def update_webhook(webhook_id: int, body: ConfigChangeWebhookUpdate):
    try:
        _webhook_admin_required()
        webhook = change_automation.update_webhook(
            webhook_id, body, g.user_params['group_id']
        )
        return jsonify({
            'status': 'success',
            'data': change_automation.serialize_webhook(webhook),
        })
    except Exception as exc:
        return _error_response(exc)


@bp.delete('/api/webhooks/<int:webhook_id>')
@change_center_subscription_required
def delete_webhook(webhook_id: int):
    try:
        _webhook_admin_required()
        change_automation.delete_webhook(webhook_id, g.user_params['group_id'])
        return jsonify({'status': 'success'})
    except Exception as exc:
        return _error_response(exc)


@bp.post('/api/webhooks/<int:webhook_id>/test')
@change_center_subscription_required
def test_webhook(webhook_id: int):
    try:
        _webhook_admin_required()
        webhook = change_automation.queue_webhook_test(
            webhook_id, g.user_params['group_id'], g.user_params['user_id']
        )
        return jsonify({
            'status': 'success',
            'data': change_automation.serialize_webhook(webhook),
        })
    except Exception as exc:
        return _error_response(exc)
