"""Local TOTP setup and removal; setup secrets never leave this origin."""
import base64
import io
import json
import qrcode
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, set_access_cookies
from app.modules.authentication import security, totp
from app.modules.authentication.routes import body, actor, public_error, finish_login
from app.modules.db.db_model import TotpCredential, RecoveryCode, UserSecurity
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiPublicError

bp = Blueprint('local_totp', __name__)
bp.register_error_handler(RoxywiPublicError, public_error)

def setup_response(user, payload, token):
    stream = io.BytesIO()
    qrcode.make(payload['uri']).save(stream, format='PNG')
    response = jsonify(status='setup', challenge=token, secret=payload['secret'],
                       qr='data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode('ascii'))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/auth/enrollment/start')
def enrollment_start():
    data = body()
    channel = data.get('channel', 'web')
    if channel not in ('web', 'api'):
        raise RoxywiPublicError('Invalid authentication request')
    result = security.consume_challenge(data.get('challenge'), 'login:' + channel,
        binding=security.browser_binding() if channel == 'web' else '',
        verify=lambda user, payload: payload.get('enrollment') and not security.has_factor(user.user_id))
    if not result:
        raise RoxywiPublicError('Enrollment request expired')
    user, login_payload = result
    with security.atomic():
        security.assert_unchanged(user, login_payload['_verified_proof']['auth_epoch'],
                                  login_payload['_verified_proof']['auth_account'])
        payload = dict(totp.setup_payload(user), next=login_payload.get('next'), channel=channel)
        token = security.issue_challenge(user, 'totp:enrollment', payload,
            binding=security.browser_binding() if channel == 'web' else '')
    return setup_response(user, payload, token)


@bp.post('/auth/enrollment/confirm')
def enrollment_confirm():
    data = body()
    channel = data.get('channel', 'web')
    with security.atomic():
        result = security.consume_challenge(data.get('challenge'), 'totp:enrollment',
            binding=security.browser_binding() if channel == 'web' else '',
            verify=lambda user, payload: payload.get('channel') == channel and totp.activate(user, payload, data.get('otp')))
        if result:
            user, payload = result
            codes = security.recovery_codes(user)
            security.revoke_sessions(user, 'authentication.totp.enrolled')
            proof = security.login_proof(user, 'totp')
    if not result:
        raise RoxywiPublicError('Invalid or expired setup code')
    payload['_proof'] = proof
    response = finish_login(user, payload, channel, 'totp')
    data = response.get_json()
    data['recovery_codes'] = codes
    response.set_data(json.dumps(data))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/auth/totp/setup')
@jwt_required(locations=['cookies'])
def totp_setup():
    user, data = actor(), body()
    expected = security.expected_snapshot(user)
    expected_epoch, expected_account = expected['auth_epoch'], expected['auth_account']
    security.require_sensitive_action(user, data, 'totp.setup')
    with security.atomic():
        security.assert_unchanged(user, expected_epoch, expected_account)
        payload = totp.setup_payload(user)
        payload['replace'] = totp.has_factor(user.user_id)
        token = security.issue_challenge(user, 'totp:setup', payload, binding=security.session_binding())
    return setup_response(user, payload, token)


@bp.post('/auth/totp/confirm')
@jwt_required(locations=['cookies'])
def totp_confirm():
    user, data = actor(), body()
    with security.atomic():
        result = security.consume_challenge(data.get('challenge'), 'totp:setup', binding=security.session_binding(),
            verify=lambda actual, payload: actual.user_id == user.user_id and totp.activate(actual, payload, data.get('otp')))
        if result:
            codes = security.recovery_codes(user)
            security.revoke_sessions(user, 'authentication.totp.enrolled')
            proof = security.login_proof(user, 'totp')
    if not result:
        raise RoxywiPublicError('Invalid or expired setup code')
    response = jsonify(status='done', recovery_codes=codes)
    set_access_cookies(response, auth.create_jwt_token(dict(user=user.user_id, group=user.group_id,
                                                          **proof)))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.delete('/auth/totp')
@jwt_required(locations=['cookies'])
def totp_remove():
    user, data = actor(), body()
    expected = security.expected_snapshot(user)
    expected_epoch, expected_account = expected['auth_epoch'], expected['auth_account']
    security.require_sensitive_action(user, data, 'totp.remove')
    with security.atomic():
        security.assert_unchanged(user, expected_epoch, expected_account)
        other_factor = any(p.has_factor(user.user_id) for p in security.providers() if p is not totp)
        if security.policy_applies(user) and not other_factor:
            raise RoxywiPublicError('The active policy requires at least one authentication factor')
        TotpCredential.delete().where(TotpCredential.user_id == user.user_id).execute()
        if not other_factor:
            RecoveryCode.delete().where(RecoveryCode.user_id == user.user_id).execute()
        security.revoke_sessions(user, 'authentication.totp.removed')
    return jsonify(status='done')
