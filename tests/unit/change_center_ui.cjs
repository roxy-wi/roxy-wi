// Exercise the page's queue/polling functions with deterministic AJAX and timers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('app/static/js/change-center.js', 'utf8');
const helpers = source.slice(source.indexOf('    function operationActive('), source.indexOf('    function textCell('));
const loader = source.slice(source.indexOf('    function loadChanges('), source.indexOf('    function formatDuration('));
const context = vm.createContext({assert});
vm.runInContext(`
    let allChanges = [], changesById = {}, changesLoaded = false;
    let loadingChanges = false, loadGeneration = 0, activeRequests = 0, actionPoll = null;
    const messages = [], requests = [], timers = new Set();
    let timerId = 0;
    const i18n = {operationQueued: 'Queued', operationSuccess: 'Done', operationFailed: 'Failed'};
    const toastr = Object.fromEntries(['info', 'success', 'error'].map(key => [key, value => messages.push([key, value])]));
    const window = {
        setInterval: () => {timers.add(++timerId); return timerId;},
        clearInterval: id => timers.delete(id)
    };
    const $ = () => ({attr() {return this;}});
    $.getJSON = () => {
        const request = {
            done(fn) {this.onDone = fn; return this;},
            fail(fn) {this.onFail = fn; return this;},
            always(fn) {this.onAlways = fn; return this;},
            resolve(data) {this.onDone({data}); this.onAlways();}
        };
        requests.push(request);
        return request;
    };
    const setListState = () => {}, updateFilterOptions = () => {}, applyFilters = () => {};
    const escapeHtml = text => String(text).replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    ${helpers}
    ${loader}

    const queued = {id: 1, status: 'validated', operation: {id: 12, active: true, status: 'created'}};
    loadChanges();
    loadChanges();
    assert.equal(requests.length, 1, 'Polling must not overlap pending reads');
    assert.equal(rememberQueued({status: 'accepted', data: queued}), true);
    activeRequests = 0;
    syncActionPolling();
    assert.equal(timers.size, 1, 'Finishing HTTP must not stop polling a queued task');
    assert.deepEqual(messages.map(item => item[0]), ['info'], 'Acceptance is not completion');
    requests[0].resolve([]);
    assert.equal(allChanges[0].operation.id, 12, 'A stale list response must not erase acceptance');
    assert.equal(timers.size, 1);

    loadChanges();
    requests[1].resolve([{...queued, status: 'deployed', operation: {id: 12, active: false, status: 'completed'}}]);
    assert.equal(timers.size, 0);
    assert.deepEqual(messages.map(item => item[0]), ['info', 'success']);

    allChanges = [];
    changesById = {};
    loadChanges();
    requests[2].resolve([queued]);
    assert.equal(timers.size, 1, 'Opening a page with active work must start polling');
    loadChanges();
    requests[3].resolve([{...queued, operation: {id: 12, active: false, status: 'failed', error: '<img onerror=alert(1)>'}}]);
    assert.equal(messages.at(-1)[0], 'error');
    assert.equal(messages.at(-1)[1], '&lt;img onerror=alert(1)&gt;');
    assert.equal(timers.size, 0);

    allChanges = [{id: 2, status: 'scheduled'}];
    syncActionPolling();
    assert.equal(timers.size, 1, 'Scheduled work must remain observable when Scheduler starts it');
`, context);
