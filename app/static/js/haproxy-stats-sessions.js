/* Session UI shares the Stats selection, refresh loop and action menu. */
window.HaproxyStatsSessions = function (options) {
    'use strict';
    const {get, make, labels, canManage, makeMenu, renderActionIcons} = options;
    const rows = new Map();
    const pageSize = 50;
    let page = 0, scope = null, selected = null;
    let serial = 0, pending = false;
    const transport = window.HaproxyStatsRuntime(options);
    const {request, result} = transport;
    const display = value => value == null || /^<none>$/i.test(value) ? '—' : value;
    const closeDetail = () => {
        selected = null;
        get('session-detail').hidden = true;
        rows.forEach(entry => entry.main.setAttribute('aria-selected', 'false'));
    };
    const updateActions = disabled => {
        get('sessions').querySelectorAll('[data-session-action]').forEach(button => {
            button.disabled = disabled || pending;
        });
    };
    const matches = row => {
        const fields = row.fields;
        const query = get('session-search').value.trim().toLocaleLowerCase();
        return (!query || [row.id, fields.src, fields.fe, fields.be, fields.srv, fields.proto]
            .some(value => String(value || '').toLocaleLowerCase().includes(query))) &&
            (!scope || (scope.kind === 'frontend' ? fields.fe === scope.proxy :
                fields.be === scope.proxy && (scope.kind !== 'server' || fields.srv === scope.name)));
    };
    const render = () => {
        const snapshot = options.getSnapshot();
        const filtered = snapshot ? snapshot.rows.filter(matches) : [];
        const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
        page = Math.min(page, pages - 1);
        const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);
        const live = new Set(visible.map(row => row.id));
        rows.forEach((entry, id) => { if (!live.has(id)) { entry.main.remove(); rows.delete(id); } });
        visible.forEach((row, index) => {
            if (!rows.has(row.id)) {
                const main = make('tr', 'hs-session-row');
                const clientCell = make('td');
                const client = make('button', 'hs-session-link');
                client.type = 'button';
                client.dataset.sessionAction = 'details';
                const protocol = make('span', 'hs-session-protocol');
                clientCell.append(client, protocol);
                const frontend = make('td'), backendCell = make('td');
                const backend = make('span'), server = make('span', 'hs-session-server');
                backendCell.append(backend, server);
                const age = make('td'), actionCell = make('td', 'admin-actions-cell');
                main.append(clientCell, frontend, backendCell, age, actionCell);
                const entry = {main, client, protocol, frontend, backend, server, age, data: row};
                client.addEventListener('click', () => open(entry.data, false));
                const items = [{label: labels.details, icon: 'info-circle', action: 'details', run: () => open(entry.data, false)}];
                if (canManage) items.push({label: labels.session_terminate, icon: 'times-circle', action: 'terminate', run: () => open(entry.data, true)});
                const menu = makeMenu(row.id, items);
                menu.querySelectorAll('button').forEach(button => { button.dataset.sessionAction = button.dataset.action || 'menu'; });
                actionCell.append(menu);
                rows.set(row.id, entry);
                renderActionIcons(menu);
            }
            const entry = rows.get(row.id);
            entry.data = row;
            entry.main.dataset.sessionId = row.id;
            entry.main.setAttribute('aria-selected', String(selected?.key === row.key));
            [['client', 'src'], ['protocol', 'proto'], ['frontend', 'fe'], ['backend', 'be'], ['server', 'srv'], ['age', 'age']]
                .forEach(([element, field]) => { entry[element].textContent = display(row.fields[field]); });
            if (get('session-rows').children[index] !== entry.main) get('session-rows').insertBefore(entry.main, get('session-rows').children[index] || null);
        });
        if (selected && snapshot) {
            const current = snapshot.rows.find(row => row.id === selected.id && row.key === selected.key);
            if (!current) { closeDetail(); result(labels.session_gone, true); }
            else {
                selected = current;
                get('session-detail').querySelectorAll('[data-session-field]').forEach(node => {
                    node.textContent = display(current.fields[node.dataset.sessionField]);
                });
            }
        }
        get('session-count').textContent = snapshot ? labels.visible + ': ' + filtered.length + ' / ' + snapshot.rows.length : '';
        get('session-empty').hidden = !snapshot || filtered.length > 0;
        get('session-pages').hidden = pages === 1;
        get('session-page').textContent = (page + 1) + ' / ' + pages;
        get('session-prev').disabled = page === 0;
        get('session-next').disabled = page === pages - 1;
        get('session-scope').hidden = !scope;
        get('session-scope').textContent = scope ? scope.proxy + (scope.kind === 'server' ? '/' + scope.name : '') + ' ×' : '';
        get('session-scope').setAttribute('aria-label', labels.session_clear_scope);
        updateActions(options.isBusy());
    };
    const renderDetail = data => {
        selected = data.row;
        const panel = get('session-detail');
        const heading = make('div', 'hs-session-detail-heading');
        const close = make('button', '', '×');
        close.type = 'button';
        close.setAttribute('aria-label', labels.close);
        close.addEventListener('click', closeDetail);
        heading.append(make('h3', '', labels.details), close);
        const fields = make('dl');
        [[labels.session_client, 'src'], ['Frontend', 'fe'], ['Backend', 'be'], [labels.name, 'srv'],
            [labels.session_age, 'age'], [labels.session_protocol, 'proto']].forEach(([label, field]) => {
            const pair = make('div');
            const value = make('dd', '', display(selected.fields[field]));
            value.dataset.sessionField = field;
            pair.append(make('dt', '', label), value);
            fields.append(pair);
        });
        const identity = make('div');
        identity.append(make('dt', '', 'ID'), make('dd', '', selected.id));
        fields.append(identity);
        const raw = make('details');
        raw.append(make('summary', '', labels.session_raw), make('pre', '', data.raw));
        panel.replaceChildren(heading, fields, make('p', 'hs-session-note',
            data.server + ' · ' + labels.updated + ': ' + new Date(data.collected_at).toLocaleTimeString()), raw);
        if (canManage) {
            if (data.revision) {
                const terminate = make('button', 'hs-session-terminate', labels.session_terminate);
                terminate.type = 'button';
                terminate.dataset.sessionAction = 'terminate';
                terminate.addEventListener('click', () => open(selected, true));
                panel.append(terminate);
            } else panel.append(make('p', 'hs-session-note', labels.session_read_only));
        }
        panel.hidden = false;
        render();
    };
    async function open(row, writing) {
        const snapshot = options.getSnapshot();
        if (!snapshot || pending || options.isBusy() || (writing && !canManage)) return;
        const token = ++serial;
        const server = options.getServer();
        const body = {session_id: row.id, row_key: row.key, pid: snapshot.info.Pid, uptime: snapshot.info.Uptime_sec};
        const url = '/stats/session/haproxy/' + encodeURIComponent(server);
        let sent = false, disappeared = false;
        pending = true;
        options.onBusyChange();
        try {
            const data = await request(url + '?' + new URLSearchParams(body));
            if (token !== serial) return;
            renderDetail(data);
            if (!writing) return;
            if (!data.revision) throw new Error('session_read_only');
            if (!await transport.confirm(labels.session_terminate, [
                data.server + ' / ' + display(data.row.fields.src),
                display(data.row.fields.be) + ' / ' + display(data.row.fields.srv),
                labels.session_terminate_hint]) || token !== serial) return;
            result(labels.applying);
            sent = true;
            await request(url, {...body, revision: data.revision});
            if (token !== serial) return;
            closeDetail();
            result(labels.session_terminated);
        } catch (error) {
            if (token !== serial) return;
            disappeared = error.message === 'session_gone';
            if (disappeared) closeDetail();
            result(labels[error.message] || (sent ? labels.action_unknown : labels.operation_failed), true);
        } finally {
            if (token === serial) {
                pending = false;
                options.onBusyChange();
                if (sent || disappeared) options.onRefresh();
            }
        }
    }
    const deactivate = () => {
        serial++;
        transport.deactivate();
        pending = false;
    };
    get('session-search').addEventListener('input', () => { page = 0; render(); });
    get('session-prev').addEventListener('click', () => { page--; render(); });
    get('session-next').addEventListener('click', () => { page++; render(); });
    get('session-scope').addEventListener('click', () => { scope = null; page = 0; render(); });
    return {
        get pending() { return pending; }, render, updateActions, deactivate,
        reset() { deactivate(); closeDetail(); scope = null; page = 0; get('session-search').value = ''; render(); },
        setScope(row) { scope = row; page = 0; get('session-search').value = ''; closeDetail(); render(); }
    };
};
