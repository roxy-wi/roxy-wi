"""Verify-only legacy compatibility; every new stored password remains scrypt."""
import json
import os
import subprocess
import sys

import pytest

from app.modules import roxy_wi_tools
from app.modules.db.db_model import User
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiPublicError
from tests.product.conftest import product as product
from tests.product.conftest import product_bootstrap_credentials as product_bootstrap_credentials

LEGACY_PASSWORD = 'LegacyVerifiedPassword!'
LEGACY_HASH = 'e1846d46d83f9c9fb336fc834f407925'
# Precomputed database-format vectors, never new password storage algorithms.
VECTORS = [
    ('normal', LEGACY_PASSWORD, LEGACY_HASH),
    ('empty', '', 'd41d8cd98f00b204e9800998ecf8427e'),
    ('unicode', 'pässwörd😀', 'eea449faace578581131b87707d5de93'),
    ('composed', '\u00e9', '66ddcd97cfdeabb2f6fb8a999b4bc76f'),
    ('decomposed', 'e\u0301', '5526861fbb1e71a1bda6ac364310a807'),
    ('nul', 'a\x00b', '70350f6027bce3713f6b76473084309b'),
    ('long-boundary', 'x' * 4097, '88751dd296563726278c2d57ab7549e4'),
    ('long-ascii', 'x' * 5000, 'a6bb7bde3251ca2d810d32dadd9e8ae7'),
    ('long-multibyte', 'ž' * 5000, 'b2142429fdd1bfb7d75ce550dd5a04d9'),
]


@pytest.mark.parametrize('_name,password,stored', VECTORS, ids=[row[0] for row in VECTORS])
def test_legacy_vectors_verify_and_mark_migration(_name, password, stored):
    assert Tools.check_password(password, stored) == (True, True)
    assert Tools.check_password(password, stored.upper()) == (True, True)
    wrong = 'Y' + password[1:] if password else 'X'
    assert Tools.check_password(wrong, stored) == (False, True)


def test_legacy_verification_does_not_normalize_unicode():
    assert Tools.check_password('\u00e9', '5526861fbb1e71a1bda6ac364310a807') == (False, True)


@pytest.mark.parametrize('password,stored', [
    (None, LEGACY_HASH), (123, LEGACY_HASH), (b'bytes', LEGACY_HASH),
    (LEGACY_PASSWORD, None), (LEGACY_PASSWORD, b'bytes'), (LEGACY_PASSWORD, 123),
    (LEGACY_PASSWORD, ''), (LEGACY_PASSWORD, 'not-a-password-hash'),
    (LEGACY_PASSWORD, 'g' * 32), (LEGACY_PASSWORD, 'a' * 31), (LEGACY_PASSWORD, 'a' * 33),
])
def test_bad_types_and_malformed_formats_deny_without_exception(password, stored):
    assert Tools.check_password(password, stored) == (False, False)


def test_no_legacy_hash_generation_and_modern_storage_does_not_load_provider(monkeypatch):
    provider = roxy_wi_tools._legacy_password_verifier()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Legacy hash generation is forbidden')
    monkeypatch.setattr(provider, 'hash', forbidden)
    assert Tools.check_password(LEGACY_PASSWORD, LEGACY_HASH) == (True, True)
    monkeypatch.setattr(roxy_wi_tools, '_legacy_password_verifier', forbidden)
    stored = Tools.get_hash(LEGACY_PASSWORD)
    assert stored.startswith('scrypt:')
    assert Tools.check_password(LEGACY_PASSWORD, stored) == (True, False)
    assert Tools.check_password('Incorrect synthetic password!', stored) == (False, False)


def child(source, **changes):
    environment = dict(os.environ, ROXYWI_PROCESS_ROLE='migrate')
    for key in ('PASSLIB_MAX_PASSWORD_SIZE', 'ROXYWI_MAIN_MAX_CONTENT_LENGTH', 'ROXYWI_MAX_CONTENT_LENGTH'):
        environment.pop(key, None)
    environment.update(changes)
    result = subprocess.run([sys.executable, '-c', source], env=environment,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('setting', ['default', 'ROXYWI_MAIN_MAX_CONTENT_LENGTH', 'ROXYWI_MAX_CONTENT_LENGTH'])
def test_first_lazy_import_uses_existing_body_bound_and_preserves_long_passwords(setting):
    changes = {} if setting == 'default' else {setting: '12000'}
    result = child('''import json,sys,os
from app.modules.roxy_wi_tools import Tools
assert 'passlib' not in sys.modules
assert Tools.check_password('x'*4097,'88751dd296563726278c2d57ab7549e4')==(True,True)
assert Tools.check_password('x'*5000,'a6bb7bde3251ca2d810d32dadd9e8ae7')==(True,True)
assert Tools.check_password('ž'*5000,'b2142429fdd1bfb7d75ce550dd5a04d9')==(True,True)
assert Tools.check_password('Y'+'ž'*4999,'b2142429fdd1bfb7d75ce550dd5a04d9')==(False,True)
from passlib.utils import MAX_PASSWORD_SIZE
print(json.dumps({'configured':os.environ['PASSLIB_MAX_PASSWORD_SIZE'],'active':MAX_PASSWORD_SIZE}))
''', **changes)
    expected = 16 * 1024 * 1024 if setting == 'default' else 12000
    assert result == {'configured': str(expected), 'active': expected}


def test_explicit_operator_bound_is_honored_and_oversize_denies():
    result = child('''import json
from app.modules.roxy_wi_tools import Tools
from app.modules import roxy_wi_tools
assert Tools.check_password('x'*4097,'88751dd296563726278c2d57ab7549e4')==(False,True)
from passlib.utils import MAX_PASSWORD_SIZE
print(json.dumps({'active':MAX_PASSWORD_SIZE}))
''', PASSLIB_MAX_PASSWORD_SIZE='128', ROXYWI_MAX_CONTENT_LENGTH='12000')
    assert result['active'] == 128


def test_disabled_backend_fails_closed_without_backend_bypass():
    result = child('''import json,hashlib,sys
from app.modules.roxy_wi_tools import Tools
assert 'passlib' not in sys.modules
def blocked(*args,**kwargs):
    assert 'usedforsecurity' not in kwargs
    raise ValueError('disabled for fips')
hashlib.md5=blocked
assert Tools.check_password('LegacyVerifiedPassword!','e1846d46d83f9c9fb336fc834f407925')==(False,True)
stored=Tools.get_hash('NewModernSyntheticPassword!')
assert stored.startswith('scrypt:')
assert Tools.check_password('NewModernSyntheticPassword!',stored)==(True,False)
print(json.dumps({'denied':True,'modern':True}))
''')
    assert result == {'denied': True, 'modern': True}


def test_preimported_provider_does_not_mutate_private_library_limits():
    # A process that imports libpass before the application owns its original
    # limit. The adapter never rewrites a private global to evade that policy.
    result = child('''import json
from passlib.hash import hex_md5
from passlib.utils import MAX_PASSWORD_SIZE
from app.modules.roxy_wi_tools import Tools
assert Tools.check_password('x'*4097,'88751dd296563726278c2d57ab7549e4')==(False,True)
print(json.dumps({'active':MAX_PASSWORD_SIZE}))
''')
    assert result['active'] == 4096


@pytest.mark.parametrize('password,stored', [
    (LEGACY_PASSWORD, LEGACY_HASH),
    ('x' * 5000, 'a6bb7bde3251ca2d810d32dadd9e8ae7'),
    ('ž' * 5000, 'b2142429fdd1bfb7d75ce550dd5a04d9'),
], ids=['normal', 'long-ascii', 'long-multibyte'])
def test_successful_legacy_login_still_performs_real_scrypt_cas_upgrade(app, product, password, stored):
    User.update(password=stored.upper()).where(User.user_id == product.admin.user_id).execute()
    with app.test_request_context('/login'):
        result = auth.check_user_password('admin', password)
    current = User.get_by_id(product.admin.user_id)
    assert result['user'] == product.admin.user_id
    assert current.password.startswith('scrypt:')
    assert Tools.check_password(password, current.password) == (True, False)


def test_verified_legacy_password_cannot_overwrite_a_concurrent_reset(app, product, monkeypatch):
    User.update(password=LEGACY_HASH).where(User.user_id == product.admin.user_id).execute()
    replacement = Tools.get_hash('AdministratorResetPassword!')
    original = Tools.check_password
    def reset_after_verification(password, stored):
        result = original(password, stored)
        assert result == (True, True)
        User.update(password=replacement).where(User.user_id == product.admin.user_id).execute()
        return result
    monkeypatch.setattr(Tools, 'check_password', reset_after_verification)
    with app.test_request_context('/login'), pytest.raises(RoxywiPublicError):
        auth.check_user_password('admin', LEGACY_PASSWORD)
    assert User.get_by_id(product.admin.user_id).password == replacement
