import os

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import ConfigChange


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.mark.parametrize('locale,theme', [
    ('en', 'light'), ('ru', 'light'), ('es-ES', 'light'), ('fr', 'light'), ('pt-br', 'light'), ('zh', 'light'),
    ('en', 'dark'),
])
def test_filters_match_config_selects_and_filter_changes(logged_in, product_url, product, app, locale, theme, tmp_path):
    for service, status, title in [('haproxy', 'draft', 'Alpha'), ('nginx', 'deployed', 'Beta')]:
        ConfigChange.create(
            server_id=product.server.server_id, group_id=1, user_id=product.admin.user_id,
            service=service, action='reload', status=status, title=title, requires_approval=0,
            remote_path=f'/etc/{service}/{service}.conf', draft_path=str(tmp_path / service),
            rollback_path=str(tmp_path / (service + '.old')), drift_status='in_sync',
        )
    page = logged_in
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    read_style = """el => {
        const style = getComputedStyle(el);
        return Object.fromEntries(['fontFamily', 'fontSize', 'fontWeight', 'lineHeight',
            'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'borderTopWidth',
            'borderRadius', 'backgroundColor'].map(key => [key, style[key]]));
    }"""
    assert page.goto(product_url + '/config/haproxy').status == 200
    expect(page.locator('#serv-button')).to_be_visible()
    parts = ['', ' .ui-selectmenu-text', ' .ui-selectmenu-icon']
    standard = {part: page.locator('#serv-button' + part).evaluate(read_style) for part in parts}

    assert page.goto(product_url + '/changes').status == 200
    rows = page.locator('#change-center-table tbody tr:visible')
    expect(rows).to_have_count(2)
    intro = page.locator('.change-center-intro')
    expect(intro).to_have_css('background-color', 'rgb(42, 42, 42)' if theme == 'dark' else 'rgb(244, 245, 246)')
    if theme == 'dark':
        expect(intro).to_have_css('color', 'rgb(240, 240, 240)')
    messages = app.jinja_env.get_template(f'languages/{locale}.html').module
    search = page.get_by_role('searchbox', name=messages.ux['search'], exact=True)
    expect(search).to_be_visible()
    expect(page.locator('.change-list-toolbar label').get_by_text(messages.ux['search'], exact=True)).to_have_count(0)
    assert search.bounding_box()['width'] == pytest.approx(190, abs=1)

    for field, value, title in [('service', 'haproxy', 'Alpha'), ('status', 'draft', 'Alpha'),
                               ('drift', 'in_sync', 'Beta')]:
        selector = '#change-list-' + field
        for part in parts:
            assert page.locator(selector + '-button' + part).evaluate(read_style) == standard[part]
        label = page.locator(selector + f' option[value="{value}"]').text_content()
        page.locator(selector + '-button').click()
        page.locator(selector + '-menu').get_by_role('option', name=label, exact=True).click()
        expect(rows).to_have_count(1)
        expect(rows).to_contain_text(title)
        page.locator('#change-list-clear').click()
        expect(rows).to_have_count(2)

    search.fill('Beta')
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text('Beta')
    search.fill('no-matching-change')
    expect(page.locator('#change-center-no-results')).to_be_visible()
    expect(page.locator('.change-list-table')).to_be_hidden()
    page.locator('#change-list-clear').click()
    expect(rows).to_have_count(2)
    page.locator('.change-list-toolbar').screenshot(path=str(tmp_path / 'filters.png'))
    page.screenshot(path=str(tmp_path / 'desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 800})
    page.wait_for_function('getComputedStyle(document.querySelector(".container")).marginLeft === "0px"')
    toolbar = page.locator('.change-list-toolbar')
    assert toolbar.evaluate('(el) => el.scrollWidth <= el.clientWidth')
    for field in ('service', 'status', 'drift'):
        expect(page.locator('#change-list-' + field + '-button')).to_be_visible()
    page.screenshot(path=str(tmp_path / 'mobile.png'), full_page=True)
