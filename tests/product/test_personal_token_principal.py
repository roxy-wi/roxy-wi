"""The optional MFA principal must survive account deletion/recreation boundaries."""
from importlib import util
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import g

from app.modules.api_tokens import service
from app.modules.db import db_model as m
from tests.product.test_personal_tokens import URL, body, create


def installed_security():
    try:
        available = util.find_spec('app.modules.authentication.security')
    except ModuleNotFoundError:
        available = None
    if available is None:
        pytest.skip('Optional local authentication core is not installed')
    from app.modules.authentication import security
    return security


@pytest.mark.parametrize('operation', ['list', 'revoke', 'create'])
@pytest.mark.parametrize('provider_kind', ['missing', 'none', 'wrong_account', 'unavailable'])
def test_present_but_incomplete_provider_cannot_bypass_principal_binding(product_client, product, monkeypatch, operation, provider_kind):
    token_id = create(product_client)['token']['id']
    def unavailable(_claims):
        raise RuntimeError('Synthetic unavailable principal provider')
    providers = {
        'missing': SimpleNamespace(),
        'none': SimpleNamespace(session_user=lambda _claims: None),
        'wrong_account': SimpleNamespace(session_user=lambda _claims: SimpleNamespace(user_id=product.admin.user_id + 1)),
        'unavailable': SimpleNamespace(session_user=unavailable),
    }
    monkeypatch.setattr(service, 'security_provider', lambda: providers[provider_kind])
    response = (product_client.get(URL) if operation == 'list' else
                product_client.delete(URL + '/' + token_id) if operation == 'revoke' else
                product_client.post(URL, json=body()))
    assert response.status_code == 403
    assert m.PersonalAccessToken.get_by_id(token_id).revoked_at is None
    assert m.PersonalTokenGate.get_by_id(product.admin.user_id).attempts == 0


@pytest.mark.parametrize('operation', ['list', 'revoke', 'create', 'create_gate'])
def test_old_validated_cookie_cannot_read_or_mutate_replacement_account(product_client, product, monkeypatch, operation):
    security = installed_security()
    original_token = create(product_client)
    old_token = dict(m.PersonalAccessToken.get_by_id(original_token['token']['id']).__data__)
    old_user = dict(m.User.get_by_id(product.admin.user_id).__data__)
    old_account = security.user_account_id(product.admin.user_id)
    replacement_id = str(uuid4())
    observed = {}

    def replace_after_cookie_validation():
        # The real cookie verifier and CSRF guard have completed. Account deletion
        # and recreation here deterministically model another worker before the
        # service takes its parent-row lock.
        assert g.local_auth_principal['snapshot']['auth_account'] == old_account
        m.User.delete().where(m.User.user_id == product.admin.user_id).execute()
        m.User.create(**old_user)
        new_account = security.user_account_id(product.admin.user_id)
        assert new_account != old_account
        replacement = dict(old_token, id=replacement_id, name='Replacement private token',
                           security_version=security.user_epoch(product.admin.user_id))
        m.PersonalAccessToken.create(**replacement)
        # A replacement can already have independent failed-attempt accounting.
        m.PersonalTokenGate.create(user_id=product.admin.user_id, attempts=2)
        observed['incarnation'] = m.PersonalTokenGate.get_by_id(product.admin.user_id).incarnation

    target = {'list': 'list_tokens', 'revoke': 'revoke', 'create': 'create',
              'create_gate': 'sensitive_attempt'}[operation]
    original = getattr(service, target)
    def race(*args, **kwargs):
        replace_after_cookie_validation()
        return original(*args, **kwargs)
    monkeypatch.setattr(service, target, race)
    response = (product_client.get(URL) if operation == 'list' else
                product_client.delete(URL + '/' + replacement_id) if operation == 'revoke' else
                product_client.post(URL, json=body()))
    assert response.status_code == 403, response.text
    assert 'Replacement private token' not in response.text
    assert observed
    assert m.PersonalAccessToken.select().count() == 1
    assert m.PersonalAccessToken.get_by_id(replacement_id).revoked_at is None
    gate = m.PersonalTokenGate.get_by_id(product.admin.user_id)
    assert gate.attempts == 2 and gate.incarnation == observed['incarnation']
