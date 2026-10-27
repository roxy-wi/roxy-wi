const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../..', 'app/static/js/ha-provider.js'), 'utf8');

function page(option, present = true) {
    const destinations = [];
    const select = {selectedOptions: option ? [option] : []};
    let changed;
    function jQuery(value) {
        if (typeof value === 'function') return value();
        assert.equal(value, select, 'Only the actual DOM select is passed to jQuery');
        return {on: (events, callback) => {
            assert.equal(events, 'selectmenuchange change');
            changed = callback;
        }};
    }
    vm.runInNewContext(source, {
        jQuery, URL,
        document: {getElementById: id => {
            assert.equal(id, 'ha-provider');
            return present ? select : null;
        }},
        window: {location: {origin: 'https://roxy.test', assign: url => destinations.push(url)}},
    });
    return {destinations, change: () => changed?.()};
}

for (const url of ['/pacemaker', '/ha/cluster', '/prefix/pacemaker?cluster=7', 'https://roxy.test/ha/cluster']) {
    const test = page({dataset: {url}, disabled: false});
    test.change();
    assert.deepEqual(test.destinations, [new URL(url, 'https://roxy.test').href]);
}
for (const url of [
    'javascript:alert(document.domain)', 'JaVaScRiPt:alert(1)',
    'data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)',
    'https://other.test/pacemaker', '//other.test/ha/cluster',
    'http://roxy.test/pacemaker', 'https://roxy.test.other.test/',
    'https://roxy.test@other.test/', 'https://[invalid', '',
]) {
    const test = page({dataset: {url}, disabled: false});
    test.change();
    assert.deepEqual(test.destinations, [], `Unsafe destination refused: ${url}`);
}
const disabled = page({dataset: {url: '/ha/cluster'}, disabled: true});
disabled.change();
assert.deepEqual(disabled.destinations, []);
const empty = page(null);
empty.change();
assert.deepEqual(empty.destinations, []);
page(null, false).change();
