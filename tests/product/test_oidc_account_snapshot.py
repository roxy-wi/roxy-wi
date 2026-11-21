"""Independent account-incarnation review regressions; no external IdP required.

Run from an MFA checkout with PYTHONPATH=. and the isolated pytest environment.
Only the paid subscription lookup is replaced; mapping, cookie creation and JWT
verification use production code and a fresh product database.
"""
import pytest
from flask_jwt_extended import decode_token

from app.modules.authentication import security
from app.modules.db.db_model import AuthenticationPolicy, User
from app.modules.db import user as user_sql
from app.modules.oidc import login
from app.modules.oidc.errors import OidcLoginError
from app.modules.roxywi import auth
from app.modules.roxywi.exception import RoxywiPublicError
from tests.security.test_oidc import make_provider



def mapped_login(product, monkeypatch):
    monkeypatch.setattr(login, 'require_feature', lambda *_args: None)
    provider = make_provider(auto_link_by_email=1, sync_group_memberships=0)
    return login.complete_oidc_login(provider, {
        'sub': 'synthetic-review-subject', 'email': product.admin.email,
        'email_verified': True, 'preferred_username': product.admin.username,
    })


def redirect_claims(app, params):
    with app.test_request_context('/oidc/callback'):
        response = auth.build_login_redirect(params, '/admin')
        cookie = next(value for value in response.headers.getlist('Set-Cookie')
                      if value.startswith('access_token_cookie='))
        return decode_token(cookie.split(';', 1)[0].split('=', 1)[1])


@pytest.mark.parametrize('replacement', [False, True])
def test_completed_oidc_mapping_cannot_authenticate_deleted_or_reused_account(
        app, product, monkeypatch, replacement):
    old = product.admin
    old_account = security.user_account_id(old.user_id)
    params = mapped_login(product, monkeypatch)
    fields = {key: getattr(old, key) for key in (
        'user_id', 'username', 'email', 'password', 'role_id', 'group_id',
        'ldap_user', 'enabled')}
    user_sql.delete_user(old.user_id)
    if replacement:
        new = User.create(**fields)
        assert security.user_account_id(new.user_id) != old_account
    try:
        claims = redirect_claims(app, params)
    except RoxywiPublicError:
        return  # Controlled denial is also acceptable; storage exceptions are not.
    assert not security.validate_session(claims)


def test_oidc_proof_preserves_provider_ownership_and_selected_group(app, product, monkeypatch):
    AuthenticationPolicy.update(mode='all', grace_until=0).execute()
    params = mapped_login(product, monkeypatch)
    claims = redirect_claims(app, params)
    assert claims['auth_method'] == 'oidc'
    assert claims['group'] == str(product.admin.group_id)
    assert claims['auth_account'] == security.user_account_id(product.admin.user_id)
    assert security.validate_session(claims)


def test_existing_oidc_mapping_is_rechecked_after_parent_lock(app, product, monkeypatch):
    mapped_login(product, monkeypatch)
    provider = login.OidcIdentity.get(login.OidcIdentity.subject == 'synthetic-review-subject').provider_id
    from app.modules.db.db_model import OidcProvider
    provider = OidcProvider.get_by_id(provider)
    original = login._locked_user
    replaced = []

    def replace_before_parent_lock(user_id):
        if not replaced:
            replaced.append(True)
            old = User.get_by_id(user_id)
            fields = {key: getattr(old, key) for key in (
                'user_id', 'username', 'email', 'password', 'role_id', 'group_id',
                'ldap_user', 'enabled')}
            user_sql.delete_user(user_id)
            User.create(**fields)
        return original(user_id)

    monkeypatch.setattr(login, '_locked_user', replace_before_parent_lock)
    with pytest.raises(OidcLoginError, match='mapping changed'):
        login.complete_oidc_login(provider, {
            'sub': 'synthetic-review-subject', 'email': product.admin.email,
            'email_verified': True, 'preferred_username': product.admin.username,
        })
    assert replaced


def test_email_link_rechecks_current_parent_email(app, product, monkeypatch):
    original = login._locked_user
    changed = []

    def change_before_parent_lock(user_id):
        if not changed:
            changed.append(True)
            User.update(email='changed@example.test').where(User.user_id == user_id).execute()
        return original(user_id)

    monkeypatch.setattr(login, '_locked_user', change_before_parent_lock)
    with pytest.raises(OidcLoginError, match='mapping changed'):
        mapped_login(product, monkeypatch)
    assert changed


@pytest.mark.parametrize('replacement', [False, True])
def test_oidc_callback_denies_account_change_without_server_error(
        app, product, client, monkeypatch, replacement):
    from app.routes.oidc import routes as oidc_routes
    provider = make_provider(userinfo_endpoint=None, sync_group_memberships=0)

    class FakeOAuthSession:
        def __init__(self, **_kwargs):
            pass

        @staticmethod
        def fetch_token(*_args, **_kwargs):
            return {'id_token': 'synthetic-signed-token', 'access_token': 'synthetic-access-token'}

    monkeypatch.setattr(oidc_routes, 'OAuth2Session', FakeOAuthSession)
    monkeypatch.setattr(oidc_routes, '_validate_id_token', lambda *_a, **_k: {
        'sub': 'synthetic-callback-subject', 'email': product.admin.email,
        'email_verified': True, 'preferred_username': product.admin.username})
    monkeypatch.setattr(oidc_routes, '_fetch_userinfo', lambda *_a, **_k: {})
    original_complete = login.complete_oidc_login

    def replace_after_verified_mapping(*args, **kwargs):
        params = original_complete(*args, **kwargs)
        old = User.get_by_id(params['user'])
        fields = {key: getattr(old, key) for key in (
            'user_id', 'username', 'email', 'password', 'role_id', 'group_id',
            'ldap_user', 'enabled')}
        user_sql.delete_user(old.user_id)
        if replacement:
            User.create(**fields)
        return params

    monkeypatch.setattr(oidc_routes, 'complete_oidc_login', replace_after_verified_mapping)
    with client.session_transaction() as oidc_session:
        oidc_session[f'oidc_state:{provider.slug}'] = 'synthetic-expected-state'
        oidc_session[f'oidc_nonce:{provider.slug}'] = 'synthetic-expected-nonce'
        oidc_session[f'oidc_return_to:{provider.slug}'] = '/admin'
    response = client.get(f'/oidc/{provider.slug}/callback?code=synthetic-code&state=synthetic-expected-state')
    assert response.status_code == 401
    assert response.get_json()['error'] == 'oidc_account_changed'
    assert client.get_cookie('access_token_cookie') is None
