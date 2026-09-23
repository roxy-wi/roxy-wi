from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.security
def test_certificate_list_treats_remote_names_as_text_and_encodes_requests():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for browser-script regression tests')
    source = Path(__file__).resolve().parents[2] / 'app/static/js/ssl.js'
    harness = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const ready = [], requests = [], toasts = [], elements = new Map();
function escapeHtml(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function element(tag = '') {
    return {tag, length: 0, children: [], attributes: {}, events: {}, value: '',
        click(callback) {this.events.click = callback; return this;},
        on(name, callback) {this.events[name] = callback; return this;},
        text(value) {this.textContent = value; return this;},
        attr(name, value) { if (value === undefined) return this.attributes[name] || ''; this.attributes[name] = value; return this;},
        val() {return this.value;},
        addClass(value) {this.attributes.class = value; return this;},
        append(child) {this.children.push(child); return this;},
        empty() {this.children = []; return this;},
        trigger(name) {this.events[name](); return this;},
        html(value) {assert.strictEqual(value, undefined, 'Untrusted certificate names entered an HTML sink'); return escapeHtml(this.textContent);}
    };
}
function $(selector) {
    if (typeof selector === 'function') {ready.push(selector); return;}
    if (selector.startsWith('<')) {assert(['<a>', '<span>', '<div>'].includes(selector)); return element(selector);}
    if (!elements.has(selector)) elements.set(selector, element());
    return elements.get(selector);
}
$.ajax = options => requests.push(options);
const context = {$, checkIsServerFiled: () => true, translate_div: {attr: () => 'Raw'},
    toastr: {success: value => toasts.push(value), error: value => toasts.push(value), clear() {}},
    document: {hidden: false}, setInterval() {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
ready.forEach(callback => callback());
$('#serv5').value = '12';
$('#ssl_key_view').trigger('click');
const malicious = '  <img src=x onerror="alert(1)">\');alert(2);//.pem';
requests.at(-1).success(malicious + '\nordinary.pem\n');
const list = $('#ajax-show-ssl').children;
assert.strictEqual(list.length, 2);
const link = list[0].children[0];
assert.strictEqual(link.textContent, malicious);
assert.strictEqual(link.attributes.title, 'View ' + malicious + ' cert');
assert.strictEqual(link.attributes.onclick, undefined);
link.events.click();
assert.strictEqual(requests.at(-1).url, '/add/cert/12/' + encodeURIComponent(malicious));
context.showRawSSL(malicious);
assert.strictEqual(requests.at(-1).url, '/add/cert/get/raw/12/' + encodeURIComponent(malicious));
context.deleteSsl(malicious);
assert.strictEqual(requests.at(-1).url, '/add/cert/12/' + encodeURIComponent(malicious));
requests.at(-1).success('deleted');
assert(!toasts.at(-1).includes('<img'));
requests.at(-1).success('error: ' + malicious);
assert(!toasts.at(-1).includes('<img'));
'''
    subprocess.run([node, '-e', harness, str(source)], check=True, capture_output=True, text=True)
