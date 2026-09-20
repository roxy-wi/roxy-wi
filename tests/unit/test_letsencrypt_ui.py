import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_le_ui_renders_lifecycle_and_keeps_deletion_pending():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the browser-script regression test')
    source = Path(__file__).resolve().parents[2] / 'app/static/js/ssl.js'
    harness = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const requests = [], appended = [], removed = [], dialogs = [];
const ready = [];
function $(selector) {
    if (typeof selector === 'function') { ready.push(selector); return; }
    return {
        length: selector === '#le_table' ? 1 : 0,
        remove() { removed.push(selector); return this; },
        append(value) { appended.push(value); return this; },
        empty() { return this; }, css() { return this; }, click() { return this; }, on() { return this; },
        dialog(value) { dialogs.push(value); return this; },
        attr() { return 'Create'; }, val() { return ''; }
    };
}
$.ajax = options => { requests.push(options); };
$.getScript = () => {};
const context = { $, document: {hidden: false}, elem: (tag, attrs, children) => ({tag, attrs:attrs || {}, children}),
    setInterval: () => 1, awesome: 'icons', cancel_word: 'Cancel', delete_word: 'Delete',
    toastr: {error() { throw Error('Unexpected error toast'); }}, runInstallationTaskCheck() {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
ready.forEach(callback => callback());
assert(requests.some(request => request.url === '/service/letsencrypts?recurse=True'));
const data = {id: 7, server_id:{hostname:'HA primary'}, type:'cloudflare', domains:['example.com'],
    description:'<img src=x onerror=alert(1)>', state:{status:'queued', legacy_pending:false,
        pem_name:'example.com.pem', next_run_at:'2026-09-20T00:00:00Z', targets:{}, history:[]}};
context.showLe(data);
const row = appended.at(-1);
assert.strictEqual(row.children[0].children, 'HA primary');
assert.strictEqual(row.children[3].children, data.description); // remains text, never HTML
assert.strictEqual(row.children[4].children[0].children, 'queued');
const menu = row.children[6].children[0];
assert.strictEqual(menu.children[0].children[0].attrs.class, 'fas fa-ellipsis-v');
assert(menu.children[1].children.find(button => button.children === 'Edit').disabled);
context.removeLe(7);
const deletion = requests.at(-1);
assert.strictEqual(deletion.method, 'DELETE');
removed.length = 0;
deletion.statusCode[202]();
assert(!removed.includes('#lets-7'));
assert.strictEqual(requests.at(-1).url, '/service/letsencrypts?recurse=True');
context.runLeAction(7, 'test');
assert.strictEqual(requests.at(-1).method, 'PATCH');
assert.strictEqual(JSON.parse(requests.at(-1).data).action, 'test');
'''
    result = subprocess.run([node, '-e', harness, str(source)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
