"""Exercise DOM text boundaries with the real jQuery and element helpers."""

import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import render_template
from playwright.sync_api import expect

from app.modules.roxywi.class_models import ServerRequest


ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.security, pytest.mark.browser, pytest.mark.skipif(
    os.environ.get('ROXYWI_TEST_BROWSER') != '1', reason='Set ROXYWI_TEST_BROWSER=1',
)]
LABELS = ['ordinary name', '''O'Brien "quoted" <img src=x onerror="window.injected=1"> & <svg onload="window.injected=1">''']


def test_map_editor_keeps_filenames_contents_and_statuses_literal(logged_in, product_url, product, monkeypatch):
    filename = "'+(window.injected=1)+[].map+'"
    markup = '<img src=x onerror="window.injected=1">'
    content = f'error: backend_a\n{markup} backend_b\n'
    monkeypatch.setattr('app.routes.add.routes.roxywi_common.get_files', lambda **_: [filename])
    page = logged_in
    page.route('**/add/map?*', lambda route: route.fulfill(content_type='text/plain', body=content))
    page.goto(product_url + '/add/haproxy#maps')
    page.locator('#edit_map').evaluate("node => {node.value = 'previous unsaved edit';}")
    with page.expect_request(lambda request: '/add/map?' in request.url) as request:
        page.locator('.list_maps a').click()
    assert parse_qs(urlsplit(request.value.url).query)['map_name'] == [filename]
    expect(page.locator('#edit_map')).to_have_value(content)
    page.locator('#serv-map').select_option(product.server.ip, force=True)
    statuses = {'PUT': f'success: uploaded to {markup} , error: {markup}', 'DELETE': f'Info: {markup}'}
    page.route('**/add/map', lambda route: route.fulfill(content_type='text/plain', body=statuses[route.request.method]))
    page.evaluate("name => saveMap('save', name)", filename)
    for status in statuses['PUT'].split(' , '):
        expect(page.locator('.toast-message').filter(has_text=status)).to_be_visible()
    page.evaluate('name => deleteMap(name)', filename)
    expect(page.locator('.toast-message').filter(has_text=statuses['DELETE'])).to_be_visible()
    expect(page.locator('.toast-message img')).to_have_count(0)
    assert not page.evaluate('window.injected')


@pytest.fixture
def dom(page):
    page.set_content('<div id="translate"></div><div id="fixture"></div>')
    page.add_script_tag(path=str(ROOT / 'app/static/js/jquery-3.7.1.min.js'))
    page.add_script_tag(path=str(ROOT / 'app/static/js/element.js'))
    page.evaluate("""() => {
        window.Cookies = {get() {return '';}};
        $.ajax = options => { window.lastRequest = options; };
        $.getScript = () => {};
        $.fn.selectmenu = $.fn.checkboxradio = $.fn.button = $.fn.controlgroup =
            $.fn.dialog = $.fn.autocomplete = function () {return this;};
        $.expr.pseudos.regex = (node, index, match) => {
            const [attribute, pattern] = match[3].split(',').map(part => part.trim());
            return new RegExp(pattern).test(node.getAttribute(attribute) || '');
        };
        window.toastr = {clear() {}, error() {}, success() {}};
        window.checkLength = () => true;
        window.makeid = () => 'row1';
        window.common_ajax_action_after_success = () => {};
        window.injected = 0;
    }""")

    def load(script, label):
        page.evaluate("""label => {
            for (const key of ['add', 'delete', 'service', 'start_enter', 'group2', 'server',
                               'port', 'weight', 'if-title', 'then', 'value', 'name']) {
                $('#translate').attr('data-' + key, label);
            }
        }""", label)
        page.add_script_tag(path=str(ROOT / 'app/static/js/variables.js'))
        page.add_script_tag(path=str(ROOT / 'app/static/js' / script))

    yield page, load
    expect(page.locator('#fixture img, #fixture svg, #fixture [onerror]')).to_have_count(0)
    assert page.evaluate('window.injected') == 0


@pytest.mark.parametrize('label', LABELS)
def test_ha_member_round_trip_keeps_labels_inert(dom, label):
    page, load = dom
    page.locator('#fixture').evaluate("""node => {node.innerHTML =
        '<div id="all-checks"><div id="add_check-7"></div></div><div id="enabled-check"></div>';}""")
    page.locator('#add_check-7').evaluate('(node, label) => node.dataset.name = label', label)
    load('ha.js', label)
    page.evaluate("addCheckToStatus(7, '192.0.2.7')")
    expect(page.locator('#remove_check-7 .check-name > div')).to_have_text(label)
    expect(page.locator('#slave_int_div-7')).to_have_attribute('data-ip', '192.0.2.7')
    page.locator('#remove_check-7 .check-button').click()
    expect(page.locator('#add_check-7 .check-name')).to_have_text(label)
    page.locator('#add_check-7 .check-button').click()
    expect(page.locator('#remove_check-7')).to_have_attribute('data-name', label)


@pytest.mark.parametrize('label', LABELS)
def test_user_group_round_trip_preserves_name_role_and_handlers(dom, label):
    page, load = dom
    page.locator('#fixture').evaluate("""node => {node.innerHTML =
        '<table id="all_groups"><tbody></tbody></table><table id="checked_groups"><tbody></tbody></table>';}""")
    load('admin/user.js', label)
    page.evaluate('label => removeGroupFromUser(7, label, label)', label)
    expect(page.locator('#add_group-7 td').first).to_have_text(label)
    page.locator('#add_group-7 span').click()
    expect(page.locator('#remove_group-7 td').first).to_have_text(label)
    page.locator('#add_role-7').select_option('3')
    expect(page.locator('#add_role-7')).to_have_value('3')
    page.locator('#remove_group-7 span').click()
    page.evaluate('addGroupToUser(7, 2)')
    expect(page.locator('#add_role-7')).to_have_value('2')
    expect(page.locator('#remove_group-7')).to_have_attribute('data-group_name', label)


@pytest.mark.parametrize('script,add_function', [
    ('admin/user.js', 'addServiceToUser'), ('admin/server.js', 'addServiceToServer'),
])
@pytest.mark.parametrize('label', LABELS)
def test_service_round_trip_uses_own_callbacks_and_literal_text(dom, script, add_function, label):
    page, load = dom
    page.locator('#fixture').evaluate("""node => {node.innerHTML =
        '<table id="all_services"><tbody><tr id="add_service-7"></tr></tbody></table>' +
        '<table id="checked_services"><tbody></tbody></table>';}""")
    page.locator('#add_service-7').evaluate('(node, label) => node.setAttribute("data-service_name", label)', label)
    load(script, label)
    page.evaluate('name => window[name](7)', add_function)
    expect(page.locator('#remove_service-7 td').first).to_have_text(label)
    page.locator('#remove_service-7 span').click()
    expect(page.locator('#add_service-7 td').first).to_have_text(label)
    page.locator('#add_service-7 span').click()
    expect(page.locator('#remove_service-7')).to_have_attribute('data-service_name', label)


@pytest.mark.parametrize('label', LABELS)
def test_group_options_keep_name_literal_on_create_and_update(dom, label):
    page, load = dom
    page.locator('#fixture').evaluate("""node => {node.innerHTML =
        '<input id="new-group-add"><input id="new-desc"><input id="name-7"><input id="descript-7">' +
        '<select id="server-group"></select>';}""")
    load('admin/group.js', label)
    page.locator('#new-group-add').fill(label)
    page.evaluate("addGroup('dialog'); lastRequest.success({id: 7});")
    expect(page.locator('#server-group option')).to_have_text(label)
    page.locator('#name-7').fill(label)
    page.evaluate('updateGroup(7); lastRequest.success({});')
    expect(page.locator('#server-group option')).to_have_count(1)
    expect(page.locator('#server-group option')).to_have_text(label)


@pytest.mark.parametrize('label', LABELS)
def test_udp_fields_and_translations_are_text(dom, label):
    page, load = dom
    page.locator('#fixture').evaluate("""node => {node.innerHTML = '<button class="add-server"></button>';}""")
    load('udp.js', label)
    page.evaluate('label => createBackendServer(label, 443, 2)', label)
    expect(page.locator('[name="new-udp-server"]')).to_have_value(label)
    expect(page.locator('[name="new-udp-port"]')).to_have_value('443')
    expect(page.locator('[name="new-udp-weight"]')).to_have_value('2')
    page.locator('#fixture .minus').dispatch_event('click')
    expect(page.locator('#fixture .servers')).to_have_count(0)


@pytest.mark.parametrize('label', LABELS)
def test_acl_labels_do_not_become_markup(dom, label):
    page, load = dom
    load('add.js', label)
    page.evaluate("make_actions_for_adding_acl_rule('#fixture')")
    expect(page.locator('#fixture b')).to_have_text([label, label, label, label])
    expect(page.locator('#fixture [name="acl_if"] option')).to_have_count(6)


@pytest.mark.parametrize('label', LABELS)
def test_header_labels_do_not_become_markup(dom, label):
    page, load = dom
    load('add.js', label)
    page.evaluate("make_actions_for_adding_header('#fixture')")
    expect(page.locator('#fixture b')).to_have_text([label, label])
    expect(page.locator('#fixture [name="headers_method"] option')).to_have_count(3)


@pytest.mark.parametrize('selected', [False, True])
@pytest.mark.parametrize('address', ['fe80::1%eth0', "fe80::1%');window.injected=1;('"])
def test_initial_ha_row_passes_validated_address_as_data(app, dom, selected, address):
    page, load = dom
    server = ServerRequest(hostname='test', ip=address, cred_id=1)
    slave = [None] * 33
    slave[0:3] = [7, server.hostname, str(server.ip)]
    slave[31:33] = [False, 'eth0']
    free = SimpleNamespace(server_id=7, hostname=server.hostname, desc='', ip=str(server.ip))
    with app.test_request_context('/'):
        markup = render_template('ajax/ha/slave_servers.html', lang='en',
                                 slaves=[slave] if selected else [], free_servers=[] if selected else [free])
    page.locator('#fixture').evaluate('(node, markup) => node.innerHTML = markup', markup)
    load('ha.js', 'test')
    page.locator('#fixture .check-button').click()
    assert page.evaluate('window.injected') == 0
    if selected:
        page.locator('#fixture .check-button').click()
    expect(page.locator('#slave_int_div-7')).to_have_attribute('data-ip', str(server.ip))
