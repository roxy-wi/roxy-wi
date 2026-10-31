from functools import wraps

from flask import abort, g, jsonify, render_template, request
from flask_jwt_extended import jwt_required

from app.middleware import get_user_params
from app.modules.audit import destinations, events
from app.modules.integrations.connection_transport import check_connection
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiPublicError, RoxywiResourceNotFound, RoxywiPermissionError, RoxywiConflictError, RoxywiValidationError
from app.routes.admin import bp


class AuditCheckResultUnavailable(RuntimeError):
    pass


def interactive_session(fn):
    @wraps(fn)
    @jwt_required(locations=['cookies'])
    def wrapped(*args, **kwargs):
        if request.headers.get('Authorization'):
            abort(403, 'Use the interactive cookie session without an Authorization header')
        return fn(*args, **kwargs)
    return wrapped


def response(call, status=200):
    try:
        result = jsonify(call())
        result.status_code = status
    except AuditCheckResultUnavailable:
        result = jsonify(error='Audit result recording failed; the connection check may have executed')
        result.status_code = 503
    except events.AuditStorageUnavailable:
        result = jsonify(error='Audit storage unavailable; receiver settings were not changed')
        result.status_code = 503
    except RoxywiPublicError as error:
        result = jsonify(error=error.public_message)
        result.status_code = (404 if isinstance(error, RoxywiResourceNotFound) else
                              403 if isinstance(error, RoxywiPermissionError) else
                              409 if isinstance(error, RoxywiConflictError) else 400)
    result.headers['Cache-Control'] = 'no-store'
    return result


def context():
    return dict(group_id=g.user_params['group_id'], role=g.user_params['role'], actor_id=g.user_params['user_id'])


@bp.get('/audit')
@interactive_session
@get_user_params()
def audit_page():
    auth.page_for_admin(level=2)
    return render_template('external_audit.html', lang=g.user_params['lang'])


@bp.get('/audit-receivers')
@interactive_session
@get_user_params()
def audit_list():
    auth.page_for_admin(level=2)
    return response(lambda: dict(receivers=destinations.list_destinations(
        g.user_params['group_id'], g.user_params['role']), profiles_available=destinations.shared_profiles() is not None))


@bp.post('/audit-receivers')
@interactive_session
@get_user_params()
def audit_create():
    auth.page_for_admin(level=2)
    return response(lambda: destinations.save(request.get_json(), **context()), 201)


@bp.put('/audit-receivers/<int:receiver_id>')
@interactive_session
@get_user_params()
def audit_update(receiver_id):
    auth.page_for_admin(level=2)
    return response(lambda: destinations.save(request.get_json(), destination_id=receiver_id, **context()))


@bp.delete('/audit-receivers/<int:receiver_id>')
@interactive_session
@get_user_params()
def audit_delete(receiver_id):
    auth.page_for_admin(level=2)
    def run():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {'revision'}:
            raise RoxywiValidationError('A receiver revision is required')
        return destinations.delete(receiver_id, expected_revision=body['revision'], **context())
    return response(run)


@bp.get('/audit-status')
@interactive_session
@get_user_params()
def audit_status():
    auth.page_for_admin(level=2)
    return response(lambda: destinations.status(g.user_params['group_id'], g.user_params['role']))


@bp.post('/audit-receivers/<int:receiver_id>/test')
@interactive_session
@get_user_params()
def audit_test(receiver_id):
    auth.page_for_admin(level=2)
    def run():
        row = destinations.get(receiver_id, g.user_params['group_id'], g.user_params['role'])
        connection = destinations.resolve_revision(destinations.revision(row))
        details = dict(subject_id=row.id, revision=row.revision)
        events.record('audit.receiver.check_requested', 'requested',
                      user_id=g.user_params['user_id'], group_id=row.group_id, details=details, force=True)
        try:
            result = check_connection(connection)
        except Exception:
            result = dict(status='failed', detail='Connection check failed; verify destination, TLS and credentials')
        outcome = ('accepted' if result['status'] in {'connected', 'accepted'} else
                   'unknown' if result['status'] == 'unverified' else 'failed')
        try:
            events.record('audit.receiver.checked', outcome,
                          user_id=g.user_params['user_id'], group_id=row.group_id, details=details, force=True)
        except events.AuditStorageUnavailable:
            raise AuditCheckResultUnavailable from None
        return result
    return response(run)


@bp.post('/audit-receivers/<int:receiver_id>/retry')
@interactive_session
@get_user_params()
def audit_retry(receiver_id):
    auth.page_for_admin(level=2)
    def run():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or set(body)-{'revision', 'include_pending'}:
            raise RoxywiValidationError('Invalid audit requeue settings')
        return dict(retried=destinations.retry_failed(receiver_id,
            expected_revision=body.get('revision'), include_pending=body.get('include_pending', False), **context()))
    return response(run)
