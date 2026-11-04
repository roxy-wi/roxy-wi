import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('language', ['en', 'ru', 'fr', 'es-ES', 'pt-br', 'zh'])
def test_exporter_check_states_and_stale_responses(app, language):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for browser-script regression tests')
    messages = app.jinja_env.get_template(f'languages/{language}.html').module.exporter_check
    assert all(messages.values())
    source = Path(__file__).resolve().parents[3] / 'app/static/js/install.js'
    harness = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const messages = JSON.parse(process.argv[2]), elements = new Map(), requests = [];
function $(selector) {
    if (typeof selector === 'function') return;
    if (!elements.has(selector)) elements.set(selector, {value: '', text: '', attrs: {}});
    const element = elements.get(selector);
    return {
        val(value) {if (value === undefined) return element.value; element.value = value; return this;},
        text(value) {if (value === undefined) return element.text; element.text = value; return this;},
        attr(key, value) {
            if (typeof key === 'object') Object.assign(element.attrs, key);
            else if (value === undefined) return element.attrs[key];
            else element.attrs[key] = value;
            return this;
        },
        removeAttr(key) {delete element.attrs[key]; return this;}
    };
}
$.ajax = options => {
    assert.strictEqual(options.suppressGlobalError, true, 'Errors are shown inline, without duplicate technical toasts');
    requests.push(options);
    return {abort() {options.error({status: 0}, 'abort');}};
};
$('#exporter-check-messages').text(JSON.stringify(messages));
const context = {$};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
for (const exporter of ['haproxy', 'nginx', 'apache', 'node', 'keepalived', 'ha_cluster']) {
    const select = $('#' + exporter + '_exp_addserv');
    const result = $('#cur_' + exporter + '_exp_ver');
    const check = () => context.showExporterVersion(exporter);
    select.val('192.0.2.11');
    result.attr('title', 'old raw command output');
    check();
    assert.strictEqual(result.text(), messages.checking);
    assert.strictEqual(result.attr('aria-busy'), 'true');
    assert.strictEqual(result.attr('title'), undefined);
    requests.at(-1).success('1.2.3\n');
    assert.strictEqual(result.text(), messages.installed.replace('{version}', '1.2.3'));
    assert.strictEqual(result.attr('aria-busy'), 'false');
    check(); requests.at(-1).success('no');
    assert.strictEqual(result.text(), messages.not_installed);
    for (const output of ['', 'No', 'Permission denied', '<html>Login</html>', '{"error":"private"}']) {
        check(); requests.at(-1).success(output);
        assert.strictEqual(result.text(), messages.failed);
    }
    for (const [status, message] of [[0, messages.failed], [500, messages.failed],
                                    [401, messages.session_expired], [403, messages.forbidden]]) {
        check(); requests.at(-1).error({status, responseText: '<html>private error</html>'});
        assert.strictEqual(result.text(), message);
        assert.strictEqual(result.attr('aria-busy'), 'false');
    }
    // A -> B -> A: checking only the selected IP would accept an obsolete response.
    check(); const old = requests.at(-1);
    select.val('192.0.2.22'); check(); const other = requests.at(-1);
    select.val('192.0.2.11'); check(); const latest = requests.at(-1);
    old.success('1.0.0'); other.error({status: 500});
    assert.strictEqual(result.text(), messages.checking);
    latest.success('2.0.0'); old.error({status: 500});
    assert.strictEqual(result.text(), messages.installed.replace('{version}', '2.0.0'));
    select.val('');
    const count = requests.length;
    check();
    assert.strictEqual(requests.length, count);
    assert.strictEqual(result.text(), messages.select_server);
    latest.success('2.0.0');
    assert.strictEqual(result.text(), messages.select_server);
}
// Different exporters must not cancel each other's checks.
$('#node_exp_addserv').val('192.0.2.11'); context.showExporterVersion('node');
const nodeRequest = requests.at(-1);
$('#nginx_exp_addserv').val('192.0.2.11'); context.showExporterVersion('nginx');
requests.at(-1).success('no'); nodeRequest.success('1.12.0');
assert.strictEqual($('#cur_node_exp_ver').text(), messages.installed.replace('{version}', '1.12.0'));
assert.strictEqual($('#cur_nginx_exp_ver').text(), messages.not_installed);
'''
    result = subprocess.run(
        [node, '-e', harness, str(source), json.dumps(messages)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
