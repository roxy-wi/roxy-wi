"""Synthetic browser evidence; screenshots never retain setup/recovery secrets."""
import os
from pathlib import Path

import pyotp
import pytest
from playwright.sync_api import expect
from app.modules.authentication import security

pytestmark=[pytest.mark.browser,pytest.mark.skipif(os.environ.get('ROXYWI_TEST_BROWSER')!='1',reason='Set ROXYWI_TEST_BROWSER=1')]


@pytest.mark.parametrize('theme',['light','dark'])
def test_totp_enrollment_management_and_login(logged_in,product_url,product,monkeypatch,theme):
    clock=[1893456000]
    monkeypatch.setattr(security,'now',lambda:clock[0])
    page=logged_in
    page.add_init_script("localStorage.setItem('theme', '"+theme+"')")
    page.goto(product_url+'/security')
    expect(page.locator('#totp-status')).to_have_text('Authenticator not configured')
    page.locator('#setup-totp').click()
    dialog=page.locator('.security-reauth')
    expect(dialog).to_be_visible()
    dialog.locator('#reauth-password').fill('TestBootstrapPassword!')
    dialog.locator('..').get_by_role('button',name='Verify',exact=True).click()
    expect(page.locator('#totp-setup')).to_be_visible()
    secret=page.locator('#totp-secret').input_value()
    assert len(secret)==32
    assert page.locator('#totp-qr').get_attribute('src').startswith('data:image/png;base64,')
    page.locator('#totp-confirm-code').fill(pyotp.TOTP(secret).at(clock[0]))
    page.get_by_role('button',name='Confirm authenticator',exact=True).click()
    recovery=page.locator('.security-recovery-dialog')
    expect(recovery).to_be_visible()
    codes=recovery.locator('pre').inner_text().splitlines()
    assert len(codes)==10 and len(codes[0].replace('-',''))==32
    recovery.locator('..').get_by_role('button',name='I saved my recovery codes').click()
    expect(page.locator('#totp-status')).to_have_text('Authenticator enabled')
    assert page.locator('#totp-secret').input_value()==''
    assert page.locator('#totp-qr').get_attribute('src') is None
    assert not page.locator('.security-recovery-dialog').count()
    page.reload()
    expect(page.locator('#recovery-count')).to_have_text('10 unused recovery codes')
    expect(page.locator('#totp-status')).to_have_text('Authenticator enabled')
    page.locator('#nprogress').wait_for(state='detached')
    target=Path('docs/screenshots/local-totp');target.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(target/f'enabled-{theme}.png'))
    # Fresh anonymous browser: password must show the second-factor step.
    page.context.clear_cookies()
    clock[0]+=30
    page.goto(product_url+'/login?next=/security')
    page.locator('#login').fill('admin')
    page.locator('#pass').fill('TestBootstrapPassword!')
    page.locator('#enter').click()
    expect(page.locator('#login-verification-code')).to_be_visible()
    assert not any(cookie['name']=='access_token_cookie' for cookie in page.context.cookies())
    page.locator('#login-verification-code').fill(pyotp.TOTP(secret).at(clock[0]))
    page.get_by_role('button',name='Verify and sign in').click()
    page.wait_for_url(product_url+'/security')
    expect(page.locator('#totp-status')).to_have_text('Authenticator enabled')
    # The refreshed CSRF cookie is used for the next protected mutation.
    clock[0]+=30
    page.locator('#regenerate-recovery').click()
    dialog=page.locator('.security-reauth')
    dialog.locator('#reauth-password').fill('TestBootstrapPassword!')
    dialog.locator('#reauth-code').fill(pyotp.TOTP(secret).at(clock[0]))
    dialog.locator('..').get_by_role('button',name='Verify',exact=True).click()
    expect(page.locator('.security-recovery-dialog')).to_be_visible()
    assert page.locator('.security-recovery-dialog pre').inner_text().splitlines()!=codes
