/* Provider schemas describe settings; certificate material never reaches this page. */
$(function () {
    const root = document.getElementById('certificate-sources');
    if (!root) return;
    const apiRoot = root.dataset.api;
    const el = id => document.getElementById('source-' + id);
    let choices, current = null, destinations = [], timer, refreshing = false, hasError = false;
    el('new').disabled = true;
    const api = (path = '', method = 'GET', body) => $.ajax({url: apiRoot + path, method,
        contentType: 'application/json', data: body === undefined ? undefined : JSON.stringify(body), global: false});
    const message = (text, error = false) => {
        hasError = error; el('message').textContent = text;
        el('message').className = error ? 'rw-error-state' : 'rw-form-help';
    };
    const guard = fn => async event => {
        event?.preventDefault();
        try { await fn(event); }
        catch (error) { message(error.responseJSON?.error || error.message || 'Certificate source operation failed', true); }
    };
    function select(node, options, value = '') {
        node.replaceChildren(...options.map(item => new Option(item.name, item.id)));
        node.value = String(value);
        if ($(node).selectmenu('instance')) $(node).selectmenu('refresh'); else $(node).selectmenu();
    }
    function settings(values = {}) {
        const definition = choices.providers.find(item => item.id === el('provider').value);
        el('settings').replaceChildren();
        for (const [name, field] of Object.entries(definition.schema.properties)) {
            const wrapper = document.createElement('div'); wrapper.className = 'rw-form-field';
            const label = document.createElement('label'); label.htmlFor = 'source-setting-' + name;
            label.textContent = field.title || name;
            const input = document.createElement(name === 'ca_pem' ? 'textarea' : 'input');
            input.id = label.htmlFor; input.dataset.setting = name; input.className = 'form-control';
            const secret = definition.secret_fields.includes(name);
            if (input.tagName === 'INPUT') input.type = secret ? 'password' : 'text';
            input.autocomplete = 'off'; input.value = secret ? '' : (values[name] ?? field.default ?? '');
            input.required = definition.schema.required?.includes(name) && !(secret && current?.provider === definition.id);
            if (field.maxLength) input.maxLength = field.maxLength;
            wrapper.append(label, input); el('settings').append(wrapper);
        }
    }
    function edit(row = null) {
        current = row; el('form').reset();
        el('name').value = row?.name || '';
        select(el('provider'), choices.providers, row?.provider || choices.providers[0].id);
        settings(row?.settings);
        select(el('server'), [{id:'',name:'Select a registered HAProxy server'},...choices.servers], row?.binding_status === 'unavailable' ? '' : (row?.server_id || ''));
        select(el('cluster'), [{id:'', name:'Use the server and its existing HA replicas'}, ...choices.clusters], row?.cluster_id || '');
        el('pem').value = row?.pem_name || ''; el('domains').value = row?.domains.join(', ') || '';
        el('interval').value = row?.interval_minutes || 360; el('enabled').checked = row?.enabled || false;
        if ($(el('enabled')).checkboxradio('instance')) $(el('enabled')).checkboxradio('refresh');
        el('directory').value = row?.directory || '';
        destinations = row?.destination ? [row.destination] : [];
        select(el('destination'), [{id:'', name:'Update an existing loaded PEM'}, ...destinations.map((d,i) => ({id:i, name:d.kind + ' · ' + d.path}))], row?.destination ? 0 : '');
        el('editor').hidden = false;
        if (row?.binding_status === 'unavailable') message(row.binding_error);
    }
    const confirm = text => new Promise(resolve => {
        $('<p>').text(text).dialog({modal:true, title:'Confirm', classes:{'ui-dialog':'rw-dialog-responsive'},
            buttons:[{text:'Cancel',click(){resolve(false);$(this).dialog('close');}},
                     {text:'Confirm',click(){resolve(true);$(this).dialog('close');}}],
            close(){resolve(false);$(this).dialog('destroy').remove();}});
    });
    function button(label, fn) {
        const node = document.createElement('button'); node.type = 'button'; node.className = 'admin-action-item'; node.setAttribute('role','menuitem');
        node.textContent = label; node.addEventListener('click', guard(fn)); return node;
    }
    async function refresh() {
        if (refreshing) return;
        clearTimeout(timer);
        refreshing = true; el('refresh').disabled = true; root.setAttribute('aria-busy','true');
        try {
        if (!choices) choices = await $.ajax({url:apiRoot.replace(/\/api$/,'/choices'),global:false});
        const result = await api();
        if (hasError) message('');
        el('rows').replaceChildren();
        for (const row of result.data) {
            const tr = document.createElement('tr');
            const values = [row.name,choices.providers.find(p=>p.id===row.provider)?.name || row.provider,row.domains.join(', '),row.status + (row.binding_error ? ' · ' + row.binding_error : row.error ? ' · ' + row.error : ''),row.last_check ? new Date(row.last_check).toLocaleString() : '—',row.next_check ? new Date(row.next_check).toLocaleString() : '—'];
            for (const [index,value] of values.entries()) {
                const td = document.createElement('td'); td.textContent = value;
                td.dataset.label = ['Name','Provider','Domains','Status','Last check','Next check'][index]; tr.append(td);
            }
            const cell = document.createElement('td'); cell.dataset.label='Actions';
            const group = document.createElement('div'); group.className='admin-actions';
            const toggle = document.createElement('button'); toggle.type='button';
            toggle.className='rw-icon-button admin-actions-toggle'; toggle.textContent='⋮';
            toggle.setAttribute('aria-label','Actions'); toggle.setAttribute('aria-haspopup','menu'); toggle.setAttribute('aria-expanded','false');
            const actions = document.createElement('div'); actions.className='admin-actions-menu'; actions.setAttribute('role','menu'); actions.hidden=true;
            group.append(toggle,actions); cell.append(group);
            actions.append(button('Edit', () => edit(row)), button('Check provider', async () => {
                await api('/' + row.id + '/check','POST',{}); message('Provider check queued; no deployment requested'); await refresh();
            }), button('Synchronize', async () => {
                if (await confirm('Deploy the current provider certificate to the selected HAProxy targets?')) {
                    await api('/' + row.id + '/sync','POST',{}); message('Synchronization queued; follow the source status and certificate history'); await refresh();
                }
            }));
            if (row.recovery_required) actions.append(button('Retry deployment recovery', async () => {
                if (await confirm('Retry the recorded certificate rollback or finalization?')) {
                    await api('/' + row.id + '/recover','POST',{}); message('Certificate recovery queued');
                }
            }));
            actions.append(button('Remove source', async () => {
                if (await confirm('Stop synchronization and remove this source? Deployed certificates will remain.')) {
                    await api('/' + row.id,'DELETE'); await refresh();
                }
            }));
            if (row.binding_status === 'unavailable') {
                actions.querySelectorAll('button').forEach(action => {
                    if (['Check provider','Synchronize','Retry deployment recovery'].includes(action.textContent)) action.disabled=true;
                });
            }
            tr.append(cell); el('rows').append(tr);
        }
        timer = setTimeout(() => guard(refresh)(),10000);
        } finally {
            refreshing = false; el('refresh').disabled = false; el('new').disabled = !choices;
            root.setAttribute('aria-busy','false');
        }
    }
    el('refresh').addEventListener('click',guard(refresh)); el('new').addEventListener('click',guard(() => edit()));
    el('cancel').addEventListener('click',() => {el('editor').hidden=true; el('settings').replaceChildren(); current=null;});
    $(el('provider')).on('selectmenuchange change',() => settings());
    el('destinations').addEventListener('click',guard(async () => {
        const response = await $.ajax({url:'/service/haproxy/certificates/' + Number(el('server').value),global:false});
        destinations = response.destinations || [];
        select(el('destination'),[{id:'',name:'Update an existing loaded PEM'},...destinations.map((d,i)=>({id:i,name:d.kind+' · '+d.path}))]);
        message('Loaded destinations discovered; select one for first deployment');
    }));
    el('form').addEventListener('submit',guard(async () => {
        const providerSettings = {};
        el('settings').querySelectorAll('[data-setting]').forEach(input => {
            const definition = choices.providers.find(item => item.id === el('provider').value);
            if (input.value || !definition.secret_fields.includes(input.dataset.setting)) providerSettings[input.dataset.setting] = input.value;
        });
        const destination = el('destination').value;
        const body = {name:el('name').value,provider:el('provider').value,settings:providerSettings,
            server_id:Number(el('server').value),cluster_id:el('cluster').value ? Number(el('cluster').value) : null,
            pem_name:el('pem').value,domains:el('domains').value.split(',').map(v=>v.trim()).filter(Boolean),
            interval_minutes:Number(el('interval').value),enabled:el('enabled').checked,
            destination:destination === '' ? null : destinations[Number(destination)],directory:el('directory').value || null,
            revision:current?.revision || null};
        await api(current ? '/' + current.id : '',current ? 'PUT' : 'POST',body);
        el('editor').hidden=true; el('settings').querySelectorAll('input[type=password]').forEach(input=>{input.value='';});
        message('Source saved'); await refresh();
    }));
    guard(refresh)();
    window.addEventListener('pagehide',() => clearTimeout(timer),{once:true});
});
