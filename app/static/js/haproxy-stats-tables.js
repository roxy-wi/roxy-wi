/* Stick tables use the same node, refresh loop, menus and dialogs as Sessions. */
window.HaproxyStatsTables = function (options) {
    'use strict';
    const {get, make, labels, canManage, makeMenu, renderActionIcons} = options;
    const transport = window.HaproxyStatsRuntime(options);
    const rows = new Map();
    const pageSize = 50;
    let page = 0, selected = null, serial = 0, pending = false;
    const table = () => options.getSnapshot()?.table;
    const closeDetail = () => { selected = null; get('table-detail').hidden = true; };
    const updateActions = disabled => {
        get('tables').querySelectorAll('[data-table-action]').forEach(button => {
            button.disabled = disabled || pending || !table();
        });
    };
    const showDetail = row => {
        selected = row.row_key;
        const panel = get('table-detail');
        const heading = make('div', 'hs-session-detail-heading');
        const close = make('button', '', '×');
        close.type = 'button';
        close.setAttribute('aria-label', labels.close);
        close.addEventListener('click', () => { closeDetail(); render(); });
        heading.append(make('h3', '', labels.details), close);
        const fields = make('dl');
        [[labels.table_key, row.key], ...Object.entries(row.fields)].forEach(([name, value]) => {
            const pair = make('div');
            pair.append(make('dt', '', name === 'exp' ? labels.table_expiry : name), make('dd', '', value));
            fields.append(pair);
        });
        panel.replaceChildren(heading, fields);
        if (canManage) {
            if (row.deletable) {
                const remove = make('button', 'hs-session-terminate', labels.table_delete);
                remove.type = 'button';
                remove.dataset.tableAction = 'delete';
                remove.addEventListener('click', () => change(row));
                panel.append(remove);
            } else panel.append(make('p', 'hs-session-note', labels.table_key_read_only));
        }
        panel.hidden = false;
    };
    const render = () => {
        const snapshot = options.getSnapshot();
        const current = table();
        const select = get('table-select');
        const names = (snapshot?.tables || []).map(item => item.name);
        if (JSON.stringify([...select.options].map(item => item.value)) !== JSON.stringify(names)) {
            select.replaceChildren(...names.map(name => { const option = make('option', '', name); option.value = name; return option; }));
        }
        select.value = current?.name || '';
        get('table-meta').textContent = current ? labels.type + ': ' + current.type + ' · ' +
            labels.table_usage + ': ' + current.used.toLocaleString() + ' / ' + current.size.toLocaleString() : '';
        const query = get('table-search').value.trim().toLocaleLowerCase();
        const filtered = current ? current.rows.filter(row => row.key.toLocaleLowerCase().includes(query)) : [];
        const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
        page = Math.min(page, pages - 1);
        const metrics = [...new Set((current?.rows || []).flatMap(row => Object.keys(row.fields)))];
        const heading = make('tr');
        [labels.table_key, ...metrics.map(name => name === 'exp' ? labels.table_expiry : name), labels.actions]
            .forEach(name => { const cell = make('th', '', name); cell.scope = 'col'; heading.append(cell); });
        get('table-head').replaceChildren(heading);
        const visible = filtered.slice(page * pageSize, (page + 1) * pageSize);
        const live = new Set(visible.map(row => row.row_key));
        rows.forEach((entry, key) => { if (!live.has(key)) { entry.main.remove(); rows.delete(key); } });
        visible.forEach((row, index) => {
            if (!rows.has(row.row_key)) {
                const main = make('tr', 'hs-stick-row');
                const entry = {main, data: row};
                const cell = make('td');
                const link = make('button', 'hs-session-link hs-table-key', row.key);
                link.type = 'button';
                link.addEventListener('click', () => { showDetail(entry.data); render(); });
                cell.append(link);
                const actions = make('td', 'admin-actions-cell');
                const items = [{label: labels.details, icon: 'info-circle', action: 'details',
                    run: () => { showDetail(entry.data); render(); }}];
                if (canManage && row.deletable) items.push({label: labels.table_delete, icon: 'trash', action: 'delete', run: () => change(entry.data)});
                const menu = makeMenu(row.row_key, items);
                menu.querySelectorAll('[data-action=delete]').forEach(button => { button.dataset.tableAction = 'delete'; });
                actions.append(menu);
                entry.cell = cell;
                entry.actions = actions;
                rows.set(row.row_key, entry);
                renderActionIcons(menu);
            }
            const entry = rows.get(row.row_key);
            entry.data = row;
            entry.main.setAttribute('aria-selected', String(selected === row.row_key));
            entry.main.replaceChildren(entry.cell, ...metrics.map(name => make('td', '', row.fields[name] ?? '—')), entry.actions);
            if (get('table-rows').children[index] !== entry.main) get('table-rows').insertBefore(entry.main, get('table-rows').children[index] || null);
        });
        if (selected) {
            const row = current?.rows.find(item => item.row_key === selected);
            if (row) showDetail(row); else closeDetail();
        }
        get('table-count').textContent = current ? labels.visible + ': ' + filtered.length + ' / ' + current.rows.length : '';
        get('table-empty').hidden = !snapshot || filtered.length > 0;
        get('table-empty').textContent = current ? labels.table_empty : labels.tables_empty;
        get('table-pages').hidden = pages === 1;
        get('table-page').textContent = (page + 1) + ' / ' + pages;
        get('table-prev').disabled = page === 0;
        get('table-next').disabled = page === pages - 1;
        updateActions(options.isBusy());
    };
    async function change(row = null) {
        const snapshot = options.getSnapshot();
        const current = table();
        if (!current || !canManage || pending || options.isBusy()) return;
        const token = ++serial;
        const body = {table: current.name, revision: current.revision, pid: snapshot.info.Pid,
            uptime: snapshot.info.Uptime_sec, action: row ? 'delete' : 'clear', row_key: row?.row_key || null};
        const server = options.getServer();
        let sent = false;
        pending = true;
        options.onBusyChange();
        try {
            const title = row ? labels.table_delete : labels.table_clear;
            const target = server + ' / ' + current.name + (row ? ' / ' + row.key : '');
            if (!await transport.confirm(title, [target, labels.table_usage + ': ' + current.used + ' / ' + current.size,
                row ? labels.table_delete_hint : labels.table_clear_hint]) || token !== serial) return;
            transport.result(labels.applying);
            sent = true;
            const data = await transport.request('/stats/tables/haproxy/' + encodeURIComponent(server), body);
            if (token !== serial) return;
            closeDetail();
            transport.result((row ? labels.table_deleted : labels.table_cleared) + ' ' +
                (data.verified ? labels.table_remaining + ': ' + data.remaining : labels.table_verify_failed));
        } catch (error) {
            if (token === serial) transport.result(labels[error.message] || (sent ? labels.action_unknown : labels.operation_failed), true);
        } finally {
            if (token === serial) {
                pending = false;
                options.onBusyChange();
                if (sent) options.onRefresh();
            }
        }
    }
    const deactivate = () => { serial++; transport.deactivate(); pending = false; };
    get('table-search').addEventListener('input', () => { page = 0; render(); });
    get('table-prev').addEventListener('click', () => { page--; render(); });
    get('table-next').addEventListener('click', () => { page++; render(); });
    if (canManage) get('table-clear').addEventListener('click', () => change());
    get('table-select').addEventListener('change', () => {
        deactivate();
        closeDetail();
        page = 0;
        get('table-search').value = '';
        options.onTableChange();
    });
    return {get pending() { return pending; }, render, updateActions, deactivate,
        reset() { deactivate(); closeDetail(); page = 0; get('table-search').value = ''; get('table-select').replaceChildren(); render(); }};
};
