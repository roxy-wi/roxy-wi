"""Local factor routes: cookie management requires Flask-JWT CSRF validation."""
from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt

from app.modules.authentication import security
from app.modules.db.db_model import User, RecoveryCode, UserSecurity, AuthenticationPolicy, AuthenticationChallenge
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiPublicError

bp = Blueprint('local_auth', __name__)


@bp.app_context_processor
def local_provider_availability():
    import importlib.util
    return {name + '_installed': importlib.util.find_spec('app.modules.authentication.' + provider) is not None
            for name, provider in (('local_totp', 'totp'), ('local_passkeys', 'passkeys'))}


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise RoxywiPublicError('A JSON object is required')
    return data


def actor():
    if 'Authorization' in request.headers:
        raise RoxywiPublicError('Use the browser session without an Authorization header')
    claims = get_jwt()
    if claims.get('credential_type') == 'pat':
        raise RoxywiPublicError('Interactive authentication is required')
    return security.session_user(claims)


@bp.errorhandler(RoxywiPublicError)
def public_error(error):
    return jsonify(status='failed', error=error.public_message), 400



def finish_login(user, payload, channel, method):
    params = dict(user=user.user_id, group=str(user.group_id), name=user.username,
                  **(payload['_proof'] if '_proof' in payload else security.proof_from_challenge(payload, method)))
    security.record(user.user_id, 'authentication.verified')
    if channel == 'api':
        return jsonify(access_token=auth.create_jwt_token(params))
    return auth.do_login(params, payload.get('next'))


@bp.post('/auth/login/complete')
def login_complete():
    data = body()
    channel = data.get('channel', 'web')
    if channel not in ('web', 'api'):
        raise RoxywiPublicError('Invalid authentication request')
    raw_token = data.get('challenge')
    challenge_before = AuthenticationChallenge.get_or_none(AuthenticationChallenge.token_hash == security.digest(raw_token)) if isinstance(raw_token, str) and len(raw_token) <= 256 else None
    attempts_before = challenge_before.attempts if challenge_before else -1
    verified_method = []
    def verify(user, payload):
        if payload.get('enrollment'):
            return False
        method = security.verify_factor_kind(user, data)
        if method:
            verified_method.append(method)
        return bool(method)
    with security.atomic():
        result = security.consume_challenge(data.get('challenge'), 'login:' + channel,
            binding=security.browser_binding() if channel == 'web' else '', verify=verify)
        if result:
            user, payload = result
            if verified_method[0] == 'recovery':
                security.revoke_sessions(user, 'authentication.recovery.used')
            payload['_proof'] = security.login_proof(user, verified_method[0])
    if not result:
        token = data.get('challenge')
        challenge = AuthenticationChallenge.get_or_none(AuthenticationChallenge.token_hash == security.digest(token)) if isinstance(token, str) and len(token) <= 256 else None
        if challenge and challenge.attempts > attempts_before and not challenge.used:
            security.record(challenge.user_id, 'authentication.factor', 'denied',
                            reason_code='invalid_factor', actor_verified=False)
        return jsonify(status='failed', error='Invalid, expired or already used authentication code'), 401
    return finish_login(*result, channel, verified_method[0])


@bp.get('/security')
@jwt_required(locations=['cookies'])
def security_page():
    from app.modules.roxywi.common import get_users_params, get_user_lang_for_flask
    from flask import g
    actor()
    g.user_params = get_users_params()
    return render_template('security.html', lang=get_user_lang_for_flask())


@bp.get('/auth/security')
@jwt_required(locations=['cookies'])
def security_status():
    user = actor()
    rule = security.policy()
    return jsonify(totp=any(p.__name__.endswith('.totp') and p.has_factor(user.user_id) for p in security.providers()),
        factors=[p.__name__.split('.')[-1] for p in security.providers() if p.has_factor(user.user_id)], policy=rule.mode,
        grace_until=rule.grace_until, admin=security.can_manage_policy(user),
        enrollment_required=security.enrollment_required(user),
        recovery_remaining=RecoveryCode.select().where((RecoveryCode.user_id == user.user_id) &
                                                       RecoveryCode.used_at.is_null()).count())


@bp.post('/auth/recovery-codes')
@jwt_required(locations=['cookies'])
def recovery_regenerate():
    user, data = actor(), body()
    expected = security.expected_snapshot(user)
    expected_epoch, expected_account = expected['auth_epoch'], expected['auth_account']
    security.require_sensitive_action(user, data, 'recovery.regenerate')
    if not security.has_factor(user.user_id):
        raise RoxywiPublicError('Configure an authentication factor first')
    with security.atomic():
        security.assert_unchanged(user, expected_epoch, expected_account)
        codes = security.recovery_codes(user)
        security.record(user.user_id, 'authentication.recovery.regenerated')
    response = jsonify(recovery_codes=codes)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/auth/reauthenticate')
@jwt_required(locations=['cookies'])
def reauthenticate():
    user, data = actor(), body()
    purpose = data.get('purpose')
    if purpose not in ('personal_token.create', 'totp.setup', 'totp.remove', 'recovery.regenerate',
                       'policy.update', 'passkey.register', 'passkey.remove', 'passkeys.register', 'passkeys.remove'):
        raise RoxywiPublicError('Unknown authentication purpose')
    failure = None
    with security.atomic():
        try:
            security.require_sensitive_action(user, data, 'reauthenticate:' + purpose)
        except RoxywiPublicError as error:
            failure = error
        if failure is None:
            token = security.issue_challenge(user, 'reauth:' + purpose, binding=security.session_binding(), ttl=120)
    if failure:
        raise failure
    return jsonify(reauth_token=token)


@bp.post('/auth/policy')
@jwt_required(locations=['cookies'])
def policy_update():
    user, data = actor(), body()
    if not security.can_manage_policy(user):
        return jsonify(error='Forbidden'), 403
    expected = security.expected_snapshot(user)
    expected_epoch, expected_account = expected['auth_epoch'], expected['auth_account']
    security.require_sensitive_action(user, data, 'policy.update')
    mode = data.get('mode')
    if mode not in ('off', 'admin', 'all'):
        raise RoxywiPublicError('Invalid policy')
    if mode != 'off' and not security.has_factor(user.user_id):
        raise RoxywiPublicError('Configure your own authentication factor before requiring MFA')
    try:
        days = int(data.get('grace_days', 7))
    except (TypeError, ValueError):
        raise RoxywiPublicError('Enrollment grace must be 1 to 30 days') from None
    if not 1 <= days <= 30:
        raise RoxywiPublicError('Enrollment grace must be 1 to 30 days')
    with security.atomic():
        rule = security.lock_policy()
        security.assert_unchanged(user, expected_epoch, expected_account)
        if not security.can_manage_policy(user):
            raise RoxywiPublicError('Current administrator permission is required')
        AuthenticationPolicy.update(mode=mode, grace_until=security.now() + days * 86400).where(
            AuthenticationPolicy.id == rule.id).execute()
        # Existing sessions and PATs cannot silently retain the previous policy.
        for account in User.select().order_by(User.user_id):
            security.state(account)
        UserSecurity.update(epoch=UserSecurity.epoch + 1).execute()
        security.record(user.user_id, 'authentication.policy.changed')
    return jsonify(status='done', reauthentication_required=True)
