"""Real Stats UI and routes, replacing only the external HAProxy transport."""
import os
import threading
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from app.modules.db.db_model import Server, Setting, UserGroups
from app.modules.service import haproxy_stats, haproxy_stats_actions
from tests.fixtures.haproxy_stats import INFO, ROWS, FIELDS_28, stats_csv
from tests.fixtures.haproxy_maxconn import maxconn_host  # noqa: F401


pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]


@pytest.fixture
def runtime_host(product, monkeypatch):
    state = SimpleNamespace(rows=[dict(row) for row in ROWS], fields=None, info=INFO, failure=False, calls=[], writes=[], reply='')
    Setting.update(value='1999').where(Setting.param == 'haproxy_sock_port', Setting.group_id == 1).execute()
    def execute(server, port, command):
        state.calls.append((server, command))
        assert port == 1999
        assert command in ('show stat', 'show info')
        if state.failure:
            raise ConnectionRefusedError('synthetic transport unavailable')
        return stats_csv(state.rows, fields=state.fields) if command == 'show stat' else state.info
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', execute)
    def write(server, port, command):
        state.writes.append((server, command))
        assert command.startswith('set server web/one ')
        if not state.reply:
            action, value = command.split()[-2:]
            if action == 'state':
                state.rows[1]['status'] = {'ready': 'UP', 'drain': 'DRAIN', 'maint': 'MAINT'}[value]
            else:
                state.rows[1]['weight'] = int(value)
        return state.reply
    monkeypatch.setattr(haproxy_stats_actions, 'execute_runtime_command', write)
    return state


def select_stats_option(page, control, value):
    label = page.locator(f'#hs-{control} option[value="{value}"]').text_content()
    page.locator(f'#hs-{control}-button').click()
    page.locator(f'#hs-{control}-menu').get_by_role('option', name=label, exact=True).click()


def open_stats(page, product_url):
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    expect(page.locator('.hs-row')).to_have_count(5)
    select_stats_option(page, 'interval', '0')


def test_toolbar_uses_standard_select_styles(logged_in, product_url, runtime_host, tmp_path):
    page = logged_in
    read_style = """el => {
        const style = getComputedStyle(el);
        return Object.fromEntries(['fontFamily', 'fontSize', 'lineHeight',
            'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'borderTopWidth',
            'borderRadius', 'backgroundColor'].map(key => [key, style[key]]));
    }"""
    page.goto(product_url + '/stats/nginx/')
    expect(page.locator('#serv-button')).to_be_visible()
    standard = page.locator('#serv-button').evaluate(read_style)
    standard_text = page.locator('#serv-button .ui-selectmenu-text').evaluate(read_style)
    standard_icon = page.locator('#serv-button .ui-selectmenu-icon').evaluate(read_style)
    open_stats(page, product_url)
    assert page.locator('#hs-server-button').evaluate(read_style) == standard
    assert page.locator('#hs-server-button .ui-selectmenu-text').evaluate(read_style) == standard_text
    assert page.locator('#hs-server-button .ui-selectmenu-icon').evaluate(read_style) == standard_icon
    page.locator('.hs-toolbar').screenshot(path=str(tmp_path / 'stats-toolbar.png'))


@pytest.mark.parametrize('service', ['nginx', 'apache'])
def test_other_stats_load_without_legacy_haproxy_scripts(logged_in, product_url, product, monkeypatch, service):
    from app.modules.service import common
    product.server.apache = 1
    product.server.save()
    content = (b'Active connections: 3\nserver accepts handled requests\n 10 10 20\nReading: 0 Writing: 1 Waiting: 2\n'
               if service == 'nginx' else b'<h1>Apache Server Status</h1><p>Total accesses: 20</p>')
    monkeypatch.setattr(common.requests, 'get', lambda *args, **kwargs: SimpleNamespace(content=content))
    page = logged_in
    page.goto(f'{product_url}/stats/{service}/{product.server.ip}')
    expect(page.locator('#service-stats-content')).to_contain_text('Active connections' if service == 'nginx' else 'Total accesses')
    expect(page.locator('h2').first).to_be_visible()
    expect(page.locator('#stats_filter')).to_have_count(0)
    page.locator('#show').click()
    expect(page.locator('#service-stats-content')).to_contain_text('Waiting' if service == 'nginx' else 'Total accesses')


def test_stats_filters_columns_details_and_refresh_preserve_view(logged_in, product_url, runtime_host, tmp_path):
    page = logged_in
    open_stats(page, product_url)
    expect(page.locator('#hs-summary')).to_contain_text('7 / 2,000')
    web = page.locator('.hs-group').filter(has=page.locator('summary', has_text='web'))
    web.get_by_role('button', name='Details: web/one', exact=True).click()
    expect(web.locator('.hs-detail-grid:visible')).to_contain_text('HTTP check passed')
    runtime_host.rows[1]['scur'] = 9
    page.locator('#hs-refresh').click()
    expect(web.locator('.hs-row').filter(has_text='one').locator('[data-column=sessions]')).to_have_text('9 / 100')
    expect(web.get_by_role('button', name='Details: web/one', exact=True)).to_have_attribute('aria-expanded', 'true')
    page.locator('#hs-search').fill('2001:db8')
    expect(page.locator('.hs-row:visible')).to_have_count(1)
    page.locator('#hs-search').fill('')
    page.locator('#hs-backup').check()
    expect(page.locator('.hs-row:visible')).to_have_count(1)
    page.locator('#hs-backup').uncheck()
    page.locator('#hs-problems').check()
    expect(page.locator('.hs-row:visible')).to_have_count(1)
    page.locator('#hs-problems').uncheck()
    page.locator('#hs-kind').select_option('server')
    expect(page.locator('.hs-row:visible')).to_have_count(3)
    page.locator('#hs-state').select_option('no_check')
    expect(page.locator('.hs-row:visible')).to_have_count(1)
    expect(page.locator('.hs-row:visible [data-column=requests]')).to_have_text('—')
    page.locator('#hs-kind').select_option('all')
    page.locator('#hs-state').select_option('all')
    page.locator('.hs-columns > summary').click()
    page.locator('#hs-column-options').get_by_label('Address', exact=True).check()
    page.locator('.hs-columns > summary').click()
    expect(page.locator('.hs-row:visible [data-column=address]')).to_have_count(5)
    web.locator(':scope > summary').click()
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert web.get_attribute('open') is None
    web.locator(':scope > summary').click()
    page.screenshot(path=str(tmp_path / 'stats-desktop.png'), full_page=True, animations='disabled')
    page.reload()
    expect(page.locator('.hs-row [data-column=address]:visible')).to_have_count(5)


def test_stats_stale_recovery_reload_and_empty_snapshot(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    runtime_host.failure = True
    page.locator('#hs-refresh').click()
    expect(page.locator('#haproxy-stats')).to_have_attribute('data-stale', 'true')
    expect(page.locator('#hs-error')).to_contain_text('Data is stale')
    expect(page.locator('.hs-row')).to_have_count(5)
    runtime_host.failure = False
    runtime_host.info = INFO.replace('Pid: 100', 'Pid: 200').replace('3600', '2')
    runtime_host.rows[1]['stot'] = 0
    page.locator('#hs-refresh').click()
    expect(page.locator('#hs-error')).to_be_hidden()
    expect(page.locator('#hs-status')).to_contain_text('HAProxy restarted')
    runtime_host.rows = []
    page.locator('#hs-refresh').click()
    expect(page.locator('.hs-row')).to_have_count(0)
    expect(page.locator('#hs-empty')).to_be_visible()


def test_stats_initial_failure_and_unsafe_names_are_text(logged_in, product_url, runtime_host, tmp_path):
    page = logged_in
    runtime_host.failure = True
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    select_stats_option(page, 'interval', '0')
    expect(page.locator('#hs-error')).to_be_visible()
    expect(page.locator('#hs-summary')).to_be_hidden()
    runtime_host.failure = False
    runtime_host.rows[1]['svname'] = '<img src=x onerror="window.statsInjection=true">'
    runtime_host.rows[1]['last_chk'] = '<script>window.statsInjection=true</script>'
    page.locator('#hs-refresh').click()
    expect(page.locator('.hs-row')).to_have_count(5)
    row = page.locator('.hs-row').filter(has_text='<img src=x')
    row.locator('.hs-detail-button').click()
    expect(page.locator('#hs-groups img, #hs-groups script')).to_have_count(0)
    assert page.evaluate('window.statsInjection') is None
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('.container')).to_have_css('margin-left', '0px')
    page.screenshot(path=str(tmp_path / 'stats-mobile.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


@pytest.mark.parametrize('locale,refresh_label', [
    ('en', 'Refresh'), ('ru', 'Обновить'), ('fr', 'Actualiser'),
    ('es-ES', 'Actualizar'), ('pt-br', 'Atualizar'), ('zh', '刷新'),
])
def test_stats_locales_in_dark_theme(logged_in, product_url, runtime_host, tmp_path, locale, refresh_label):
    page = logged_in
    page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
    open_stats(page, product_url)
    expect(page.locator('#hs-refresh')).to_have_text(refresh_label)
    page.add_style_tag(url=product_url + '/static/css/dark.css')
    expect(page.locator('#hs-summary .hs-card').first).to_have_css('background-color', 'rgb(31, 31, 31)')
    expect(page.locator('#haproxy-stats')).to_have_css('color', 'rgb(240, 240, 240)')
    page.get_by_role('button', name=f"{ {'en': 'Details', 'ru': 'Подробнее', 'fr': 'Détails', 'es-ES': 'Detalles', 'pt-br': 'Detalhes', 'zh': '详情'}[locale] }: web/one", exact=True).click()
    page.locator('.hs-metric-help[data-metric=qtime]').focus()
    expect(page.get_by_role('tooltip')).to_contain_text('1024')
    page.keyboard.press('Escape')
    page.screenshot(path=str(tmp_path / f'stats-dark-{locale}.png'), full_page=True, animations='disabled')


def test_switch_server_discards_inflight_snapshot(logged_in, product_url, product, runtime_host, monkeypatch):
    Server.create(server_id=33, hostname='Second HAProxy', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    page = logged_in
    entered, release = threading.Event(), threading.Event()
    def execute(server, port, command):
        if server == '192.0.2.11' and not release.is_set():
            entered.set()
            assert release.wait(10), 'Test did not release the first server'
        rows = [{**ROWS[1], 'svname': server}]
        return stats_csv(rows) if command == 'show stat' else INFO
    monkeypatch.setattr(haproxy_stats, 'execute_runtime_command', execute)
    try:
        page.goto(product_url + '/stats/haproxy/192.0.2.11')
        assert entered.wait(5)
        select_stats_option(page, 'server', '192.0.2.33')
        expect(page.locator('.hs-row')).to_have_count(1)
        expect(page.locator('.hs-name')).to_contain_text('192.0.2.33')
    finally:
        release.set()
    expect(page.locator('.hs-name')).not_to_contain_text('192.0.2.11')
    expect(page).to_have_url(product_url + '/stats/haproxy/192.0.2.33')


def test_auto_refresh_has_one_request_and_pause_stops_polling(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    page.clock.install()
    runtime_host.calls.clear()
    select_stats_option(page, 'interval', '5')
    with page.expect_response('**/stats/view/haproxy/*'):
        page.clock.fast_forward(5000)
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(runtime_host.calls) == 3
    select_stats_option(page, 'interval', '0')
    count = len(runtime_host.calls)
    page.clock.fast_forward(30000)
    assert len(runtime_host.calls) == count


def test_default_refresh_waits_thirty_seconds(logged_in, product_url, runtime_host):
    page = logged_in
    page.clock.install()
    page.goto(product_url + '/stats/haproxy/192.0.2.11')
    expect(page.locator('.hs-row')).to_have_count(5)
    expect(page.locator('#hs-interval')).to_have_value('30')
    expect(page.locator('#hs-interval-button')).to_contain_text('30')
    runtime_host.calls.clear()
    page.clock.fast_forward(29000)
    assert runtime_host.calls == []
    with page.expect_response('**/stats/view/haproxy/*'):
        page.clock.fast_forward(1000)
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(runtime_host.calls) == 3


def test_field_help_covers_runtime_columns_and_survives_refresh(logged_in, product_url, runtime_host, tmp_path):
    page = logged_in
    page.clock.install()
    runtime_host.fields = FIELDS_28 + ['future_metric']
    runtime_host.rows[1]['qtime_max'] = 42
    open_stats(page, product_url)
    select_stats_option(page, 'interval', '30')
    row = page.locator('.hs-row[data-kind=server]').filter(has_text='one')
    row.locator('.hs-detail-button').click()
    detail = row.locator('xpath=following-sibling::tr[1]')
    expect(detail.locator('.hs-metric-help')).to_have_count(len(FIELDS_28))  # '-' omitted; one future field.
    descriptions = detail.locator('.hs-metric-help').evaluate_all('''buttons => buttons.map(button => {
        button.focus();
        return {key: button.dataset.metric, text: document.getElementById('hs-metric-tooltip').textContent};
    })''')
    assert all(value['text'] and 'not yet described' not in value['text'] for value in descriptions if value['key'] != 'future_metric')
    assert 'not yet described' in next(value['text'] for value in descriptions if value['key'] == 'future_metric')
    metric = detail.locator('[data-metric=qtime_max]')
    metric.focus()
    tooltip = page.get_by_role('tooltip')
    expect(tooltip).to_contain_text('Longest observed queue wait')
    expect(metric).to_have_attribute('aria-describedby', 'hs-metric-tooltip')
    expect(metric.locator('xpath=../following-sibling::dd')).to_have_text('42 ms')
    page.screenshot(path=str(tmp_path / 'stats-tooltip.png'), full_page=True, animations='disabled')
    # Exercise a real scheduled poll without moving keyboard focus.
    with page.expect_response('**/stats/view/haproxy/*'):
        page.clock.fast_forward(30000)
    expect(page.locator('#hs-refresh')).to_be_enabled()
    expect(metric).to_be_focused()
    expect(tooltip).to_be_visible()
    page.keyboard.press('Escape')
    expect(tooltip).to_be_hidden()
    metric.blur()
    metric.hover()
    expect(tooltip).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    metric.click()
    bounds = tooltip.bounding_box()
    assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= 390
    page.locator('#hs-search').fill('nothing-matches')
    expect(tooltip).to_be_hidden()


def test_type_colors_and_page_spacing_in_both_themes(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    root = page.locator('#haproxy-stats')
    expect(root).to_have_css('padding-left', '15px')
    expect(root).to_have_css('padding-right', '15px')
    selectors = ['[data-kind=frontend]', '[data-kind=backend]', '[data-kind=server][data-backup=false]', '[data-kind=server][data-backup=true]']
    colors = lambda: [page.locator('.hs-row' + selector + ' > td').first.evaluate('(cell) => getComputedStyle(cell).backgroundColor') for selector in selectors]
    light = colors()
    assert len(set(light)) == 4
    page.add_style_tag(url=product_url + '/static/css/dark.css')
    dark = colors()
    assert len(set(dark)) == 4
    assert all(before != after for before, after in zip(light, dark))


def open_server_action(page, action):
    row = page.locator('.hs-row[data-kind=server]').filter(has_text='one')
    row.locator('.admin-actions-toggle').click()
    row.locator(f'[data-action={action}]').click()
    expect(row.get_by_role('menu')).to_be_hidden()
    expect(row.locator('.admin-actions-toggle')).to_have_attribute('aria-expanded', 'false')
    return row


def open_global_maxconn(page):
    actions = page.locator('#hs-global-actions')
    page.add_style_tag(content='* {scroll-behavior:auto !important; transition:none !important;}')
    actions.locator('.admin-actions-toggle').scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    actions.locator('.admin-actions-toggle').click()
    expect(actions.get_by_role('menuitem')).to_have_count(1)
    actions.locator('#hs-global-maxconn').click()
    expect(actions.get_by_role('menu')).to_be_hidden()
    expect(actions.locator('.admin-actions-toggle')).to_have_attribute('aria-expanded', 'false')


@pytest.mark.parametrize('theme,width', [('light', 1440), ('dark', 1440), ('light', 390), ('dark', 390)])
def test_summary_is_compact_with_status_colors_and_shared_menu(logged_in, product_url, runtime_host, tmp_path, theme, width):
    page = logged_in
    page.set_viewport_size({'width': width, 'height': 844})
    runtime_host.rows[1]['status'] = 'MAINT'
    runtime_host.rows[4]['status'] = 'DRAIN'
    open_stats(page, product_url)
    if theme == 'dark':
        page.add_style_tag(url=product_url + '/static/css/dark.css')
    toolbar, updated = page.locator('.hs-toolbar').bounding_box(), page.locator('#hs-status').bounding_box()
    assert 0 <= updated['y'] - toolbar['y'] - toolbar['height'] <= 2
    expect(page.locator('#hs-status')).to_have_css('padding-top', '8px')
    for card in page.locator('.hs-card').all():
        assert card.bounding_box()['height'] <= 85
    for state in ('down', 'maint', 'drain'):
        label = page.locator(f'[data-card=down] .hs-card-label .hs-state-{state}')
        value = page.locator(f'[data-card=down] strong .hs-state-{state}')
        row = page.locator(f'.hs-row .hs-state-{state}')
        color = row.evaluate('el => getComputedStyle(el).color')
        expect(label).to_have_css('color', color)
        expect(value).to_have_css('color', color)
        expect(value).to_have_text('1')
    runtime_host.rows[1]['status'] = 'DOWN'
    page.locator('#hs-refresh').click()
    expect(page.locator('[data-card=down] strong .hs-state-down')).to_have_text('2')
    expect(page.locator('[data-card=down] strong .hs-state-maint')).to_have_text('0')
    expect(page.locator('#hs-global-maxconn')).to_be_hidden()
    toggle = page.locator('#hs-global-actions .admin-actions-toggle')
    page.add_style_tag(content='* {scroll-behavior:auto !important; transition:none !important;}')
    toggle.scroll_into_view_if_needed()
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expect(toggle.locator('svg')).to_be_visible()
    toggle.click()
    menu = page.locator('#hs-global-actions').get_by_role('menu')
    expect(menu).to_be_visible()
    bounds = menu.bounding_box()
    assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= width
    expect(menu.get_by_role('menuitem')).to_have_css('border-top-width', '0px')
    page.screenshot(path=str(tmp_path / f'stats-compact-{theme}-{width}.png'))
    page.keyboard.press('Escape')
    expect(menu).to_be_hidden()


@pytest.mark.parametrize('action,status', [('ready', 'UP'), ('drain', 'DRAIN'), ('maint', 'MAINT')])
def test_row_state_action_confirms_and_refreshes(logged_in, product_url, runtime_host, action, status):
    page = logged_in
    open_stats(page, product_url)
    expect(page.locator('.hs-row[data-kind=frontend] .admin-actions-toggle')).to_have_count(1)
    expect(page.locator('.hs-row[data-kind=frontend] [data-action=ready]')).to_have_count(0)
    expect(page.locator('.hs-row[data-kind=backend] .admin-actions-toggle')).to_have_count(0)
    row = open_server_action(page, action)
    dialog = page.get_by_role('dialog')
    expect(dialog).to_contain_text('web/one')
    expect(dialog).to_contain_text('do not change the configuration')
    assert runtime_host.writes == []
    dialog.get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('Change applied')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    expect(row.locator('[data-column=status]')).to_have_text(status)
    assert runtime_host.writes == [('192.0.2.11', f'set server web/one state {action}')]


def test_weight_validation_cancel_and_zero(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    open_server_action(page, 'weight')
    dialog = page.get_by_role('dialog')
    expect(dialog.get_by_role('spinbutton')).to_have_value('100')
    dialog.get_by_role('spinbutton').fill('257')
    dialog.get_by_role('button', name='Apply', exact=True).click()
    expect(dialog).to_be_visible()
    assert runtime_host.writes == []
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    expect(dialog).to_have_count(0)
    assert runtime_host.writes == []
    row = open_server_action(page, 'weight')
    page.get_by_role('spinbutton').fill('0')
    page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
    expect(row.locator('[data-column=weight]')).to_have_text('0')
    assert runtime_host.writes == [('192.0.2.11', 'set server web/one weight 0')]


def test_rejected_action_is_visible_and_not_retried(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    runtime_host.reply = 'Permission denied\n'
    row = open_server_action(page, 'maint')
    page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('requires admin access')
    expect(page.locator('#hs-action-result')).to_have_attribute('data-error', 'true')
    expect(row.locator('[data-column=status]')).to_have_text('UP')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(runtime_host.writes) == 1


def test_reload_while_confirming_prevents_write(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    open_server_action(page, 'drain')
    runtime_host.info = INFO.replace('Pid: 100', 'Pid: 200')
    page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('process or server changed')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert runtime_host.writes == []


def test_actions_pause_polling_and_are_disabled_for_stale_data(logged_in, product_url, runtime_host):
    page = logged_in
    open_stats(page, product_url)
    page.clock.install()
    select_stats_option(page, 'interval', '5')
    open_server_action(page, 'drain')
    runtime_host.calls.clear()
    page.clock.fast_forward(20000)
    assert runtime_host.calls == []
    page.keyboard.press('Escape')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    runtime_host.failure = True
    page.locator('#hs-refresh').click()
    expect(page.locator('#haproxy-stats')).to_have_attribute('data-stale', 'true')
    for button in page.locator('.hs-row .admin-actions-toggle').all():
        expect(button).to_be_disabled()
    expect(page.locator('#hs-global-actions .admin-actions-toggle')).to_be_disabled()
    expect(page.locator('#hs-global-maxconn')).to_be_disabled()
    assert runtime_host.writes == []


def test_reader_has_no_action_menu(logged_in, product_url, product, runtime_host):
    UserGroups.update(user_role_id=4).where(UserGroups.user_id == product.admin.user_id).execute()
    open_stats(logged_in, product_url)
    expect(logged_in.locator('.admin-actions-toggle')).to_have_count(0)
    expect(logged_in.locator('#hs-global-maxconn')).to_have_count(0)
    expect(logged_in.locator('.hs-read-only')).to_have_text('Read only')


def test_late_action_reply_does_not_change_selected_host(logged_in, product_url, product, runtime_host, monkeypatch):
    Server.create(server_id=33, hostname='Second HAProxy', ip='192.0.2.33', group_id='1', cred_id=11, haproxy=1)
    entered, release = threading.Event(), threading.Event()
    def write(server, port, command):
        runtime_host.writes.append((server, command))
        entered.set()
        assert release.wait(10)
        return ''
    monkeypatch.setattr(haproxy_stats_actions, 'execute_runtime_command', write)
    page = logged_in
    open_stats(page, product_url)
    try:
        open_server_action(page, 'drain')
        page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
        assert entered.wait(5)
        expect(page.locator('.hs-row .admin-actions-toggle').first).to_be_disabled()
        select_stats_option(page, 'server', '192.0.2.33')
        expect(page.locator('#hs-refresh')).to_be_enabled()
        with page.expect_response('**/stats/server/haproxy/192.0.2.11'):
            release.set()
        expect(page.locator('#hs-action-result')).to_be_hidden()
        expect(page).to_have_url(product_url + '/stats/haproxy/192.0.2.33')
    finally:
        release.set()
    assert runtime_host.writes == [('192.0.2.11', 'set server web/one state drain')]


def test_menu_uses_shared_styles_and_fits_mobile_in_both_themes(logged_in, product_url, runtime_host, tmp_path):
    page = logged_in
    open_stats(page, product_url)
    page.add_style_tag(content='* {scroll-behavior: auto !important; transition: none !important;}')
    for theme in ('light', 'dark'):
        if theme == 'dark':
            page.add_style_tag(url=product_url + '/static/css/dark.css')
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 844})
            row = page.locator('.hs-row[data-kind=server]').filter(has_text='one')
            row.locator('.admin-actions-toggle').scroll_into_view_if_needed()
            # Let viewport and scrolling events close the previous menu before opening.
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            expect(row.locator('.admin-actions-toggle svg')).to_be_visible()
            expect(row.locator('.hs-detail-button')).to_have_css('border-top-width', '0px')
            row.locator('.admin-actions-toggle').click()
            menu = row.get_by_role('menu')
            expect(menu).to_be_visible()
            bounds = menu.bounding_box()
            assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= width
            expect(menu.get_by_role('menuitem', name='Ready', exact=True)).to_have_css('border-top-width', '0px')
            page.screenshot(path=str(tmp_path / f'stats-actions-{theme}-{width}.png'))
            page.keyboard.press('Escape')


def test_runtime_console_links_moved_commands_to_stats(logged_in, product_url, product, monkeypatch):
    monkeypatch.setattr('app.modules.service.haproxy.runtime_command',
                        lambda *args: pytest.fail('Moved command reached transport'))
    page = logged_in
    page.goto(product_url + '/runtimeapi')
    expect(page.get_by_text('Server state, weight and Maxconn are now managed', exact=False)).to_have_count(0)
    page.locator('#serv').select_option(product.server.ip, force=True)
    page.locator('#servaction').select_option('set', force=True)
    page.locator('#servbackend').fill('server web/one state drain')
    page.locator('#runtimeapiform').evaluate('form => $(form).trigger("submit")')
    expect(page.locator('#ajaxruntime')).to_contain_text('now managed from the row menu')
    expect(page.locator('#ajaxruntime a')).to_have_attribute('href', f'/stats/haproxy/{product.server.ip}')


@pytest.mark.parametrize('scope,initial,value', [('server', '100', '150'), ('frontend', '2000', '1800'), ('global', '2000', '1900')])
def test_maxconn_dialog_applies_to_all_nodes_and_saves_config(logged_in, product_url, maxconn_host, scope, initial, value):
    page = logged_in
    open_stats(page, product_url)
    if scope == 'global':
        open_global_maxconn(page)
    elif scope == 'server':
        open_server_action(page, 'maxconn')
    else:
        row = page.locator('.hs-row[data-kind=frontend]')
        row.locator('.admin-actions-toggle').click()
        expect(row.get_by_role('menuitem')).to_have_count(1)
        row.locator('[data-action=maxconn]').click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_contain_text('192.0.2.11')
    expect(dialog).to_contain_text('Replica — 192.0.2.33')
    expect(dialog).to_contain_text('without a reload')
    expect(dialog.get_by_role('spinbutton')).to_have_value(initial)
    assert maxconn_host.writes == []
    dialog.get_by_role('spinbutton').fill(value)
    dialog.get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('configuration saved on all nodes')
    expect(page.locator('#hs-action-result')).to_contain_text('192.0.2.33: Runtime — applied; Configuration — saved')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(maxconn_host.writes) == len(maxconn_host.saves) == 2


def test_maxconn_cancel_invalid_value_and_partial_result(logged_in, product_url, maxconn_host):
    page = logged_in
    open_stats(page, product_url)
    maxconn_host.info['192.0.2.11'] = maxconn_host.info['192.0.2.11'].replace('Maxconn: 2000', 'Maxconn: 1900')
    page.locator('#hs-refresh').click()
    expect(page.locator('[data-card=connections] strong')).to_have_text('7 / 1,900')
    open_global_maxconn(page)
    dialog = page.get_by_role('dialog')
    expect(dialog.get_by_role('spinbutton')).to_have_value('1900')
    dialog.get_by_role('spinbutton').fill('2001')
    dialog.get_by_role('button', name='Apply', exact=True).click()
    expect(dialog).to_be_visible()
    dialog.get_by_role('button', name='Cancel', exact=True).click()
    assert maxconn_host.writes == []
    maxconn_host.fail_save = '192.0.2.33'
    open_server_action(page, 'maxconn')
    page.get_by_role('spinbutton').fill('0')
    page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_have_attribute('data-error', 'true')
    expect(page.locator('#hs-action-result')).to_contain_text('192.0.2.11: Runtime — applied; Configuration — saved')
    expect(page.locator('#hs-action-result')).to_contain_text('192.0.2.33: Runtime — applied; Configuration — not confirmed')
    expect(page.locator('#hs-refresh')).to_be_enabled()
    assert len(maxconn_host.writes) == 2


def test_maxconn_ui_locales_and_mobile(logged_in, product_url, maxconn_host, tmp_path):
    page = logged_in
    for locale in ('en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'):
        page.context.add_cookies([{'name': 'lang', 'value': locale, 'url': product_url}])
        open_stats(page, product_url)
        page.set_viewport_size({'width': 390, 'height': 844})
        open_global_maxconn(page)
        dialog = page.get_by_role('dialog')
        expect(dialog).to_contain_text('192.0.2.33')
        bounds = dialog.bounding_box()
        assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= 390
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert 'undefined' not in dialog.text_content()
        page.screenshot(path=str(tmp_path / f'maxconn-{locale}-mobile.png'))
        page.keyboard.press('Escape')
    assert not maxconn_host.writes


def test_runtime_maxconn_tab_and_handlers_removed(logged_in, product_url, product, monkeypatch):
    page = logged_in
    monkeypatch.setattr('app.modules.service.haproxy.runtime_command', lambda *args: pytest.fail('Legacy Maxconn executed'))
    page.goto(product_url + '/runtimeapi')
    expect(page.locator('a[href="#maxconn"]')).to_have_count(0)
    expect(page.locator('#maxconn')).to_have_count(0)
    page.locator('#serv').select_option(product.server.ip, force=True)
    page.locator('#servaction').select_option('set', force=True)
    page.locator('#servbackend').fill('maxconn global 1000')
    page.locator('#runtimeapiform').evaluate('form => $(form).trigger("submit")')
    expect(page.locator('#ajaxruntime')).to_contain_text('Maxconn')
    expect(page.locator('#ajaxruntime a')).to_have_attribute('href', f'/stats/haproxy/{product.server.ip}')


def test_global_maxconn_edit_section_shows_value_saved_from_stats(logged_in, product_url, product, maxconn_host):
    from app.modules.db import add as add_sql
    from app.modules.roxywi.class_models import HaproxyGlobalRequest
    add_sql.insert_or_update_new_section(product.server.server_id, 'global', 'global', HaproxyGlobalRequest(maxconn=5000, daemon=True))
    page = logged_in
    open_stats(page, product_url)
    open_global_maxconn(page)
    page.get_by_role('dialog').get_by_role('spinbutton').fill('1900')
    page.get_by_role('dialog').get_by_role('button', name='Apply', exact=True).click()
    expect(page.locator('#hs-action-result')).to_contain_text('configuration saved on all nodes')
    page.goto(product_url + f'/config/haproxy/{product.server.ip}/show')
    section = page.locator('.cv-section').filter(has=page.locator('.cv-title', has_text='global'))
    expect(section).to_be_visible()
    if not section.evaluate('node => node.open'):
        section.locator('summary').click()
    section.locator('.cv-edit-section').click()
    expect(page.locator('#edit-section')).to_be_visible()
    expect(page.locator('#edit-global input[name=maxconn]')).to_have_value('1900')
