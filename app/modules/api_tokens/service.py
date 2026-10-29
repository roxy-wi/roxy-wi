"""Issue once, store a digest, and recheck authority on every API request."""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import hmac
import importlib.util
import json
import secrets
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.hmac import HMAC

from flask import abort, request, g
from peewee import SqliteDatabase
from flask_jwt_extended import create_access_token, get_jwt

from app.modules.api_tokens.scopes import SCOPES, ENDPOINTS
from app.modules.common.time import utc_now
from app.modules.db.db_model import PersonalAccessToken, PersonalTokenGate, User, UserGroups, Server, Services, ConfigChange, ConfigChangeTarget
from app.modules.roxywi.exception import RoxywiPermissionError, RoxywiResourceNotFound, RoxywiValidationError, RoxywiPublicError


class CredentialWriteUnavailable(RoxywiPublicError):
    pass


def audit_credential(event_type, row):
    if importlib.util.find_spec('app.modules.audit') is None:
        return
    from app.modules.audit import events
    try:
        events.record(event_type, 'succeeded', user_id=row.user_id, group_id=row.group_id,
                      details=dict(token_id=row.id, subject_type='personal_token'))
    except events.AuditStorageUnavailable:
        raise CredentialWriteUnavailable('Audit storage unavailable; credential was not changed') from None


def security_provider():
    if importlib.util.find_spec('app.modules.authentication') is None:
        return None
    if importlib.util.find_spec('app.modules.authentication.security') is None:
        return None
    from app.modules.authentication import security
    return security


def password_version(user):
    # This is a credential-change marker, never a password verifier. Keep it
    # keyed independently of the Fernet key used for encrypted configuration.
    from app import app
    key = app.config['SECRET_KEY']
    key = key.encode('utf-8') if isinstance(key, str) else bytes(key)
    material = b'roxywi.personal-token.password-version.v1\x00' + str(user.password or '').encode('utf-8')
    # Secret-keyed change marker over a stored hash, never a password verifier.
    mac = HMAC(key, hashes.SHA256())
    mac.update(material)
    return mac.finalize().hex()


def security_version(user_id):
    provider = security_provider()
    return provider.user_epoch(user_id) if provider else 0


def owner_eligible(row, user):
    return bool(user is not None and user.enabled and not user.ldap_user and user.password and
                hmac.compare_digest(row.password_version, password_version(user)) and
                row.security_version == security_version(row.user_id))


def public(row):
    user = User.get_or_none(User.user_id == row.user_id)
    available = (not row.revoked_at and row.expires_at > utc_now() and owner_eligible(row, user)) and UserGroups.select().where(
        (UserGroups.user_id == row.user_id) & (UserGroups.user_group_id == row.group_id)).exists()
    return dict(available=bool(available), id=row.id, name=row.name, group_id=row.group_id, scopes=json.loads(row.scopes),
                created_at=row.created_at.isoformat()+'Z', expires_at=row.expires_at.isoformat()+'Z',
                revoked_at=row.revoked_at.isoformat()+'Z' if row.revoked_at else None,
                last_used_at=row.last_used_at.isoformat()+'Z' if row.last_used_at else None)


def list_tokens(user_id):
    with token_write():
        current = lock_user(user_id)
        require_interactive_principal(current)
        return [public(row) for row in PersonalAccessToken.select().where(
            PersonalAccessToken.user_id == user_id).order_by(PersonalAccessToken.created_at.desc())]


@contextmanager
def token_write():
    database = PersonalAccessToken._meta.database
    with database.atomic(*(('IMMEDIATE',) if isinstance(database, SqliteDatabase) else ())):
        yield



def lock_user(user_id):
    query = User.select().where(User.user_id == user_id)
    if not isinstance(User._meta.database, SqliteDatabase):
        query = query.for_update()
    user = query.first()
    if user is None:
        raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
    return user


def require_interactive_principal(user):
    """Keep optional MFA's original cookie principal bound to the locked account."""
    provider = security_provider()
    if provider is None:
        return user
    bind = getattr(provider, 'session_user', None)
    if not callable(bind):
        raise RoxywiPermissionError('Interactive authentication is unavailable; authenticate again')
    try:
        principal = bind(get_jwt())
    except (RoxywiPublicError, RuntimeError):
        raise RoxywiPermissionError('Credentials changed during authentication; authenticate again') from None
    if getattr(principal, 'user_id', None) != user.user_id:
        raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
    return principal


def lock_gate(user_id):
    lock_user(user_id)  # Match parent-before-child order used by account deletion.
    PersonalTokenGate.get_or_create(user_id=user_id)
    query = PersonalTokenGate.select().where(PersonalTokenGate.user_id == user_id)
    if not isinstance(PersonalTokenGate._meta.database, SqliteDatabase):
        query = query.for_update()
    return query.get()


def sensitive_attempt(user_id, *, interactive=False):
    with token_write():
        if interactive:
            require_interactive_principal(lock_user(user_id))
        gate = lock_gate(user_id)
        now = utc_now()
        if gate.window_started_at < now-timedelta(minutes=5):
            gate.window_started_at, gate.attempts = now, 0
        if gate.attempts >= 5:
            raise RoxywiPermissionError('Too many authentication attempts; try again in five minutes')
        gate.attempts += 1
        gate.save()
        return gate.incarnation


def create(data, user_id):
    if not isinstance(data, dict) or set(data)-{
        'name', 'group_id', 'scopes', 'expires_days', 'password', 'otp', 'reauth_token',
    }:
        raise RoxywiValidationError('Invalid personal token settings')
    name, group_id = data.get('name'), data.get('group_id')
    scopes, days = data.get('scopes'), data.get('expires_days', 90)
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 128 or type(group_id) is not int
            or not isinstance(scopes, list) or not scopes or len(scopes) > len(SCOPES)
            or any(not isinstance(scope, str) or scope not in SCOPES for scope in scopes)
            or type(days) is not int or not 1 <= days <= 365):
        raise RoxywiValidationError('Choose a name, group, known scopes and expiry between 1 and 365 days')
    with token_write():
        user = require_interactive_principal(lock_user(user_id))
    if not user.enabled or user.ldap_user or not user.password:
        raise RoxywiPermissionError('A local account with an interactive authentication method is required')
    membership = UserGroups.get_or_none((UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
    if membership is None:
        raise RoxywiPermissionError('No current membership in the token group')
    if PersonalAccessToken.select().where(
            (PersonalAccessToken.user_id == user_id) & PersonalAccessToken.revoked_at.is_null(True) &
            (PersonalAccessToken.expires_at > utc_now())).count() >= 25:
        raise RoxywiValidationError('Revoke unused personal tokens before creating another (maximum 25 active)')
    expected_password, expected_epoch = password_version(user), security_version(user_id)
    expected_incarnation = sensitive_attempt(user_id, interactive=True)
    provider = security_provider()
    if provider:
        provider.require_sensitive_action(user, data, purpose='personal_token.create')
    else:
        from app.modules.roxywi.auth import check_user_password
        try:
            check_user_password(user.username, data.get('password'))
        except Exception:
            raise RoxywiPermissionError('Interactive authentication failed') from None
    # Password rehash during authentication is also a credential version change.
    user = User.get_by_id(user_id)
    version = security_version(user_id)
    if (not user.enabled or user.ldap_user or not user.password or version != expected_epoch or
            (provider and password_version(user) != expected_password)):
        raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
    if not provider and password_version(user) != expected_password:
        # Permit an intentional legacy-hash upgrade, but never bind a proof of
        # the old password to a different password reset concurrently.
        from app.modules.roxy_wi_tools import Tools
        if not Tools.check_password(data.get('password'), user.password)[0]:
            raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
    approved_password = password_version(user)
    now, token_id = utc_now(), str(uuid4())
    access_token = create_access_token(str(user_id), expires_delta=timedelta(days=days), additional_claims={
        'credential_type': 'pat', 'group': str(group_id), 'pat_id': token_id,
        'nonce': secrets.token_urlsafe(32),
    })
    with token_write():
        current = lock_user(user_id)
        require_interactive_principal(current)
        gate = lock_gate(user_id)
        if (gate.incarnation != expected_incarnation or not current.enabled or current.ldap_user or
                password_version(current) != approved_password or security_version(user_id) != version):
            raise RoxywiPermissionError('Credentials changed during authentication; authenticate again')
        membership_query = UserGroups.select().where(
            (UserGroups.user_id == user_id) & (UserGroups.user_group_id == group_id))
        if not isinstance(UserGroups._meta.database, SqliteDatabase):
            membership_query = membership_query.for_update()
        current_membership = membership_query.first()
        if current_membership is None or current_membership.user_role_id not in {1, 2, 3, 4}:
            raise RoxywiPermissionError('No current membership in the token group')
        if PersonalAccessToken.select().where(
                (PersonalAccessToken.user_id == user_id) & PersonalAccessToken.revoked_at.is_null(True) &
                (PersonalAccessToken.expires_at > utc_now())).count() >= 25:
            raise RoxywiValidationError('Revoke unused personal tokens before creating another (maximum 25 active)')
        if PersonalAccessToken.select().where(PersonalAccessToken.user_id == user_id).count() >= 250:
            raise RoxywiValidationError('Personal token metadata limit reached (250 per user); contact an administrator')
        row = PersonalAccessToken.create(id=token_id, user_id=user_id, group_id=group_id, name=name.strip(),
            token_digest=hashlib.sha256(access_token.encode('ascii')).hexdigest(),
            password_version=approved_password, security_version=version,
            scopes=json.dumps(sorted(set(scopes))), created_at=now, expires_at=now+timedelta(days=days))
        audit_credential('auth.personal_token.created', row)
        gate.attempts = 0
        gate.window_started_at = now
        gate.save()
    return dict(token=public(row), access_token=access_token)


def revoke(token_id, user_id):
    with token_write():
        require_interactive_principal(lock_user(user_id))
        row = PersonalAccessToken.get_or_none((PersonalAccessToken.id == token_id) & (PersonalAccessToken.user_id == user_id))
        if row is None:
            raise RoxywiResourceNotFound('Personal token not found')
        changed = PersonalAccessToken.update(revoked_at=utc_now()).where(
            (PersonalAccessToken.id == token_id) & (PersonalAccessToken.user_id == user_id) &
            PersonalAccessToken.revoked_at.is_null(True)).execute()
        if changed:
            audit_credential('auth.personal_token.revoked', row)
    return dict(status='revoked')


def revoke_all(user_id):
    return PersonalAccessToken.update(revoked_at=utc_now()).where(
        (PersonalAccessToken.user_id == user_id) & PersonalAccessToken.revoked_at.is_null(True)).execute()


def purge_metadata():
    """Drop inactive credentials after 90 days; absence always means denied."""
    cutoff = utc_now()-timedelta(days=90)
    eligible = (PersonalAccessToken.expires_at < cutoff) | (
        PersonalAccessToken.revoked_at.is_null(False) & (PersonalAccessToken.revoked_at < cutoff))
    ids = [row.id for row in PersonalAccessToken.select(PersonalAccessToken.id).where(eligible).limit(1000)]
    return PersonalAccessToken.delete().where(PersonalAccessToken.id.in_(ids)).execute() if ids else 0


def verify(payload):
    """Called by the supported JWT verification callback, never mint a web JWT."""
    if payload.get('credential_type') != 'pat':
        return True
    if request.blueprint != 'api':
        abort(403, 'Personal tokens are restricted to the API')
    header = request.headers.get('Authorization', '').split()
    if len(header) != 2 or header[0].lower() != 'bearer':
        return False  # PAT cookies and query-string tokens are not accepted.
    row = PersonalAccessToken.get_or_none(PersonalAccessToken.id == payload.get('pat_id'))
    if row is None or row.revoked_at or row.expires_at <= utc_now():
        return False
    if not hmac.compare_digest(row.token_digest, hashlib.sha256(header[1].encode('utf-8')).hexdigest()):
        return False
    user = User.get_or_none(User.user_id == row.user_id)
    if (not owner_eligible(row, user) or str(payload.get('user_id')) != str(row.user_id) or
            str(payload.get('group')) != str(row.group_id)):
        return False
    membership = UserGroups.get_or_none((UserGroups.user_id == row.user_id) &
                                        (UserGroups.user_group_id == row.group_id))
    if membership is None or membership.user_role_id not in {1, 2, 3, 4}:
        return False
    scope = ENDPOINTS.get((request.endpoint, request.method))
    if scope is None or scope not in json.loads(row.scopes):
        abort(403, 'Personal token scope does not permit this API operation')
    # Even a super administrator cannot widen a token through an API group override.
    if any(value != str(row.group_id) for value in request.args.getlist('group_id')):
        abort(403, 'Personal tokens have a fixed group')
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    if 'group_id' in body and str(body['group_id']) != str(row.group_id):
        abort(403, 'Personal tokens have a fixed group')
    args = request.view_args or {}
    def check_server(value):
        query = Server.server_id == value if isinstance(value, int) or str(value).isdigit() else Server.ip == value
        server = Server.get_or_none(query)
        if server is None or str(server.group_id) != str(row.group_id):
            abort(403, 'Server is outside the token group')
        return server
    server_id = args.get('server_id', body.get('server_id', request.args.get('server_id')))
    if server_id is not None:
        check_server(server_id)
    for key in ('canary_server_ids', 'excluded_server_ids'):
        if key in body:
            if not isinstance(body[key], list) or len(body[key]) > 50:
                abort(403, 'Invalid rollout target selection')
            for value in body[key]:
                check_server(value)
    change = None
    if args.get('change_id') is not None:
        change = ConfigChange.get_or_none(ConfigChange.id == args['change_id'])
        if change:
            if str(change.group_id) != str(row.group_id):
                abort(403, 'Change is outside the token group')
            check_server(change.server_id)
            for target in ConfigChangeTarget.select().where(ConfigChangeTarget.change == change.id):
                check_server(target.server_id)
    service = change.service if change else args.get('service', body.get('service', request.args.get('service')))
    if service is not None:
        service_row = Services.get_or_none(Services.slug == service)
        if service_row is None or str(service_row.service_id) not in str(user.user_services).split():
            abort(403, 'Current user has no access to this service')
    # Change Center discovers slaves implicitly before capturing snapshots or
    # previewing/replanning a rollout. Validate that live topology as well as the
    # stored/explicit targets above, before its view can perform any remote I/O.
    primary_id = change.server_id if change else server_id
    if scope.startswith('changes.') and service in {'haproxy', 'nginx', 'apache'} and primary_id is not None:
        primary = check_server(primary_id)
        for target in Server.select().where(Server.master == primary.server_id):
            check_server(target.server_id)
    # Role checks, group checks and subscription checks in the actual API view
    # still execute. last_used is operational metadata, never an authority cache.
    if row.last_used_at is None or row.last_used_at < utc_now()-timedelta(seconds=60):
        try:
            PersonalAccessToken.update(last_used_at=utc_now()).where(
                (PersonalAccessToken.id == row.id) &
                (PersonalAccessToken.last_used_at.is_null(True) |
                 (PersonalAccessToken.last_used_at < utc_now()-timedelta(seconds=60)))).execute()
        except Exception:
            from app.modules.roxywi import logger
            logger.warning('Personal token last-used metadata could not be updated', token_id=row.id)

    g.personal_token_id = row.id
    return True
