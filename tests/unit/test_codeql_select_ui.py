from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.security
@pytest.mark.parametrize('scenario', ['server', 'credentials_create', 'credentials_update', 'ha'])
@pytest.mark.parametrize('label', ['edge-prod.example.com', '</option><img src=x onerror="alert(1)">\' [name] &'])
def test_select_labels_are_text_and_preserve_option_values(scenario, label):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for browser-script regression tests')
    root = Path(__file__).resolve().parents[2]
    harness = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const root = process.argv[1], scenario = process.argv[2], label = process.argv[3];
const elements = new Map(), requests = [], refreshes = [];
function element() { return {value: '', text: '', attrs: {}, props: {}, children: []}; }
function wrap(items, selector = '') {
    const q = {length: items.length,
        val(value) {if (value === undefined) return items[0]?.value; items.forEach(e => e.value = String(value)); return q;},
        text(value) {if (value === undefined) return items[0]?.text; items.forEach(e => e.text = String(value)); return q;},
        attr(key, value) {if (value === undefined) return items[0]?.attrs[key]; items.forEach(e => e.attrs[key] = String(value)); return q;},
        prop(key, value) {items.forEach(e => e.props[key] = value); return q;},
        append(child) {
            assert(child && typeof child !== 'string', 'Untrusted option passed to an HTML parser');
            items.forEach(e => child.nodes.forEach(n => {e.children.push(n); n.parent = e;})); return q;
        },
        selectmenu(action) {if (action === 'refresh') refreshes.push(selector); return q;},
        filter(callback) {return wrap(items.filter((e, i) => callback.call(e, i, e)));},
        each(callback) {items.forEach((e, i) => callback.call(e, i, e)); return q;},
        remove() {items.forEach(e => e.parent && (e.parent.children = e.parent.children.filter(n => n !== e))); return q;},
        not() {return q;}, is() {return false;},
        nodes: items
    };
    for (const method of ['add', 'removeClass', 'addClass', 'button', 'checkboxradio', 'controlgroup',
                          'dialog', 'show', 'hide', 'css', 'on', 'click']) q[method] = () => q;
    return q;
}
function $(selector) {
    if (typeof selector === 'function' || Array.isArray(selector)) return wrap([]);
    if (typeof selector === 'object') return wrap([selector]);
    if (selector.startsWith('<')) {
        assert.strictEqual(selector, '<option>', 'Untrusted string passed to element constructor');
        return wrap([element()]);
    }
    const options = selector.match(/^(.*?) option(?:\[value=(\d+)\])?$/);
    if (options) {
        let children = $(options[1]).nodes[0].children;
        if (options[2]) children = children.filter(e => e.value === options[2]);
        return wrap(children, selector);
    }
    if (!elements.has(selector)) elements.set(selector, element());
    return wrap([elements.get(selector)], selector);
}
$.ajax = options => requests.push(options);
$.getScript = () => {};
const context = {$, setTimeout() {}, checkLength: () => true, api_prefix: '/api', ha: 'ha.js', cancel_word: 'Cancel',
    translate_div: {attr: () => 'next'}, common_ajax_action_after_success() {},
    toastr: {clear() {}, error(message) {throw Error(message);}}};
vm.createContext(context);
function load(file) {vm.runInContext(fs.readFileSync(root + '/app/static/js/' + file, 'utf8'), context);}
function check(selector, value) {
    const children = $(selector).nodes[0].children;
    assert.strictEqual(children.length, 1, selector + ': exactly one option');
    assert.strictEqual(children[0].text, label);
    assert.strictEqual(children[0].value, String(value));
    assert.strictEqual(children[0].children.length, 0, 'No parsed HTML children');
    assert(refreshes.includes(selector), selector + ': widget refreshed');
    return children[0];
}
if (scenario === 'server') {
    load('admin/server.js');
    $('#new-server-add').val(label); $('#new-ip').val('192.0.2.10');
    $('#credentials').val('4'); $('#new-server-group-add').val('1'); $('#new-port').val('22');
    context.addServer('dialog');
    assert.strictEqual(JSON.parse(requests.at(-1).data).hostname, label);
    requests.at(-1).success({id: 7, data: ''});
    check('select:regex(id, git-server)', 7);
    for (const name of ['backup-server', 'haproxy_exp_addserv', 'nginx_exp_addserv', 'apache_exp_addserv',
                        'node_exp_addserv', 'geoipserv', 'haproxyaddserv', 'nginxaddserv', 'apacheaddserv']) {
        check('select:regex(id, ' + name + ')', '192.0.2.10');
    }
} else if (scenario.startsWith('credentials')) {
    load('admin/ssh.js');
    if (scenario === 'credentials_create') {
        $('#new-ssh-add').val(label); $('#ssh_user').val('test'); $('#new-sshgroup').val('1');
        context.addCreds('dialog');
    } else {
        $('#ssh_name-7').val(label); $('#sshgroup-7').val('1');
        $('select:regex(id, credentials)').append($('<option>').val(7).text('previous'));
        $('select:regex(id, ssh-key-name)').append($('<option>').val(label).text('previous'));
        context.updateSSH(7);
    }
    assert.strictEqual(JSON.parse(requests.at(-1).data).name, label);
    requests.at(-1).success({id: 7, data: ''});
    check('select:regex(id, credentials)', 7);
    check('select:regex(id, ssh-key-name)', scenario === 'credentials_create' ? 7 : label);
} else {
    load('ha.js');
    context.clearClusterDialog = () => {};
    context.get_keepalived_ver = () => {};
    // The available-master response contains another stored label. Edit adds the current master.
    $.ajax = options => {
        requests.push(options);
        if (options.url === '/ha/cluster/masters') {
            options.success([{ip: '192.0.2.20', server_id: 8, hostname: label}]);
        }
    };
    $('#master-server-7').text(label); $('#master-ip-7').text('192.0.2.10'); $('#master-id-7').text('7');
    context.createHaClusterStep1(true, 7, true);
    const children = $('#ha-cluster-master').nodes[0].children;
    assert.strictEqual(children.length, 2);
    assert.strictEqual(children[0].text, label);
    assert.strictEqual(children[0].props.disabled, true);
    assert.strictEqual(children[0].attrs['data-id'], '8');
    assert.strictEqual(children[1].text, label);
    assert.strictEqual(children[1].value, '192.0.2.10');
    assert.strictEqual(children[1].attrs['data-id'], '7');
    assert.strictEqual(children[1].props.selected, true);
    assert(children.every(e => e.children.length === 0));
    assert(refreshes.includes('#ha-cluster-master'));
}
'''
    result = subprocess.run([node, '-e', harness, str(root), scenario, label], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
