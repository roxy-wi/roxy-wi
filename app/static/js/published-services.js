document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('published-services');
    if (!root) return;
    const el = id => document.getElementById('map-' + id);
    const node = (tag, text) => {
        const value = document.createElement(tag);
        if (text !== undefined) value.textContent = text;
        return value;
    };
    const endpoint = value => (value.host.includes(':') ? '[' + value.host + ']' : value.host) + ':' + value.port;
    const dialog = jQuery(el('confirm-dialog')).removeClass('ui-helper-hidden').dialog({
        autoOpen: false, modal: true, title: 'Confirm publication relationship',
        width: Math.min(640, window.innerWidth - 32), maxHeight: window.innerHeight - 32,
        classes: {'ui-dialog': 'rw-dialog-responsive'}
    });
    let servers = [], selected, timer, generation = 0, discoveryPending = false;
    function message(text, error = false, busy = false) {
        el('message').classList.toggle('rw-error-state', error);
        window.RoxywiUI.operationStatus(el('message'), null, text, busy);
    }
    function disabled(button, value) {
        if (!button) return;
        button.disabled = value;
        if (jQuery(button).button('instance')) jQuery(button).button('refresh');
    }
    function discoveryButton() {
        disabled(el('discover'), discoveryPending || !el('server').value);
    }
    async function api(path = '', data, method) {
        try {
            return await jQuery.ajax({url: root.dataset.api + path,
                method: method || (data === undefined ? 'GET' : 'POST'),
                contentType: 'application/json', global: false,
                data: data === undefined ? undefined : JSON.stringify(data)});
        } catch (error) {
            throw new Error(error.responseJSON?.error || 'Service map request failed');
        }
    }
    function select(input, values, first) {
        const old = input.value;
        input.replaceChildren(...(first ? [new Option(first, '')] : []), ...values.map(v => new Option(v.name, v.id)));
        if (values.some(v => String(v.id) === old)) input.value = old;
        if (jQuery(input).selectmenu('instance')) jQuery(input).selectmenu('refresh');
        else jQuery(input).selectmenu();
    }
    function action(menu, text, run, danger = false) {
        const button = node('button', text);
        button.type = 'button';
        button.className = 'admin-action-item' + (danger ? ' admin-action-item-danger' : '');
        button.setAttribute('role', 'menuitem');
        button.addEventListener('click', run);
        menu.append(button);
    }
    function render(item) {
        const row = node('tr'), domain = node('td'), proxy = node('td'), details = node('td'), actions = node('td');
        domain.append(node('strong', item.domain || 'Domain unknown'));
        const relationship = node('span', item.relationship);
        relationship.className = 'rw-status-badge ' + (item.confirmation ? 'rw-status-running' : 'rw-status-stale');
        const evidence = node('p'); evidence.append(relationship); domain.append(evidence);
        domain.append(node('p', 'Domain: ' + item.domain_origin));
        if (item.confirmation) domain.append(node('p', item.confirmation.note));
        proxy.append(node('strong', item.server + ' · ' + item.service), node('p', item.frontend),
            node('p', new Date(item.observed_at).toLocaleString()));
        for (const [visible, text] of [[!item.identity_current, 'STALE: server/runtime identity changed'], [item.partial, 'Partial configuration inventory']]) {
            if (visible) {
                const status = node('p', text); status.className = 'rw-status-badge rw-status-unavailable'; proxy.append(status);
            }
        }
        details.append(node('p', item.ha.map(c => c.provider + ': ' + c.name).join(', ') || 'No registered HA dependency visible'),
            node('p',item.certificate.length?item.certificate.map(c=>c.state+' · '+c.tls+' · '+(c.fingerprint||'No fingerprint')+' · '+new Date(c.observed_at).toLocaleString()+(c.expectation_current?'':' · expected source changed')).join('; '):'No served-TLS assessment; configured files are not client evidence'), node('p', item.impact.map(i => 'Node #' + i.server_id + ': ' + i.reason).join('; ')));
        const more = node('details');
        more.append(node('summary', 'Snapshot scope'), node('p', item.freshness), node('p', 'Host addresses: ' + item.addresses.join(', ')));
        details.append(more);
        const wrapper = el('action-menu').content.firstElementChild.cloneNode(true);
        wrapper.querySelector('.admin-actions-toggle').setAttribute('aria-label', 'Actions for ' + (item.domain || item.frontend) + ' on ' + item.server);
        const menu = wrapper.querySelector('.admin-actions-menu');
        const link = node('a', 'Diagnose'); link.className = 'admin-action-item'; link.setAttribute('role', 'menuitem');
        link.href = '/insights/diagnostics?' + new URLSearchParams({service: item.service, server_id: String(item.server_id)}); menu.append(link);
        if (root.dataset.write === '1' && item.identity_current) action(menu, 'Confirm relationship', () => {
            selected = item; el('domain').value = item.domain; el('note').value = ''; el('confirm-message').textContent = '';
            dialog.dialog('open');
        });
        if (root.dataset.write === '1' && item.confirmation) action(menu, 'Retract confirmation', async () => {
            try { await api('/confirm/' + item.confirmation.id, undefined, 'DELETE'); await refresh(); }
            catch (error) { message(error.message, true); }
        }, true);
        actions.className = 'admin-actions-cell'; actions.append(wrapper);
        row.append(domain, node('td', item.listeners.map(endpoint).join(', ') || 'Unknown'), proxy,
            node('td', item.backends.map(endpoint).join(', ') || 'None discovered'), details, actions);
        for (const cell of row.children) {
            if (cell.childNodes.length > 1) {
                const content = node('div'); content.append(...cell.childNodes); cell.append(content);
            }
        }
        return row;
    }
    async function refresh() {
        const current = ++generation;
        root.setAttribute('aria-busy', 'true'); disabled(el('refresh'), true); message('Loading service map…', false, true);
        try {
            const result = await api(el('impact').value ? '?impact_node=' + encodeURIComponent(el('impact').value) : '');
            if (current !== generation) return;
            el('rows').replaceChildren(...result.data.map(render)); el('results').hidden = false;
            if (window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node: el('rows')});
            message(result.summary + (result.omitted ? ' Some snapshots are no longer accessible.' : ''));
        } catch (error) {
            if (current === generation) message(error.message + (el('results').hidden ? '' : ' The displayed map is from the last successful refresh.'), true);
        } finally {
            if (current === generation) { root.setAttribute('aria-busy', 'false'); disabled(el('refresh'), false); }
        }
    }
    async function poll(id) {
        try {
            const value = await jQuery.ajax({url: root.dataset.assessments.replace(/\/0$/, '/' + id), global: false});
            if (['created', 'published', 'running'].includes(value.data.status)) {
                timer = setTimeout(() => poll(id), 2000); return;
            }
            discoveryPending = false; discoveryButton(); await refresh();
            if (value.data.error) message(value.data.error, true);
        } catch (error) {
            discoveryPending = false; discoveryButton(); message(error.responseJSON?.error || 'Discovery status failed', true);
        }
    }
    function choose() {
        select(el('server'), servers.filter(s => s.services.includes(el('service').value)).map(s => ({id: s.id, name: s.name + ' (' + s.ip + ')'})), 'Select proxy');
        discoveryButton();
    }
    el('form').addEventListener('submit', async event => {
        event.preventDefault(); if (!el('server').value || discoveryPending) return;
        clearTimeout(timer); discoveryPending = true; discoveryButton();
        try {
            const result = await api('/discover', {service: el('service').value, server_id: Number(el('server').value)});
            message('Discovery queued in Operations.', false, true); poll(result.id);
        } catch (error) { discoveryPending = false; discoveryButton(); message(error.message, true); }
    });
    el('confirm-form').addEventListener('submit', async event => {
        event.preventDefault(); const submit = event.submitter; disabled(submit, true);
        try {
            await api('/confirm', {assessment_id: selected.assessment_id, frontend_id: selected.frontend_id,
                domain: el('domain').value, note: el('note').value});
            dialog.dialog('close'); await refresh();
        } catch (error) { el('confirm-message').textContent = error.message; }
        finally { disabled(submit, false); }
    });
    el('cancel').addEventListener('click', () => dialog.dialog('close'));
    el('refresh').addEventListener('click', refresh);
    jQuery(el('impact')).selectmenu({change: refresh}); el('impact').addEventListener('change', refresh);
    jQuery(el('service')).selectmenu({change: choose}); el('service').addEventListener('change', choose);
    jQuery(el('server')).selectmenu({change: discoveryButton}); el('server').addEventListener('change', discoveryButton);
    discoveryButton();
    jQuery.ajax({url: root.dataset.choices, global: false}).then(data => {
        servers = data.servers; select(el('service'), data.services.map(name => ({id: name, name}))); choose();
        select(el('impact'), data.nodes.map(s => ({id: s.id, name: s.name + ' (#' + s.id + ')'})), 'All discovered services'); refresh();
    }).catch(() => message('Could not load registered proxy choices', true));
    window.addEventListener('pagehide', () => { clearTimeout(timer); generation++; });
});
