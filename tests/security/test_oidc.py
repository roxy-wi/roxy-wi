import json
import time
import uuid
from pathlib import Path

import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from flask_jwt_extended import create_access_token
from flask import g, render_template

from app.modules.db.db_model import (
    Groups,
    OidcGroupMapping,
    OidcIdentity,
    OidcProvider,
    Role,
    User,
    UserGroups,
)
from app.modules.oidc.errors import OidcLoginError
from app.modules.oidc import access as oidc_access
from app.modules.oidc.login import complete_oidc_login, extract_claim
from app.modules.roxy_wi_tools import Tools
from app.routes.oidc import routes as oidc_routes


SUPPORTED_LANGUAGES = ('en', 'es-ES', 'fr', 'pt-br', 'ru', 'zh')


def make_provider(**overrides):
    suffix = uuid.uuid4().hex
    values = {
        'slug': f'oidc-test-{suffix}',
        'label': 'Test OIDC',
        'enabled': 1,
        'client_id': 'roxy-wi-test',
        'metadata_url': None,
        'issuer': 'https://idp.example.test',
        'authorization_endpoint': 'https://idp.example.test/authorize',
        'token_endpoint': 'https://idp.example.test/token',
        'userinfo_endpoint': 'https://idp.example.test/userinfo',
        'jwks_uri': 'https://idp.example.test/jwks',
        'scope': 'openid email profile',
        'subject_claim': 'sub',
        'email_claim': 'email',
        'username_claim': 'preferred_username',
        'groups_claim': 'groups',
        'allowed_domains': json.dumps([]),
        'auto_create_users': 0,
        'auto_link_by_email': 1,
        'require_verified_email': 1,
        'sync_group_memberships': 1,
        'remove_missing_group_memberships': 0,
        'default_group_id': 1,
        'default_role_id': 4,
    }
    values.update(overrides)
    return OidcProvider.create(**values)


@pytest.fixture(autouse=True)
def clean_oidc_data():
    OidcGroupMapping.delete().execute()
    OidcIdentity.delete().execute()
    OidcProvider.delete().execute()
    yield
    user_ids = [
        user.user_id
        for user in User.select(User.user_id).where(User.username.startswith('oidc-test-'))
    ]
    if user_ids:
        UserGroups.delete().where(UserGroups.user_id.in_(user_ids)).execute()
        User.delete().where(User.user_id.in_(user_ids)).execute()
    OidcGroupMapping.delete().execute()
    OidcIdentity.delete().execute()
    OidcProvider.delete().execute()


@pytest.fixture(autouse=True)
def active_company_subscription(monkeypatch):
    monkeypatch.setattr(
        oidc_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'company'},
    )


@pytest.mark.security
@pytest.mark.parametrize(
    ('subscription', 'expected'),
    (
        ({'user_status': 1, 'user_plan': 'company'}, True),
        ({'user_status': 1, 'user_plan': 'cloud'}, True),
        ({'user_status': 1, 'user_plan': 'support'}, True),
        ({'user_status': 1, 'user_plan': 'user'}, False),
        ({'user_status': 1, 'user_plan': 'Trial'}, False),
        ({'user_status': 0, 'user_plan': 'support'}, False),
    ),
)
def test_oidc_requires_active_company_or_higher(subscription, expected):
    assert oidc_access.is_oidc_available(subscription) is expected


@pytest.mark.security
def test_oidc_is_hidden_and_public_routes_are_blocked_without_subscription(client, monkeypatch):
    provider = make_provider(label='Subscription-only Login')
    monkeypatch.setattr(
        oidc_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'user'},
    )

    providers_response = client.get('/oidc/providers')
    login_response = client.get(f'/oidc/{provider.slug}/login')
    callback_response = client.get(f'/oidc/{provider.slug}/callback')
    login_page = client.get('/login').get_data(as_text=True)

    assert providers_response.status_code == 403
    assert login_response.status_code == 403
    assert callback_response.status_code == 403
    assert providers_response.get_json()['error'] == oidc_access.OIDC_SUBSCRIPTION_ERROR
    assert 'Subscription-only Login' not in login_page


@pytest.mark.security
def test_oidc_admin_api_is_blocked_without_company_subscription(app, client, monkeypatch):
    monkeypatch.setattr(
        oidc_access.roxywi_common,
        'return_user_subscription',
        lambda: {'user_status': 1, 'user_plan': 'user'},
    )
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})

    response = client.get(
        '/admin/oidc/providers',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 403
    assert response.get_json() == {
        'status': 'failed',
        'error': oidc_access.OIDC_SUBSCRIPTION_ERROR,
    }


@pytest.mark.security
def test_oidc_availability_is_injected_into_authenticated_templates(app):
    with app.test_request_context('/admin'):
        g.user_params = {'user': 'admin'}
        context = {}
        app.update_template_context(context)

    assert context['oidc_available'] is True


@pytest.mark.security
def test_oidc_ui_uses_single_icons_and_menu_anchor(app):
    app_root = Path(app.root_path)
    oidc_script = (app_root / 'static' / 'js' / 'admin' / 'oidc.js').read_text(encoding='utf-8')
    menu_template = (app_root / 'templates' / 'include' / 'main_menu.html').read_text(encoding='utf-8')
    admin_script = (app_root / 'static' / 'js' / 'admin' / 'common.js').read_text(encoding='utf-8')

    assert "append($('<i>')" not in oidc_script
    assert "url_for('admin.admin') }}#oidc" in menu_template
    assert 'class="oidc head-submenu"' in menu_template
    assert 'window.history.replaceState' in admin_script


@pytest.mark.security
def test_oidc_public_provider_list_and_login_page_hide_disabled(client):
    enabled = make_provider(label='Company Login')
    make_provider(label='Disabled Login', enabled=0)

    response = client.get('/oidc/providers')
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == [{'label': 'Company Login', 'slug': enabled.slug}]

    login_page = client.get('/login').get_data(as_text=True)
    assert 'class="login-auth-column"' in login_page
    assert 'Sign in with Company Login' in login_page
    assert 'Disabled Login' not in login_page


@pytest.mark.security
def test_oidc_login_stores_state_nonce_and_safe_return_path(client, monkeypatch):
    provider = make_provider(userinfo_endpoint=None)

    class FakeOAuthSession:
        def __init__(self, **kwargs):
            assert kwargs['client_id'] == provider.client_id
            assert kwargs['redirect_uri'].endswith(f'/oidc/{provider.slug}/callback')

        @staticmethod
        def create_authorization_url(endpoint, nonce):
            assert endpoint == provider.authorization_endpoint
            assert nonce
            return 'https://idp.example.test/authorize?state=generated-state', 'generated-state'

    monkeypatch.setattr(oidc_routes, 'OAuth2Session', FakeOAuthSession)

    response = client.get(f'/oidc/{provider.slug}/login?next=/admin')
    assert response.status_code == 302
    assert response.location.startswith('https://idp.example.test/authorize')

    with client.session_transaction() as oidc_session:
        assert oidc_session[f'oidc_state:{provider.slug}'] == 'generated-state'
        assert oidc_session[f'oidc_nonce:{provider.slug}']
        assert oidc_session[f'oidc_return_to:{provider.slug}'] == '/admin'


@pytest.mark.security
def test_oidc_callback_rejects_missing_or_wrong_state(client):
    provider = make_provider()
    with client.session_transaction() as oidc_session:
        oidc_session[f'oidc_state:{provider.slug}'] = 'expected-state'
        oidc_session[f'oidc_nonce:{provider.slug}'] = 'expected-nonce'

    response = client.get(f'/oidc/{provider.slug}/callback?code=code&state=wrong-state')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'oidc_state_invalid'


@pytest.mark.security
def test_oidc_callback_issues_normal_jwt_cookie(client, monkeypatch):
    provider = make_provider(userinfo_endpoint=None)

    class FakeOAuthSession:
        def __init__(self, **_kwargs):
            pass

        @staticmethod
        def fetch_token(endpoint, authorization_response, timeout):
            assert endpoint == provider.token_endpoint
            assert 'state=expected-state' in authorization_response
            assert timeout == 10
            return {'id_token': 'signed-token', 'access_token': 'access-token'}

    monkeypatch.setattr(oidc_routes, 'OAuth2Session', FakeOAuthSession)
    monkeypatch.setattr(oidc_routes, '_validate_id_token', lambda *_args, **_kwargs: {'sub': 'subject'})
    monkeypatch.setattr(oidc_routes, '_fetch_userinfo', lambda *_args, **_kwargs: {})
    from app.modules.authentication import security
    def verified_local_identity(*_args, **_kwargs):
        user, expected = security.capture_account(1)
        return {'group': '1', 'user': 1, 'name': 'admin',
                **security.login_proof(user, 'oidc', expected=expected)}
    monkeypatch.setattr(oidc_routes, 'complete_oidc_login', verified_local_identity)

    with client.session_transaction() as oidc_session:
        oidc_session[f'oidc_state:{provider.slug}'] = 'expected-state'
        oidc_session[f'oidc_nonce:{provider.slug}'] = 'expected-nonce'
        oidc_session[f'oidc_return_to:{provider.slug}'] = 'https://evil.example/'

    response = client.get(f'/oidc/{provider.slug}/callback?code=code&state=expected-state')
    assert response.status_code == 302
    assert response.location == '/overview'
    assert any('access_token_cookie=' in cookie for cookie in response.headers.getlist('Set-Cookie'))


@pytest.mark.security
def test_oidc_signed_id_token_is_verified(monkeypatch):
    provider = make_provider()
    key = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'test-key'})
    public_jwks = {'keys': [key.as_dict(is_private=False)]}
    monkeypatch.setattr(oidc_routes, '_load_jwks', lambda *_args: public_jwks)

    now = int(time.time())
    encoded = JsonWebToken(['RS256']).encode(
        {'alg': 'RS256', 'kid': 'test-key'},
        {
            'iss': provider.issuer,
            'sub': 'stable-subject',
            'aud': provider.client_id,
            'exp': now + 300,
            'iat': now,
            'nonce': 'expected-nonce',
            'email': 'user@example.test',
        },
        key,
    )
    if isinstance(encoded, bytes):
        encoded = encoded.decode('utf-8')

    claims = oidc_routes._validate_id_token(
        provider,
        {'id_token_signing_alg_values_supported': ['RS256']},
        {'id_token': encoded},
        'expected-nonce',
    )
    assert claims['sub'] == 'stable-subject'


@pytest.mark.security
def test_oidc_id_token_rejects_wrong_nonce(monkeypatch):
    provider = make_provider()
    key = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'test-key'})
    monkeypatch.setattr(
        oidc_routes,
        '_load_jwks',
        lambda *_args: {'keys': [key.as_dict(is_private=False)]},
    )
    now = int(time.time())
    encoded = JsonWebToken(['RS256']).encode(
        {'alg': 'RS256', 'kid': 'test-key'},
        {
            'iss': provider.issuer,
            'sub': 'stable-subject',
            'aud': provider.client_id,
            'exp': now + 300,
            'iat': now,
            'nonce': 'actual-nonce',
        },
        key,
    )

    with pytest.raises(OidcLoginError) as error:
        oidc_routes._validate_id_token(
            provider,
            {'id_token_signing_alg_values_supported': ['RS256']},
            {'id_token': encoded},
            'expected-nonce',
        )
    assert error.value.error == 'oidc_id_token_invalid'


@pytest.mark.security
def test_oidc_userinfo_subject_must_match_signed_token():
    with pytest.raises(OidcLoginError) as error:
        oidc_routes._merge_claims(
            {'sub': 'signed-subject', 'email': 'user@example.test'},
            {'sub': 'different-subject', 'name': 'User'},
        )
    assert error.value.error == 'oidc_subject_mismatch'


@pytest.mark.security
def test_oidc_auto_creates_user_and_stable_identity():
    provider = make_provider(auto_create_users=1)
    result = complete_oidc_login(provider, {
        'sub': 'new-user-subject',
        'email': 'oidc-test-created@example.test',
        'email_verified': True,
        'preferred_username': 'oidc-test-created',
        'groups': [],
    })

    user = User.get_by_id(result['user'])
    identity = OidcIdentity.get(
        (OidcIdentity.issuer == provider.issuer)
        & (OidcIdentity.subject == 'new-user-subject')
    )
    membership = UserGroups.get(
        (UserGroups.user_id == user.user_id)
        & (UserGroups.user_group_id == provider.default_group_id)
    )

    assert identity.user_id == user.user_id
    assert membership.user_role_id == provider.default_role_id
    assert Tools.check_password('not-the-generated-password', user.password) == (False, False)


@pytest.mark.security
def test_oidc_links_existing_user_by_verified_email():
    provider = make_provider(auto_create_users=0, auto_link_by_email=1)
    suffix = uuid.uuid4().hex
    user = User.create(
        username=f'oidc-test-linked-{suffix}',
        email=f'oidc-test-linked-{suffix}@example.test',
        password=Tools.get_hash('Local-password-only!'),
        role_id='3',
        group_id='1',
        enabled=1,
    )
    UserGroups.create(user_id=user.user_id, user_group_id=1, user_role_id=3)

    result = complete_oidc_login(provider, {
        'sub': 'linked-subject',
        'email': user.email,
        'email_verified': True,
        'preferred_username': 'different-external-name',
    })

    assert result['user'] == user.user_id
    assert OidcIdentity.get(OidcIdentity.subject == 'linked-subject').user_id == user.user_id


@pytest.mark.security
def test_oidc_group_mapping_supports_dotted_claim_and_sets_active_group():
    group = Groups.create(name=f'OIDC Test {uuid.uuid4().hex}', description='OIDC test group')
    provider = make_provider(
        auto_create_users=1,
        groups_claim='realm_access.roles',
        default_group_id=1,
    )
    OidcGroupMapping.create(
        provider_id=provider.id,
        external_group='roxy-editors',
        group_id=group.group_id,
        role_id=2,
        active=1,
        priority=10,
    )

    try:
        result = complete_oidc_login(provider, {
            'sub': 'mapped-subject',
            'email': 'oidc-test-mapped@example.test',
            'email_verified': True,
            'preferred_username': 'oidc-test-mapped',
            'realm_access': {'roles': ['ROXY-EDITORS']},
        })
        user = User.get_by_id(result['user'])
        membership = UserGroups.get(
            (UserGroups.user_id == user.user_id)
            & (UserGroups.user_group_id == group.group_id)
        )
        assert int(user.group_id) == group.group_id
        assert membership.user_role_id == 2
        assert extract_claim({'realm_access': {'roles': ['one']}}, 'realm_access.roles') == ['one']
    finally:
        Groups.delete().where(Groups.group_id == group.group_id).execute()


@pytest.mark.security
def test_oidc_unmatched_group_rolls_back_new_user_and_identity():
    group = Groups.create(name=f'OIDC Test {uuid.uuid4().hex}', description='OIDC test group')
    provider = make_provider(auto_create_users=1)
    OidcGroupMapping.create(
        provider_id=provider.id,
        external_group='required-group',
        group_id=group.group_id,
        role_id=4,
    )
    email = f'oidc-test-orphan-{uuid.uuid4().hex}@example.test'
    try:
        with pytest.raises(OidcLoginError) as error:
            complete_oidc_login(provider, {
                'sub': 'orphan-subject',
                'email': email,
                'email_verified': True,
                'preferred_username': 'oidc-test-orphan',
                'groups': ['another-group'],
            })
        assert error.value.error == 'oidc_group_mapping_not_matched'
        assert User.get_or_none(User.email == email) is None
        assert OidcIdentity.get_or_none(OidcIdentity.subject == 'orphan-subject') is None
    finally:
        Groups.delete().where(Groups.group_id == group.group_id).execute()


@pytest.mark.security
def test_oidc_denies_unverified_or_unapproved_email():
    provider = make_provider(
        auto_create_users=1,
        allowed_domains=json.dumps(['example.test']),
    )
    with pytest.raises(OidcLoginError) as error:
        complete_oidc_login(provider, {
            'sub': 'bad-domain',
            'email': 'oidc-test-user@evil.test',
            'email_verified': True,
            'preferred_username': 'oidc-test-user',
        })
    assert error.value.error == 'oidc_domain_denied'

    with pytest.raises(OidcLoginError) as error:
        complete_oidc_login(provider, {
            'sub': 'unverified',
            'email': 'oidc-test-user@example.test',
            'email_verified': False,
            'preferred_username': 'oidc-test-user',
        })
    assert error.value.error == 'oidc_email_not_verified'


@pytest.mark.security
def test_oidc_admin_api_encrypts_and_never_returns_client_secret(app, client, monkeypatch):
    monkeypatch.setattr('app.routes.admin.oidc_routes.roxywi_common.logging', lambda *_args, **_kwargs: None)
    with app.app_context():
        token = create_access_token('1', additional_claims={'group': '1'})
    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'slug': f'admin-{uuid.uuid4().hex}',
        'label': 'Admin OIDC',
        'client_id': 'roxy-wi',
        'client_secret': 'super-secret-value',
        'metadata_url': 'https://idp.example.test/.well-known/openid-configuration',
        'default_group_id': 1,
        'default_role_id': 4,
    }

    response = client.post('/admin/oidc/providers', json=payload, headers=headers)
    assert response.status_code == 201
    data = response.get_json()
    assert data['client_secret_configured'] is True
    assert 'client_secret' not in data
    assert 'client_secret_encrypted' not in data

    provider = OidcProvider.get_by_id(data['id'])
    original_secret = provider.client_secret_encrypted
    assert original_secret != payload['client_secret']

    response = client.put(
        f'/admin/oidc/providers/{provider.id}',
        json={'client_secret': ''},
        headers=headers,
    )
    assert response.status_code == 200
    assert OidcProvider.get_by_id(provider.id).client_secret_encrypted == original_secret

    response = client.put(
        f'/admin/oidc/providers/{provider.id}',
        json={'metadata_url': None},
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.security
def test_oidc_admin_ui_template_renders_provider_and_mapping_forms(app):
    with app.test_request_context('/admin'):
        language = app.jinja_env.get_template('languages/en.html').module
        html = render_template(
            'include/admin_oidc.html',
            groups=list(Groups.select()),
            roles=list(Role.select()),
            lang=language,
        )

    assert 'id="oidc-provider-form"' in html
    assert 'id="oidc-provider-dialog"' in html
    assert 'id="oidc-mapping-form"' in html
    assert 'id="oidc-mapping-dialog"' in html
    assert 'id="oidc-mappings-dialog"' in html


@pytest.mark.security
def test_oidc_translation_catalogs_have_the_same_complete_key_set(app):
    with app.app_context():
        catalogs = {
            language: app.jinja_env.get_template(f'languages/{language}.html').module.oidc_page
            for language in SUPPORTED_LANGUAGES
        }

    expected_keys = set(catalogs['en'])
    assert expected_keys
    for catalog in catalogs.values():
        assert set(catalog) == expected_keys
        assert all(value.strip() for value in catalog.values())
