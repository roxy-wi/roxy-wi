/* Group-scoped audit receivers; credential values are never read back. */
(() => {
    'use strict';
    const form = document.getElementById('audit-receiver-form');
    const table = document.querySelector('#audit-receiver-table tbody');
    const status = document.getElementById('audit-receiver-status');
    const t = JSON.parse(document.getElementById('audit-receiver-translations').textContent);
    const secretFields = ['password', 'token', 'ca_pem', 'client_cert_pem', 'client_key_pem'];
    const fields = ['name', 'group_id', 'transport', 'host', 'port', 'url', 'timeout', 'framing', 'auth', 'username', 'header_name'];
    const endpoint = '/admin/audit-receivers';
    const transportLabels = {tcp_tls: 'TCP + TLS', tcp: 'TCP', udp: 'UDP', https: 'HTTPS'};
    function transportDefaults() {
        if ([6514, 514, 443].includes(Number(form.elements.port.value))) {
            form.elements.port.value = {tcp_tls: 6514, tcp: 514, udp: 514, https: 443}[form.elements.transport.value];
        }
    }
    form.elements.transport.addEventListener('change', transportDefaults);
    $(form.elements.transport).on('selectmenuchange', transportDefaults);
    function request(method, url, data) {
        return new Promise((resolve, reject) => $.ajax({
            type: method, url, contentType: 'application/json',
            data: data === undefined ? undefined : JSON.stringify(data),
            success: resolve,
            error: xhr => reject(new Error(xhr.responseJSON?.error || t.failed))
        }));
    }
    function message(text) { status.textContent = text; }
    function refreshWidgets() {
        form.querySelectorAll('select').forEach(node => {
            if ($(node).data('ui-selectmenu')) $(node).selectmenu('refresh');
        });
        form.querySelectorAll('[type="checkbox"]').forEach(node => {
            if ($(node).data('ui-checkboxradio')) $(node).checkboxradio('refresh');
        });
    }
    function reset() {
        form.reset();
        form.elements.id.value = '';
        form.elements.revision.value = '';
        form.elements.group_id.disabled = false;
        form.querySelectorAll('[data-configured]').forEach(node => { node.textContent = ''; });
        refreshWidgets();
        form.hidden = true;
    }
    function edit(profile) {
        reset();
        if (profile) {
            form.elements.id.value = profile.id;
            form.elements.revision.value = profile.revision;
            const values = {...profile.connection, name: profile.name, group_id: profile.group_id};
            fields.forEach(key => { form.elements[key].value = values[key]; });
            if (![...form.elements.group_id.options].some(option => option.value === String(profile.group_id))) {
                form.elements.group_id.add(new Option(String(profile.group_id), String(profile.group_id)));
            }
            form.elements.group_id.value = profile.group_id;
            form.elements.group_id.disabled = true;
            form.elements.events.value = profile.events.join(', ');
            form.elements.profile_id.value = profile.profile_id || '';
            form.elements.enabled.checked = profile.enabled;
            secretFields.forEach(key => {
                form.querySelector(`[data-configured="${key}"]`).textContent = profile.configured[key] ? t.configured : '';
            });
        }
        document.getElementById('audit-receiver-form-title').textContent = profile ? t.edit : t.new;
        form.hidden = false;
        refreshWidgets();
        form.elements.name.focus();
    }
    function action(cell, label, run) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = label;
        button.addEventListener('click', async () => {
            button.disabled = true;
            $(button).button('refresh');
            try { await run(); } catch (error) { message(error.message); }
            finally { button.disabled = false; $(button).button('refresh'); }
        });
        cell.append(button);
        $(button).button();
    }
    async function reload() {
        const data = await request('GET', endpoint);
        table.replaceChildren();
        const queue = await request('GET', '/admin/audit-status');
        document.getElementById('audit-receiver-queue').textContent = Object.entries(queue.counts)
            .map(([key, value]) => `${t.states[key] || key}: ${value}`).join(' · ') || t.empty_queue;
        document.getElementById('audit-profile-select').hidden = !data.profiles_available;
        document.getElementById('audit-profile-help').hidden = !data.profiles_available;
        const selectedProfile = form.elements.profile_id.value;
        form.elements.profile_id.replaceChildren(new Option(t.inline, ''));
        if (data.profiles_available) {
            const shared = await request('GET', '/admin/connection-profiles');
            for (const item of shared.profiles.filter(item => item.enabled)) {
                form.elements.profile_id.add(new Option(item.name + ' (r' + item.revision + ')', item.id));
            }
        }
        form.elements.profile_id.value = selectedProfile;
        refreshWidgets();
        for (const profile of data.receivers) {
            const row = document.createElement('tr');
            [profile.name, transportLabels[profile.connection.transport], profile.group_id === 0 ? t.shared : profile.group_id === Number(form.dataset.groupId) ? t.current_group : String(profile.group_id),
             profile.enabled ? t.yes : t.no].forEach(value => {
                const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
            });
            const cell = document.createElement('td');
            const canManage = Number(form.dataset.role) === 1 || profile.group_id !== 0;
            if (canManage) {
                action(cell, t.edit, () => edit(profile));
                action(cell, t.test, async () => {
                    message(t.checking);
                    const result = await request('POST', `${endpoint}/${profile.id}/test`, {});
                    message(`${result.detail || result.status}${result.http_status ? ' (' + result.http_status + ')' : ''}`);
                });
                action(cell, t.retry, async () => {
                    if (!window.confirm(t.confirm_retry)) return;
                    const result = await request('POST', `${endpoint}/${profile.id}/retry`, {revision: profile.revision, include_pending: true});
                    message(`${t.retried}: ${result.retried}`); await reload();
                });
                if (!profile.enabled) action(cell, t.remove, async () => {
                    if (!window.confirm(t.confirm_remove)) return;
                    await request('DELETE', `${endpoint}/${profile.id}`, {revision: profile.revision});
                    if (form.elements.id.value === String(profile.id)) reset();
                    await reload(); message(t.removed);
                });
            }
            row.append(cell); table.append(row);
        }
    }
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const data = {enabled: form.elements.enabled.checked, secrets: {}, clear_secrets: []};
        fields.forEach(key => { data[key] = form.elements[key].value; });
        ['group_id', 'port', 'timeout'].forEach(key => { data[key] = Number(data[key]); });
        const id = form.elements.id.value;
        if (id) data.revision = Number(form.elements.revision.value);
        secretFields.forEach(key => {
            if (form.elements[key].value) data.secrets[key] = form.elements[key].value;
            if (form.elements['clear_' + key].checked) data.clear_secrets.push(key);
        });
        const payload = {name: data.name, group_id: data.group_id, enabled: data.enabled,
            events: form.elements.events.value.split(',').map(value => value.trim()).filter(Boolean)};
        if (id) payload.revision = data.revision;
        if (form.elements.profile_id.value) payload.profile_id = Number(form.elements.profile_id.value);
        else {
            delete data.name; delete data.group_id; delete data.enabled; delete data.revision;
            payload.connection = data;
        }
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        try {
            await request(id ? 'PUT' : 'POST', id ? `${endpoint}/${id}` : endpoint, payload);
            reset(); await reload(); message(t.saved);
        } catch (error) { message(error.message); }
        finally { button.disabled = false; }
    });
    document.getElementById('audit-receiver-new').addEventListener('click', () => edit());
    document.getElementById('audit-receiver-cancel').addEventListener('click', reset);
    reload().catch(error => message(error.message));
})();
