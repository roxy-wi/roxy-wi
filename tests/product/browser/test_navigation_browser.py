"""Exercise the real navigation with touch input and mobile viewport changes."""
import os

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.fixture(scope='session')
def browser_context_args(browser_context_args):
    return {**browser_context_args, 'has_touch': True}


@pytest.mark.parametrize('locale', ['en', 'ru', 'es-ES', 'fr', 'pt-br', 'zh'])
@pytest.mark.parametrize('width', [390, 820])
def test_mobile_menu_search_submenus_and_navigation(logged_in, product_url, waf_modes, app, locale, width):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 844})
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/nettools')
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module.menu_links['navigation']
    toggle = page.locator('#app-mobile-nav-toggle')
    navigation = page.locator('#app-navigation')
    search = page.locator('#app-navigation-search')
    nginx = navigation.locator('.nav-service').filter(has=page.locator('#menu-nginx'))
    expect(navigation).to_have_attribute('inert', '')
    toggle.tap()
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    expect(search).to_be_visible()
    expect(search).to_have_attribute('aria-label', messages['search'])
    expect(nginx.locator('.nav-label')).to_be_visible()
    nginx.locator('.nav-submenu-toggle').tap()
    expect(nginx.locator('a[href="/waf/nginx"]')).to_be_visible()
    search.fill('nginx')
    expect(nginx).to_be_visible()
    expect(navigation.locator('#menu-haproxy')).to_be_hidden()
    search.fill('')
    services = navigation.locator('[data-nav-group="services"]')
    services.locator(':scope > .nav-group-toggle').tap()
    expect(nginx).to_be_hidden()
    services.locator(':scope > .nav-group-toggle').tap()
    expect(nginx).to_be_visible()
    # The lower navigation groups must remain reachable inside the drawer.
    navigation.locator('[data-nav-group="administration"] > button').tap()
    assert navigation.locator('.app-nav-scroll').evaluate('(node) => node.scrollTop') > 0
    nginx.locator('a[href="/waf/nginx"]').tap()
    expect(page).to_have_url(product_url + '/waf/nginx')
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(navigation).to_have_attribute('inert', '')
    expect(page.locator('[data-waf-card]')).to_be_visible()
    toggle.tap()
    expect(nginx.locator('a[href="/waf/nginx"]')).to_have_attribute('aria-current', 'page')
    if locale == 'ru' and width == 390:
        page.wait_for_function('document.getElementById("app-navigation").getBoundingClientRect().left === 0')
        expect(toggle.locator('svg')).to_be_visible()
        page.screenshot(path='.test-artifacts/navigation-mobile.png')
    # A tap outside the drawer closes it without activating page content.
    page.locator('#app-nav-backdrop').tap(position={'x': width - 8, 'y': 80})
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    toggle.tap()
    page.keyboard.press('Escape')
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    expect(toggle).to_be_focused()


@pytest.mark.parametrize('width', [320, 390, 900])
def test_mobile_drawer_ignores_desktop_collapse_and_recovers_after_resize(logged_in, product_url, width):
    page = logged_in
    page.goto(product_url + '/nettools')
    collapse = page.locator('#hide_menu')
    collapse.click()
    expect(collapse).to_have_attribute('aria-pressed', 'true')
    page.set_viewport_size({'width': width, 'height': 700})
    page.reload()
    toggle = page.locator('#app-mobile-nav-toggle')
    toggle.tap()
    search = page.locator('#app-navigation-search')
    expect(search).to_be_visible()
    nginx = page.locator('.nav-service').filter(has=page.locator('#menu-nginx'))
    nginx.locator('.nav-submenu-toggle').tap()
    expect(nginx.locator('a[href="/waf/nginx"]')).to_be_visible()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    expect(toggle).to_be_hidden()
    expect(page.locator('#app-nav-backdrop')).to_be_hidden()
    expect(collapse).to_have_attribute('aria-pressed', 'true')
    assert page.locator('html').evaluate('(node) => getComputedStyle(node).overflow') != 'hidden'
    collapse.click()
    expect(search).to_be_visible()
    expect(nginx.locator('a[href="/waf/nginx"]')).to_be_visible()
    page.set_viewport_size({'width': width, 'height': 700})
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    page.locator('.container h2').click()
    page.keyboard.press('/')
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    expect(search).to_be_focused()
