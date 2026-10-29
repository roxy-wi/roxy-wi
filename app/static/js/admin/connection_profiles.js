/* Group-scoped connection profiles; credential values are never read back. */
(() => {
    'use strict';
    const form = document.getElementById('connection-profile-form');
    const table = document.querySelector('#connection-profile-table tbody');
    const status = document.getElementById('connection-profile-status');
    const t = JSON.parse(document.getElementById('connection-profile-translations').textContent);
    const secretFields = ['password', 'token', 'ca_pem', 'client_cert_pem', 'client_key_pem'];
    const fields = ['name', 'group_id', 'transport', 'host', 'port', 'url', 'timeout', 'framing', 'auth', 'username', 'header_name'];
    const endpoint = '/admin/connection-profiles';
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
            const values = {...profile.settings, name: profile.name, group_id: profile.group_id};
            fields.forEach(key => { form.elements[key].value = values[key]; });
            form.elements.group_id.disabled = true;
            form.elements.enabled.checked = profile.enabled;
            secretFields.forEach(key => {
                form.querySelector(`[data-configured="${key}"]`).textContent = profile.configured[key] ? t.configured : '';
            });
        }
        document.getElementById('connection-profile-form-title').textContent = profile ? t.edit : t.new;
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
        for (const profile of data.profiles) {
            const row = document.createElement('tr');
            [profile.name, transportLabels[profile.settings.transport], profile.group_id === 0 ? t.shared : t.current_group,
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
                    message(`${result.detail}${result.http_status ? ' (' + result.http_status + ')' : ''}`);
                });
                action(cell, t.remove, async () => {
                    if (!window.confirm(t.confirm_remove)) return;
                    await request('DELETE', `${endpoint}/${profile.id}`, {revision: profile.revision});
                    reset(); await reload(); message(t.removed);
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
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        try {
            await request(id ? 'PUT' : 'POST', id ? `${endpoint}/${id}` : endpoint, data);
            reset(); await reload(); message(t.saved);
        } catch (error) { message(error.message); }
        finally { button.disabled = false; }
    });
    document.getElementById('connection-profile-new').addEventListener('click', () => edit());
    document.getElementById('connection-profile-cancel').addEventListener('click', reset);
    reload().catch(error => message(error.message));
})();
