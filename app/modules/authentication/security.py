"""Persistent, purpose-bound local authentication. Providers are optional modules."""
import hashlib
import importlib
import importlib.util
import json
import re
import secrets
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.hmac import HMAC

from flask import has_request_context, session, request, g
from flask_jwt_extended import get_jwt
from peewee import SqliteDatabase
from app.modules.db.db_model import (User, UserGroups, UserSecurity, AuthenticationChallenge, RecoveryCode,
                                     AuthenticationPolicy, AuthenticationEvent)
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi.exception import RoxywiPublicError, RoxywiPermissionError
from app.modules.server.ssh import crypt_password, decrypt_password

PROOF_FIELDS = ('auth_epoch', 'auth_account', 'auth_method', 'auth_time', 'credential_version')
COMPLETE_METHODS = ('totp', 'recovery', 'passkey')
MAX_LOCAL_EVENTS = 10000


def now():
    return int(time.time())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_version(user):
    # Public JWT claims must not expose a fast verifier for legacy passwords.
    # Flask's stable application key is independent of encrypted-secret rotation.
    from app import app
    key = app.config['SECRET_KEY']
    key = key.encode('utf-8') if isinstance(key, str) else bytes(key)
    material = b'roxywi.local-auth.password-version.v1\x00' + (user.password or '').encode('utf-8')
    # Secret-keyed change marker over a stored hash, never a password verifier.
    mac = HMAC(key, hashes.SHA256())
    mac.update(material)
    return mac.finalize().hex()


def atomic():
    database = UserSecurity._meta.database
    return database.atomic('IMMEDIATE') if isinstance(database, SqliteDatabase) else database.atomic()


def current_user(user_id):
    query = User.select().where(User.user_id == user_id)
    database = User._meta.database
    if database.in_transaction() and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return query.first()


def _state_locked(user):
    query = UserSecurity.select().where(UserSecurity.user_id == user.user_id)
    if not isinstance(UserSecurity._meta.database, SqliteDatabase):
        query = query.for_update()
    row = query.first()
    if row is None:
        row, _ = UserSecurity.get_or_create(user_id=user.user_id,
                                          defaults={'password_version': password_version(user)})
    return row


def _snapshot(user, row):
    return dict(_user_id=user.user_id, auth_epoch=row.epoch, auth_account=row.account_id,
                credential_version=password_version(user))


def _locked_account(user_id, allow_disabled=False):
    user = current_user(user_id)
    if user is None or not allow_disabled and not user.enabled:
        raise RoxywiPublicError('Account is unavailable; authenticate again')
    row = _state_locked(user)
    return user, row


def capture_account(user_id, allow_disabled=False):
    """Capture an account before verifying a password, factor or provider binding."""
    with atomic():
        user, row = _locked_account(user_id, allow_disabled)
        snapshot = _snapshot(user, row)
        user._authentication_snapshot = snapshot
        return user, dict(snapshot)


def state(user):
    # Storage lookup never binds a late snapshot to the caller's possibly stale object.
    with atomic():
        _current, row = _locked_account(user.user_id, allow_disabled=True)
        return row


def user_epoch(user_id):
    # Optional PAT verification may run while its caller streams another SELECT.
    # One joined read is coherent and never upgrades that snapshot or mints state.
    row = (UserSecurity.select(UserSecurity.epoch).join(User, on=(UserSecurity.user_id == User.user_id))
           .join(AuthenticationPolicy, on=(AuthenticationPolicy.id == 1))
           .where(User.user_id == user_id).first())
    if row is None:
        raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
    return row.epoch


def user_account_id(user_id):
    return capture_account(user_id, allow_disabled=True)[1]['auth_account']


def expected_snapshot(user):
    expected = getattr(user, '_authentication_snapshot', None)
    if expected is None and has_request_context():
        principal = getattr(g, 'local_auth_principal', None)
        try:
            claims = get_jwt()
        except RuntimeError:
            claims = {}
        if principal and principal.get('jti') == claims.get('jti') and str(principal['snapshot']['_user_id']) == str(user.user_id):
            expected = principal['snapshot']
    if not isinstance(expected, dict):
        raise RoxywiPublicError('Authentication snapshot is required; authenticate again')
    return dict(expected)


def _assert_snapshot(user, row, expected):
    current = _snapshot(user, row)
    if not isinstance(expected, dict) or any(current[key] != expected.get(key) for key in current):
        raise RoxywiPublicError('Account security changed; authenticate again')
    return current


def bind_snapshot(user_id, expected):
    with atomic():
        user, row = _locked_account(user_id)
        user._authentication_snapshot = _assert_snapshot(user, row, expected)
        return user


def session_user(claims):
    principal = getattr(g, 'local_auth_principal', None)
    if not principal or principal.get('jti') != claims.get('jti') or str(principal['snapshot']['_user_id']) != str(claims.get('user_id')):
        raise RoxywiPublicError('Interactive authentication is required')
    return bind_snapshot(claims['user_id'], principal['snapshot'])


def initialize_baseline():
    # The singleton survives user deletion. Reruns never whitelist a new account
    # that reused an older account's numeric ID.
    with atomic():
        rule = policy()
        query = AuthenticationPolicy.select().where(AuthenticationPolicy.id == rule.id)
        if not isinstance(AuthenticationPolicy._meta.database, SqliteDatabase):
            query = query.for_update()
        if query.get().baseline_initialized:
            return
        for user in User.select():
            UserSecurity.get_or_create(user_id=user.user_id, defaults={
                'password_version': password_version(user), 'legacy_allowed': True})
        AuthenticationPolicy.update(baseline_initialized=True).where(AuthenticationPolicy.id == rule.id).execute()


def providers():
    result = []
    for name in ('totp', 'passkeys'):
        module = 'app.modules.authentication.' + name
        if importlib.util.find_spec(module) is not None:
            result.append(importlib.import_module(module))
    return result


def has_factor(user_id, *, locking=True):
    return any(provider.has_factor(user_id) if locking else provider.has_factor(user_id, locking=False)
               for provider in providers())


def local_user(user):
    return not user.ldap_user and bool(user.password)


def policy():
    return AuthenticationPolicy.get_or_create(id=1)[0]


def lock_policy():
    rule = policy()
    query = AuthenticationPolicy.select().where(AuthenticationPolicy.id == rule.id)
    if not isinstance(AuthenticationPolicy._meta.database, SqliteDatabase):
        query = query.for_update()
    return query.get()


def _memberships(user, *, locking=True):
    query = UserGroups.select().where(UserGroups.user_id == user.user_id)
    database = UserGroups._meta.database
    if locking and database.in_transaction() and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return query


def policy_applies(user, rule=None, *, locking=True):
    rule = policy() if rule is None else rule
    return local_user(user) and (rule.mode == 'all' or
        (rule.mode == 'admin' and (int(user.role_id) <= 2 or
                                  _memberships(user, locking=locking).where(UserGroups.user_role_id <= 2).exists())))


def can_manage_policy(user):
    return _memberships(user).where((UserGroups.user_group_id == int(user.group_id)) &
                                   (UserGroups.user_role_id == 1)).exists()


def enrollment_required(user):
    return policy_applies(user) and not has_factor(user.user_id) and now() >= policy().grace_until


def login_proof(user, method, expected=None):
    expected = expected_snapshot(user) if expected is None else dict(expected)
    with atomic():
        current, row = _locked_account(user.user_id)
        snapshot = _assert_snapshot(current, row, expected)
        return dict(auth_epoch=snapshot['auth_epoch'], auth_account=snapshot['auth_account'],
                    credential_version=snapshot['credential_version'], auth_method=method, auth_time=now())


def proof_from_challenge(payload, method):
    proof = payload['_verified_proof']
    return {**{key: proof[key] for key in PROOF_FIELDS if key in proof}, 'auth_method': method}


def validate_session(claims):
    if claims.get('credential_type') == 'pat':
        module = 'app.modules.api_tokens'
        if importlib.util.find_spec(module) is None:
            return False
        return importlib.import_module(module + '.service').verify(claims)
    try:
        # Validation is a coherent read snapshot, including when called while a
        # handler is streaming another SELECT. SQLite must never upgrade that
        # cursor's WAL snapshot with BEGIN IMMEDIATE (SQLITE_BUSY_SNAPSHOT).
        # Issuance and mutations still bind the captured principal under the
        # current parent-account lock; this read path never initializes state.
        with UserSecurity._meta.database.atomic():
            user = User.get_or_none(User.user_id == claims.get('user_id'))
            if user is None or not user.enabled:
                return False
            row = UserSecurity.get_or_none(UserSecurity.user_id == user.user_id)
            rule = AuthenticationPolicy.get_or_none(AuthenticationPolicy.id == 1)
            if row is None or rule is None:
                return False
            snapshot = _snapshot(user, row)
            if 'auth_epoch' in claims:
                expected = dict(_user_id=user.user_id, **{key: claims.get(key) for key in ('auth_epoch', 'auth_account', 'credential_version')})
                _assert_snapshot(user, row, expected)
            elif not row.legacy_allowed or row.epoch or row.password_version != snapshot['credential_version']:
                return False
            if claims.get('auth_method') != 'oidc' and local_user(user):
                configured = has_factor(user.user_id, locking=False)
                if configured and claims.get('auth_method') not in COMPLETE_METHODS:
                    return False
                if (policy_applies(user, rule, locking=False) and not configured and now() >= rule.grace_until and
                        (not has_request_context() or request.endpoint not in {
                            'local_auth.security_page', 'local_auth.security_status', 'local_auth.reauthenticate',
                            'local_totp.totp_setup', 'local_totp.totp_confirm', 'logout',
                            'passkeys.page', 'passkeys.register_options', 'passkeys.register_finish'})):
                    return False
            if has_request_context():
                g.local_auth_principal = dict(jti=claims.get('jti'), snapshot=snapshot)
            return True
    except RoxywiPublicError:
        return False


def record(user_id, event, outcome='success', external=True, reason_code=None, actor_verified=True):
    # Denial accounting survives known export outages; successful changes fail closed.
    AuthenticationEvent.delete().where(AuthenticationEvent.created_at < now() - 90 * 86400).execute()
    AuthenticationEvent.create(user_id=user_id, event=event, outcome=outcome, created_at=now())
    cutoff = AuthenticationEvent.select(AuthenticationEvent.id).order_by(AuthenticationEvent.id.desc()).offset(MAX_LOCAL_EVENTS - 1).scalar()
    if cutoff is not None:
        AuthenticationEvent.delete().where(AuthenticationEvent.id < cutoff).execute()
    module = 'app.modules.audit.events'
    if external and importlib.util.find_spec('app.modules.audit') is not None:
        adapter = importlib.import_module(module)
        user = User.get_or_none(User.user_id == user_id)
        exported = 'succeeded' if outcome == 'success' else outcome
        details = {'subject_id': str(user_id)}
        if reason_code in ('invalid_assertion', 'invalid_registration', 'invalid_factor',
                           'expired_challenge', 'verification_failed'):
            details['reason_code'] = reason_code
        try:
            # Only a completed login proof can use audit's bounded repair reserve.
            # Configuration changes and denied/unverified attempts remain ordinary writes.
            login_result = (outcome == 'success' and actor_verified and event in {
                'authentication.verified', 'authentication.passkey.login', 'authentication.recovery.used'})
            adapter.record(event, exported, user_id=user_id if actor_verified else None,
                           group_id=int(user.group_id) if user else None, details=details,
                           **({'force': True} if login_result else {}))
        except adapter.AuditStorageUnavailable:
            if outcome not in ('denied', 'failed'):
                raise
            # A full external queue must not undo a charged local denial.
            from app.modules.roxywi import logger
            logger.warning('External authentication audit export unavailable',
                           user_id=user_id, event=event)


def issue_challenge(user, purpose, payload=None, binding='', ttl=300):
    expected = getattr(user, '_authentication_snapshot', None)
    with atomic():
        current, row = _locked_account(user.user_id)
        if expected is not None:
            _assert_snapshot(current, row, expected)
        if current.username != user.username or password_version(current) != password_version(user):
            raise RoxywiPublicError('Account credentials changed; authenticate again')
        user = current
        token = secrets.token_urlsafe(32)
        AuthenticationChallenge.delete().where((AuthenticationChallenge.user_id == user.user_id) &
            ((AuthenticationChallenge.expires_at < now()) | (AuthenticationChallenge.used == True))).execute()
        # Bound persistent state: a password holder cannot fill the DB with live challenges.
        live = AuthenticationChallenge.select().where(
            (AuthenticationChallenge.user_id == user.user_id) &
            (AuthenticationChallenge.used == False) & (AuthenticationChallenge.expires_at >= now()))
        if live.count() >= 20:
            raise RoxywiPublicError('Too many pending authentication requests; try again later')
        AuthenticationChallenge.create(token_hash=digest(token), user_id=user.user_id, purpose=purpose,
            epoch=row.epoch, password_version=password_version(user),
            binding=digest(binding) if binding else '',
            payload=crypt_password(json.dumps(payload or {})).decode('ascii'), expires_at=now() + min(ttl, 600))
        return token


def consume_challenge(token, purpose, verify=None, binding=''):
    """The conditional write locks the challenge before checking/consuming a factor.

    Failed attempts commit; factor counter/recovery-code consumption and successful
    challenge consumption share the transaction. Works across workers on SQLite/MySQL.
    """
    if not isinstance(token, str) or len(token) > 256:
        return None
    candidate = AuthenticationChallenge.get_or_none(AuthenticationChallenge.token_hash == digest(token))
    if candidate is None:
        return None
    user = User.get_or_none(User.user_id == candidate.user_id)
    if user is None:
        return None
    result = None
    with atomic():
        # Parent account, security state, then challenge: compatible with FK deletion.
        user = current_user(user.user_id)
        if user is None:
            return None
        row = _state_locked(user)
        user._authentication_snapshot = _snapshot(user, row)
        UserSecurity.update(failed_attempts=UserSecurity.failed_attempts).where(UserSecurity.user_id == user.user_id).execute()
        if not user.enabled or not local_user(user) or row.blocked_until > now():
            return None
        eligible = ((AuthenticationChallenge.token_hash == digest(token)) &
                    (AuthenticationChallenge.purpose == purpose) &
                    (AuthenticationChallenge.binding == (digest(binding) if binding else '')) &
                    (AuthenticationChallenge.expires_at >= now()) &
                    (AuthenticationChallenge.used == False) & (AuthenticationChallenge.attempts < 5))
        if not AuthenticationChallenge.update(attempts=AuthenticationChallenge.attempts + 1).where(eligible).execute():
            return None
        challenge = AuthenticationChallenge.get_by_id(digest(token))
        if challenge.epoch != row.epoch or challenge.password_version != password_version(user):
            return None
        payload = json.loads(decrypt_password(challenge.payload))
        try:
            verified = verify is None or verify(user, payload)
        except (ValueError, RoxywiPublicError):
            verified = False
        if verified:
            AuthenticationChallenge.update(used=True).where(AuthenticationChallenge.token_hash == digest(token)).execute()
            UserSecurity.update(failed_attempts=0, blocked_until=0).where(UserSecurity.user_id == user.user_id).execute()
            payload['_verified_proof'] = dict(_snapshot(user, _state_locked(user)), auth_time=now())
            result = (user, payload)
        else:
            failures = row.failed_attempts + 1
            UserSecurity.update(failed_attempts=failures if failures < 5 else 0,
                blocked_until=now() + 300 if failures >= 5 else 0).where(UserSecurity.user_id == user.user_id).execute()
    return result


def verify_recovery(user, value):
    if not isinstance(value, str) or len(value) > 64:
        return False
    normalized = value.replace('-', '').strip().lower()
    if not re.fullmatch(r'[0-9a-f]{32}', normalized):
        return False
    return bool(RecoveryCode.update(used_at=now()).where(
        (RecoveryCode.user_id == user.user_id) & (RecoveryCode.digest == digest(normalized)) &
        RecoveryCode.used_at.is_null()).execute())


def verify_factor_kind(user, data):
    if data.get('recovery_code'):
        return 'recovery' if verify_recovery(user, data['recovery_code']) else None
    for provider in providers():
        if provider.has_factor(user.user_id) and provider.verify_factor(user, data):
            return 'passkey' if provider.__name__.endswith('.passkeys') else 'totp'
    return None


def verify_factor(user, data):
    return bool(verify_factor_kind(user, data))


def recovery_codes(user):
    codes = [secrets.token_hex(16) for _ in range(10)]
    RecoveryCode.delete().where(RecoveryCode.user_id == user.user_id).execute()
    RecoveryCode.insert_many([dict(user_id=user.user_id, digest=digest(code)) for code in codes]).execute()
    return ['-'.join(code[i:i+8] for i in range(0,32,8)) for code in codes]


def browser_binding():
    if 'local_auth_binding' not in session:
        session['local_auth_binding'] = secrets.token_urlsafe(32)
    return session['local_auth_binding']


def session_binding():
    if not has_request_context():
        return ''
    try:
        return get_jwt().get('jti', '')
    except RuntimeError:
        return ''


def require_sensitive_action(user, data, purpose='personal_token.create'):
    user = bind_snapshot(user.user_id, expected_snapshot(user))
    if not local_user(user):
        raise RoxywiPublicError('Use your identity provider to manage this account')
    if data.get('reauth_token'):
        result = consume_challenge(data['reauth_token'], 'reauth:' + purpose, binding=session_binding(),
                                   verify=lambda actual, payload: actual.user_id == user.user_id)
        if result:
            return
        raise RoxywiPublicError('Authentication proof expired or was already used')
    token = issue_challenge(user, 'sensitive:' + purpose, ttl=60)
    def verify(actual, _payload):
        password = data.get('password')
        return isinstance(password, str) and Tools.check_password(password, actual.password)[0] and (
            not has_factor(actual.user_id) or verify_factor(actual, data))
    if not consume_challenge(token, 'sensitive:' + purpose, verify=verify):
        raise RoxywiPublicError('Verify your password and configured second factor')


def revoke_sessions(user, event='authentication.reset', external=True):
    expected = getattr(user, '_authentication_snapshot', None)
    with atomic():
        current, row = _locked_account(user.user_id, allow_disabled=True)
        if expected is not None:
            _assert_snapshot(current, row, expected)
        elif has_request_context():
            _assert_snapshot(current, row, expected_snapshot(user))
        UserSecurity.update(epoch=UserSecurity.epoch + 1, password_version=password_version(current),
                            failed_attempts=0, blocked_until=0).where(UserSecurity.user_id == current.user_id).execute()
        AuthenticationChallenge.delete().where(AuthenticationChallenge.user_id == current.user_id).execute()
        record(current.user_id, event, external=external)
        if expected is not None:
            user._authentication_snapshot = _snapshot(current, _state_locked(current))


def assert_unchanged(user, expected_epoch, expected_account=None):
    with atomic():
        current, row = _locked_account(user.user_id)
        if (row.epoch != expected_epoch or expected_account is not None and row.account_id != expected_account or
                password_version(current) != password_version(user)):
            raise RoxywiPublicError('Account security changed; authenticate again')
        return current


def before_password_login(user_params, data, channel='web'):
    expected = user_params.get('_password_proof')
    if not isinstance(expected, dict):
        raise RoxywiPublicError('Authentication snapshot is required; authenticate again')
    with atomic():
        user = bind_snapshot(user_params['user'], expected)
        if not local_user(user):
            user_params.update(login_proof(user, 'ldap'))
            return None
        if has_factor(user.user_id) or enrollment_required(user):
            token = issue_challenge(user, 'login:' + channel, {'group': str(user.group_id), 'next': data.get('next', ''),
                'enrollment': enrollment_required(user)}, binding=browser_binding() if channel == 'web' else '')
            return dict(status='enrollment_required' if enrollment_required(user) else 'mfa_required', challenge=token,
                methods=[p.__name__.split('.')[-1] for p in providers() if p.has_factor(user.user_id)], expires_in=300)
        user_params.update(login_proof(user, 'password'))
    return None


def console_reset(username, reason):
    if reason not in ('lost-device', 'compromise', 'restore'):
        raise RoxywiPublicError('Select an account recovery reason')
    with atomic():
        selected = User.get(User.username == username)
        user, _expected = capture_account(selected.user_id, allow_disabled=True)
    if not local_user(user):
        raise RoxywiPublicError('This account is managed by an identity provider')
    with atomic():
        state(user)
        UserSecurity.update(epoch=UserSecurity.epoch).where(UserSecurity.user_id == user.user_id).execute()
        for provider in providers():
            provider.reset(user.user_id)
        RecoveryCode.delete().where(RecoveryCode.user_id == user.user_id).execute()
        # Recovery must work even when the external audit queue is unavailable.
        revoke_sessions(user, 'authentication.console_reset.' + reason, external=False)
    return user_epoch(user.user_id)


def rotate_encrypted_state(old_fernet, new_fernet):
    from cryptography.fernet import InvalidToken
    count = 0
    for row in AuthenticationChallenge.select():
        try:
            plaintext = old_fernet.decrypt(row.payload.encode('ascii'))
        except InvalidToken:
            new_fernet.decrypt(row.payload.encode('ascii'))
            continue
        AuthenticationChallenge.update(payload=new_fernet.encrypt(plaintext).decode('ascii')).where(
            AuthenticationChallenge.token_hash == row.token_hash).execute()
        count += 1
    for provider in providers():
        if hasattr(provider, 'rotate_encrypted_state'):
            count += provider.rotate_encrypted_state(old_fernet, new_fernet)
    return count
