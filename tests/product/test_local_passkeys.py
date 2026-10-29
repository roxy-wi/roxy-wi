"""Real WebAuthn signatures against the product DB (no external identity service)."""
import hashlib
import json
import secrets
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url as b64, base64url_to_bytes as unb64
from app.modules.authentication import passkeys, security
from app.modules.db.db_model import PasskeyCredential, AuthenticationChallenge, User
from app.modules.roxywi.exception import RoxywiPublicError

PASSWORD = 'TestBootstrapPassword!'
# Pre-existing legacy DB fixture, shared with test_password_rehash_races.py.
# New passwords use scrypt; this known value exercises compatibility only.
LEGACY_PASSWORD = 'LegacyVerifiedPassword!'
LEGACY_DATABASE_HASH = 'e1846d46d83f9c9fb336fc834f407925'
ORIGIN = 'https://roxy.example.test'


class Authenticator:
    def __init__(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.id = secrets.token_bytes(32)

    def client_data(self, options, kind, origin=ORIGIN):
        return json.dumps({'type': kind, 'challenge': options['publicKey']['challenge'],
                           'origin': origin, 'crossOrigin': False}, separators=(',', ':')).encode()

    def registration(self, options, *, origin=ORIGIN, rp='roxy.example.test', uv=True, backed_up=False):
        self.handle = options['publicKey']['user']['id']
        numbers = self.private_key.public_key().public_numbers()
        public = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, 'big'), -3: numbers.y.to_bytes(32, 'big')})
        auth_data = hashlib.sha256(rp.encode()).digest() + bytes([0x41 | (4 if uv else 0) | (0x18 if backed_up else 0)]) + struct.pack('>I', 0)
        auth_data += bytes(16) + struct.pack('>H', len(self.id)) + self.id + public
        return {'id': b64(self.id), 'rawId': b64(self.id), 'type': 'public-key', 'response': {
            'clientDataJSON': b64(self.client_data(options, 'webauthn.create', origin)),
            'attestationObject': b64(cbor2.dumps({'fmt': 'none', 'attStmt': {}, 'authData': auth_data}))}}

    def assertion(self, options, *, origin=ORIGIN, rp='roxy.example.test', uv=True, count=0, handle=None, backed_up=False):
        client = self.client_data(options, 'webauthn.get', origin)
        auth_data = hashlib.sha256(rp.encode()).digest() + bytes([1 | (4 if uv else 0) | (0x18 if backed_up else 0)]) + struct.pack('>I', count)
        signature = self.private_key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {'id': b64(self.id), 'rawId': b64(self.id), 'type': 'public-key', 'response': {
            'clientDataJSON': b64(client), 'authenticatorData': b64(auth_data), 'signature': b64(signature),
            'userHandle': self.handle if handle is None else handle}}


@pytest.fixture
def ceremony(app, product, monkeypatch):
    monkeypatch.setitem(app.config, 'WEBAUTHN_RP_ID', 'roxy.example.test')
    monkeypatch.setitem(app.config, 'WEBAUTHN_ORIGINS', [ORIGIN])
    with app.test_request_context('/', base_url=ORIGIN):
        yield security.capture_account(product.admin.user_id)[0]


def register(user, device=None):
    device = device or Authenticator()
    options = passkeys.begin_registration(user, 'session-one')
    passkeys.complete_registration(user, {'name': 'Work laptop', 'challenge_token': options['challenge_token'],
                                         'credential': device.registration(options)}, 'session-one')
    return device


def test_real_registration_multiple_credentials_public_keys_only(ceremony):
    first = register(ceremony)
    options = passkeys.begin_registration(ceremony, 'session-one')
    assert options['publicKey']['authenticatorSelection']['userVerification'] == 'required'
    assert options['publicKey']['authenticatorSelection']['residentKey'] == 'required'
    assert options['publicKey']['excludeCredentials'][0]['id'] == b64(first.id)
    register(ceremony)
    assert PasskeyCredential.select().count() == 2
    assert not any('private' in name or 'secret' in name for name in PasskeyCredential._meta.fields)
    assert passkeys.has_factor(ceremony.user_id)


@pytest.mark.parametrize('change', [dict(origin='https://attacker.test'), dict(rp='attacker.test'), dict(uv=False)])
def test_registration_rejects_origin_rp_and_missing_uv(ceremony, change):
    device = Authenticator()
    options = passkeys.begin_registration(ceremony, 'session-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_registration(ceremony, {'name': 'Laptop', 'challenge_token': options['challenge_token'],
            'credential': device.registration(options, **change)}, 'session-one')
    assert PasskeyCredential.select().count() == 0


@pytest.mark.parametrize('change', [dict(origin='https://attacker.test'), dict(rp='attacker.test'),
                                    dict(uv=False), dict(handle=b64(b'wrong user'))])
def test_authentication_rejects_origin_rp_uv_userhandle(ceremony, change):
    device = register(ceremony)
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': options['challenge_token'],
            'credential': device.assertion(options, **change)}, 'browser-one')


def test_zero_counters_valid_and_replayed_challenge_rejected(ceremony):
    device = register(ceremony)
    for _ in range(2):
        options = passkeys.begin_authentication(ceremony, 'browser-one')
        data = {'challenge_token': options['challenge_token'], 'credential': device.assertion(options)}
        assert passkeys.complete_authentication(data, 'browser-one')[0].user_id == ceremony.user_id
        with pytest.raises(passkeys.PasskeyError):
            passkeys.complete_authentication(data, 'browser-one')
    assert PasskeyCredential.get().sign_count == 0


@pytest.mark.parametrize('regression', [0, 1, 2])
def test_nonzero_counter_cannot_regress_or_repeat(ceremony, regression):
    device = register(ceremony)
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    passkeys.complete_authentication({'challenge_token': options['challenge_token'],
        'credential': device.assertion(options, count=2)}, 'browser-one')
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': options['challenge_token'],
            'credential': device.assertion(options, count=regression)}, 'browser-one')
    assert PasskeyCredential.get().sign_count == 2


def test_challenge_binding_expiry_epoch_and_purpose(ceremony):
    device = register(ceremony)
    for mutation in ('binding', 'expiry', 'epoch', 'purpose', 'challenge'):
        options = passkeys.begin_authentication(ceremony, 'browser-one')
        assertion = device.assertion(options)
        token = options['challenge_token']
        if mutation == 'expiry':
            AuthenticationChallenge.update(expires_at=security.now() - 1).where(AuthenticationChallenge.token_hash == security.digest(token)).execute()
        elif mutation == 'epoch':
            security.revoke_sessions(ceremony)
        elif mutation == 'challenge':
            other = passkeys.begin_authentication(ceremony, 'browser-one')
            assertion = device.assertion(other)
        with pytest.raises(passkeys.PasskeyError):
            passkeys.complete_authentication({'challenge_token': token, 'credential': assertion},
                'browser-two' if mutation == 'binding' else 'browser-one',
                purpose='passkeys.factor' if mutation == 'purpose' else 'passkeys.login')


def test_configuration_does_not_trust_host_headers(ceremony, app, monkeypatch):
    with app.test_request_context('/', headers={'Host': 'attacker.test', 'X-Forwarded-Host': 'attacker.test'}):
        assert passkeys.configuration() == ('roxy.example.test', [ORIGIN])
    for origins in (['http://roxy.example.test'], ['https://attacker.test'], ['https://roxy.example.test/'], []):
        monkeypatch.setitem(app.config, 'WEBAUTHN_ORIGINS', origins)
        with pytest.raises(passkeys.PasskeyError):
            passkeys.configuration()


def test_credential_cannot_authenticate_another_account(ceremony):
    device = register(ceremony)
    other = User.create(username='other', email='other@example.test', password=ceremony.password, enabled=1, role_id=1, group_id=1)
    other = security.capture_account(other.user_id)[0]
    register(other)
    options = passkeys.begin_authentication(other, 'browser-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': options['challenge_token'],
            'credential': device.assertion(options)}, 'browser-one')


@pytest.fixture
def passkey_http(app, product_client, monkeypatch):
    monkeypatch.setitem(app.config, 'WEBAUTHN_RP_ID', 'roxy.example.test')
    monkeypatch.setitem(app.config, 'WEBAUTHN_ORIGINS', [ORIGIN])
    product_client.environ_base['HTTP_ORIGIN'] = ORIGIN
    return product_client


def http_register(client, device=None):
    device = device or Authenticator()
    start = client.post('/security/passkeys/register/options', json={'password': PASSWORD})
    assert start.status_code == 200, start.json
    options = start.json
    result = client.post('/security/passkeys/register/finish', json={'challenge_token': options['challenge_token'],
        'name': 'Work laptop', 'credential': device.registration(options)})
    assert result.status_code == 200, result.json
    client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
    return device, result.json


def http_login(client, device):
    options = client.post('/security/passkeys/login/options', json={'login': 'admin'}).json
    result = client.post('/security/passkeys/login/finish', json={'challenge_token': options['challenge_token'],
        'credential': device.assertion(options), 'next': '/security/passkeys'})
    assert result.status_code == 200, result.json
    client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get_cookie('csrf_access_token').value
    return result


def test_web_api_password_fallback_blocked_and_passkey_login_works(passkey_http, product):
    device, result = http_register(passkey_http)
    assert len(result['recovery_codes']) == 10
    result = passkey_http.post('/login', json={'login': 'admin', 'pass': PASSWORD})
    assert result.status_code == 202 and result.json['methods'] == ['passkeys']
    result = passkey_http.post('/api/login', json={'login': 'admin', 'password': PASSWORD})
    assert result.status_code == 202 and 'access_token' not in result.json
    assert http_login(passkey_http, device).json['status'] == 'done'
    assert passkey_http.get('/security/passkeys').status_code == 200


def test_password_then_passkey_second_factor(passkey_http):
    device, _ = http_register(passkey_http)
    first = passkey_http.post('/login', json={'login': 'admin', 'pass': PASSWORD, 'next': '/security'}).json
    start = passkey_http.post('/security/passkeys/factor/options', json={'login_challenge': first['challenge']})
    assert start.status_code == 200, start.json
    proof = start.json
    complete = passkey_http.post('/auth/login/complete', json={'challenge': proof['login_challenge'],
        'passkey_challenge': proof['challenge_token'], 'credential': device.assertion(proof)})
    assert complete.status_code == 200, complete.json
    assert complete.json['next_url'].endswith('/security')
    assert passkey_http.post('/auth/login/complete', json={'challenge': proof['login_challenge'],
        'passkey_challenge': proof['challenge_token'], 'credential': device.assertion(proof)}).status_code == 401


def test_opaque_reauth_proof_user_session_purpose_and_single_use(passkey_http, product, app):
    device, _ = http_register(passkey_http)
    def proof():
        start = passkey_http.post('/security/passkeys/reauth/options', json={'purpose': 'personal_token.create'}).json
        result = passkey_http.post('/security/passkeys/reauth/finish', json={'purpose': 'personal_token.create',
            'challenge_token': start['challenge_token'], 'credential': device.assertion(start)})
        assert result.status_code == 200, result.json
        return result.json['reauth_token']
    token = proof()
    with app.test_request_context('/'), pytest.raises(RoxywiPublicError):
        security.require_sensitive_action(product.admin, {'reauth_token': token}, 'passkeys.remove')
    # A legitimate sensitive consumer executes under the same authenticated JWT session.
    response = passkey_http.post('/security/passkeys/register/options', json={'reauth_token': token})
    assert response.status_code == 400
    token = proof()
    with app.test_request_context('/'):
        assert security.consume_challenge(token, 'reauth:personal_token.create', binding='different-session') is None
    assert passkey_http.post('/auth/reauthenticate', json={'password': PASSWORD, 'purpose': 'personal_token.create'}).status_code == 400


def test_recovery_codes_one_use_and_console_reset(passkey_http, product):
    _device, setup = http_register(passkey_http)
    login = passkey_http.post('/login', json={'login': 'admin', 'pass': PASSWORD}).json
    result = passkey_http.post('/auth/login/complete', json={'challenge': login['challenge'], 'recovery_code': setup['recovery_codes'][0]})
    assert result.status_code == 200, result.json
    login = passkey_http.post('/login', json={'login': 'admin', 'pass': PASSWORD}).json
    assert passkey_http.post('/auth/login/complete', json={'challenge': login['challenge'], 'recovery_code': setup['recovery_codes'][0]}).status_code == 401
    before = security.user_epoch(product.admin.user_id)
    security.console_reset('admin', 'lost-device')
    assert not passkeys.has_factor(product.admin.user_id)
    assert security.user_epoch(product.admin.user_id) == before + 1
    assert passkey_http.get('/security/passkeys').status_code == 401


def test_management_requires_csrf_and_matching_origin(passkey_http):
    assert passkey_http.post('/security/passkeys/register/options', json={'password': PASSWORD}, headers={'X-CSRF-TOKEN': ''}).status_code == 401
    assert passkey_http.post('/security/passkeys/register/options', json={'password': PASSWORD}, headers={'Origin': 'https://attacker.test'}).status_code == 400


def test_user_deletion_cascades_credentials(ceremony):
    register(ceremony)
    ceremony.delete_instance()
    assert PasskeyCredential.select().count() == 0


def test_same_assertion_cannot_win_concurrently(ceremony, app, product):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    device = register(ceremony)
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    data = {'challenge_token': options['challenge_token'], 'credential': device.assertion(options)}
    barrier = Barrier(2)
    def attempt():
        with app.app_context(), product.db.connection_context():
            barrier.wait(timeout=5)
            try:
                return bool(passkeys.complete_authentication(data, 'browser-one'))
            except passkeys.PasskeyError:
                return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == [False, True]


def test_required_policy_enrollment_stays_restricted_until_verified(passkey_http, product):
    from app.modules.db.db_model import AuthenticationPolicy
    AuthenticationPolicy.get_or_create(id=1)
    AuthenticationPolicy.update(mode='all', grace_until=0).execute()
    assert passkey_http.get('/overview').status_code == 401
    login = passkey_http.post('/login', json={'login': 'admin', 'pass': PASSWORD, 'next': '/security/passkeys'})
    assert login.status_code == 202 and login.json['status'] == 'enrollment_required'
    assert passkey_http.post('/auth/login/complete', json={'challenge': login.json['challenge'], 'recovery_code': 'invalid'}).status_code == 401
    options = passkey_http.post('/security/passkeys/enrollment/options', json={'challenge': login.json['challenge']})
    assert options.status_code == 200, options.json
    device = Authenticator()
    result = passkey_http.post('/security/passkeys/enrollment/finish', json={'name': 'Required device',
        'challenge_token': options.json['challenge_token'], 'credential': device.registration(options.json)})
    assert result.status_code == 200, result.json
    assert len(result.json['recovery_codes']) == 10
    assert passkey_http.get('/security/passkeys').status_code == 200


def test_policy_prevents_removing_last_factor(passkey_http):
    from app.modules.db.db_model import AuthenticationPolicy
    device, _ = http_register(passkey_http)
    AuthenticationPolicy.get_or_create(id=1)
    AuthenticationPolicy.update(mode='all', grace_until=0).execute()
    start = passkey_http.post('/security/passkeys/reauth/options', json={'purpose': 'passkeys.remove'}).json
    proof = passkey_http.post('/security/passkeys/reauth/finish', json={'purpose': 'passkeys.remove',
        'challenge_token': start['challenge_token'], 'credential': device.assertion(start)}).json
    credential_hash = PasskeyCredential.get().credential_hash
    result = passkey_http.post('/security/passkeys/' + credential_hash + '/remove', json={'reauth_token': proof['reauth_token']})
    assert result.status_code == 400
    assert PasskeyCredential.select().count() == 1


def test_passkey_login_cannot_mint_post_reset_epoch(passkey_http, product, monkeypatch):
    from app.modules.roxywi import auth
    device, _ = http_register(passkey_http)
    original = auth.do_login
    def reset_before_mint(params, next_url):
        security.revoke_sessions(security.capture_account(product.admin.user_id)[0])
        return original(params, next_url)
    monkeypatch.setattr(auth, 'do_login', reset_before_mint)
    assert http_login(passkey_http, device).status_code == 200
    assert passkey_http.get('/security/passkeys').status_code == 401


def test_passkey_reauthentication_proof_consumed_once(passkey_http, product, app):
    from flask_jwt_extended import verify_jwt_in_request
    device, _ = http_register(passkey_http)
    start = passkey_http.post('/security/passkeys/reauth/options', json={'purpose': 'personal_token.create'}).json
    response = passkey_http.post('/security/passkeys/reauth/finish', json={'purpose': 'personal_token.create',
        'challenge_token': start['challenge_token'], 'credential': device.assertion(start)})
    token = response.json['reauth_token']
    cookie = passkey_http.get_cookie('access_token_cookie').value
    with app.test_request_context('/', headers={'Cookie': 'access_token_cookie=' + cookie}):
        verify_jwt_in_request(locations=['cookies'])
        security.require_sensitive_action(product.admin, {'reauth_token': token}, 'personal_token.create')
        with pytest.raises(RoxywiPublicError):
            security.require_sensitive_action(product.admin, {'reauth_token': token}, 'personal_token.create')


def test_passkey_migrations_idempotent(product):
    import importlib
    for name in ('20261029040000_local_authentication', '20261029060000_local_passkeys'):
        module = importlib.import_module('app.modules.db.migrations.' + name)
        module.up()
        module.up()
        with pytest.raises(RuntimeError):
            module.down()
    assert {'passkey_identities', 'passkey_credentials', 'authentication_challenges'} <= set(product.db.get_tables())


def test_failed_assertions_use_persistent_attempt_limit(ceremony):
    device = register(ceremony)
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    for _ in range(5):
        with pytest.raises(passkeys.PasskeyError):
            passkeys.complete_authentication({'challenge_token': options['challenge_token'],
                'credential': device.assertion(options, uv=False)}, 'browser-one')
    row = AuthenticationChallenge.get_by_id(security.digest(options['challenge_token']))
    assert row.attempts == 5
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': options['challenge_token'],
            'credential': device.assertion(options)}, 'browser-one')


def test_synced_backed_up_passkey_zero_counter_is_valid(ceremony):
    device = Authenticator()
    start = passkeys.begin_registration(ceremony, 'session-one')
    passkeys.complete_registration(ceremony, {'name': 'Synced device', 'challenge_token': start['challenge_token'],
        'credential': device.registration(start, backed_up=True)}, 'session-one')
    for _ in range(2):
        start = passkeys.begin_authentication(ceremony, 'browser-one')
        passkeys.complete_authentication({'challenge_token': start['challenge_token'],
            'credential': device.assertion(start, backed_up=True)}, 'browser-one')
    assert PasskeyCredential.get().sign_count == 0
    assert PasskeyCredential.get().device_type == 'multi_device'
    assert PasskeyCredential.get().backed_up is True


def test_invalid_assertion_signature_is_rejected(ceremony):
    device = register(ceremony)
    start = passkeys.begin_authentication(ceremony, 'browser-one')
    credential = device.assertion(start)
    credential['response']['signature'] = b64(b'not a valid signature')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': start['challenge_token'], 'credential': credential}, 'browser-one')


def test_registration_ceremony_user_session_replay_and_expiry(ceremony):
    device = Authenticator()
    start = passkeys.begin_registration(ceremony, 'session-one')
    data = {'name': 'Laptop', 'challenge_token': start['challenge_token'], 'credential': device.registration(start)}
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_registration(ceremony, data, 'session-two')
    passkeys.complete_registration(ceremony, data, 'session-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_registration(ceremony, data, 'session-one')
    start = passkeys.begin_registration(ceremony, 'session-one')
    AuthenticationChallenge.update(expires_at=security.now() - 1).where(AuthenticationChallenge.token_hash == security.digest(start['challenge_token'])).execute()
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_registration(ceremony, {'name': 'Expired', 'challenge_token': start['challenge_token'],
            'credential': Authenticator().registration(start)}, 'session-one')
    assert PasskeyCredential.select().count() == 1


def test_cross_origin_embedded_assertion_rejected(ceremony):
    device = register(ceremony)
    start = passkeys.begin_authentication(ceremony, 'browser-one')
    credential = device.assertion(start)
    client_data = json.loads(unb64(credential['response']['clientDataJSON']))
    client_data.update(crossOrigin=True, topOrigin='https://attacker.test')
    credential['response']['clientDataJSON'] = b64(json.dumps(client_data).encode())
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': start['challenge_token'], 'credential': credential}, 'browser-one')


def test_interactive_page_rejects_mixed_cookie_and_authorization(passkey_http):
    assert passkey_http.get('/security/passkeys', headers={'Authorization': 'Bearer irrelevant'}).status_code == 401


def test_invalid_rp_configuration_is_rejected(ceremony, app, monkeypatch):
    for rp_id in ('127.0.0.1', 'https://roxy.example.test', 'roxy.example.test:443', '*.example.test', 'bad..test'):
        monkeypatch.setitem(app.config, 'WEBAUTHN_RP_ID', rp_id)
        with pytest.raises(passkeys.PasskeyError):
            passkeys.configuration()


def test_direct_failure_audit_is_bounded_and_uses_safe_metadata(ceremony):
    from app.modules.db.db_model import AuthenticationEvent
    device = register(ceremony)
    options = passkeys.begin_authentication(ceremony, 'browser-one')
    for _ in range(8):
        with pytest.raises(passkeys.PasskeyError):
            passkeys.complete_authentication({'challenge_token': options['challenge_token'],
                'credential': device.assertion(options, uv=False)}, 'browser-one')
    events = list(AuthenticationEvent.select().where(AuthenticationEvent.event == 'authentication.passkey.login'))
    assert len(events) == 5
    assert all(event.outcome == 'denied' and event.user_id == ceremony.user_id for event in events)
    assert all(not any(value in str(event.__data__) for value in ('clientDataJSON', 'signature', 'Work laptop', options['challenge_token'])) for event in events)


def test_external_failure_audit_has_anonymous_actor_and_constant_reason(ceremony, monkeypatch):
    import sys
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    device = register(ceremony)
    events = []
    package = ModuleType('app.modules.audit')
    package.__spec__ = ModuleSpec(package.__name__, loader=None, is_package=True)
    adapter = ModuleType('app.modules.audit.events')
    adapter.__spec__ = ModuleSpec(adapter.__name__, loader=None)
    adapter.record = lambda *args, **kwargs: events.append((args, kwargs))
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    start = passkeys.begin_authentication(ceremony, 'browser-one')
    with pytest.raises(passkeys.PasskeyError):
        passkeys.complete_authentication({'challenge_token': start['challenge_token'],
            'credential': device.assertion(start, uv=False)}, 'browser-one')
    assert events == [(('authentication.passkey.login', 'denied'), {
        'user_id': None, 'group_id': 1, 'details': {'subject_id': str(ceremony.user_id), 'reason_code': 'invalid_assertion'}})]


def test_registration_cannot_rebind_proof_after_security_reset(passkey_http, product, monkeypatch):
    original = security.require_sensitive_action
    def reset_after_proof(user, data, purpose):
        original(user, data, purpose)
        security.revoke_sessions(user)
    monkeypatch.setattr(security, 'require_sensitive_action', reset_after_proof)
    response = passkey_http.post('/security/passkeys/register/options', json={'password': PASSWORD})
    assert response.status_code == 400
    assert not AuthenticationChallenge.select().where(AuthenticationChallenge.purpose == 'passkeys.register').exists()
    assert not passkeys.has_factor(product.admin.user_id)


def test_audit_export_outage_cannot_rollback_failed_attempt_gate(ceremony, monkeypatch):
    import sys
    from types import ModuleType
    from importlib.machinery import ModuleSpec
    from app.modules.db.db_model import UserSecurity, AuthenticationEvent
    device = register(ceremony)
    package = ModuleType('app.modules.audit')
    package.__spec__ = ModuleSpec(package.__name__, loader=None, is_package=True)
    adapter = ModuleType('app.modules.audit.events')
    adapter.__spec__ = ModuleSpec(adapter.__name__, loader=None)
    class AuditStorageUnavailable(Exception):
        pass
    adapter.AuditStorageUnavailable = AuditStorageUnavailable
    def unavailable(*_args, **_kwargs):
        raise AuditStorageUnavailable('Synthetic audit quota unavailable')
    adapter.record = unavailable
    monkeypatch.setitem(sys.modules, package.__name__, package)
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    start = passkeys.begin_authentication(ceremony, 'browser-one')
    for _ in range(7):
        with pytest.raises(passkeys.PasskeyError):
            passkeys.complete_authentication({'challenge_token': start['challenge_token'],
                'credential': device.assertion(start, uv=False)}, 'browser-one')
    challenge = AuthenticationChallenge.get_by_id(security.digest(start['challenge_token']))
    assert challenge.attempts == 5
    assert UserSecurity.get_by_id(ceremony.user_id).blocked_until > security.now()
    assert AuthenticationEvent.select().where(AuthenticationEvent.event == 'authentication.passkey.login').count() == 5


def test_deleted_account_cannot_inherit_legacy_or_modern_session(ceremony):
    user_id = ceremony.user_id
    legacy = {'user_id': str(user_id), 'group': '1'}
    modern = dict(legacy, **security.login_proof(ceremony, 'password', expected=security.capture_account(ceremony.user_id)[1]))
    assert security.validate_session(legacy)
    old_account_id = modern['auth_account']
    ceremony.delete_instance()
    replacement = User.create(user_id=user_id, username='replacement', email='replacement@example.test',
        password=ceremony.password, group_id='1', role_id='1', enabled=1)
    assert security.user_account_id(user_id) != old_account_id
    assert not security.validate_session(legacy)
    assert not security.validate_session(modern)
    security.initialize_baseline()
    assert not security.validate_session(legacy)
    fresh = dict(legacy, **security.login_proof(replacement, 'password', expected=security.capture_account(replacement.user_id)[1]))
    assert security.validate_session(fresh)


def test_new_directory_account_keeps_provider_owned_authentication(app, product, monkeypatch):
    from flask_jwt_extended import decode_token
    from app.modules.db.db_model import UserGroups, AuthenticationPolicy
    from app.modules.roxywi import auth
    account = User.create(username='directoryuser', email='directory@example.test', password=None,
        role_id='3', group_id='1', ldap_user=1, enabled=1)
    UserGroups.create(user_id=account.user_id, user_group_id=1, user_role_id=3)
    monkeypatch.setattr(auth, 'check_in_ldap', lambda username, password: True)
    AuthenticationPolicy.update(mode='all', grace_until=0).execute()
    client = app.test_client()
    response = client.post('/login', json={'login': account.username, 'pass': 'DirectoryPassword!'})
    assert response.status_code == 200
    assert client.get('/api/swagger').status_code == 200
    with app.app_context():
        claims = decode_token(client.get_cookie('access_token_cookie').value)
    assert claims['auth_method'] == 'ldap'
    assert claims['auth_account'] == security.user_account_id(account.user_id)
    assert not security.state(account).legacy_allowed


def test_legacy_password_rehash_cannot_undo_administrator_reset(app, product, monkeypatch):
    from app.modules.roxy_wi_tools import Tools
    User.update(password=LEGACY_DATABASE_HASH).where(User.user_id == product.admin.user_id).execute()
    replacement = Tools.get_hash('AdministratorResetPassword!')
    original = Tools.check_password
    def reset_after_verification(password, stored):
        result = original(password, stored)
        assert result == (True, True)
        User.update(password=replacement).where(User.user_id == product.admin.user_id).execute()
        return result
    monkeypatch.setattr(Tools, 'check_password', reset_after_verification)
    client = app.test_client()
    response = client.post('/login', json={'login': 'admin', 'pass': LEGACY_PASSWORD})
    assert response.status_code == 401
    assert User.get_by_id(product.admin.user_id).password == replacement
    assert client.get_cookie('access_token_cookie') is None


def test_upgrade_from_existing_schema_initializes_legacy_eligibility_once(app, product):
    from app import initialize_database
    from app.modules.db.db_model import (PasskeyIdentity, RecoveryCode, UserSecurity,
        AuthenticationEvent, AuthenticationPolicy)
    from app.modules.db.migration_manager import Migration
    from app.modules.roxy_wi_tools import Tools
    existing = User.create(username='existinguser', email='existing@example.test', password=Tools.get_hash(PASSWORD),
        role_id='3', group_id='1', ldap_user=0, enabled=1)
    product.db.drop_tables([PasskeyCredential, PasskeyIdentity, AuthenticationChallenge,
        RecoveryCode, UserSecurity, AuthenticationEvent, AuthenticationPolicy])
    Migration.delete().where(Migration.name.in_([
        '20261029040000_local_authentication', '20261029060000_local_passkeys'])).execute()
    initialize_database()
    for account in (product.admin, existing):
        row = UserSecurity.get_by_id(account.user_id)
        assert row.legacy_allowed and len(row.account_id) == 32
        assert security.validate_session({'user_id': str(account.user_id), 'group': '1'})
    assert AuthenticationPolicy.get_by_id(1).baseline_initialized
    assert PasskeyCredential.select().count() == 0
    initialize_database()
    assert UserSecurity.select().count() == User.select().count()


def test_public_password_version_is_keyed_and_independent_of_fernet(product, app, monkeypatch):
    from cryptography.fernet import Fernet
    legacy_hash = LEGACY_DATABASE_HASH
    User.update(password=legacy_hash).where(User.user_id == product.admin.user_id).execute()
    account = User.get_by_id(product.admin.user_id)
    version = security.password_version(account)
    assert version != hashlib.sha256(legacy_hash.encode()).hexdigest()
    monkeypatch.setenv('ROXYWI_SECRET_PHRASE', Fernet.generate_key().decode())
    assert security.password_version(account) == version
    monkeypatch.setitem(app.config, 'SECRET_KEY', 'another-stable-application-key-for-test-only')
    assert security.password_version(account) != version


@pytest.mark.parametrize('application_key', ['stable-application-key-for-test-only', b'bytes-application-key-for-test-only'])
@pytest.mark.parametrize('stored_hash', [None, LEGACY_DATABASE_HASH, 'scrypt:32768:8:1$salt$stored-hash'])
def test_password_version_preserves_existing_hmac_claims(product, app, monkeypatch, application_key, stored_hash):
    import hmac
    monkeypatch.setitem(app.config, 'SECRET_KEY', application_key)
    product.admin.password = stored_hash
    key = application_key.encode() if isinstance(application_key, str) else application_key
    material = b'roxywi.local-auth.password-version.v1\x00' + (stored_hash or '').encode()
    expected = hmac.new(key, material, 'sha256').hexdigest()
    assert security.password_version(product.admin) == expected
    product.admin.password = (stored_hash or '') + '-changed'
    assert security.password_version(product.admin) != expected
