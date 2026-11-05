/* NGINX OSS / Apache snapshots; all remote values are rendered as text. */
(function () {
    'use strict';
    const root = document.getElementById('proxy-stats');
    if (!root) return;
    const labels = JSON.parse(root.dataset.labels);
    const common = JSON.parse(root.dataset.common);
    const service = root.dataset.service;
    const summaryKeys = service === 'nginx' ? ['active', 'connection_rate', 'rps', 'gap'] :
        ['version', 'uptime', 'connections', 'rps', 'bps'];
    const get = id => document.getElementById('ps-' + id);
    const serverSelect = document.getElementById('serv');
    const number = new Intl.NumberFormat(document.documentElement.lang || undefined, {maximumFractionDigits: 2});
    const colors = ['#6999bb', '#8baa93', '#bda16d', '#a593b9'];
    let previous = null, latest = null, controller = null, generation = 0, timer = null, stopped = false, selected = null;
    const charts = [];
    const cards = new Map();
    function text(key) { return labels[key] || common[key] || key; }
    function element(tag, className, value) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (value !== undefined) node.textContent = value;
        return node;
    }
    function format(key, value) {
        if (value === null || value === undefined) return '—';
        if (key === 'version') return value;
        if (key === 'uptime') {
            const days = Math.floor(value / 86400);
            const clock = [Math.floor(value % 86400 / 3600), Math.floor(value % 3600 / 60), value % 60]
                .map(part => String(part).padStart(2, '0')).join(':');
            return `${days ? days + 'd ' : ''}${clock}`;
        }
        return number.format(value);
    }
    function description(key) { return labels.fields[key] || [key, key]; }
    function card(key) {
        const [name, help] = description(key);
        const card = element('div', 'hs-card');
        const label = element('span', 'hs-card-label', name);
        label.title = help;
        label.tabIndex = 0;
        card.dataset.metric = key;
        const value = element('strong');
        card.append(label, value);
        get('summary').append(card);
        cards.set(key, value);
    }
    function rates(sample) {
        const result = {rps: null, bps: null, connection_rate: null, gap: null, reset: false};
        if (!previous) return result;
        const seconds = (Date.parse(sample.observed_at) - Date.parse(previous.observed_at)) / 1000;
        if (!(seconds > 0)) return result;
        const current = sample.counters, old = previous.counters;
        const keys = ['requests', 'total_kbytes', 'accepts', 'handled', 'uptime'];
        result.reset = keys.some(key => current[key] != null && old[key] != null && current[key] < old[key]);
        if (result.reset) return result;
        if (current.requests != null && old.requests != null) result.rps = (current.requests - old.requests) / seconds;
        if (current.total_kbytes != null && old.total_kbytes != null) result.bps = (current.total_kbytes - old.total_kbytes) * 1024 / seconds;
        if (current.accepts != null && old.accepts != null) {
            result.connection_rate = (current.accepts - old.accepts) / seconds;
            result.gap = Math.max(0, (current.accepts - old.accepts) - (current.handled - old.handled));
        }
        return result;
    }
    function createChart(id, keys) {
        const style = getComputedStyle(root);
        const chart = new Chart(get(id), {
            type: 'line',
            data: {labels: [], datasets: keys.map((key, index) => ({
                label: description(key)[0], data: [], borderColor: colors[index], borderWidth: 2,
                pointRadius: 2, spanGaps: false,
            }))},
            options: {responsive: true, maintainAspectRatio: false, animation: false,
                interaction: {mode: 'index', intersect: false},
                plugins: {legend: {display: keys.length > 1, labels: {color: style.getPropertyValue('--rw-text-muted')}}},
                scales: {x: {ticks: {maxTicksLimit: 6, maxRotation: 0, color: style.getPropertyValue('--rw-text-muted')}, grid: {display: false}},
                    y: {beginAtZero: true, ticks: {color: style.getPropertyValue('--rw-text-muted')},
                        grid: {color: style.getPropertyValue('--rw-border')}}}},
        });
        charts.push(chart);
        return chart;
    }
    function drawCharts(sample, computed) {
        const keys = service === 'nginx' ? ['reading', 'writing', 'waiting'] : ['busy', 'idle'];
        if (!charts.length) {
            createChart('requests-chart', ['rps']);
            createChart('connections-chart', keys);
        }
        const values = [[computed.rps], keys.map(key => sample.counters[key])];
        charts.forEach((chart, index) => appendSample(chart, sample.observed_at, values[index]));
    }
    function appendSample(chart, timestamp, values) {
        chart.data.labels.push(new Date(timestamp).toLocaleTimeString());
        chart.data.datasets.forEach((dataset, n) => dataset.data.push(values[n] ?? null));
        if (chart.data.labels.length > 120) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => dataset.data.shift());
        }
        chart.update('none');
    }
    function scoreboard(value) {
        const states = '._SRWKDCLGI';
        const palette = ['#b6bdc5', '#8baa93', '#bda16d', '#6999bb', '#5483a5', '#a593b9', '#c0a884', '#9badae', '#a6a286', '#b38d83', '#9ca1b4'];
        const counts = Object.fromEntries([...states].map(state => [state, 0]));
        for (const state of value) counts[state]++;
        get('scoreboard-bar').replaceChildren();
        get('scoreboard-legend').replaceChildren();
        [...states].forEach((state, index) => {
            if (!counts[state]) return;
            const label = `${state} · ${labels.states[state]}: ${number.format(counts[state])}`;
            const segment = element('span');
            segment.style.width = `${100 * counts[state] / value.length}%`;
            segment.style.backgroundColor = palette[index];
            segment.title = label;
            const legend = element('span');
            const dot = element('i');
            dot.style.backgroundColor = palette[index];
            legend.append(dot, element('span', '', label));
            get('scoreboard-bar').append(segment);
            get('scoreboard-legend').append(legend);
        });
    }
    function render(sample) {
        const computed = rates(sample), counters = sample.counters;
        const values = {...counters, ...computed, version: sample.info?.version};
        get('data').hidden = false;
        get('data').dataset.stale = 'false';
        summaryKeys.forEach(key => {
            if (!cards.has(key)) card(key);
            cards.get(key).textContent = format(key, values[key]);
        });
        get('note').textContent = computed.reset ? text('reset') :
            (service === 'apache' && counters.requests === null ? text('extended') :
                (computed.rps === null ? text('rate_pending') : ''));
        get('note').hidden = !get('note').textContent;
        get('details').replaceChildren();
        for (const [key, value] of Object.entries(counters)) {
            if (key === 'scoreboard' || summaryKeys.includes(key)) continue;
            const [name, help] = description(key);
            const row = element('div');
            const term = element('dt', '', name);
            term.title = help;
            term.tabIndex = 0;
            row.append(term, element('dd', '', format(key, value)));
            get('details').append(row);
        }
        if (service === 'apache') scoreboard(counters.scoreboard);
        drawCharts(sample, computed);
        previous = latest = sample;
        get('status').textContent = `${common.updated}: ${new Date(sample.observed_at).toLocaleString()}`;
    }
    function schedule() {
        clearTimeout(timer);
        const interval = Number(get('interval').value);
        if (!stopped && !document.hidden && selected && interval && !controller) timer = setTimeout(refresh, interval * 1000);
    }
    async function refresh() {
        clearTimeout(timer);
        if (stopped || !selected || controller) return;
        const currentGeneration = generation;
        const request = new AbortController();
        controller = request;
        let timedOut = false;
        const timeout = setTimeout(() => { timedOut = true; request.abort(); }, 25000);
        get('refresh').disabled = true;
        get('status').textContent = common.loading;
        get('status').setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(`/stats/view/${service}/${encodeURIComponent(serverSelect.value)}`, {
                credentials: 'same-origin', cache: 'no-store', signal: request.signal,
                headers: {Accept: 'application/json'},
            });
            if (response.status === 401) throw new Error('unauthorized');
            if (response.status === 403) throw new Error('forbidden');
            let data;
            try { data = await response.json(); } catch (_) { throw new Error('invalid_response'); }
            if (!response.ok) throw new Error(data?.code || 'operation_failed');
            if (!data || data.status !== 'ok' || data.service !== service || !data.counters || !Number.isFinite(Date.parse(data.observed_at))) throw new Error('invalid_response');
            if (currentGeneration !== generation) return;
            get('error').hidden = true;
            render(data);
        } catch (error) {
            if (currentGeneration !== generation || (error.name === 'AbortError' && !timedOut)) return;
            const code = timedOut ? 'timeout' : error.message;
            get('error').textContent = labels[code] || labels.operation_failed;
            get('error').hidden = false;
            get('data').dataset.stale = 'true';
            get('status').textContent = latest ? `${common.stale} ${common.updated}: ${new Date(latest.observed_at).toLocaleString()}` : common.unavailable;
            previous = null;
            charts.forEach(chart => appendSample(chart, Date.now(), []));
        } finally {
            clearTimeout(timeout);
            if (currentGeneration === generation) {
                controller = null;
                get('refresh').disabled = !selected;
                get('status').removeAttribute('aria-busy');
                schedule();
            }
        }
    }
    function selectServer() {
        generation++;
        if (controller) controller.abort();
        controller = null;
        clearTimeout(timer);
        previous = latest = null;
        charts.splice(0).forEach(chart => chart.destroy());
        get('data').hidden = true;
        get('error').hidden = true;
        get('status').textContent = common.select_server;
        get('status').removeAttribute('aria-busy');
        const option = serverSelect.selectedOptions[0];
        selected = option && !option.disabled ? option.value : null;
        get('refresh').disabled = !selected;
        if (!selected) return;
        const url = new URL(location.href);
        url.pathname = `/stats/${service}/${encodeURIComponent(selected)}`;
        history.replaceState(null, '', url);
        refresh();
    }
    serverSelect.addEventListener('change', selectServer);
    get('refresh').addEventListener('click', refresh);
    get('interval').addEventListener('change', schedule);
    [serverSelect, get('interval')].forEach(control => {
        jQuery(control).on('selectmenuchange', () => control.dispatchEvent(new Event('change')));
    });
    document.addEventListener('visibilitychange', () => {
        clearTimeout(timer);
        if (!document.hidden && Number(get('interval').value)) { previous = null; refresh(); }
    });
    window.addEventListener('pagehide', () => {
        stopped = true; generation++; clearTimeout(timer);
        if (controller) controller.abort();
        controller = null;
    });
    window.addEventListener('pageshow', event => {
        if (event.persisted) { stopped = false; previous = null; refresh(); }
    });
    selectServer();
}());
