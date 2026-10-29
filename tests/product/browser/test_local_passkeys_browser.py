"""Chromium CDP virtual authenticator exercises real browser WebAuthn ceremonies."""
from pathlib import Path
import os

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium')]


@pytest.fixture
def passkey_browser(page, product_url, app, monkeypatch):
    product_url = product_url.replace('127.0.0.1', 'localhost')
    result = page.request.post(product_url + '/login', data={'login': 'admin', 'pass': 'TestBootstrapPassword!', 'next': '/security/passkeys'})
    assert result.status == 200
    monkeypatch.setitem(app.config, 'WEBAUTHN_RP_ID', 'localhost')
    monkeypatch.setitem(app.config, 'WEBAUTHN_ORIGINS', [product_url])
    session = page.context.new_cdp_session(page)
    session.send('WebAuthn.enable')
    authenticator = session.send('WebAuthn.addVirtualAuthenticator', {'options': {
        'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
        'hasUserVerification': True, 'isUserVerified': True, 'automaticPresenceSimulation': True}})
    yield page, product_url, session, authenticator['authenticatorId']
    session.send('WebAuthn.removeVirtualAuthenticator', {'authenticatorId': authenticator['authenticatorId']})


def add_passkey(page, url, name='Work laptop'):
    page.goto(url + '/security/passkeys')
    page.locator('#passkey-name').fill(name)
    page.locator('#passkey-add').click()
    page.locator('#reauth-password').fill('TestBootstrapPassword!')
    page.get_by_role('button', name='Verify', exact=True).click()
    try:
        expect(page.locator('#passkey-recovery')).to_be_visible()
    except AssertionError:
        raise AssertionError('Passkey browser error: ' + page.locator('#passkey-status').inner_text()) from None
    expect(page.locator('#passkey-recovery-codes')).not_to_be_empty()
    page.get_by_role('link', name='I saved my codes').click()
    expect(page.locator('.passkeys-table')).to_contain_text(name)


def test_virtual_authenticator_registration_and_passwordless_login(passkey_browser):
    page, url, session, authenticator_id = passkey_browser
    add_passkey(page, url)
    credentials = session.send('WebAuthn.getCredentials', {'authenticatorId': authenticator_id})['credentials']
    assert len(credentials) == 1
    assert credentials[0]['isResidentCredential'] is True
    page.goto(url + '/login?next=/security/passkeys')
    page.locator('#login').fill('admin')
    page.get_by_role('button', name='Sign in with a passkey', exact=True).click()
    expect(page).to_have_url(url + '/security/passkeys')
    expect(page.locator('.passkeys-table')).to_contain_text('Work laptop')


def test_password_plus_virtual_passkey_and_safe_removal(passkey_browser):
    page, url, _session, _authenticator_id = passkey_browser
    add_passkey(page, url)
    page.goto(url + '/login?next=/security/passkeys')
    page.locator('#login').fill('admin')
    page.locator('#pass').fill('TestBootstrapPassword!')
    page.locator('#enter').click()
    expect(page.locator('#local-auth-step')).to_be_visible()
    page.get_by_role('button', name='Use passkey', exact=True).click()
    expect(page).to_have_url(url + '/security/passkeys')
    page.get_by_role('button', name='Remove', exact=True).click()
    page.get_by_role('button', name='Use passkey', exact=True).click()
    expect(page).to_have_url(url + '/login')
    page.locator('#login').fill('admin')
    page.locator('#pass').fill('TestBootstrapPassword!')
    page.locator('#enter').click()
    expect(page.locator('#local-auth-step')).not_to_be_visible()


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_passkeys_synthetic_screenshots(passkey_browser, theme):
    page, url, _session, _authenticator_id = passkey_browser
    add_passkey(page, url, 'Example work laptop')
    page.evaluate('(theme) => localStorage.setItem("theme", theme)', theme)
    page.reload()
    expect(page.locator('.passkeys-table')).to_contain_text('Example work laptop')
    assert not page.locator('#passkey-recovery-codes').text_content()
    path = Path(__file__).resolve().parents[3] / 'docs/screenshots/local-passkeys'
    path.mkdir(parents=True, exist_ok=True)
    page.locator('#nprogress').wait_for(state='detached')
    page.screenshot(path=str(path / (theme + '.png')))


def test_required_policy_enrolls_with_real_webauthn(passkey_browser):
    from app.modules.db.db_model import AuthenticationPolicy
    page, url, _session, _authenticator_id = passkey_browser
    AuthenticationPolicy.get_or_create(id=1)
    AuthenticationPolicy.update(mode='all', grace_until=0).execute()
    page.goto(url + '/login?next=/security/passkeys')
    page.locator('#login').fill('admin')
    page.locator('#pass').fill('TestBootstrapPassword!')
    page.locator('#enter').click()
    expect(page.locator('#local-auth-step')).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept('Required work laptop'))
    page.get_by_role('button', name='Set up a passkey', exact=True).click()
    expect(page.get_by_role('dialog', name='Recovery codes', exact=True)).to_be_visible()
    page.get_by_role('button', name='I saved my recovery codes', exact=True).click()
    expect(page).to_have_url(url + '/security/passkeys')
    expect(page.locator('.passkeys-table')).to_contain_text('Required work laptop')
