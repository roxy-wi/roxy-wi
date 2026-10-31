"""Local WebAuthn verification. Only public credentials are stored on the server."""
import hashlib
import json
import ipaddress
import re
import secrets
import time
from urllib.parse import urlsplit

from flask import current_app, request, session
from peewee import SqliteDatabase
from webauthn import (generate_registration_options, verify_registration_response,
                      generate_authentication_options, verify_authentication_response, options_to_json)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, ResidentKeyRequirement,
    UserVerificationRequirement, PublicKeyCredentialDescriptor)

from app.modules.db.db_model import PasskeyCredential, PasskeyIdentity


class PasskeyError(ValueError):
    """A public, non-sensitive ceremony failure."""


def configuration():
    """Trust only administrator configuration, never Host/proxy headers."""
    rp_id = str(current_app.config.get('WEBAUTHN_RP_ID', '')).strip().lower()
    origins = current_app.config.get('WEBAUTHN_ORIGINS', [])
    if isinstance(origins, str):
        origins = [value.strip() for value in origins.split(',') if value.strip()]
    if not rp_id or not isinstance(origins, (list, tuple)) or not origins or len(origins) > 20:
        raise PasskeyError('Passkeys require an explicit RP ID and HTTPS origins')
    try:
        ipaddress.ip_address(rp_id)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip or len(rp_id) > 253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*', rp_id):
        raise PasskeyError('Invalid passkey RP ID')
    validated = []
    for origin in origins:
        if not isinstance(origin, str) or len(origin) > 512:
            raise PasskeyError('Invalid passkey origin')
        try:
            parsed = urlsplit(origin)
        except ValueError:
            raise PasskeyError('Invalid passkey origin') from None
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or parsed.hostname != rp_id and not parsed.hostname.endswith('.' + rp_id)):
            raise PasskeyError('Passkey origins must be explicit HTTPS origins within the RP ID')
        try:
            parsed.port
        except ValueError:
            raise PasskeyError('Invalid passkey origin') from None
        validated.append(origin)
    return rp_id, validated


def enabled():
    try:
        configuration()
        return True
    except PasskeyError:
        return False


def check_origin():
    _, origins = configuration()
    if request.headers.get('Origin') not in origins:
        raise PasskeyError('Passkey request origin is not allowed')


def browser_binding():
    if not session.get('passkey_binding'):
        session['passkey_binding'] = secrets.token_urlsafe(32)
    return 'passkeys:' + session['passkey_binding']


def local_user(user):
    if not user or not user.enabled or user.ldap_user or not user.password:
        raise PasskeyError('Local authentication is unavailable')
    return user


def list_credentials(user_id, locking=False):
    query = PasskeyCredential.select().where(PasskeyCredential.user_id == user_id)
    database = PasskeyCredential._meta.database
    if locking and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return list(query)


def has_factor(user_id, *, locking=True):
    database = PasskeyCredential._meta.database
    query = PasskeyCredential.select().where(PasskeyCredential.user_id == user_id).limit(1)
    if locking and database.in_transaction() and not isinstance(database, SqliteDatabase):
        query = query.for_update()
    return query.get_or_none() is not None


def _credentials(user):
    rp_id, _ = configuration()
    return list(PasskeyCredential.select().where(
        PasskeyCredential.user_id == user.user_id, PasskeyCredential.rp_id == rp_id))


def _identity(user):
    identity, _ = PasskeyIdentity.get_or_create(user_id=user.user_id,
        defaults={'user_handle': bytes_to_base64url(secrets.token_bytes(32))})
    return identity


def _snapshot():
    rp_id, origins = configuration()
    return {'rp_id': rp_id, 'origins': origins, 'challenge': bytes_to_base64url(secrets.token_bytes(32))}


def _check_snapshot(payload):
    rp_id, origins = configuration()
    if payload.get('rp_id') != rp_id or payload.get('origins') != origins:
        raise PasskeyError('Passkey configuration changed; start again')


def _credential(data):
    value = data.get('credential')
    if not isinstance(value, dict) or len(json.dumps(value)) > 32768:
        raise PasskeyError('Invalid passkey response')
    try:
        client = json.loads(base64url_to_bytes(value['response']['clientDataJSON']))
        if client.get('crossOrigin', False) or client.get('topOrigin'):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise PasskeyError('Cross-origin passkey responses are not allowed') from None
    return value


def _record_denial(user, event, reason_code):
    from app.modules.authentication import security
    # Generic recording preserves the local denial/gate when the optional audit
    # export reaches its quota; successful security mutations remain strict.
    security.record(user.user_id, event, 'denied', reason_code=reason_code, actor_verified=False)


def begin_registration(user, binding, purpose='passkeys.register', context=None):
    from app.modules.authentication import security
    with security.atomic():
        local_user(user)
        user = security.bind_snapshot(user.user_id, security.expected_snapshot(user))
        payload = _snapshot()
        identity = _identity(user)
        payload['user_handle'] = identity.user_handle
        payload['context'] = context or {}
        if PasskeyCredential.select().where(PasskeyCredential.user_id == user.user_id).count() >= 10:
            raise PasskeyError('A maximum of ten passkeys is allowed')
        options = generate_registration_options(rp_id=payload['rp_id'], rp_name='Roxy-WI',
            user_name=user.username, user_display_name=user.username,
            user_id=base64url_to_bytes(identity.user_handle), challenge=base64url_to_bytes(payload['challenge']),
            timeout=120000, authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
                                 for c in _credentials(user)])
        token = security.issue_challenge(user, purpose, payload, binding=binding, ttl=120)
        return {'challenge_token': token, 'publicKey': json.loads(options_to_json(options))}


def complete_registration(user, data, binding, purpose='passkeys.register'):
    from app.modules.authentication import security
    name = data.get('name', '')
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise PasskeyError('Enter a passkey name of at most 80 characters')
    credential = _credential(data)
    def verify_registration(owner, payload):
        local_user(owner)
        if user is not None and owner.user_id != user.user_id:
            return False
        _check_snapshot(payload)
        if payload.get('context', {}).get('enrollment') and security.has_factor(owner.user_id):
            return False
        if len(list_credentials(owner.user_id, locking=True)) >= 10 or _identity(owner).user_handle != payload['user_handle']:
            return False
        try:
            verified = verify_registration_response(credential=credential,
                expected_challenge=base64url_to_bytes(payload['challenge']), expected_rp_id=payload['rp_id'],
                expected_origin=payload['origins'], require_user_verification=True)
        except WebAuthnException:
            return False
        credential_id = bytes_to_base64url(verified.credential_id)
        if PasskeyCredential.select().where(PasskeyCredential.credential_hash == hashlib.sha256(verified.credential_id).hexdigest()).exists():
            return False
        PasskeyCredential.create(credential_hash=hashlib.sha256(verified.credential_id).hexdigest(),
            user_id=owner.user_id, credential_id=credential_id,
            public_key=bytes_to_base64url(verified.credential_public_key), name=name.strip(),
            rp_id=payload['rp_id'], sign_count=verified.sign_count,
            device_type=verified.credential_device_type.value, backed_up=verified.credential_backed_up,
            created_at=int(time.time()))
        return True
    def verify(owner, payload):
        try:
            valid = verify_registration(owner, payload)
        except ValueError:
            valid = False
        if not valid:
            _record_denial(owner, 'authentication.passkey.registration', 'invalid_registration')
        return valid
    try:
        result = security.consume_challenge(data.get('challenge_token', ''), purpose,
                                            verify=verify, binding=binding)
    except Exception:
        raise PasskeyError('Passkey registration failed; start again') from None
    if not result:
        raise PasskeyError('Passkey registration failed; start again')
    return result


def begin_authentication(user, binding, purpose='passkeys.login'):
    from app.modules.authentication import security
    with security.atomic():
        local_user(user)
        user = security.bind_snapshot(user.user_id, security.expected_snapshot(user))
        credentials = _credentials(user)
        if not credentials:
            raise PasskeyError('Passkey authentication is unavailable')
        payload = _snapshot()
        payload['user_handle'] = _identity(user).user_handle
        options = generate_authentication_options(rp_id=payload['rp_id'],
            challenge=base64url_to_bytes(payload['challenge']), timeout=120000,
            allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
                               for c in credentials], user_verification=UserVerificationRequirement.REQUIRED)
        token = security.issue_challenge(user, purpose, payload, binding=binding, ttl=120)
        return {'challenge_token': token, 'publicKey': json.loads(options_to_json(options))}


def complete_authentication(data, binding, purpose='passkeys.login', expected_user=None):
    from app.modules.authentication import security
    credential = _credential(data)
    def verify_assertion(user, payload):
        local_user(user)
        if expected_user is not None and user.user_id != expected_user.user_id:
            return False
        _check_snapshot(payload)
        raw_id = base64url_to_bytes(credential.get('id', ''))
        query = PasskeyCredential.select().where(PasskeyCredential.credential_hash == hashlib.sha256(raw_id).hexdigest(),
            PasskeyCredential.user_id == user.user_id, PasskeyCredential.rp_id == payload['rp_id'])
        if not isinstance(PasskeyCredential._meta.database, SqliteDatabase):
            query = query.for_update()
        row = query.get_or_none()
        if not row or credential.get('id') != row.credential_id:
            return False
        handle = credential.get('response', {}).get('userHandle')
        if handle is not None and handle != payload['user_handle']:
            return False
        if _identity(user).user_handle != payload['user_handle']:
            return False
        try:
            verified = verify_authentication_response(credential=credential,
                expected_challenge=base64url_to_bytes(payload['challenge']), expected_rp_id=payload['rp_id'],
                expected_origin=payload['origins'], credential_public_key=base64url_to_bytes(row.public_key),
                credential_current_sign_count=row.sign_count, require_user_verification=True)
        except WebAuthnException:
            return False
        # Zero counters are valid for synced passkeys. When either counter is
        # nonzero the SDK enforces increment; CAS also rejects concurrent stale updates.
        changed = PasskeyCredential.update(sign_count=verified.new_sign_count, use_revision=row.use_revision + 1,
            backed_up=verified.credential_backed_up, device_type=verified.credential_device_type.value,
            last_used_at=int(time.time())).where(PasskeyCredential.credential_hash == row.credential_hash,
                PasskeyCredential.sign_count == row.sign_count, PasskeyCredential.use_revision == row.use_revision).execute()
        return changed == 1
    def verify(user, payload):
        try:
            valid = verify_assertion(user, payload)
        except ValueError:
            valid = False
        # The generic password-factor route records its own bounded failure.
        # Direct ceremonies record only a charged attempt on a trusted challenge.
        if not valid and (purpose == 'passkeys.login' or purpose.startswith('passkeys.reauth:')):
            event = 'authentication.passkey.login' if purpose == 'passkeys.login' else 'authentication.passkey.reauthentication'
            _record_denial(user, event, 'invalid_assertion')
        return valid
    try:
        result = security.consume_challenge(data.get('challenge_token', ''), purpose,
                                            verify=verify, binding=binding)
    except Exception:
        raise PasskeyError('Passkey authentication failed; start again') from None
    if not result:
        raise PasskeyError('Passkey authentication failed; start again')
    return result


def verify_factor(user, data):
    if not data.get('passkey_challenge'):
        return False
    assertion = dict(data, challenge_token=data['passkey_challenge'])
    try:
        return bool(complete_authentication(assertion, browser_binding(),
                    purpose='passkeys.factor', expected_user=user))
    except PasskeyError:
        return False


def remove_all(user_id):
    PasskeyCredential.delete().where(PasskeyCredential.user_id == user_id).execute()
    PasskeyIdentity.delete().where(PasskeyIdentity.user_id == user_id).execute()


def reset(user_id):
    remove_all(user_id)
