"""Request intent and HTTP result, separate from domain/worker completion."""
from uuid import uuid4

from flask import g, jsonify, request
from flask_jwt_extended import get_jwt

from app.modules.audit import events
from app.modules.db.db_model import User
from app.modules.roxywi import logger


def _login_request():
    return request.endpoint in {'login_page', 'api.do_login'} and request.method == 'POST'


def _actor():
    try:
        # The earlier global authentication guard already verified this request.
        # Reuse its request-local principal rather than swallowing a second
        # verification/storage failure as if this were an anonymous operation.
        claims = get_jwt()
    except RuntimeError:
        return None, None
    if not claims:
        return None, None
    return int(claims['user_id']), int(claims['group'])


def install(app):
    @app.before_request
    def audit_request_intent():
        if request.method in {'GET', 'HEAD', 'OPTIONS'} or _login_request():
            return None
        if (request.endpoint or '').startswith('admin.audit_'):
            return None  # Domain audit uses the reserved recovery allowance.
        try:
            if not events.enabled():
                return None
            user_id, group_id = _actor()
            if user_id is None:
                return None
            request_id = str(uuid4())
            details = {'request_id': request_id, 'method': request.method,
                       'route': request.url_rule.rule if request.url_rule else '-',
                       'token_id': getattr(g, 'personal_token_id', None)}
            events.record('request.started', 'requested', user_id=user_id, group_id=group_id,
                          source_ip=request.remote_addr, details=details)
            g.audit_context = (user_id, group_id, details)
        except Exception:
            logger.error('Audit storage unavailable before request execution')
            return jsonify(error='Audit storage unavailable; operation was not started'), 503

    @app.after_request
    def audit_request_result(response):
        if _login_request():
            try:
                if not events.enabled():
                    return response
                data = request.get_json(silent=True)
                data = data if isinstance(data, dict) else {}
                result = response.get_json(silent=True) or {}
                succeeded = response.status_code == 200 and (result.get('status') == 'done' or 'access_token' in result)
                pending = result.get('status') in {'mfa_required', 'enrollment_required'} or result.get('mfa_required') is True
                user = User.get_or_none(User.username == str(data.get('login', ''))[:256]) if succeeded else None
                events.record('auth.login', 'succeeded' if succeeded else 'pending' if pending else 'failed',
                              user_id=user.user_id if user else None, group_id=int(user.group_id) if user else None,
                              source_ip=request.remote_addr,
                              details={'method': request.method, 'route': request.url_rule.rule,
                                       'http_status': response.status_code}, force=succeeded or pending)
            except Exception:
                logger.error('Audit login result could not be recorded')
                failed = jsonify(error='Audit result could not be recorded; sign in again')
                failed.status_code = 503
                return failed
        context = getattr(g, 'audit_context', None)
        if context:
            user_id, group_id, details = context
            try:
                events.record('request.finished', 'accepted' if response.status_code < 400 else 'denied',
                              user_id=user_id, group_id=group_id, source_ip=request.remote_addr,
                              details={**details, 'http_status': response.status_code}, force=True)
            except Exception:
                logger.error('Audit request result could not be recorded', request_id=details['request_id'])
                failed = jsonify(error='Audit result recording failed; the operation may have completed',
                                 request_id=details['request_id'])
                failed.status_code = 503
                return failed
        return response
