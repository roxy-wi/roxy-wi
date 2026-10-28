(function () {
    'use strict';
    const root = document.getElementById('haproxy-stats');
    if (!root) return;
    const labels = JSON.parse(root.dataset.labels);
    const fieldHelp = JSON.parse(root.dataset.fieldHelp);
    const canManage = root.dataset.canManage === 'true';
    const renderActionIcons = node => {
        if (window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node});
    };
    // Font Awesome is deferred and does not observe dynamically added rows.
    document.addEventListener('DOMContentLoaded', () => renderActionIcons(root), {once: true});
    const get = id => document.getElementById('hs-' + id);
    // The shared server macro uses a disabled placeholder without an explicit value.
    get('server').querySelector('option[disabled]').value = '';
    const text = (element, value) => { element.textContent = value; };
    const make = (tag, className, value) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined) text(element, value);
        return element;
    };
    const number = value => value == null ? '—' : Number(value).toLocaleString();
    const bytes = value => {
        if (value == null) return '—';
        if (value < 1024) return number(value) + ' B';
        const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
        return (value / Math.pow(1024, exponent)).toLocaleString(undefined, {maximumFractionDigits: 1}) +
            ' ' + ['B', 'KiB', 'MiB', 'GiB', 'TiB'][exponent];
    };
    const duration = value => {
        if (value == null) return '—';
        const days = Math.floor(value / 86400);
        const hours = Math.floor(value % 86400 / 3600);
        const minutes = Math.floor(value % 3600 / 60);
        return (days ? days + 'd ' : '') + [hours, minutes, value % 60].map(v => String(v).padStart(2, '0')).join(':');
    };
    const columns = [
        {id: 'status', label: labels.state, value: row => row.status || '—'},
        {id: 'sessions', label: labels.sessions, value: row => number(row.metrics.scur) + ' / ' + number(row.metrics.slim)},
        {id: 'rate', label: labels.session_rate, value: row => number(row.metrics.rate)},
        {id: 'requests', label: labels.request_rate, value: row => number(row.metrics.req_rate)},
        {id: 'queue', label: labels.queue, value: row => number(row.metrics.qcur)},
        {id: 'traffic', label: labels.traffic, value: row => bytes(row.metrics.bin) + ' / ' + bytes(row.metrics.bout)},
        {id: 'errors', label: labels.errors, value: row => ['ereq', 'econ', 'eresp'].map(key => number(row.metrics[key])).join(' / ')},
        {id: 'weight', label: labels.weight, value: row => number(row.metrics.weight)},
        {id: 'check', label: labels.check, value: row => [row.metrics.check_status, row.metrics.check_code,
            row.metrics.check_duration == null ? null : row.metrics.check_duration + ' ms'].filter(v => v != null).join(' / ') || '—'},
        {id: 'address', label: labels.address, optional: true, value: row => row.address || '—'},
        {id: 'total', label: labels.total_sessions, optional: true, value: row => number(row.metrics.stot)},
        {id: 'response', label: labels.response_time, optional: true, value: row => row.metrics.rtime == null ? '—' : number(row.metrics.rtime) + ' ms'}
    ];
    const filterIds = ['search', 'state', 'kind', 'backup', 'problems'];
    const storageKey = 'roxywi.haproxy-stats.v1.' + root.dataset.user + '.' + root.dataset.group;
    let preferences = {};
    try { preferences = JSON.parse(localStorage.getItem(storageKey)) || {}; }
    catch (error) { console.warn('Stats preferences could not be loaded:', error.name); }
    filterIds.forEach(id => {
        const control = get(id);
        if (control.type === 'checkbox') control.checked = preferences[id] === true;
        else if (typeof preferences[id] === 'string') {
            control.value = preferences[id];
            if (control.tagName === 'SELECT' && !control.value) control.value = 'all';
        }
    });
    const visibleColumns = new Set(columns.filter(column => Array.isArray(preferences.columns) ?
        preferences.columns.includes(column.id) : !column.optional).map(column => column.id));
    const savePreferences = () => {
        const value = {columns: [...visibleColumns]};
        filterIds.forEach(id => { value[id] = get(id).type === 'checkbox' ? get(id).checked : get(id).value; });
        try { localStorage.setItem(storageKey, JSON.stringify(value)); }
        catch (error) { console.warn('Stats preferences could not be saved:', error.name); }
    };
    const groups = new Map();
    const cards = new Map();
    let snapshot = null;
    let timer = null;
    let controller = null;
    let generation = 0;
    let busy = false;
    let stopped = false;
    let selection = 0;
    let actionPending = null;
    let actionDialog = null;
    const snapshots = {sessions: null, tables: null};
    const views = {};
    const viewNames = ['overview', 'sessions', 'tables'];
    const requestedView = new URL(location.href).searchParams.get('view');
    let activeView = viewNames.includes(requestedView) ? requestedView : 'overview';
    let selectedTable = '';
    const currentSnapshot = () => activeView === 'overview' ? snapshot : snapshots[activeView];
    const runtimePending = () => Object.values(views).some(view => view.pending);

    const updateActions = () => {
        const disabled = busy || !!actionPending || runtimePending() || root.dataset.stale === 'true';
        groups.forEach(group => group.rows.forEach(entry => {
            if (entry.actions) entry.actions.querySelectorAll('button').forEach(button => { button.disabled = disabled; });
            entry.cells.get('sessions').disabled = disabled || !['frontend', 'backend', 'server'].includes(entry.data.kind);
        }));
        get('refresh').disabled = !get('server').value || busy || !!actionPending || runtimePending();
        Object.values(views).forEach(view => view.updateActions(disabled));
        if (get('global-actions')) get('global-actions').querySelectorAll('button').forEach(button => {
            button.disabled = disabled || !snapshot;
        });
    };

    const confirmServerAction = (row, action, targets = []) => new Promise(resolve => {
        const dialog = make('div', 'hs-action-dialog');
        const form = make('form');
        form.append(make('p', 'hs-action-target', get('server').value + ' / ' +
            (row.kind === 'global' ? labels.global_maxconn : row.proxy + '/' + row.name)));
        let input;
        if (action === 'weight' || action === 'maxconn') {
            const isMaxconn = action === 'maxconn';
            const label = make('label', 'rw-form-field', isMaxconn ? 'Maxconn' : labels.weight);
            input = make('input', 'form-control');
            input.type = 'number';
            input.min = isMaxconn && row.kind !== 'server' ? '1' : '0';
            input.max = isMaxconn ? (row.kind === 'global' ? snapshot.info.Hard_maxconn ?? 2147483647 : 2147483647) : '256';
            input.step = '1';
            input.required = true;
            input.value = isMaxconn ? (row.metrics.slim ?? (row.kind === 'server' ? 0 : '')) : (row.metrics.uweight ?? row.metrics.weight ?? '');
            label.append(input);
            form.append(label, make('p', '', isMaxconn ? labels['maxconn_' + row.kind + '_hint'] : labels.weight_hint));
        } else {
            form.append(make('p', '', labels[action + '_hint']));
        }
        form.append(make('p', 'hs-action-note', action === 'maxconn' ? labels.maxconn_persist : labels.runtime_only));
        if (action === 'maxconn') {
            form.append(make('p', '', labels.maxconn_targets));
            const list = make('ul', 'hs-action-targets');
            targets.forEach(node => list.append(make('li', '', node.hostname + ' — ' + node.ip)));
            form.append(list);
        }
        dialog.append(form);
        document.body.append(dialog);
        let result = null;
        const submit = () => {
            if (!form.reportValidity()) return;
            result = input ? Number(input.value) : action;
            $(dialog).dialog('close');
        };
        form.addEventListener('submit', event => { event.preventDefault(); submit(); });
        actionDialog = dialog;
        $(dialog).dialog({
            modal: true, width: Math.min(520, window.innerWidth - 32),
            title: action === 'maxconn' ? labels.change_maxconn : action === 'weight' ? labels.change_weight : labels.confirm_state + ' ' + action[0].toUpperCase() + action.slice(1),
            classes: {'ui-dialog': 'rw-dialog-responsive hs-stats-dialog'},
            buttons: [{text: labels.apply, click: submit}, {text: labels.cancel, click: () => $(dialog).dialog('close')}],
            close: () => {
                if (actionDialog === dialog) actionDialog = null;
                $(dialog).dialog('destroy').remove();
                resolve(result);
            }
        });
    });

    async function changeServer(entry, action) {
        if (!canManage || busy || actionPending || !snapshot || root.dataset.stale === 'true') return;
        const target = {server: get('server').value, selection, row: entry.data,
            pid: snapshot.info.Pid, uptime: snapshot.info.Uptime_sec};
        actionPending = target;
        clearTimeout(timer);
        hideTooltip();
        updateActions();
        let sent = false;
        const isMaxconn = action === 'maxconn';
        const targetName = target.row.kind === 'global' ? labels.global_maxconn : target.row.proxy + '/' + target.row.name;
        const showNodes = nodes => {
            if (!Array.isArray(nodes)) return;
            const list = make('ul', 'hs-action-targets');
            nodes.forEach(node => list.append(make('li', '', node.server + ': Runtime — ' +
                (labels['node_' + node.runtime] || labels.node_unknown) + '; ' + labels.configuration + ' — ' +
                (labels['node_' + node.config] || labels.node_unknown))));
            get('action-result').append(list);
        };
        try {
            let targets = [];
            if (isMaxconn) {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 20000);
                try {
                    const response = await fetch('/stats/maxconn/haproxy/' + encodeURIComponent(target.server), {
                        cache: 'no-store', signal: controller.signal, headers: {'Accept': 'application/json'}
                    });
                    const data = await response.json();
                    if (!response.ok || data.status !== 'ok') throw new Error(data.code || 'permission_denied');
                    targets = data.targets;
                } finally { clearTimeout(timeout); }
                if (selection !== target.selection || stopped) return;
            }
            const value = await confirmServerAction(target.row, action, targets);
            if (value === null || selection !== target.selection || stopped) return;
            const result = get('action-result');
            result.hidden = false;
            result.dataset.error = 'false';
            text(result, labels.applying);
            const writeController = new AbortController();
            const timeout = setTimeout(() => writeController.abort(), isMaxconn ? 180000 : 30000);
            sent = true;
            try {
                const payload = {row_key: target.row.key, pid: target.pid, uptime: target.uptime, value};
                if (isMaxconn) Object.assign(payload, {scope: target.row.kind, targets: targets.map(node => node.ip)});
                else payload.action = action === 'weight' ? 'weight' : 'state';
                const response = await fetch('/stats/' + (isMaxconn ? 'maxconn' : 'server') + '/haproxy/' + encodeURIComponent(target.server), {
                    method: 'POST', signal: writeController.signal,
                    headers: {'Accept': 'application/json', 'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-TOKEN': csrf_token},
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok || data.status !== 'ok') {
                    const error = new Error(response.status === 401 ? 'auth_required' : data.code ||
                        (response.status === 403 ? 'permission_denied' : isMaxconn ? 'maxconn_unknown' : 'action_unknown'));
                    error.nodes = data.nodes;
                    throw error;
                }
                if (selection !== target.selection || stopped) return;
                text(result, targetName + ': ' + (isMaxconn ? labels.maxconn_saved : labels.action_applied));
                showNodes(data.nodes);
            } catch (error) {
                if (selection !== target.selection || stopped) return;
                result.dataset.error = 'true';
                text(result, targetName + ': ' + (labels[error.message] || (isMaxconn ? labels.maxconn_unknown : labels.action_unknown)));
                showNodes(error.nodes);
            } finally {
                clearTimeout(timeout);
            }
        } catch (error) {
            if (selection === target.selection && !stopped) {
                get('action-result').hidden = false;
                get('action-result').dataset.error = 'true';
                text(get('action-result'), labels[error.message] || labels.operation_failed);
            }
        } finally {
            if (actionPending === target) {
                actionPending = null;
                updateActions();
                if (sent && !stopped) await refresh(); else schedule();
            }
        }
    }

    const confirmServerEdit = (target, action, context) => new Promise(resolve => {
        const dialog = make('div', 'hs-action-dialog');
        const form = make('form');
        const fields = make('div', 'hs-server-fields');
        form.append(make('p', 'hs-action-target', target.server + ' / ' + target.row.proxy +
            (action === 'add' ? '' : '/' + target.row.name)));
        const controls = {};
        const field = (key, label, type, value) => {
            const wrapper = make('label', type === 'checkbox' ? 'hs-server-check' : 'rw-form-field', label);
            const input = make('input', type === 'checkbox' ? '' : 'form-control');
            input.type = type;
            input.name = key;
            input.required = type !== 'checkbox';
            if (type === 'checkbox') input.checked = value;
            else input.value = value;
            if (type === 'number') { input.min = '1'; input.max = '65535'; input.step = '1'; }
            if (type === 'checkbox') wrapper.prepend(input);
            else wrapper.append(input);
            fields.append(wrapper);
            controls[key] = input;
            return input;
        };
        if (action !== 'delete') {
            if (action === 'add') {
                const name = field('name', labels.name, 'text', '');
                name.maxLength = 255;
                name.pattern = '[A-Za-z0-9_.:\\-]+';
            }
            field('address', labels.server_ip_address, 'text', context.value.address);
            field('port', labels.server_port, 'number', context.value.port);
            if (action === 'add') {
                field('check', labels.server_health_check, 'checkbox', context.value.check);
                field('check_port', labels.server_check_port, 'number', context.value.check_port);
                controls.address.addEventListener('input', () => {
                    if (!controls.name.dataset.edited) controls.name.value = controls.address.value;
                });
                controls.name.addEventListener('input', () => { controls.name.dataset.edited = 'true'; });
                controls.port.addEventListener('input', () => {
                    if (!controls.check_port.dataset.edited) controls.check_port.value = controls.port.value;
                });
                controls.check_port.addEventListener('input', () => { controls.check_port.dataset.edited = 'true'; });
            }
            form.append(fields);
        } else form.append(make('p', '', labels.server_delete_hint));
        form.append(make('p', 'hs-action-note', labels[action === 'delete' ? 'server_reload_hint' : 'server_runtime_hint']));
        const list = make('ul', 'hs-action-targets');
        context.targets.forEach(node => list.append(make('li', '', node.hostname + ' — ' + node.ip)));
        form.append(list);
        dialog.append(form);
        document.body.append(dialog);
        let result = null;
        const submit = () => {
            if (!form.reportValidity()) return;
            const value = action === 'delete' ? null : {address: controls.address.value.trim(), port: Number(controls.port.value)};
            if (action === 'add') Object.assign(value, {name: controls.name.value.trim(),
                check: controls.check.checked, check_port: Number(controls.check_port.value)});
            result = {value};
            $(dialog).dialog('close');
        };
        form.addEventListener('submit', event => { event.preventDefault(); submit(); });
        actionDialog = dialog;
        $(dialog).dialog({
            modal: true, width: Math.min(540, window.innerWidth - 32), title: labels['server_' + action],
            classes: {'ui-dialog': 'rw-dialog-responsive hs-stats-dialog'},
            buttons: [{text: labels[action === 'delete' ? 'server_save_reload' : 'server_save_runtime'], click: submit},
                {text: labels.cancel, click: () => $(dialog).dialog('close')}],
            close: () => {
                if (actionDialog === dialog) actionDialog = null;
                $(dialog).dialog('destroy').remove();
                resolve(result);
            }
        });
    });

    async function manageServer(entry, action) {
        if (!canManage || busy || actionPending || !snapshot || root.dataset.stale === 'true') return;
        const target = {server: get('server').value, selection, row: entry.data};
        const body = {action, row_key: target.row.key, pid: snapshot.info.Pid, uptime: snapshot.info.Uptime_sec};
        const url = '/stats/servers/haproxy/' + encodeURIComponent(target.server);
        actionPending = target;
        clearTimeout(timer);
        hideTooltip();
        updateActions();
        let sent = false;
        const active = () => selection === target.selection && !stopped;
        const request = async (url, options = {}) => {
            const abort = new AbortController();
            const timeout = setTimeout(() => abort.abort(), options.method ? 180000 : 60000);
            try {
                const response = await fetch(url, {...options, cache: 'no-store', signal: abort.signal,
                    headers: {'Accept': 'application/json', 'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-TOKEN': csrf_token}});
                const data = await response.json();
                if (!response.ok || data.status !== 'ok') {
                    const error = new Error(data.code || (response.status === 403 ? 'permission_denied' : 'server_incomplete'));
                    error.nodes = data.nodes;
                    throw error;
                }
                return data;
            } finally { clearTimeout(timeout); }
        };
        const showNodes = nodes => {
            if (!Array.isArray(nodes)) return;
            const list = make('ul', 'hs-action-targets');
            nodes.forEach(node => list.append(make('li', '', node.server + ': ' + labels.configuration + ' — ' +
                (labels['node_' + node.config] || labels.node_unknown) + '; Runtime — ' +
                (labels['node_' + node.runtime] || labels.node_unknown) + '; ' + labels.server_section_settings + ' — ' +
                (labels['node_' + node.settings] || labels.node_unknown))));
            get('action-result').append(list);
        };
        try {
            const context = await request(url + '?' + new URLSearchParams(body));
            if (!active()) return;
            const answer = await confirmServerEdit(target, action, context);
            if (!answer || !active()) return;
            const result = get('action-result');
            result.hidden = false;
            result.dataset.error = 'false';
            text(result, labels.applying);
            sent = true;
            const data = await request(url, {method: 'POST', body: JSON.stringify({...body, ...answer,
                revision: context.revision, targets: context.targets.map(node => node.ip)})});
            if (!active()) return;
            text(result, labels.server_saved);
            showNodes(data.nodes);
        } catch (error) {
            if (!active()) return;
            const result = get('action-result');
            result.hidden = false;
            result.dataset.error = 'true';
            text(result, labels[error.message] || (sent ? labels.server_incomplete : labels.operation_failed));
            showNodes(error.nodes);
        } finally {
            if (actionPending === target) {
                actionPending = null;
                updateActions();
                if (sent && !stopped) await refresh(); else schedule();
            }
        }
    }

    const actionMenu = (target, items) => {
        const container = make('div', 'admin-actions');
        const toggle = make('button', 'rw-icon-button admin-actions-toggle');
        toggle.type = 'button';
        toggle.setAttribute('aria-label', labels.actions + ': ' + target);
        toggle.setAttribute('aria-haspopup', 'menu');
        toggle.setAttribute('aria-expanded', 'false');
        const icon = make('span', 'fas fa-ellipsis-v');
        icon.setAttribute('aria-hidden', 'true');
        toggle.append(icon);
        const menu = make('div', 'admin-actions-menu');
        menu.setAttribute('role', 'menu');
        menu.hidden = true;
        items.forEach(item => {
            const button = make('button', 'admin-action-item');
            button.type = 'button';
            button.dataset.action = item.action;
            button.setAttribute('role', 'menuitem');
            const icon = make('span', 'fas fa-' + item.icon);
            icon.setAttribute('aria-hidden', 'true');
            button.append(icon, document.createTextNode(item.label));
            button.addEventListener('click', () => {
                // Close through the shared toggle before disabling the clicked item.
                // jQuery skips delegated click handlers for disabled buttons.
                if (!menu.hidden) toggle.click();
                item.run();
            });
            menu.append(button);
        });
        container.append(toggle, menu);
        return container;
    };

    const serverActions = entry => {
        const isGlobal = entry.data.kind === 'global';
        const actions = entry.data.kind === 'server' ? [['ready', 'play'], ['drain', 'pause'], ['maint', 'wrench'], ['weight', 'balance-scale']] : [];
        if (entry.data.kind === 'backend') actions.push(['add', 'plus']);
        else actions.push(['maxconn', 'sliders-h']);
        if (entry.data.kind === 'server') actions.push(['edit', 'pen'], ['delete', 'trash']);
        const container = actionMenu(isGlobal ? labels.global_maxconn : entry.data.proxy + '/' + entry.data.name,
            actions.map(([action, icon]) => {
                const isEdit = ['add', 'edit', 'delete'].includes(action);
                return {action, icon,
                    label: isEdit ? labels['server_' + action] : action === 'maxconn' ? labels.change_maxconn :
                        action === 'weight' ? labels.change_weight : action[0].toUpperCase() + action.slice(1),
                    run: () => {
                        if (isEdit) manageServer(entry, action);
                        else changeServer(isGlobal ? {data: {key: null, kind: 'global', metrics: {slim: snapshot?.info.Maxconn}}} : entry, action);
                    }};
            }));
        if (isGlobal) {
            container.id = 'hs-global-actions';
            container.querySelector('[data-action=maxconn]').id = 'hs-global-maxconn';
        }
        return container;
    };

    const applyColumns = () => {
        root.querySelectorAll('[data-column]').forEach(cell => { cell.hidden = !visibleColumns.has(cell.dataset.column); });
        root.querySelectorAll('.hs-detail-cell').forEach(cell => { cell.colSpan = visibleColumns.size + 1 + Number(canManage); });
    };
    columns.forEach(column => {
        const label = make('label', 'hs-check');
        const input = make('input');
        input.type = 'checkbox';
        input.checked = visibleColumns.has(column.id);
        input.addEventListener('change', () => {
            if (input.checked) visibleColumns.add(column.id); else visibleColumns.delete(column.id);
            applyColumns();
            savePreferences();
        });
        label.append(input, document.createTextNode(column.label));
        get('column-options').append(label);
    });

    // Field semantics: https://docs.haproxy.org/2.8/management.html#9.1
    const describeField = key => {
        if (Object.hasOwn(fieldHelp, key)) return fieldHelp[key];
        let match = /^hrsp_([1-5]xx)$/.exec(key);
        if (match) return fieldHelp.http_responses.replace('{code}', match[1]);
        match = /^h([123])_?(sess|req)$/.exec(key);
        if (match) return fieldHelp[match[2] === 'sess' ? 'protocol_sessions' : 'protocol_requests'].replace('{protocol}', 'HTTP/' + match[1]);
        match = /^h([12])_(open_connections|total_connections|open_streams|total_streams|bytes_in|bytes_out|spliced_bytes_in|spliced_bytes_out)$/.exec(key);
        if (match) return fieldHelp['protocol_' + match[2]].replace('{protocol}', 'HTTP/' + match[1]);
        match = /^h2_(headers|data|settings|rst_stream|goaway)_(rcvd|resp)$/.exec(key);
        if (match) return fieldHelp[match[2] === 'rcvd' ? 'h2_frames_received' : 'h2_frames_sent'].replace('{frame}', match[1].toUpperCase());
        return fieldHelp.unknown_field;
    };
    const tooltip = make('div', 'hs-tooltip');
    tooltip.id = 'hs-metric-tooltip';
    tooltip.setAttribute('role', 'tooltip');
    tooltip.hidden = true;
    get('content').append(tooltip);
    let tooltipOwner = null;
    const hideTooltip = () => {
        if (tooltipOwner) tooltipOwner.removeAttribute('aria-describedby');
        tooltipOwner = null;
        tooltip.hidden = true;
    };
    const positionTooltip = () => {
        if (!tooltipOwner) return;
        if (!tooltipOwner.isConnected || !tooltipOwner.getClientRects().length) { hideTooltip(); return; }
        const rect = tooltipOwner.getBoundingClientRect();
        const width = tooltip.offsetWidth;
        const height = tooltip.offsetHeight;
        tooltip.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px';
        tooltip.style.top = Math.max(12, rect.bottom + height + 10 < window.innerHeight ? rect.bottom + 6 : rect.top - height - 6) + 'px';
    };
    const showTooltip = button => {
        hideTooltip();
        tooltipOwner = button;
        text(tooltip, describeField(button.dataset.metric));
        tooltip.hidden = false;
        button.setAttribute('aria-describedby', tooltip.id);
        positionTooltip();
    };
    root.addEventListener('mouseover', event => {
        const button = event.target.closest('.hs-metric-help');
        if (button && button !== tooltipOwner) showTooltip(button);
    });
    root.addEventListener('mouseout', event => {
        if (tooltipOwner && (tooltipOwner.contains(event.target) || tooltip.contains(event.target)) &&
            !tooltipOwner.contains(event.relatedTarget) && !tooltip.contains(event.relatedTarget) &&
            document.activeElement !== tooltipOwner) hideTooltip();
    });
    root.addEventListener('focusin', event => {
        if (event.target.matches('.hs-metric-help')) showTooltip(event.target);
    });
    root.addEventListener('focusout', event => {
        if (event.target === tooltipOwner) hideTooltip();
    });
    document.addEventListener('click', event => {
        if (event.target.closest('.hs-metric-help')) showTooltip(event.target.closest('.hs-metric-help'));
        else if (!tooltip.contains(event.target)) hideTooltip();
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hideTooltip(); });
    window.addEventListener('resize', positionTooltip);
    window.addEventListener('scroll', positionTooltip, true);

    const detailLabels = {qtime: labels.queue_time, ctime: labels.connect_time, rtime: labels.response_time,
        ttime: labels.total_time, last_chk: labels.check_detail, lastchg: labels.last_change,
        downtime: labels.downtime, addr: labels.address, mode: labels.mode};
    const renderDetails = entry => {
        if (entry.detail.hidden) return;
        const keys = new Set();
        Object.entries(entry.data.metrics).forEach(([key, value]) => {
            // '-' separates static CSV fields from module fields; it is not a metric.
            if (key === '-') return;
            keys.add(key);
            if (!entry.detailFields.has(key)) {
                const pair = make('div');
                const term = make('dt');
                const help = make('button', 'hs-metric-help', detailLabels[key] ? detailLabels[key] + ' (' + key + ')' : key);
                help.type = 'button';
                help.dataset.metric = key;
                term.append(help);
                const description = make('dd');
                pair.append(term, description);
                entry.detailCell.append(pair);
                entry.detailFields.set(key, {pair, description});
            }
            text(entry.detailFields.get(key).description, value == null ? '—' :
                ['qtime', 'ctime', 'rtime', 'ttime', 'qtime_max', 'ctime_max', 'rtime_max', 'ttime_max', 'check_duration', 'agent_duration'].includes(key) ? value + ' ms' :
                    ['lastchg', 'downtime'].includes(key) ? duration(value) : String(value));
        });
        entry.detailFields.forEach((field, key) => {
            if (!keys.has(key)) { field.pair.remove(); entry.detailFields.delete(key); }
        });
        positionTooltip();
    };

    const newGroup = proxy => {
        const element = make('details', 'hs-group');
        element.open = true;
        const summary = make('summary');
        const name = make('span', '', proxy);
        const note = make('span', 'hs-group-note');
        summary.append(name, note);
        const scroll = make('div', 'hs-table-scroll');
        const table = make('table');
        const head = make('thead');
        const heading = make('tr');
        heading.append(make('th', '', labels.name));
        columns.forEach(column => {
            const cell = make('th', '', column.label);
            cell.dataset.column = column.id;
            cell.scope = 'col';
            heading.append(cell);
        });
        if (canManage) heading.append(make('th', 'admin-actions-cell', labels.actions));
        head.append(heading);
        const body = make('tbody');
        table.append(head, body);
        scroll.append(table);
        element.append(summary, scroll);
        get('groups').append(element);
        return {element, note, body, rows: new Map()};
    };
    const newRow = group => {
        const main = make('tr', 'hs-row');
        const nameCell = make('td', 'hs-name');
        const button = make('button', 'hs-detail-button', '▸');
        button.type = 'button';
        button.setAttribute('aria-expanded', 'false');
        const name = make('span');
        const kind = make('span', 'hs-kind');
        nameCell.append(button, name, kind);
        main.append(nameCell);
        const cells = new Map();
        columns.forEach(column => {
            const cell = make('td');
            cell.dataset.column = column.id;
            const value = make(column.id === 'sessions' ? 'button' : 'span', column.id === 'sessions' ? 'hs-session-link hs-session-count-link' : '');
            if (column.id === 'sessions') {
                value.type = 'button';
                value.addEventListener('click', () => {
                    if (!['frontend', 'backend', 'server'].includes(entry.data.kind)) return;
                    views.sessions.setScope(entry.data);
                    selectView('sessions');
                });
            }
            cell.append(value);
            main.append(cell);
            cells.set(column.id, value);
        });
        const actionCell = canManage ? make('td', 'admin-actions-cell') : null;
        if (actionCell) main.append(actionCell);
        const detail = make('tr');
        detail.hidden = true;
        const container = make('td', 'hs-detail-cell');
        const detailCell = make('dl', 'hs-detail-grid');
        container.append(detailCell);
        detail.append(container);
        group.body.append(main, detail);
        const entry = {main, name, kind, button, cells, detail, detailCell, actionCell, actions: null, detailFields: new Map(), data: null};
        button.addEventListener('click', () => {
            detail.hidden = !detail.hidden;
            button.setAttribute('aria-expanded', String(!detail.hidden));
            text(button, detail.hidden ? '▸' : '▾');
            renderDetails(entry);
            positionTooltip();
        });
        return entry;
    };
    const matches = row => {
        const query = get('search').value.trim().toLocaleLowerCase();
        const state = get('state').value;
        return (!query || [row.proxy, row.name, row.address].some(value => String(value || '').toLocaleLowerCase().includes(query))) &&
            (state === 'all' || row.state === state || (state === 'drain' && row.state === 'nolb')) &&
            (get('kind').value === 'all' || row.kind === get('kind').value) &&
            (!get('backup').checked || (row.kind === 'server' && row.backup)) &&
            (!get('problems').checked || ['down', 'nolb', 'unknown'].includes(row.state));
    };
    const filterRows = () => {
        let count = 0;
        groups.forEach(group => {
            let visible = 0;
            group.rows.forEach(entry => {
                const show = matches(entry.data);
                entry.main.hidden = !show;
                entry.detail.hidden = !show || entry.button.getAttribute('aria-expanded') !== 'true';
                renderDetails(entry);
                if (show) visible++;
            });
            group.element.hidden = visible === 0;
            text(group.note, visible + ' / ' + group.rows.size);
            count += visible;
        });
        get('empty').hidden = !snapshot || count > 0;
        text(get('count'), snapshot ? labels.visible + ': ' + count + ' / ' + snapshot.rows.length : '');
        positionTooltip();
    };
    filterIds.forEach(id => get(id).addEventListener(id === 'search' ? 'input' : 'change', () => {
        filterRows(); savePreferences();
    }));

    const render = data => {
        const summary = [
            ['version', labels.version, data.info.Version],
            ['uptime', labels.uptime, duration(data.info.Uptime_sec)],
            ['connections', labels.connections, number(data.info.CurrConns) + ' / ' + number(data.info.Maxconn)],
            ['rate', labels.connection_rate, number(data.info.ConnRate)],
            ['servers', labels.servers, number(data.summary.servers)],
            ['down', 'DOWN / MAINT / DRAIN', [data.summary.down, data.summary.maint, data.summary.drain]]
        ];
        summary.forEach(([key, label, value]) => {
            if (!cards.has(key)) {
                const card = make('div', 'hs-card');
                card.dataset.card = key;
                const title = make('span', 'hs-card-label', label);
                const strong = make('strong');
                if (key === 'down') {
                    title.replaceChildren(...['down', 'maint', 'drain'].flatMap((state, index) =>
                        [...(index ? [' / '] : []), make('span', 'hs-state-' + state, state.toUpperCase())]));
                }
                card.append(title, strong);
                if (key === 'connections' && canManage) {
                    const actions = serverActions({data: {kind: 'global'}});
                    card.append(actions);
                    renderActionIcons(actions);
                }
                get('summary').append(card);
                cards.set(key, strong);
            }
            if (key === 'down') {
                cards.get(key).replaceChildren(...['down', 'maint', 'drain'].flatMap((state, index) =>
                    [...(index ? [' / '] : []), make('span', 'hs-state-' + state, number(value[index]))]));
            } else {
                text(cards.get(key), value);
            }
        });
        get('summary').hidden = false;
        const liveGroups = new Map();
        data.rows.forEach(row => {
            const key = JSON.stringify([row.metrics.pid, row.metrics.iid, row.proxy]);
            if (!groups.has(key)) groups.set(key, newGroup(row.proxy));
            if (!liveGroups.has(key)) liveGroups.set(key, new Set());
            liveGroups.get(key).add(row.key);
            const group = groups.get(key);
            if (!group.rows.has(row.key)) group.rows.set(row.key, newRow(group));
            const entry = group.rows.get(row.key);
            entry.data = row;
            if (canManage && ['server', 'frontend', 'backend'].includes(row.kind) && !entry.actions) {
                entry.actions = serverActions(entry);
                entry.actionCell.append(entry.actions);
                renderActionIcons(entry.actions);
            }
            entry.main.dataset.kind = row.kind;
            entry.main.dataset.backup = String(row.backup);
            text(entry.name, row.name);
            text(entry.kind, [row.kind, row.mode, row.backup ? 'backup' : null].filter(Boolean).join(' · '));
            entry.button.setAttribute('aria-label', labels.details + ': ' + row.proxy + '/' + row.name);
            entry.cells.get('sessions').setAttribute('aria-label', labels.session_view + ': ' + row.proxy + '/' + row.name);
            columns.forEach(column => text(entry.cells.get(column.id), column.value(row)));
            entry.cells.get('status').className = 'hs-badge hs-state-' + row.state;
        });
        groups.forEach((group, key) => {
            if (!liveGroups.has(key)) { group.element.remove(); groups.delete(key); return; }
            group.rows.forEach((entry, rowKey) => {
                if (!liveGroups.get(key).has(rowKey)) { entry.main.remove(); entry.detail.remove(); group.rows.delete(rowKey); }
            });
        });
        applyColumns();
        filterRows();
        updateActions();
    };

    const viewOptions = {get, make, labels, canManage, renderActionIcons, makeMenu: actionMenu,
        getServer: () => get('server').value,
        isBusy: () => busy || !!actionPending || root.dataset.stale === 'true',
        onBusyChange: () => { updateActions(); schedule(); }, onRefresh: refresh};
    views.sessions = window.HaproxyStatsSessions({...viewOptions, getSnapshot: () => snapshots.sessions});
    views.tables = window.HaproxyStatsTables({...viewOptions, getSnapshot: () => snapshots.tables,
        onTableChange: () => {
            selectedTable = get('table-select').value;
            generation++;
            if (controller) controller.abort();
            busy = false;
            get('action-result').hidden = true;
            refresh();
        }});

    const status = (prefix = '') => {
        const current = currentSnapshot();
        const time = current ? new Date(current.collected_at).toLocaleTimeString() : '';
        text(get('status'), [prefix, time ? labels.updated + ': ' + time : '',
            get('interval').value === '0' ? labels.paused : ''].filter(Boolean).join(' · '));
    };
    const schedule = () => {
        clearTimeout(timer);
        const interval = Number(get('interval').value);
        if (!stopped && interval && get('server').value && !document.hidden && !busy && !actionPending && !runtimePending()) timer = setTimeout(refresh, interval * 1000);
    };
    async function refresh() {
        if (busy || stopped || actionPending || runtimePending() || !get('server').value) return;
        clearTimeout(timer);
        const server = get('server').value;
        const token = ++generation;
        busy = true;
        get('refresh').disabled = true;
        updateActions();
        const requestController = new AbortController();
        controller = requestController;
        let timedOut = false;
        const timeout = setTimeout(() => { timedOut = true; requestController.abort(); }, 20000);
        status(labels.loading);
        try {
            const endpoint = activeView === 'overview' ? 'view' : activeView;
            const query = activeView === 'tables' && selectedTable ? '?' + new URLSearchParams({table: selectedTable}) : '';
            const response = await fetch('/stats/' + endpoint + '/haproxy/' + encodeURIComponent(server) + query, {
                signal: requestController.signal, cache: 'no-store',
                headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            });
            let data;
            try { data = await response.json(); }
            catch (_) { throw new Error('invalid_response'); }
            if (!response.ok || data.status !== 'ok') {
                throw new Error(response.status === 401 ? 'auth_required' : response.status === 403 ? 'permission_denied' : data.code || 'operation_failed');
            }
            if (token !== generation) return;
            const current = currentSnapshot();
            const restarted = current && (current.info.Pid !== data.info.Pid || current.info.Uptime_sec > data.info.Uptime_sec);
            if (activeView !== 'overview') {
                if (restarted) views[activeView].reset();
                snapshots[activeView] = data;
                if (activeView === 'tables') selectedTable = data.table?.name || '';
                views[activeView].render();
            } else {
                snapshot = data;
                render(data);
            }
            get('error').hidden = true;
            root.dataset.stale = 'false';
            status(restarted ? labels.restarted : '');
        } catch (error) {
            if (token !== generation) return;
            // Reload the catalogue on the next refresh if a reload removed the table.
            if (activeView === 'tables' && error.message === 'table_gone') selectedTable = '';
            get('error').hidden = false;
            text(get('error'), (currentSnapshot() ? labels.stale + ' ' : '') +
                (timedOut ? labels.runtime_timeout : labels[error.message] || labels.operation_failed));
            root.dataset.stale = currentSnapshot() ? 'true' : 'false';
            status(currentSnapshot() ? labels.stale : labels.unavailable);
        } finally {
            clearTimeout(timeout);
            if (token === generation) {
                busy = false;
                controller = null;
                get('refresh').disabled = !get('server').value;
                updateActions();
                schedule();
            }
        }
    }
    const showView = () => {
        viewNames.forEach(view => {
            get(view).hidden = view !== activeView;
            get('tab-' + view).setAttribute('aria-selected', String(view === activeView));
        });
    };
    const selectView = view => {
        if (view === activeView) return;
        Object.values(views).forEach(view => view.deactivate());
        selection++;
        actionPending = null;
        if (actionDialog) $(actionDialog).dialog('close');
        generation++;
        if (controller) controller.abort();
        controller = null;
        busy = false;
        clearTimeout(timer);
        activeView = view;
        get('error').hidden = true;
        get('action-result').hidden = true;
        root.dataset.stale = 'false';
        hideTooltip();
        showView();
        const url = new URL(location.href);
        if (view !== 'overview') url.searchParams.set('view', view); else url.searchParams.delete('view');
        history.replaceState(null, '', url);
        status();
        updateActions();
        refresh();
    };
    viewNames.forEach(view => get('tab-' + view).addEventListener('click', () => selectView(view)));
    get('refresh').addEventListener('click', refresh);
    get('interval').addEventListener('change', () => { if (!busy) status(); schedule(); });
    get('server').addEventListener('change', () => {
        hideTooltip();
        selection++;
        actionPending = null;
        if (actionDialog) $(actionDialog).dialog('close');
        get('action-result').hidden = true;
        generation++;
        if (controller) controller.abort();
        controller = null;
        busy = false;
        clearTimeout(timer);
        snapshot = null;
        selectedTable = '';
        Object.keys(views).forEach(name => { snapshots[name] = null; views[name].reset(); });
        groups.clear();
        get('groups').replaceChildren();
        get('summary').hidden = true;
        get('error').hidden = true;
        root.dataset.stale = 'false';
        filterRows();
        get('refresh').disabled = !get('server').value;
        if (get('server').value) {
            history.replaceState(null, '', '/stats/haproxy/' + encodeURIComponent(get('server').value) + (activeView !== 'overview' ? '?view=' + activeView : ''));
            refresh();
        } else {
            history.replaceState(null, '', '/stats/haproxy/');
            text(get('status'), labels.select_server);
        }
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) clearTimeout(timer);
        else if (get('interval').value !== '0') refresh();
    });
    window.addEventListener('pagehide', () => {
        hideTooltip();
        selection++;
        actionPending = null;
        if (actionDialog) $(actionDialog).dialog('close');
        stopped = true;
        Object.values(views).forEach(view => view.deactivate());
        generation++;
        clearTimeout(timer);
        if (controller) controller.abort();
    });
    window.addEventListener('pageshow', event => {
        if (event.persisted) { stopped = false; busy = false; refresh(); }
    });
    get('refresh').disabled = !get('server').value;
    // The common initializer owns these widgets; retain native events for this page.
    ['server', 'interval'].forEach(id => {
        $(get(id)).on('selectmenuchange', () => get(id).dispatchEvent(new Event('change')));
    });
    showView();
    if (get('server').value) refresh();
}());
