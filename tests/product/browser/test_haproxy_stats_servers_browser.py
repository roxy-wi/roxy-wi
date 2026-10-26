import os
import re

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import HaproxySection
from tests.fixtures.haproxy_servers import server_host, maxconn_host  # noqa: F401


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


def row(page, name):
    return page.locator('.hs-row').filter(has=page.locator('.hs-name > span').filter(has_text=re.compile('^' + re.escape(name) + '$')))


def open_action(page, name, action):
    target = row(page, name)
    target.locator('.admin-actions-toggle').scroll_into_view_if_needed()
    # The shared menu intentionally closes on scroll. Finish scrolling before opening it.
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    target.locator('.admin-actions-toggle').click()
    target.locator(f'[data-action={action}]').click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    return dialog


def test_add_edit_delete_and_edit_section_preserve_server_identity(logged_in, product_url, product, server_host, tmp_path):
    page = logged_in
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    dialog = open_action(page, 'BACKEND', 'add')
    dialog.locator('[name=address]').fill('2001:db8::10')
    expect(dialog.locator('[name=name]')).to_have_value('2001:db8::10')
    dialog.locator('[name=name]').fill('new-server')
    dialog.locator('[name=port]').fill('9000')
    expect(dialog.locator('[name=check_port]')).to_have_value('9000')
    dialog.locator('[name=check]').uncheck()
    expect(dialog).to_contain_text('without a reload')
    expect(dialog).to_contain_text('192.0.2.33')
    page.screenshot(path=str(tmp_path / 'add-server-desktop.png'))
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('Server changes applied')
    expect(row(page, 'new-server')).to_be_visible()
    expect(page.locator('#hs-refresh')).to_be_enabled()

    dialog = open_action(page, 'new-server', 'edit')
    expect(dialog.locator('[name=address]')).to_have_value('2001:db8::10')
    dialog.locator('[name=address]').fill('192.0.2.55')
    dialog.locator('[name=port]').fill('8088')
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(server_host.saves) == 4

    page.goto(product_url + '/config/haproxy/192.0.2.11/show')
    section = page.locator('.cv-section').filter(has=page.locator('.cv-title', has_text='backend web'))
    expect(section).to_be_visible()
    if not section.evaluate('node => node.open'):
        section.locator('summary').click()
    section.locator('.cv-edit-section').click()
    expect(page.locator('#edit-section')).to_be_visible()
    expect(page.locator('#edit-backend input[name=servers]').nth(2)).to_have_value('192.0.2.55')
    expect(page.locator('#edit-backend input[name=server_port]').nth(2)).to_have_value('8088')
    payload = page.evaluate("getFormData($('#edit-backend'), 'edit-backend')")
    assert payload['backend_servers'][2]['name'] == 'new-server'
    assert payload['backend_servers'][2]['check_enabled'] is False

    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    dialog = open_action(page, 'new-server', 'delete')
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert len(server_host.saves) == 4
    dialog = open_action(page, 'new-server', 'delete')
    dialog.get_by_role('button', name='Save and reload', exact=True).click()
    expect(row(page, 'new-server')).to_have_count(0)
    assert len(server_host.saves) == 6
    assert len(HaproxySection.get_by_id(server_host.records[0].id).config['backend_servers']) == 2


def test_open_dialog_rejects_concurrent_change_and_shows_partial_failure(logged_in, product_url, server_host):
    page = logged_in
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    dialog = open_action(page, 'one', 'edit')
    server_host.configs['192.0.2.33'] += '# changed while the dialog was open\n'
    dialog.locator('[name=address]').fill('192.0.2.90')
    dialog.get_by_role('button', name='Save and apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_have_attribute('data-error', 'true')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert not server_host.saves
    dialog = open_action(page, 'one', 'delete')
    server_host.fail_save = '192.0.2.33'
    dialog.get_by_role('button', name='Save and reload', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('Some changes may have been applied')
    expect(page.locator('#hs-action-result')).to_contain_text('192.0.2.33')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(server_host.saves) == 1


@pytest.mark.parametrize('locale', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_server_dialog_translations_and_mobile_layout(logged_in, product_url, server_host, app, locale, tmp_path):
    page = logged_in
    page.set_viewport_size({'width': 390, 'height': 844})
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    page.add_style_tag(url=product_url + '/static/css/dark.css')
    dialog = open_action(page, 'BACKEND', 'add')
    labels = app.jinja_env.get_template(f'languages/{locale}.html').module.haproxy_stats
    expect(dialog).to_contain_text(labels['server_add'])
    expect(dialog).to_contain_text(labels['server_runtime_hint'])
    box = dialog.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 391
    page.screenshot(path=str(tmp_path / f'add-server-{locale}.png'))
    title = dialog.locator('.ui-dialog-title')
    title_hit = title.evaluate('''node => {
        const r = node.getBoundingClientRect(), hit = document.elementFromPoint(r.x + 3, r.y + 3);
        return {visible: hit === node, hit: hit?.outerHTML, z: getComputedStyle(node.closest('.ui-dialog')).zIndex};
    }''')
    assert title_hit['visible'], title_hit
    for field in dialog.locator('input').all():
        rect = field.bounding_box()
        assert rect['x'] >= box['x'] and rect['x'] + rect['width'] <= box['x'] + box['width']
        if field.get_attribute('type') != 'checkbox':
            expect(field).to_have_css('background-color', 'rgba(0, 0, 0, 0)')
    dialog.get_by_role('button', name=labels['cancel'], exact=True).click()
    assert not server_host.saves
