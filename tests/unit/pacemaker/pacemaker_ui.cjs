// Exercise crm_mon text booleans and the widget lifecycle when reviewing a draft.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../..', 'app/static/js/pacemaker.js'), 'utf8');
function section(start, end) { return source.slice(source.indexOf(start), source.indexOf(end)); }
class Element {
    constructor(tagName = 'div') { this.tagName = tagName.toUpperCase(); this.children = []; this.rows = []; this.dataset = {}; this.textContent = ''; }
    append(...children) { this.children.push(...children); }
    insertRow() { const row = new Element('tr'); this.rows.push(row); return row; }
    insertCell() { const cell = new Element('td'); this.children.push(cell); return cell; }
    replaceChildren() { this.children = []; this.rows = []; }
    setAttribute() {}
    addEventListener() {}
    scrollIntoView() {}
}
const elements = new Map();
const byId = id => {
    if (!elements.has(id)) elements.set(id, new Element(id === 'cluster' ? 'select' : 'button'));
    return elements.get(id);
};
const widgetCalls = [];
function jQuery(element) {
    return Object.fromEntries(['button', 'selectmenu'].map(widget => [widget, (...args) => {
        widgetCalls.push([element, widget, ...args]);
        if (args[0] === 'option' && args[1] === 'disabled') element.disabled = args[2];
    }]));
}
// Legacy fragments now resolve to real service pages and retain the selected cluster.
const destinations = [];
const navWindow = {location: {hash: '#configuration', origin: 'http://roxy.test', replace: url => destinations.push(url)}};
const navContext = vm.createContext({window: navWindow, URL, selected: {id: 7}});
vm.runInContext(section('    function pageURL(', '    function quorumNotice('), navContext);
vm.runInContext('navigateSection()', navContext);
assert.equal(destinations.at(-1), '/pacemaker/configuration?cluster=7');
navWindow.location.hash = '#logs'; vm.runInContext('navigateSection()', navContext);
assert.equal(destinations.at(-1), '/pacemaker/logs?cluster=7');
navWindow.location.hash = '#quorum'; vm.runInContext('navigateSection()', navContext);
assert.equal(destinations.at(-1), '/pacemaker/quorum?cluster=7');
const count = destinations.length;
navWindow.location.hash = '#unknown'; vm.runInContext('navigateSection()', navContext);
assert.equal(destinations.length, count);
assert.equal(vm.runInContext("pageURL('setup', {setup:'new'})", navContext), '/ha/cluster?cluster=7&setup=new');

let response;
const context = vm.createContext({assert, byId, jQuery, URL,
    window: {location: {origin: 'http://roxy.test'}, history: {replaceState: () => {}}},
    document: {createElement: tag => new Element(tag)},
    guard: fn => fn, api: async () => ({data: response}), history: async () => {},
    path: suffix => suffix, message: () => {}, operator: true, view: 'configuration', selected: {id: 1, members: [{name: 'node-1'}]}});
vm.runInContext(`let digest, changeId, changeKind;
    let refreshing = false, polling = false, clusters = [{id: 1}];
    ${section('    function button(', '    function path(')}
    ${section('    async function refresh()', '    async function history()')}
    ${section('    async function showChange(', '    let memberSequence')}
    ${section('    function editorChanged()', '    async function loadClusters(')}
`, context);
(async () => {
    response = {quorate: true, nodes: [{name: '<img src=x>', online: 'true', standby: 'false', maintenance: false, unclean: 'false'}],
        resources: [{id: 'vip', resource_agent: 'ocf:heartbeat:IPaddr2', nodes: ['node-1'], failed: 'false', blocked: 'false'}]};
    await vm.runInContext('refresh()', context);
    const nodeCells = byId('nodes').rows[0].children;
    assert.equal(nodeCells[0].textContent, '<img src=x>', 'Node labels remain literal text');
    assert.equal(nodeCells[2].children[0].textContent, 'No', 'String false is not an active standby state');
    assert.equal(nodeCells[4].children[0].className, 'rw-status-badge rw-status-running');
    assert.equal(byId('resources').rows[0].children[4].children[0].textContent, 'Healthy');
    vm.runInContext("selected.members = [{name:'n1'}, {name:'n2'}]; quorumNotice({quorum_details:{configured:false,votes:0}})", context);
    assert.equal(byId('quorum-note').hidden, false);
    assert.match(byId('quorum-description').textContent, /without an external quorum witness/);
    vm.runInContext("quorumNotice({quorum_details:{configured:true,votes:1}})", context);
    assert.equal(byId('quorum-description').className, 'alert alert-info');
    vm.runInContext("quorumNotice({quorum_details:{configured:true,votes:0}})", context);
    assert.match(byId('quorum-description').textContent, /vote is unavailable/);

    response.resources[0].blocked = 'true'; response.nodes[0].unclean = true;
    await vm.runInContext('refresh()', context);
    assert.equal(byId('resources').rows[0].children[4].children[0].textContent, 'Blocked');
    assert.equal(byId('nodes').rows[0].children[4].children[0].className, 'rw-status-badge rw-status-stopped');
    response = {kind: 'cib', status: 'validated', previous: 'old', xml: 'new'};
    await vm.runInContext('showChange(7)', context);
    assert.equal(byId('apply').disabled, false, 'Validated review enables the actual shared widget');
    vm.runInContext('editorChanged()', context);
    assert.equal(byId('apply').disabled, true, 'Changing XML invalidates the reviewed candidate');
    assert.equal(byId('validate').disabled, true);
    assert.equal(vm.runInContext('changeId', context), null);
    response.status = 'applied';
    await vm.runInContext('showChange(7)', context);
    assert.equal(byId('apply').disabled, true);
    assert.equal(byId('validate').disabled, true);
    vm.runInContext("setDisabled('cluster', true)", context);
    assert(widgetCalls.some(([el, widget, op, key, value]) => el === byId('cluster') && widget === 'selectmenu' && op === 'option' && key === 'disabled' && value));
})().catch(error => { console.error(error); process.exitCode = 1; });
