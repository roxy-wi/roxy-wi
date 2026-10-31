from flask import jsonify, request, render_template, g
from flask_jwt_extended import jwt_required, get_jwt, set_access_cookies
from app.routes.passkeys import bp
from app.modules.authentication import passkeys, security
from app.modules.db.db_model import PasskeyCredential, RecoveryCode, User
from app.modules.roxywi import auth, common
from app.middleware import get_user_params
from app.modules.roxywi.exception import RoxywiPublicError


@bp.app_context_processor
def passkey_availability():
    return {'passkeys_available': passkeys.enabled()}


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise passkeys.PasskeyError('A JSON request is required')
    return data


def user():
    if request.headers.get('Authorization'):
        raise passkeys.PasskeyError('Use an interactive browser session')
    return passkeys.local_user(security.session_user(get_jwt()))


def protected_origin():
    passkeys.check_origin()
    # Management must use the interactive cookie identity and its CSRF protection.
    if request.headers.get('Authorization'):
        raise passkeys.PasskeyError('Use an interactive browser session')


@bp.errorhandler(passkeys.PasskeyError)
def safe_error(error):
    return jsonify(error=str(error)), 400


@bp.errorhandler(RoxywiPublicError)
def public_error(error):
    return jsonify(error=error.public_message), 400


@bp.get('')
@jwt_required(locations=['cookies'])
@get_user_params()
def page():
    owner = user()
    credentials = PasskeyCredential.select().where(PasskeyCredential.user_id == owner.user_id)
    return render_template('local_passkeys.html', lang=common.get_user_lang_for_flask(),
                           passkeys=list(credentials), passkeys_enabled=passkeys.enabled())


@bp.post('/register/options')
@jwt_required(locations=['cookies'])
def register_options():
    protected_origin()
    owner = user()
    failed = None
    with security.atomic():
        try:
            expected = security.expected_snapshot(owner)
            expected_epoch = expected['auth_epoch']
            security.assert_unchanged(owner, expected_epoch, expected['auth_account'])
            security.require_sensitive_action(owner, body(), purpose='passkeys.register')
            security.assert_unchanged(owner, expected_epoch, expected['auth_account'])
        except RoxywiPublicError as error:
            failed = error
        if failed is None:
            options = passkeys.begin_registration(owner, security.session_binding())
    if failed:
        raise failed
    return jsonify(options)


@bp.post('/register/finish')
@jwt_required(locations=['cookies'])
def register_finish():
    protected_origin()
    owner = user()
    failed = None
    with security.atomic():
        try:
            passkeys.complete_registration(owner, body(), security.session_binding())
        except passkeys.PasskeyError as error:
            failed = error
        if failed is None:
            codes = security.recovery_codes(owner) if not RecoveryCode.select().where(RecoveryCode.user_id == owner.user_id).exists() else []
            security.revoke_sessions(owner, event='authentication.passkey.enrolled')
            proof = security.login_proof(owner, 'passkey')
    if failed:
        raise failed
    response = jsonify(status='done', recovery_codes=codes)
    claims = {'user': owner.user_id, 'group': str(owner.group_id), **proof}
    set_access_cookies(response, auth.create_jwt_token(claims))
    return response


@bp.post('/<credential_hash>/remove')
@jwt_required(locations=['cookies'])
def remove(credential_hash):
    protected_origin()
    owner = user()
    failed = None
    with security.atomic():
        try:
            security.require_sensitive_action(owner, body(), purpose='passkeys.remove')
        except RoxywiPublicError as error:
            failed = error
        if failed is None:
            credentials = passkeys.list_credentials(owner.user_id, locking=True)
            credential = next((item for item in credentials if item.credential_hash == credential_hash), None)
            remaining = len(credentials)
            other_factor = any(provider.has_factor(owner.user_id) for provider in security.providers()
                               if provider.__name__ != passkeys.__name__)
            if not credential:
                failed = passkeys.PasskeyError('Passkey does not exist')
            elif remaining <= 1 and not other_factor and security.policy_applies(owner):
                failed = passkeys.PasskeyError('Security policy requires at least one authentication factor')
            else:
                credential.delete_instance()
                if remaining <= 1 and not other_factor:
                    RecoveryCode.delete().where(RecoveryCode.user_id == owner.user_id).execute()
                security.revoke_sessions(owner, event='authentication.passkey.removed')
    if failed:
        raise failed
    return jsonify(status='done', sign_in_required=True)


@bp.post('/login/options')
def login_options():
    passkeys.check_origin()
    data = body()
    login = data.get('login', '')
    if not isinstance(login, str) or len(login) > 128:
        raise passkeys.PasskeyError('Passkey authentication is unavailable')
    owner = User.get_or_none(User.username == login)
    if not owner:
        raise passkeys.PasskeyError('Passkey authentication is unavailable')
    try:
        owner, _expected = security.capture_account(owner.user_id)
        if owner.username != login:
            raise passkeys.PasskeyError('Passkey authentication is unavailable')
        return jsonify(passkeys.begin_authentication(owner, passkeys.browser_binding()))
    except passkeys.PasskeyError:
        raise passkeys.PasskeyError('Passkey authentication is unavailable') from None


@bp.post('/login/finish')
def login_finish():
    passkeys.check_origin()
    data = body()
    owner, payload = passkeys.complete_authentication(data, passkeys.browser_binding())
    security.record(owner.user_id, 'authentication.passkey.login')
    params = {'user': owner.user_id, 'group': str(owner.group_id), **security.proof_from_challenge(payload, 'passkey')}
    return auth.do_login(params, data.get('next', ''))


@bp.post('/factor/options')
def factor_options():
    passkeys.check_origin()
    data = body()
    # A factor challenge is offered only after the generic password challenge is
    # proven valid. Consuming this short intermediate token cannot authenticate.
    purpose = data.get('purpose', 'login:web')
    if purpose not in ('login:web', 'login:api'):
        raise passkeys.PasskeyError('Invalid authentication purpose')
    with security.atomic():
        consumed = security.consume_challenge(data.get('login_challenge', ''), purpose,
            verify=lambda owner, payload: not payload.get('enrollment'),
            binding=security.browser_binding() if purpose == 'login:web' else '')
        if consumed:
            owner, payload = consumed
            result = passkeys.begin_authentication(owner, passkeys.browser_binding(), purpose='passkeys.factor')
            # Preserve the password proof and its epoch while holding the same user lock.
            result['login_challenge'] = security.issue_challenge(owner, purpose, payload,
                binding=security.browser_binding() if purpose == 'login:web' else '')
    if not consumed:
        raise passkeys.PasskeyError('Password authentication challenge expired')
    return jsonify(result)


@bp.post('/reauth/options')
@jwt_required(locations=['cookies'])
def reauth_options():
    protected_origin()
    data = body()
    purpose = data.get('purpose', '')
    if not isinstance(purpose, str) or len(purpose) > 60 or not purpose:
        raise passkeys.PasskeyError('A sensitive action purpose is required')
    return jsonify(passkeys.begin_authentication(user(), security.session_binding(),
                    purpose='passkeys.reauth:' + purpose))


@bp.post('/reauth/finish')
@jwt_required(locations=['cookies'])
def reauth_finish():
    protected_origin()
    data = body()
    purpose = data.get('purpose', '')
    if not isinstance(purpose, str) or len(purpose) > 60 or not purpose:
        raise passkeys.PasskeyError('A sensitive action purpose is required')
    failed = None
    with security.atomic():
        try:
            owner, _ = passkeys.complete_authentication(data, security.session_binding(),
                purpose='passkeys.reauth:' + purpose, expected_user=user())
        except passkeys.PasskeyError as error:
            failed = error
        if failed is None:
            token = security.issue_challenge(owner, 'reauth:' + purpose,
                        binding=security.session_binding(), ttl=120)
    if failed:
        raise failed
    return jsonify(reauth_token=token)


@bp.post('/enrollment/options')
def enrollment_options():
    passkeys.check_origin()
    data = body()
    with security.atomic():
        consumed = security.consume_challenge(data.get('challenge', ''), 'login:web',
            binding=security.browser_binding(),
            verify=lambda owner, payload: bool(payload.get('enrollment')) and not security.has_factor(owner.user_id))
        if consumed:
            owner, payload = consumed
            result = passkeys.begin_registration(owner, security.browser_binding(),
                purpose='passkeys.enrollment', context={'enrollment': True, 'next': payload.get('next', '')})
    if not consumed:
        raise passkeys.PasskeyError('Enrollment request expired')
    return jsonify(result)


@bp.post('/enrollment/finish')
def enrollment_finish():
    passkeys.check_origin()
    failed = None
    with security.atomic():
        try:
            owner, payload = passkeys.complete_registration(None, body(), security.browser_binding(),
                                                            purpose='passkeys.enrollment')
        except passkeys.PasskeyError as error:
            failed = error
        if failed is None:
            codes = security.recovery_codes(owner)
            security.revoke_sessions(owner, event='authentication.passkey.enrolled')
            proof = security.login_proof(owner, 'passkey')
    if failed:
        raise failed
    response = auth.do_login({'user': owner.user_id, 'group': str(owner.group_id),
        **proof}, payload.get('context', {}).get('next', ''))
    result = response.get_json()
    result['recovery_codes'] = codes
    response.set_data(__import__('json').dumps(result))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response
