"""Canonical MAC provider preserves existing credential state, not password hashes."""
from datetime import timedelta
from importlib import import_module, util
from types import SimpleNamespace
from uuid import uuid4
import hashlib
import json
import secrets

import pytest
from flask_jwt_extended import create_access_token

from app.modules.common.time import utc_now
from app.modules.db import db_model as m, user as user_sql
from app.modules.roxy_wi_tools import Tools
from tests.product import conftest as product_fixtures

pytestmark = pytest.mark.security
HAS_AUTH = util.find_spec('app.modules.authentication') is not None
HAS_PAT = util.find_spec('app.modules.api_tokens') is not None
LEGACY_TEXT = 'LegacyVerifiedPassword!'
KEYS = ('compatibility-key-text-0123456789abcdef',
 b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17'
 b'\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !"#$%&\'()*+,-./0123456789:;<=>?',
 'příliš-žluťoučký-application-key-0123456789')
STORED_VALUES = (None,
 'e1846d46d83f9c9fb336fc834f407925',
 'scrypt:32768:8:1$fixture$0123456789abcdef',
 'pbkdf2:sha256:1000000$fixture$0123456789abcdef',
 'E1846D46D83F9C9FB336FC834F407925',
 'stored-☃-hash')
# Frozen outputs from the previous stdlib HMAC-SHA256 v1 implementation.
# These synthetic vectors cover short/block/long UTF8 keys and stored verifier forms.
GOLDENS = {'local': (('ce8d332f77ed51039ef504ce116897cc87f8934866de4048fcbc83fb739ba76c',
            '421205e4a20bb75be6a3e3e3967a13c2d239209d720fe1a5751e8f8e8e7b9d20',
            '077877c100355cc88a33bc4e54f78cc94b50c09b9a16c6b881d4631a1f3762a2',
            '5598b049f6e38abbf4ab2bfb48338afa0d450e392d0591dd14096b99a645b1d9',
            'd26d174b8203ca0a45b80c2257c5509d30ba63b40c0209f10716a48a8ffa6d70',
            '11a2826e84940addd00bd96ab85022389bdfc5bf0e2492ca8e19bf842566c02e'),
           ('e98b802c4ac7c56cdfe7b24fe3c7c821a1f35d9a0beeb065740f8b8070c79084',
            '5bc6d1975d7de1930201533ea58cec7dd0e18fe746b7f7c6bbe46e46195be06f',
            'cdaa79484a4ace5b4e772e7752e94ce1e61abeef83d1467e3065c50e8d662bfd',
            '692fafbcf219ecf393017bd45e1fb6df359ac636b728f5563ef341ecf0a79d69',
            '1874be1f4751460c28c3cb95baefe923de89f56cabac8bac2a535b3f99d716eb',
            '1b3a7e663aa99af17ff00de05101953869a99c2eebb0552f850859f18b111a59'),
           ('c5cb296194e7e77ec7286a49f5fe52cd54157543f09b52d807d408dfa56eac26',
            '9414b71b4a2d86b90ad2b8fb6a30170d57bbc4493c8ff40b98cf6a3b191b0b20',
            'd65ca3682a6b0b2ee5c7bb9a5058e6262b38c45ba5817915b752f8986a7dd3f3',
            '48d970bc161fa2a31d4b4c83c2e04af0f300a154456cee7f64a4679bdf91bb60',
            '9249dd11ea172ee02dcb98a2c204e4e94ea5b6b64b785275de7aef0329bafad5',
            '629d3fbd71e438ee1770ed6a478f44a689d2db587f243396bded553ee775a753')),
 'personal': (('397507bf394c7205f025187171ebbcbaeb8b364299e127c8c7dd6e7b248b1ae1',
               '580a1c752d61a1b38e2214f0a1fef9294161bc05a4aef5b26ba87578764b3cd8',
               '1bda2ce320959683689aa1f093767fe26025b2902862d84f0cf954bdaf231fe0',
               '201d1a79b4b27961680588c1050d124172d7fb30869c4516f2319fad6d6c8e00',
               'c1613c2660face97290fa53736ee09c411926488b0a5c87fc8aa1d9050023800',
               'c33c6a160f996e990b9a89af06255b12db53ee394dd7a11e5f59d188f30e1559'),
              ('c346c4166a9fbd5b76862c2d8f97e3ce191c62dd0dbe79579c7b77da39bbc24d',
               '1610e369cf67c485db9320d56264b2c4b65bb5fc0a3302676026228987229109',
               '3808975435bbfae534a655159efe5b55e936d5e5f49a5de5d3c18e0fe1fac2b0',
               '598267c8d03fc16913a2ce28b9e53cc1891656188fce344bc6677c8963ae3f61',
               'b66642528ee6f80f4d8daa0a2c1d53668576f908fd5cbba04099cd345b6f3aff',
               'bb66587e1a6decf40a69bcaacf47fcad734ee0fed2c54381a301fe9bcd668122'),
              ('c28976ec9f119eb4fb05681583914a59a4f8fdf602dcb68438758ab24569ba41',
               '8242faa2b4d938913053bd834833c7541821f48fb8017ebbed7f46d394220e82',
               'd3754796c2aa4c4065851062097b89e47401ba52a0b02d75bd284b75b57acde1',
               'f474ca7a4465267afd39235ec18ee031e8b45364f00ec7ae6b64b1b16895a2c7',
               '3ff4da28b67b23761420b0fdab4e9d8b476d4394aee5bd8f13ff40833f96a8df',
               'd6d36bdb3e623ff0ef8b3fee0848a4cb11aa38acb1abaa38b231f0e861724a3e'))}
RAW_SHA256_FIXTURE = 'a160dffdaaa04269971e42e76bdc15e8e74ed4839599b2e6f0cbae18f7d5dcbf'

def version_provider(kind):
    if kind == 'local':
        if not HAS_AUTH:
            pytest.skip('Optional local authentication provider is not installed')
        return import_module('app.modules.authentication.security')
    if not HAS_PAT:
        pytest.skip('Optional personal token provider is not installed')
    return import_module('app.modules.api_tokens.service')


@pytest.mark.parametrize('kind', ['local', 'personal'])
@pytest.mark.parametrize('key_index', range(3))
@pytest.mark.parametrize('stored_index', range(6))
def test_v1_stdlib_golden_mac_is_preserved(app, monkeypatch, kind, key_index, stored_index):
    monkeypatch.setitem(app.config, 'SECRET_KEY', KEYS[key_index])
    actual = version_provider(kind).password_version(SimpleNamespace(password=STORED_VALUES[stored_index]))
    assert actual == GOLDENS[kind][key_index][stored_index]
    assert len(actual) == 64 and actual == actual.lower()


@pytest.fixture(scope='session')
def mac_bootstrap_credentials():
    return product_fixtures.product_bootstrap_credentials.__wrapped__()


@pytest.fixture
def mac_account(app, tmp_path, monkeypatch, mac_bootstrap_credentials):
    # Reuse the real isolated product DB without changing global fixture scope.
    monkeypatch.setitem(app.config, 'SECRET_KEY', KEYS[0])
    yield from product_fixtures.product.__wrapped__(app, tmp_path, monkeypatch, mac_bootstrap_credentials)


@pytest.mark.skipif(not HAS_AUTH, reason='Optional local authentication provider is not installed')
@pytest.mark.parametrize('mutation', ['unchanged', 'password', 'epoch', 'replacement', 'disabled', 'missing_state'])
def test_old_stdlib_mac_claims_still_require_the_original_live_account(app, mac_account, mutation):
    security = version_provider('local')
    user_id = mac_account.admin.user_id
    m.User.update(password=STORED_VALUES[1]).where(m.User.user_id == user_id).execute()
    current, captured = security.capture_account(user_id)
    old_claims = dict(user_id=str(user_id), group='1', auth_method='password', auth_time=security.now(),
        auth_epoch=captured['auth_epoch'], auth_account=captured['auth_account'],
        credential_version=GOLDENS['local'][0][1])
    assert security.validate_session(old_claims)
    with app.app_context():
        bearer = create_access_token(str(user_id), additional_claims=old_claims)
    if mutation == 'password':
        m.User.update(password=Tools.get_hash('AdministratorResetPassword!')).where(m.User.user_id == user_id).execute()
    elif mutation == 'epoch':
        m.UserSecurity.update(epoch=m.UserSecurity.epoch+1).where(m.UserSecurity.user_id == user_id).execute()
    elif mutation == 'replacement':
        fields = {key: getattr(current, key) for key in ('user_id', 'username', 'email', 'password',
                  'role_id', 'group_id', 'ldap_user', 'enabled')}
        user_sql.delete_user(user_id)
        m.User.create(**fields)
        _, replacement = security.capture_account(user_id)
        assert replacement['auth_account'] != captured['auth_account']
    elif mutation == 'disabled':
        m.User.update(enabled=0).where(m.User.user_id == user_id).execute()
    elif mutation == 'missing_state':
        m.UserSecurity.delete().where(m.UserSecurity.user_id == user_id).execute()
    assert security.validate_session(old_claims) == (mutation == 'unchanged')
    response = app.test_client().get('/api/servers', headers={'Authorization': 'Bearer '+bearer,
                                                            'Accept': 'application/json'})
    if mutation == 'unchanged':
        assert response.status_code == 200, response.text
        assert {row['server_id'] for row in response.json} == {mac_account.server.server_id}
    else:
        assert response.status_code in {401, 422}, response.text
    if mutation == 'missing_state':
        assert not m.UserSecurity.select().where(m.UserSecurity.user_id == user_id).exists()


@pytest.mark.skipif(not HAS_PAT, reason='Optional personal token provider is not installed')
def test_existing_pat_stdlib_marker_is_accepted_and_live_revocation_is_enforced(app, mac_account):
    user_id = mac_account.admin.user_id
    m.User.update(password=STORED_VALUES[1]).where(m.User.user_id == user_id).execute()
    epoch = version_provider('local').user_epoch(user_id) if HAS_AUTH else 0
    token_id, stamp = str(uuid4()), utc_now()
    with app.app_context():
        bearer = create_access_token(str(user_id), expires_delta=timedelta(days=90), additional_claims={
            'credential_type': 'pat', 'group': '1', 'pat_id': token_id, 'nonce': secrets.token_urlsafe(32)})
    row = m.PersonalAccessToken.create(id=token_id, user_id=user_id, group_id=1, name='Existing integration',
        token_digest=hashlib.sha256(bearer.encode()).hexdigest(), password_version=GOLDENS['personal'][0][1],
        security_version=epoch, scopes=json.dumps(['inventory.read']), created_at=stamp,
        expires_at=stamp+timedelta(days=90))
    client = app.test_client()
    headers = {'Authorization': 'Bearer '+bearer, 'Accept': 'application/json'}
    assert client.get('/api/servers', headers=headers).status_code == 200
    m.PersonalAccessToken.update(revoked_at=utc_now()).where(m.PersonalAccessToken.id == row.id).execute()
    assert client.get('/api/servers', headers=headers).status_code in {401, 422}


def test_password_storage_and_verification_do_not_accept_mac_or_raw_digest(app):
    encoded = Tools.get_hash(LEGACY_TEXT)
    assert encoded.startswith('scrypt:')
    assert Tools.check_password(LEGACY_TEXT, encoded) == (True, False)
    assert Tools.check_password(LEGACY_TEXT, STORED_VALUES[1]) == (True, True)
    assert Tools.check_password(LEGACY_TEXT, GOLDENS['local'][0][1]) == (False, False)
    assert Tools.check_password(LEGACY_TEXT, RAW_SHA256_FIXTURE) == (False, False)
