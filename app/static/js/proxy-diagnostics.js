/* Request-path diagnostics are scoped to the service card that opened the dialog. */
jQuery(() => {
    'use strict';
    const root = document.getElementById('proxy-diagnostics');
    if (!root) return;
    const el = id => document.getElementById('diagnostics-' + id);
    const drafts = new Map(), requests = new Set();
    const active = item => ['created', 'published', 'running'].includes(item.status);
    const labels = {configuration: 'Configuration sources', frontend: 'Frontend', 'dns-controller': 'DNS (controller)',
        'dns-proxy-host': 'DNS (proxy host)', vip: 'VIP / destination', 'vip-addresses': 'Host addresses',
        'proxy-listener': 'Proxy listener', tcp: 'TCP', 'tls-sni': 'TLS / SNI', http: 'HTTP response', backends: 'Candidate backends'};
    let context, opened = false, version = 0, timer, pending = false, loading = false, selectedId = null, records = [];
    const key = () => context.service + ':' + context.id;
    const current = generation => opened && generation === version;
    const node = (tag, text) => {
        const result = document.createElement(tag);
        if (text !== undefined) result.textContent = text;
        return result;
    };
    function message(text, busy = pending || requests.has(key()), disabled = loading) {
        RoxywiUI.operationStatus(el('message'), el('run'), text, busy, disabled);
    }
    async function api(url, data) {
        try {
            return await jQuery.ajax({url, method: data === undefined ? 'GET' : 'POST', contentType: 'application/json',
                timeout: 20000, global: false, data: data === undefined ? undefined : JSON.stringify(data)});
        } catch (error) {
            const failure = new Error(error.responseJSON?.error || 'Diagnostic request failed');
            failure.status = error.status;
            throw failure;
        }
    }
    function status(item) {
        pending = active(item);
        const state = pending ? (item.status === 'running' ? 'running…' : 'queued, waiting for a worker…') : item.status;
        message(`Diagnostics #${item.id}: ${state}${item.error ? ' — ' + item.error : ''}`);
    }
    function display(item = {}) {
        const report = item.report;
        selectedId = item.id || null;
        el('result').hidden = !item.id;
        el('summary').textContent = report?.summary || (item.error || 'No completed report for this assessment');
        el('time').textContent = report ? `#${item.id} · Observed ${new Date(report.observed_at).toLocaleString()} · ${report.url}` : '';
        el('stages').replaceChildren();
        for (const stage of report?.stages || []) {
            const row = node('tr'), evidence = node('td', stage.message), details = node('details');
            details.append(node('summary', 'Observed details'), node('pre', JSON.stringify(stage.details, null, 2)));
            evidence.append(details);
            const state = node('td'), badge = node('span', stage.state);
            const color = {observed: 'running', discovered: 'running', fail: 'stopped', warning: 'unavailable'}[stage.state] || 'stale';
            badge.className = 'rw-status-badge rw-status-' + color;
            state.append(badge);
            row.append(node('td', labels[stage.key] || stage.key), state, evidence);
            el('stages').append(row);
        }
        root.querySelectorAll('[data-assessment]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.assessment) === selectedId)));
    }
    function frontends(values = [], selected = '') {
        if (!el('frontend')) return;
        const select = el('frontend');
        select.replaceChildren(new Option('Choose automatically when unambiguous', ''),
            ...values.map(front => new Option(front.name, front.id)));
        if (values.some(front => front.id === selected)) select.value = selected;
        jQuery(select).selectmenu('refresh');
        el('frontend-field').hidden = !values.length;
        drafts.get(key()).frontends = values;
    }
    function canonicalURL(value) {
        try { return new URL(value.includes('://') ? value : 'https://' + value).href; }
        catch (_error) { return null; }
    }
    function updateFrontends(report) {
        if (!report || !el('url') || canonicalURL(el('url').value.trim()) !== canonicalURL(report.url)) return;
        const url = new URL(report.url), port = Number(url.port || (url.protocol === 'https:' ? 443 : 80));
        frontends(report.frontends.filter(front => front.listeners.some(listener => listener.port === port)));
    }
    function renderHistory() {
        el('history').replaceChildren();
        if (!records.length) el('history').textContent = 'No assessments yet.';
        for (const item of records) {
            const button = node('button', `#${item.id} · ${new Date(item.created_at).toLocaleString()} · ${item.status}`);
            button.type = 'button'; button.className = 'rw-button rw-button-secondary';
            button.dataset.assessment = item.id;
            button.setAttribute('aria-pressed', String(item.id === selectedId));
            button.addEventListener('click', () => display(item));
            el('history').append(button);
        }
    }
    function schedule(id, generation, delay = 2000) {
        clearTimeout(timer);
        timer = setTimeout(() => poll(id, generation), delay);
    }
    async function poll(id, generation) {
        try {
            const data = await api(root.dataset.assessments.replace(/\/0$/, '/' + id));
            if (!current(generation)) return;
            el('retry').hidden = true;
            const item = data.data;
            status(item);
            if (active(item)) { schedule(id, generation); return; }
            records = [item, ...records.filter(row => row.id !== item.id)];
            renderHistory();
            if (selectedId === null || selectedId === item.id) display(item);
            updateFrontends(item.report);
        } catch (error) {
            if (!current(generation)) return;
            message('Unable to refresh diagnostics status: ' + error.message, false, true);
            el('retry').hidden = false;
            // Keep following an accepted job after a transient read failure, without submitting it again.
            if (!error.status || error.status >= 500) schedule(id, generation, 5000);
        }
    }
    async function history() {
        if (requests.has(key())) { message('Starting request diagnostics…', true, true); return; }
        clearTimeout(timer);
        const generation = ++version;
        loading = true; el('retry').hidden = true;
        message('Loading diagnostics history…', true, true);
        try {
            const data = await api(root.dataset.api + '?' + new URLSearchParams({service: context.service, server_id: context.id}));
            if (!current(generation)) return;
            records = data.data; loading = false;
            const running = records.find(active);
            pending = Boolean(running);
            const selected = records.find(item => item.id === selectedId);
            display(selected || records[0]);
            renderHistory();
            if (running) { status(running); schedule(running.id, generation); }
            else if (records.length) status(records[0]);
            else message('Ready to run diagnostics.');
        } catch (error) {
            if (!current(generation)) return;
            loading = false;
            message('Unable to refresh diagnostics history: ' + error.message, false, true);
            el('retry').hidden = false;
        }
    }
    function saveDraft() {
        if (!context || !el('url')) return;
        Object.assign(drafts.get(key()), {url: el('url').value, frontend: el('frontend').value});
    }
    function resize() {
        dialog.dialog('option', {width: Math.min(1050, window.innerWidth - 24), maxHeight: window.innerHeight - 32,
            position: {my: 'center', at: 'center', of: window}});
    }
    const dialog = jQuery(root).dialog({
        autoOpen: false, modal: true, resizable: false, draggable: false,
        classes: {'ui-dialog': 'rw-dialog-responsive proxy-diagnostics-dialog'},
        open() { jQuery('.ui-widget-overlay').last().addClass('proxy-diagnostics-overlay'); },
        close() {
            saveDraft(); opened = false; version++; clearTimeout(timer);
            const url = new URL(window.location.href); url.searchParams.delete('diagnostics');
            window.history.replaceState(null, '', url);
        }
    });
    if (el('frontend')) jQuery(el('frontend')).selectmenu({appendTo: dialog.dialog('widget')});
    function open(trigger) {
        saveDraft(); version++; clearTimeout(timer);
        context = {service: trigger.dataset.service, id: trigger.dataset.serverId};
        const name = {haproxy: 'HAProxy', nginx: 'NGINX', apache: 'Apache'}[context.service];
        dialog.dialog('widget').find('.ui-dialog-title').text(`Request diagnostics · ${name} · ${trigger.dataset.serverName} (${trigger.dataset.serverIp})`);
        opened = true; pending = false; loading = false; selectedId = null; records = [];
        if (!drafts.has(key())) drafts.set(key(), {url: '', frontends: [], frontend: ''});
        const draft = drafts.get(key());
        if (el('url')) { el('url').value = draft.url; frontends(draft.frontends, draft.frontend); }
        display(); renderHistory(); resize(); dialog.dialog('open');
        const url = new URL(window.location.href); url.searchParams.set('diagnostics', context.id);
        window.history.replaceState(null, '', url);
        history();
    }
    jQuery(document).on('click', '.proxy-diagnostics-trigger', function () {
        jQuery(this).closest('.service-actions-menu').prop('hidden', true);
        jQuery(this).closest('.service-actions').find('.service-actions-toggle').attr('aria-expanded', 'false');
        open(this);
    });
    el('retry').addEventListener('click', history);
    el('url')?.addEventListener('input', () => frontends());
    el('form')?.addEventListener('submit', async event => {
        event.preventDefault();
        const requestKey = key();
        if (loading || pending || requests.has(requestKey)) return;
        const body = {service: context.service, server_id: Number(context.id), url: el('url').value, frontend_id: el('frontend').value || null};
        requests.add(requestKey); version++; clearTimeout(timer);
        message('Starting request diagnostics…');
        try {
            const data = await api(root.dataset.api, body);
            if (!opened || key() !== requestKey) return;
            requests.delete(requestKey);
            const item = {id: data.id, created_at: new Date().toISOString(), status: data.status};
            records = [item, ...records]; display(item); renderHistory(); status(item);
            poll(data.id, version);
        } catch (error) {
            if (!opened || key() !== requestKey) return;
            requests.delete(requestKey);
            pending = false;
            message(error.message, false, false);
            // A timeout may still have queued the request; read its state before allowing a retry.
            if (!error.status || error.status === 409) history();
        } finally { requests.delete(requestKey); }
    });
    window.addEventListener('resize', () => { if (opened) resize(); });
    window.addEventListener('pagehide', () => { opened = false; version++; clearTimeout(timer); });
    const requested = new URLSearchParams(window.location.search).get('diagnostics');
    const trigger = [...document.querySelectorAll('.proxy-diagnostics-trigger')].find(item => item.dataset.serverId === requested);
    if (trigger) open(trigger);
});
