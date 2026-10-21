import os
from pathlib import Path

import pytest
from playwright.sync_api import expect


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1 and install Chromium',
)]


@pytest.mark.parametrize('locale,title', [
    ('en', 'Page not found'), ('ru', 'Страница не найдена'), ('fr', 'Page introuvable'),
    ('pt-br', 'Página não encontrada'), ('es-ES', 'Página no encontrada'), ('zh', '找不到页面'),
])
def test_missing_rule_is_localized_responsive_and_has_working_recovery_links(logged_in, product_url, product, locale, title):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    response = page.goto(product_url + f'/waf/haproxy/{product.server.ip}/rule/999999')
    assert response.status == 404
    expect(page.get_by_role('heading', level=1)).to_have_text(title)
    expect(page.locator('.error-code')).to_have_text('404')
    assert page.locator('.error-card').bounding_box()['width'] <= 500
    assert page.locator('.error-brand img').evaluate('(img) => img.complete && img.naturalWidth > 0')
    illustration = page.locator('.error-illustration')
    expect(illustration).to_be_visible()
    assert illustration.evaluate('(img) => img.complete && img.naturalWidth > 0')
    page.locator('.error-actions a').first.focus()
    page.keyboard.press('Tab')
    expect(page.locator('.error-actions a').last).to_be_focused()
    for width, height in ((1280, 800), (1024, 768), (800, 600), (390, 800), (320, 568), (320, 800)):
        page.set_viewport_size({'width': width, 'height': height})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        expect(page.locator('.error-actions a').first).to_be_visible()
        expect(page.locator('.error-actions a').last).to_be_visible()
        picture = illustration.bounding_box()
        card = page.locator('.error-card').bounding_box()
        logo = page.locator('.error-brand img').bounding_box()
        assert logo['x'] + logo['width'] / 2 == pytest.approx(width / 2, abs=1)
        assert picture['x'] + picture['width'] == pytest.approx(width, abs=1)
        assert picture['y'] + picture['height'] == pytest.approx(
            page.evaluate('document.documentElement.scrollHeight - window.scrollY'), abs=1,
        )
        assert (card['x'] + card['width'] <= picture['x']
                or card['y'] + card['height'] <= picture['y'])
    if locale in ('en', 'ru'):
        folder = Path('.test-artifacts/error-pages')
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / f'404-{locale}-mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1280, 'height': 800})
        page.screenshot(path=str(folder / f'404-{locale}.png'), full_page=True)
    page.keyboard.press('Enter')
    expect(page).to_have_url(product_url + '/login')
    expect(page.locator('#auth')).to_be_visible()


def test_server_error_works_with_failed_context_processor_and_saved_dark_theme(logged_in, product_url, app, monkeypatch):
    def broken_page():
        from flask import render_template
        return render_template('ovw.html')

    def broken_context():
        raise RuntimeError('private-database-password')

    monkeypatch.setitem(app.view_functions, 'overview.index', broken_page)
    monkeypatch.setitem(app.template_context_processors, None, [broken_context])
    page = logged_in
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    response = page.goto(product_url + '/overview')
    assert response.status == 500
    expect(page.locator('.error-code')).to_have_text('500')
    expect(page.get_by_role('heading', level=1)).to_have_text('Something went wrong')
    expect(page.locator('body')).not_to_contain_text('private-database-password')
    expect(page.locator('#error-dark-theme')).to_have_attribute('media', 'all')
    assert page.locator('.error-card').evaluate('(el) => getComputedStyle(el).backgroundColor') == 'rgb(31, 31, 31)'
    assert page.locator('.error-brand img').evaluate('(img) => img.complete && img.naturalWidth > 0')
    expect(page.locator('.error-illustration')).to_be_visible()
    assert page.locator('.error-illustration').evaluate('(img) => img.complete && img.naturalWidth > 0')
    folder = Path('.test-artifacts/error-pages')
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / '500-dark.png'), full_page=True)


def test_error_page_overview_link_recovers_to_application(logged_in, product_url):
    page = logged_in
    response = page.goto(product_url + '/missing-page-for-error-test')
    assert response.status == 404
    # A working authenticated destination, without unrelated host probes/charts.
    page.route('**/overview/server/**', lambda route: route.fulfill(body=''))
    page.route('**/metrics/*', lambda route: route.fulfill(status=503, json={'error': 'unavailable'}))
    page.get_by_role('link', name='Go to Overview', exact=True).click()
    expect(page.locator('#overview-services')).to_be_visible()
    expect(page).to_have_url(product_url + '/overview')
