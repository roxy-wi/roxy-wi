"""An authentication approval stays bound to one captured account incarnation."""
import pytest
from app.modules.authentication import security
from app.modules.db.db_model import AuthenticationChallenge, User, UserSecurity
from app.modules.db import user as user_sql
from app.modules.roxy_wi_tools import Tools
from app.modules.roxywi.exception import RoxywiPublicError


def replacement(account):
    fields = {key: getattr(account, key) for key in (
        'user_id', 'username', 'email', 'password', 'role_id', 'group_id', 'ldap_user', 'enabled')}
    user_sql.delete_user(account.user_id)
    return User.create(**fields)


def test_raw_or_captured_stale_user_cannot_mint_replacement_proof(product):
    raw = product.admin
    captured, expected = security.capture_account(raw.user_id)
    new = replacement(raw)
    assert security.user_account_id(new.user_id) != expected['auth_account']
    for old, snapshot in ((raw, None), (captured, None), (captured, expected)):
        with pytest.raises(RoxywiPublicError):
            security.login_proof(old, 'oidc', expected=snapshot)
    fresh, current = security.capture_account(new.user_id)
    proof = security.login_proof(fresh, 'password', expected=current)
    assert security.validate_session(dict(user_id=new.user_id, group='1', **proof))


def test_proof_uses_one_snapshot_instead_of_separate_epoch_and_nonce_reads(product, monkeypatch):
    user, expected = security.capture_account(product.admin.user_id)
    def forbidden(*_args):
        pytest.fail('A verified proof must not combine independent identity reads')
    monkeypatch.setattr(security, 'user_epoch', forbidden)
    monkeypatch.setattr(security, 'user_account_id', forbidden)
    proof = security.login_proof(user, 'oidc', expected=expected)
    assert proof['auth_epoch'] == expected['auth_epoch']
    assert proof['auth_account'] == expected['auth_account']
    assert proof['credential_version'] == expected['credential_version']


def test_missing_parent_is_safe_denial_without_security_state_recreation(product):
    user, expected = security.capture_account(product.admin.user_id)
    user_sql.delete_user(user.user_id)
    for operation in (lambda: security.state(user), lambda: security.user_epoch(user.user_id),
                      lambda: security.user_account_id(user.user_id), lambda: security.login_proof(user, 'oidc')):
        with pytest.raises(RoxywiPublicError):
            operation()
    assert not security.validate_session(dict(user_id=user.user_id, group='1', **expected))
    assert not UserSecurity.select().where(UserSecurity.user_id == user.user_id).exists()


def test_old_cookie_cannot_reauthenticate_replacement_after_jwt_validation(product_client, product, monkeypatch):
    original = security.session_user
    changed = []
    def replace_before_actor_binding(claims):
        if not changed:
            changed.append(True)
            replacement(User.get_by_id(product.admin.user_id))
        return original(claims)
    monkeypatch.setattr(security, 'session_user', replace_before_actor_binding)
    response = product_client.post('/auth/reauthenticate', json={
        'purpose': 'personal_token.create', 'password': 'TestBootstrapPassword!'})
    assert response.status_code == 400
    assert 'reauth_token' not in response.get_json()
    assert changed
    assert not AuthenticationChallenge.select().exists()


def test_password_or_reset_change_after_snapshot_cannot_be_adopted(product):
    user, expected = security.capture_account(product.admin.user_id)
    User.update(password=Tools.get_hash('NewAdministratorPassword!')).where(User.user_id == user.user_id).execute()
    with pytest.raises(RoxywiPublicError):
        security.login_proof(user, 'password', expected=expected)
    user, expected = security.capture_account(product.admin.user_id)
    security.console_reset(user.username, 'compromise')
    with pytest.raises(RoxywiPublicError):
        security.login_proof(user, 'oidc', expected=expected)
