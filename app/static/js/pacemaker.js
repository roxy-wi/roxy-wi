/* Cluster values are rendered as text; never interpolate node output into HTML. */
jQuery(() => {
    'use strict';
    const root = document.getElementById('pacemaker-app');
    const operator = root.dataset.operator === 'true';
    const view = root.dataset.view || 'overview';
    const requestedCluster = new URLSearchParams(window.location.search).get('cluster');
    const byId = id => document.getElementById(`pcmk-${id}`);
    let clusters = [], servers = [], selected = null, digest = null, changeId = null, changeKind = 'cib', polling = false, discovery = null;
    const message = (text, error = false) => {
        byId('message').textContent = text;
        byId('message').className = error ? 'rw-error-state' : 'rw-form-help';
    };
    async function api(path, method = 'GET', body) {
        const response = await fetch(`/pacemaker/api${path}`, {
            method, credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-TOKEN': typeof csrf_token === 'undefined' ? '' : csrf_token},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Cluster request failed');
        return result;
    }
    const guard = fn => async event => {
        if (event) event.preventDefault();
        try { await fn(event); } catch (error) { message(error.message, true); }
    };
    function button(label, action) {
        const result = document.createElement('button');
        result.type = 'button'; result.className = 'rw-button rw-button-secondary';
        result.textContent = label; result.addEventListener('click', guard(action)); jQuery(result).button(); return result;
    }
    function cell(row, value) {
        const result = row.insertCell(); result.textContent = value === null || value === undefined ? '—' : String(value); return result;
    }
    function option(select, value, label) { select.add(new Option(label, value)); }
    function confirmAction(text, expectedName = null) {
        return RoxywiUI.confirm({title: 'Confirm cluster operation', message: text, confirmText: 'Continue', requiredText: expectedName});
    }
    function refreshSelect(select) { jQuery(select).selectmenu('refresh'); }
    function setDisabled(id, disabled) {
        const control = byId(id);
        jQuery(control)[control.tagName === 'SELECT' ? 'selectmenu' : 'button']('option', 'disabled', disabled);
    }
    function isTrue(value) { return value === true || value === 'true'; }
    function rowIn(id) {
        const body = byId(id); const row = body.insertRow();
        row.className = body.rows.length % 2 ? 'odd' : 'even'; return row;
    }
    function badge(container, label, state) {
        const status = document.createElement('span');
        status.className = `rw-status-badge rw-status-${state}`; status.textContent = label; container.append(status);
    }
    function actionMenu(cell, label, actions) {
        cell.className = 'admin-actions-cell';
        const wrapper = document.createElement('div'); wrapper.className = 'admin-actions';
        const toggle = document.createElement('button'); toggle.type = 'button';
        toggle.className = 'rw-icon-button admin-actions-toggle'; toggle.textContent = '⋮';
        toggle.setAttribute('aria-label', `Actions for ${label}`); toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-haspopup', 'true');
        const menu = document.createElement('div'); menu.className = 'admin-actions-menu'; menu.hidden = true;
        actions.forEach(([text, action]) => {
            const item = button(text, action); item.className += ' admin-action-item'; menu.append(item);
        });
        wrapper.append(toggle, menu); cell.append(wrapper); jQuery(toggle).button();
    }
    function pageURL(target, extra = {}) {
        const paths = {overview: '/pacemaker', setup: '/install/pacemaker'};
        const url = new URL(paths[target] || `/pacemaker/${target}`, window.location.origin);
        if (selected) url.searchParams.set('cluster', selected.id);
        Object.entries(extra).forEach(([key, value]) => url.searchParams.set(key, value));
        return url.pathname + url.search;
    }
    function navigateSection() {
        const section = window.location.hash.slice(1);
        const targets = {overview: 'overview', resources: 'resources', configuration: 'configuration',
            quorum: 'quorum', logs: 'logs', monitoring: 'monitoring', history: 'history'};
        if (targets[section]) window.location.replace(pageURL(targets[section]));
    }
    function updateNavigation() {
        if (!selected) return;
        const current = new URL(window.location.href);
        current.searchParams.set('cluster', selected.id);
        window.history.replaceState(null, '', current.pathname + current.search + current.hash);
        document.querySelectorAll('#app-navigation a[href]').forEach(link => {
            const url = new URL(link.href, window.location.origin);
            if (url.pathname === '/pacemaker' || url.pathname.startsWith('/pacemaker/') || url.pathname === '/install/pacemaker') {
                url.searchParams.set('cluster', selected.id); link.href = url.pathname + url.search + url.hash;
            }
        });
    }
    function quorumNotice(data) {
        const note = byId('quorum-description'), witness = data.quorum_details || {};
        const twoNodes = selected.members.length === 2;
        byId('quorum-note').hidden = !twoNodes && !(witness.configured && witness.votes === 0);
        note.className = witness.configured && witness.votes > 0 ? 'alert alert-info' : 'alert alert-warning';
        note.textContent = witness.configured && witness.votes > 0
            ? 'Two-node cluster: an external quorum witness vote is available. Keep fencing enabled and the witness independent of both nodes.'
            : witness.configured ? 'The quorum witness is configured but its vote is unavailable. Check qnetd connectivity and TLS certificates. Keep fencing enabled.'
            : witness.configured === false ? 'Two-node cluster without an external quorum witness: configure an independent qnetd witness, optionally on the Roxy-WI host. Corosync two-node mode is not an independent arbitrator. Fencing remains necessary.'
            : 'Two-node cluster: the external quorum witness could not be verified. Check quorum diagnostics and configure an independent witness. Fencing remains necessary.';
    }
    function registrationWarning() {
        byId('registration-quorum').hidden = !!discovery || byId('members').rows.length !== 2;
    }
    function witnessServers() {
        const members = new Set(clusters.flatMap(cluster => cluster.members.map(member => member.server_id)));
        for(const select of [byId('witness-server'),byId('trust-target')]){
        const previous = select.value;
        select.replaceChildren(new Option('Select an independent Linux server', ''));
        servers.filter(server => !members.has(server.id)).forEach(server => option(select, server.id, `${server.name} (${server.ip})${server.ip === window.location.hostname || server.name === window.location.hostname ? ' — Roxy-WI host' : ''}`));
        if (Array.from(select.options).some(item => item.value === previous)) select.value = previous;
        refreshSelect(select);
        }
    }
    function path(suffix = '') {
        if (!selected) throw new Error('Select a cluster');
        return `/${selected.id}${suffix}`;
    }
    function resetDraft() {
        digest = null; changeId = null; changeKind = 'cib';
        if (!operator) return;
        byId('xml').value = ''; byId('xml').readOnly = false;
        byId('editor-label').textContent = 'Candidate CIB XML';
        byId('previous').textContent = ''; byId('proposed').textContent = '';
        byId('simulation').textContent = ''; byId('change-label').textContent = '';
        setDisabled('validate', true); setDisabled('apply', true); setDisabled('save-draft', false);
    }
    function editorChanged() {
        if (changeKind !== 'cib') return;
        changeId = null;
        setDisabled('validate', true); setDisabled('apply', true);
        byId('change-label').textContent = 'Editor changed. Save a new draft, then validate it before applying.';
        byId('simulation').textContent = '';
    }
    async function loadClusters(selectId) {
        clusters = (await api('')).data;
        byId('cluster').replaceChildren();
        clusters.forEach(cluster => option(byId('cluster'), cluster.id, cluster.name));
        if (selectId || requestedCluster) byId('cluster').value = selectId || requestedCluster;
        refreshSelect(byId('cluster'));
        selected = clusters.find(item => String(item.id) === byId('cluster').value) || null;
        resetDraft();
        byId('dashboard').hidden = !selected;
        if (operator) {
            witnessServers(); agentUI.reset();
            byId('membership-members').querySelectorAll('select').forEach(select => jQuery(select).selectmenu('destroy'));
            byId('membership-members').replaceChildren(); byId('membership-json').value='';
            byId('autostart-nodes').replaceChildren();byId('autostart-result').textContent='';
            byId('autostart-policy').value=selected?.corosync_settings.autostart_policy || 'default';refreshSelect(byId('autostart-policy'));
        }
        if (!selected) { message('Register an existing cluster or select empty supported Linux servers to create one.'); return; }
        if (operator) {
            byId('adopted-note').hidden = !selected.corosync_settings.adopted;
            setDisabled('bootstrap', !!selected.corosync_settings.adopted);
            const imported = selected.corosync_settings.membership_managed === false;
            setDisabled('membership-save', imported); setDisabled('membership-load', imported); setDisabled('membership-add', imported);
            byId('membership-json').disabled = imported; byId('token').disabled = imported;
            jQuery(byId('witness')).selectmenu('option', 'disabled', imported);
            if (imported) {
                byId('membership-json').value = JSON.stringify(selected.members, null, 2);
                byId('token').value = selected.corosync_settings.token || 1000;
                byId('witness').replaceChildren(new Option(selected.corosync_settings.qdevice_host ? `Preserved witness: ${selected.corosync_settings.qdevice_host}` : 'Preserved external configuration', ''));
                refreshSelect(byId('witness'));
            }
            byId('bootstrap-syn').checked = !!selected.corosync_settings.syn_flood; jQuery(byId('bootstrap-syn')).checkboxradio('refresh');
            byId('bootstrap-fence-pve').checked = !!selected.corosync_settings.fence_pve; jQuery(byId('bootstrap-fence-pve')).checkboxradio('refresh');
            byId('monitor').checked = selected.monitor_enabled; jQuery(byId('monitor')).checkboxradio('refresh');
            byId('log-node').replaceChildren();
            selected.members.forEach(member => option(byId('log-node'), member.server_id, member.name));
            refreshSelect(byId('log-node'));
        }
        updateNavigation();
        // An empty registration has no running daemons yet. Installation and
        // discovery must remain usable even when the selected cluster is down.
        try { await refresh(); } catch (error) { message(error.message, true); }
        navigateSection();
    }
    async function operate(action, target = '', node = '') {
        if (!await confirmAction(`${action}: ${target || selected.name}${node ? ` → ${node}` : ''}?`)) return;
        await waitTask(await api(path('/actions'), 'POST', {action, target, node})); await refresh();
    }
    async function refresh() {
        await history();
        const clusterId = selected.id;
        const data = (await api(path('/status'))).data;
        if (selected.id !== clusterId) return;
        quorumNotice(data);
        byId('quorum').textContent = data.quorate ? 'Quorum available' : 'NO QUORUM';
        byId('quorum').className = `rw-status-badge rw-status-${data.quorate ? 'running' : 'stopped'}`;
        byId('dc').textContent = `Coordinator: ${data.dc || 'unavailable'} · Failed actions: ${data.failures} · Read from: ${data.source}`;
        byId('nodes').replaceChildren();
        data.nodes.forEach(node => {
            const row = rowIn('nodes');
            cell(row, node.name);
            ['online', 'standby', 'maintenance', 'unclean'].forEach(key => {
                const active = isTrue(node[key]);
                const healthy = key === 'online' ? active : !active;
                badge(cell(row, ''), active ? 'Yes' : 'No', healthy ? 'running' : (key === 'unclean' || key === 'online' ? 'stopped' : 'unavailable'));
            });
            const actions = cell(row, '');
            if (operator) {
                actionMenu(actions, node.name, [['Standby', () => operate('standby', node.name)], ['Online', () => operate('online', node.name)]]);
            }
        });
        byId('resources').replaceChildren();
        data.resources.forEach(resource => {
            const row = rowIn('resources');
            [resource.id, resource.resource_agent, resource.role, resource.nodes.join(', ')].forEach(value => cell(row, value));
            const failed = isTrue(resource.failed), blocked = isTrue(resource.blocked);
            badge(cell(row, ''), failed && blocked ? 'Failed / blocked' : failed ? 'Failed' : blocked ? 'Blocked' : 'Healthy', failed || blocked ? 'stopped' : 'running');
            const actions = cell(row, '');
            if (operator) {
                const items = ['enable', 'disable', 'restart', 'cleanup', 'clear'].map(action => [action.charAt(0).toUpperCase() + action.slice(1), () => operate(action, resource.target_id || resource.id)]);
                selected.members.filter(member => !resource.nodes.includes(member.name)).forEach(member => items.push([`Move to ${member.name}`, () => operate('move', resource.target_id || resource.id, member.name)]));
                actionMenu(actions, resource.id, items);
            }
        });
    }
    async function history() {
        const data = await api(path('/history'));
        byId('history').replaceChildren();
        byId('task-status').textContent = data.task ? `Operation #${data.task.id}: ${data.task.status}` : '';
        if (data.task && !polling) waitTask({task_id: data.task.id}).catch(error => message(error.message, true));
        data.changes.forEach(change => {
            const row = rowIn('history');
            cell(row, change.id); cell(row, change.date);
            badge(cell(row, ''), change.status, change.status === 'applied' ? 'running' : change.status === 'failed' ? 'stopped' : 'stale');
            const actions = cell(row, '');
            if (operator) {
                const items = [['Review', () => showChange(change.id)]];
                if (change.kind === 'cib') items.push(['Restore as draft', async () => {
                    const restored = await api(path(`/changes/${change.id}/restore`), 'POST', {}); await showChange(restored.id);
                }]);
                actionMenu(actions, `change #${change.id}`, items);
            }
        });
        byId('events').textContent = data.events.map(event => `${event.date} · ${event.user_id === 0 ? 'System' : `User ${event.user_id}`} · ${event.action} · ${event.status}`).join('\n');
    }

    async function waitTask(task) {
        if (polling) throw new Error('An operation is already being followed');
        polling = true;
        const id = selected.id;
        setDisabled('cluster', true);
        try {
            for (let attempt = 0; attempt < 1200; attempt++) {
                const data = (await api(`/${id}/tasks/${task.task_id}`)).data;
                message(`Operation #${data.id}: ${data.status}`);
                if (['completed', 'failed'].includes(data.status)) {
                    if (data.error) throw new Error(data.error);
                    if (changeId) await showChange(changeId);
                    return;
                }
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
            throw new Error('The operation is still pending. Check Operations worker health and refresh history.');
        } finally {
            polling = false; setDisabled('cluster', false);
        }
    }
    async function showChange(id) {
        if (view !== 'configuration') { window.location.assign(pageURL('configuration', {change: id})); return; }
        const change = (await api(path(`/changes/${id}`))).data;
        window.history.replaceState(null, '', pageURL('configuration', {change: id}));
        changeId = id;
        changeKind = change.kind;
        digest = change.base_digest;
        byId('editor-panel').open = true;
        byId('editor-panel').scrollIntoView({behavior: 'smooth', block: 'start'});
        byId('previous').textContent = change.previous;
        byId('proposed').textContent = change.xml;
        byId('xml').value = change.xml;
        byId('xml').readOnly = change.kind !== 'cib';
        byId('editor-label').textContent = change.kind === 'cib' ? 'Candidate CIB XML' : 'Candidate Corosync configuration';
        byId('change-label').textContent = `${change.kind} change #${id}: ${change.status}`;
        setDisabled('save-draft', change.kind !== 'cib');
        setDisabled('validate', ['applied', 'applying', 'unknown'].includes(change.status));
        setDisabled('apply', change.status !== 'validated');
        byId('simulation').textContent = change.result ? JSON.parse(change.result).simulation : '';
    }
    let memberSequence = 0;
    function addMember(member = null, target = 'members', fixed = false) {
        memberSequence++;
        const row = rowIn(target);
        const server = document.createElement('select'); server.required = true; server.setAttribute('aria-label', `Server for member ${memberSequence}`);
        option(server, '', member ? 'Select the matching Roxy-WI server' : 'Select a server');
        servers.forEach(item => option(server, item.id, `${item.name} (${item.ip})`));
        server.value = member?.server_id || '';
        row.insertCell().append(server);
        ['name', 'address', 'nodeid'].forEach((name, index) => {
            const input = document.createElement('input'); input.dataset.field = name; input.required = true; input.className = 'form-control'; input.setAttribute('aria-label', `${name} for member ${memberSequence}`);
            if (name === 'nodeid') { input.type = 'number'; input.min = '1'; }
            const nodeIds = Array.from(byId(target).querySelectorAll('[data-field=nodeid]')).map(item => Number(item.value));
            input.value = member ? member[name] : index < 2 ? '' : String(Math.max(0, ...nodeIds) + 1);
            input.readOnly = !!member;
            row.insertCell().append(input);
        });
        if (!member) {
            const address = row.querySelector('[data-field=address]'), choice = document.createElement('select');
            choice.required = true; choice.setAttribute('aria-label', `Network address for member ${memberSequence}`);
            address.hidden = true; address.required = false;
            address.parentElement.insertBefore(choice, address);
            const note = document.createElement('p'); note.className = 'rw-form-help'; row.cells[0].append(note);
            function addressChoices(values = []) {
                choice.replaceChildren(new Option('Select a host address', ''));
                values.forEach(item => option(choice, item.address, `${item.interface}: ${item.address}/${item.prefix}`));
                option(choice, '__custom__', 'Custom IP address or DNS name');
                address.value = ''; address.hidden = true; address.required = false; refreshSelect(choice);
            }
            jQuery(choice).selectmenu(); addressChoices(); row.dataset.factsReady = 'false';
            jQuery(choice).on('selectmenuchange change', () => {
                const custom = choice.value === '__custom__';
                address.hidden = !custom; address.required = custom;
                address.value = custom ? '' : choice.value;
            });
            jQuery(server).on('selectmenuchange change', guard(async () => {
                const serverId = server.value;
                row.dataset.factsReady = 'false'; row.querySelector('[data-field=name]').value = ''; addressChoices();
                if (!serverId) { note.textContent = ''; return; }
                note.textContent = 'Reading hostname and network addresses…';
                try {
                    const facts = (await api(`/servers/${serverId}/facts`)).data;
                    if (!row.isConnected || server.value !== serverId) return;
                    row.querySelector('[data-field=name]').value = facts.hostname;
                    addressChoices(facts.addresses);
                    if (facts.active_cluster_services.length || facts.existing_witness_data) {
                        note.textContent = `Existing services: ${facts.active_cluster_services.join(', ') || 'Docker witness data'}. Choose an empty host or use adoption.`;
                        return;
                    }
                    row.dataset.factsReady = 'true'; note.textContent = `Hostname read from host. Select the intended cluster network${facts.fqdn !== facts.hostname ? `; FQDN: ${facts.fqdn}` : ''}.`;
                } catch (error) { note.textContent = 'Cannot read this host. Check SSH access, then select it again.'; throw error; }
            }));
        }
        const actions = row.insertCell();
        if (!member || fixed) actions.append(button('Remove', () => { row.querySelectorAll('select').forEach(select => jQuery(select).selectmenu('destroy')); row.remove(); registrationWarning(); }));
        jQuery(server).selectmenu();
        if (fixed) { jQuery(server).selectmenu('option','disabled',true); row.dataset.factsReady='true'; }
        registrationWarning();
    }
    const agentUI = operator ? RoxywiPacemakerDiscovery({byId, api, guard, selected: () => selected, waitTask, refreshSelect, setDisabled, message}) : null;
    jQuery(byId('cluster')).on('selectmenuchange change', guard(() => loadClusters(byId('cluster').value)));
    byId('refresh').addEventListener('click', guard(refresh));
    window.addEventListener('hashchange', navigateSection);
    if (operator) {
        function setupMode(mode) {
            byId('bootstrap-panel').hidden = mode !== 'new';
            byId('witness-panel').hidden = mode !== 'witness';
            byId('discovery').hidden = mode !== 'adopt';
            byId('registration').hidden = true;
            if (view === 'setup') {
                const url = new URL(window.location.href); url.searchParams.set('setup', mode);
                window.history.replaceState(null, '', url.pathname + url.search);
            }
        }
        byId('witness-open').addEventListener('click', () => setupMode('witness'));
        byId('witness-self').addEventListener('click', guard(() => {
            const host = servers.find(server => server.ip === window.location.hostname || server.name === window.location.hostname);
            if (!host || !Array.from(byId('witness-server').options).some(option => option.value === String(host.id))) throw new Error('Register the independent Roxy-WI host as a server in this group with SSH credentials first');
            byId('witness-server').value = host.id; refreshSelect(byId('witness-server')); jQuery(byId('witness-server')).trigger('change');
        }));
        function witnessId() {
            const id = Number(byId('witness-server').value);
            if (!id) throw new Error('Select an independent witness server'); return id;
        }
        async function readWitness(id) {
            const data = (await api(`/witness/${id}`)).data;
            if (data.mode === 'docker' || data.ca_fingerprint) { byId('witness-docker').checked = data.mode === 'docker'; jQuery(byId('witness-docker')).checkboxradio('refresh'); }
            byId('witness-result').textContent = `${data.mode === 'docker' ? 'Docker' : 'Native'} · ${data.active ? 'qnetd running' : 'qnetd not running'} · Version: ${data.version || 'not installed'} · CA fingerprint: ${data.ca_fingerprint || 'not initialized'}`;
        }
        let migrationPlan = null;
        function resetMigration() {
            migrationPlan = null;
            byId('migration-review').replaceChildren(); byId('migration-status').textContent = '';
            byId('witness-log-output').hidden = true;
            setDisabled('migration-start', true); setDisabled('migration-recover', true);
        }
        jQuery(byId('witness-server')).on('selectmenuchange change', resetMigration);
        async function reviewMigration() {
            const id = witnessId(); resetMigration();
            byId('migration-status').textContent = 'Reading native witness and checking all attached nodes…';
            const data = (await api(`/witness/${id}/migration`)).data;
            if (id !== witnessId()) return;
            migrationPlan = data;
            const row = (name, value) => {
                const item = byId('migration-review').insertRow();
                [name, value].forEach(text => { const cell = item.insertCell(); cell.className = 'padding10'; cell.textContent = text; });
            };
            if (data.pending.length) {
                data.pending.forEach(item => row('Unfinished migration', `${item.token}: ${item.phase}`));
                byId('migration-status').textContent = 'Recover the native witness before starting another conversion.';
                setDisabled('migration-recover', false); return;
            }
            row('Conversion', 'Native qnetd → Docker on the same host and TCP 5403');
            row('CA fingerprint to preserve', data.source.ca_fingerprint);
            row('Attached clusters', data.clusters.map(cluster => cluster.name).join(', ') || 'No attached registered clusters');
            row('Node checks', 'All attached members online, quorate, connected with TLS and a witness vote');
            row('Recovery', 'Private host backup and independent 180-second rollback timer');
            byId('migration-status').textContent = 'Review these checks. Preparation may install Docker Engine from enabled host repositories and build the fixed image. No cluster configuration or client certificates will be replaced.';
            setDisabled('migration-start', !data.eligible);
        }
        byId('migration-plan').addEventListener('click', guard(reviewMigration));
        async function migrationTask(action) {
            const id = witnessId(), plan = migrationPlan;
            if (!plan || plan.server_id && plan.server_id !== id) throw new Error('Review the selected witness first');
            const recover = action === 'recover', token = plan.pending[0]?.token;
            if (!await confirmAction(recover ? `Restore the native witness on ${plan.server}?` : `Convert ${plan.server} to Docker while preserving its current CA? The witness connection briefly restarts.`, plan.server)) return;
            ['migration-plan', 'migration-start', 'migration-recover', 'witness-install', 'witness-server'].forEach(item => setDisabled(item, true));
            try {
                const result = await api(`/witness/${id}/migration${recover ? '/recover' : ''}`, 'POST', recover
                    ? {token, confirm: plan.server} : {plan_digest: plan.plan_digest, confirm: plan.server});
                for (let attempt = 0; attempt < 650; attempt++) {
                    const state = (await api(`/witness/tasks/${result.task_id}`)).data;
                    byId('migration-status').textContent = `Witness ${recover ? 'recovery' : 'conversion'} #${state.id}: ${state.status}`;
                    if (state.status === 'failed') throw new Error(state.error);
                    if (state.status === 'completed') {
                        await readWitness(id);
                        byId('migration-status').textContent = recover ? 'Native witness restored; attached node votes verified.' : 'Conversion completed. CA preserved and attached node votes verified. The native service is disabled; its backup stays on the host.';
                        migrationPlan = null; return;
                    }
                    await new Promise(resolve => setTimeout(resolve, 2000));
                }
                throw new Error('The operation is still pending. Read migration status before retrying.');
            } finally {
                ['migration-plan', 'witness-install', 'witness-server'].forEach(item => setDisabled(item, false));
            }
        }
        byId('migration-start').addEventListener('click', guard(() => migrationTask('convert')));
        byId('migration-recover').addEventListener('click', guard(() => migrationTask('recover')));
        let lifecyclePlan=null;
        function resetLifecycle(){lifecyclePlan=null;byId('lifecycle-review').replaceChildren();byId('lifecycle-status').textContent='';setDisabled('lifecycle-start',true);setDisabled('lifecycle-recover',true);}
        jQuery(byId('witness-server')).on('selectmenuchange change',resetLifecycle);
        jQuery(byId('lifecycle-operation')).on('selectmenuchange change',resetLifecycle);
        byId('lifecycle-plan').addEventListener('click',guard(async()=>{
            const id=witnessId(),operation=byId('lifecycle-operation').value;resetLifecycle();
            byId('lifecycle-status').textContent='Checking witness, certificate storage and attached nodes…';
            const data=(await api(`/witness/${id}/lifecycle/${operation}`)).data;
            if(id!==witnessId()||operation!==byId('lifecycle-operation').value)return;
            lifecyclePlan={...data,operation};
            const row=(name,value)=>{const item=byId('lifecycle-review').insertRow();[name,value].forEach(text=>{const cell=item.insertCell();cell.className='padding10';cell.textContent=text;});};
            if(data.pending.length){data.pending.forEach(item=>row('Unfinished operation',`${item.operation}: ${item.token} (${item.phase})`));setDisabled('lifecycle-recover',false);return;}
            row('Operation',operation==='native'?'Docker → native qnetd':'Refresh the fixed Roxy-WI image recipe with current distribution packages');
            row('Current version / image',`${data.source.version} / ${data.source.image_id}`);
            row('CA to preserve',data.source.ca_fingerprint);
            row('Attached clusters',data.clusters.map(item=>item.name).join(', ')||'No attached registered clusters');
            row('Node checks','Every member online, quorate, using TLS with a witness vote');
            row('Recovery','Original container, private certificate backup and independent host timer');
            byId('lifecycle-status').textContent='Review the operation. Native conversion may install qnetd from enabled host repositories. Image update downloads the fixed Debian recipe; the resulting version and image are recorded in the operation.';
            setDisabled('lifecycle-start',!data.eligible);
        }));
        async function lifecycleTask(recover=false){
            const plan=lifecyclePlan,id=witnessId();if(!plan||plan.server_id&&plan.server_id!==id)throw new Error('Review this witness first');
            if(!await confirmAction(`${recover?'Recover the original witness':'Apply the reviewed witness operation'} on ${plan.server}? Witness clients briefly reconnect.`,plan.server))return;
            ['lifecycle-start','lifecycle-plan','lifecycle-recover','lifecycle-operation','witness-server','witness-install'].forEach(item=>setDisabled(item,true));
            try{
                const result=await api(`/witness/${id}/lifecycle/${recover?'recover':plan.operation}`,'POST',recover?{token:plan.pending[0].token,confirm:plan.server}:{plan_digest:plan.plan_digest,confirm:plan.server});
                for(let attempt=0;attempt<700;attempt++){
                    const state=(await api(`/witness/tasks/${result.task_id}`)).data;byId('lifecycle-status').textContent=`Witness operation #${state.id}: ${state.status}`;
                    if(state.status==='failed')throw new Error(state.error);
                    if(state.status==='completed'){await readWitness(id);byId('lifecycle-status').textContent=`${recover?'Original witness recovered':'Operation completed'}. CA preserved and attached node votes verified. Version: ${state.result?.version||'see witness status'}`;lifecyclePlan=null;return;}
                    await new Promise(resolve=>setTimeout(resolve,2000));
                }
                throw new Error('Operation is still pending. Read its status before retrying.');
            }finally{['lifecycle-plan','lifecycle-operation','witness-server','witness-install'].forEach(item=>setDisabled(item,false));}
        }
        byId('lifecycle-start').addEventListener('click',guard(()=>lifecycleTask()));
        byId('lifecycle-recover').addEventListener('click',guard(()=>lifecycleTask(true)));
        let trustPlan=null;
        function resetTrust(){trustPlan=null;byId('trust-review').replaceChildren();byId('trust-status').textContent='';setDisabled('trust-start',true);setDisabled('trust-recover',true);}
        jQuery(byId('witness-server')).on('selectmenuchange change',resetTrust);
        jQuery(byId('trust-target')).on('selectmenuchange change',resetTrust);
        byId('trust-rotate').addEventListener('change',()=>{resetTrust();setDisabled('trust-target',byId('trust-rotate').checked);});
        byId('trust-plan').addEventListener('click',guard(async()=>{
            const id=witnessId(),rotate=byId('trust-rotate').checked,target=rotate?id:Number(byId('trust-target').value);resetTrust();
            if(!target)throw new Error('Select an installed independent target witness, or CA rotation on the current host');
            byId('trust-status').textContent='Checking both witnesses and every attached node…';
            const data=(await api(`/witness/${id}/trust/${target}?rotate=${rotate?1:0}`)).data;
            if(id!==witnessId())return;trustPlan=data;
            const row=(name,value)=>{const item=byId('trust-review').insertRow();[name,value].forEach(text=>{const cell=item.insertCell();cell.className='padding10';cell.textContent=text;});};
            if(data.pending.length){data.pending.forEach(item=>row('Unfinished trust change',`${item.token}: ${item.phase}`));setDisabled('trust-recover',false);return;}
            row('Change',rotate?'Generate a new CA on the current witness':`${data.server} → ${data.target_server}`);
            row('Current CA',data.source.ca_fingerprint);row('Target CA',rotate?'New CA generated locally during preparation':data.target.ca_fingerprint);
            row('Clusters / clients',`${data.clusters.map(item=>item.name).join(', ')} / ${data.nodes.length} nodes`);
            row('Private keys','Stay on their hosts; only public CSRs, CA and certificates are exchanged');
            row('Configuration','Preserve custom Corosync transport; change only the witness address when moving hosts');
            row('Interrupted operation','Target stops after 180 seconds; clients restore backups after 195 seconds. A remote source stays stopped until reviewed recovery proves the target stopped.');
            byId('trust-status').textContent='All attached members must stay online and quorate. The workflow stops all qdevice clients before retiring the old witness and starting the new trust. Cluster services and workloads remain running.';
            setDisabled('trust-start',!data.eligible);
        }));
        async function trustTask(recover=false){
            const plan=trustPlan,id=witnessId();if(!plan||plan.source_id&&plan.source_id!==id)throw new Error('Review this source witness first');
            if(!await confirmAction(`${recover?'Recover the original witness trust':'Apply the reviewed witness and CA change'} for ${plan.server}? All attached qdevice clients briefly reconnect.`,plan.server))return;
            ['trust-plan','trust-start','trust-recover','trust-target','witness-server','witness-install'].forEach(item=>setDisabled(item,true));
            try{
                const queued=await api(`/witness/${id}/trust${recover?'/recover':''}`,'POST',recover?{token:plan.pending[0].token,confirm:plan.server}:{target_id:plan.target_id,rotate_ca:plan.rotate,plan_digest:plan.plan_digest,confirm:plan.server});
                for(let attempt=0;attempt<700;attempt++){
                    const state=(await api(`/witness/tasks/${queued.task_id}`)).data;byId('trust-status').textContent=`Trust operation #${state.id}: ${state.status}`;
                    if(state.status==='failed')throw new Error(state.error);
                    if(state.status==='completed'){byId('trust-status').textContent=recover?'Original witness trust restored and every TLS vote verified.':'Witness trust changed; every attached TLS vote verified. Old remote witness remains stopped. CA: '+state.result.ca_fingerprint;trustPlan=null;await loadClusters(selected?.id);return;}
                    await new Promise(resolve=>setTimeout(resolve,2000));
                }
                throw new Error('Operation is still pending. Review its journal before retrying.');
            }finally{['trust-plan','trust-target','witness-server','witness-install'].forEach(item=>setDisabled(item,false));}
        }
        byId('trust-start').addEventListener('click',guard(()=>trustTask()));
        byId('trust-recover').addEventListener('click',guard(()=>trustTask(true)));
        byId('witness-logs').addEventListener('click', guard(async () => {
            const output = byId('witness-log-output');
            output.textContent = (await api(`/witness/${witnessId()}/logs`)).data.trim() || 'No witness log entries'; output.hidden = false;
        }));
        function platformText(server, platform) {
            return platform.supported ? `${server.name}: ${platform.id} ${platform.version}, ${platform.manager}, ${platform.qualified ? 'live-qualified' : 'installation profile implemented; live qualification required'}` : `${server.name}: ${platform.reason}`;
        }
        byId('platform-check').addEventListener('click', guard(async () => {
            path(); setDisabled('platform-check', true);
            try {
                const result = await Promise.all(selected.members.map(async member => {
                    const server = servers.find(item => item.id === member.server_id);
                    return platformText(server, (await api(`/platform/${member.server_id}`)).data);
                }));
                byId('platform-result').textContent = result.join(' · ');
            } finally { setDisabled('platform-check', false); }
        }));
        byId('witness-platform').addEventListener('click', guard(async () => {
            const id = witnessId(), server = servers.find(item => item.id === id);
            const profile = (await api(`/platform/${id}`)).data;
            byId('witness-result').textContent = byId('witness-docker').checked && profile.supported
                ? `${server.name}: ${profile.id} ${profile.version} · Docker host profile; engine/packages and image build access are checked during installation.`
                : platformText(server, profile);
        }));
        byId('witness-status').addEventListener('click', guard(() => readWitness(witnessId())));
        byId('witness-install').addEventListener('click', guard(async () => {
            const id = witnessId(), server = servers.find(server => server.id === id), docker = byId('witness-docker').checked;
            if (!await confirmAction(`Install and enable corosync-qnetd ${docker ? 'in Docker' : 'using native packages'} on ${server.name}? Existing witness certificates will be preserved. This does not attach or change any cluster.`)) return;
            setDisabled('witness-install', true); setDisabled('witness-server', true); jQuery(byId('witness-docker')).checkboxradio('option', 'disabled', true);
            try {
                const task = await api('/witness/install', 'POST', {server_id: id, docker});
                for (let attempt = 0; attempt < 630; attempt++) {
                    const state = (await api(`/witness/tasks/${task.task_id}`)).data;
                    byId('witness-result').textContent = `Witness installation #${state.id}: ${state.status}`;
                    if (state.status === 'failed') throw new Error(state.error);
                    if (state.status === 'completed') { await readWitness(id); return; }
                    await new Promise(resolve => setTimeout(resolve, 2000));
                }
                throw new Error('Witness installation is still pending. Check Operations and read witness status before retrying.');
            } finally { setDisabled('witness-install', false); setDisabled('witness-server', false); jQuery(byId('witness-docker')).checkboxradio('option', 'disabled', false); }
        }));
        async function readAutostart() {
            const id=selected?.id;const result=(await api(path('/autostart'))).data;
            if (selected?.id!==id)return;
            byId('autostart-nodes').replaceChildren();
            result.nodes.forEach(node=>node.units.forEach(unit=>{
                const row=byId('autostart-nodes').insertRow();
                [node.name,unit.unit,unit.active,unit.restart,unit.delay,unit.managed?'Roxy-WI':'Package/default'].forEach(value=>{const cell=row.insertCell();cell.className='padding10';cell.textContent=value;});
            }));
            byId('autostart-result').textContent=result.proxy_conflicts.length ? 'Conflicting proxy Auto Start settings: '+result.proxy_conflicts.map(item=>item.node+': '+item.service).join(', ') : 'No conflicting proxy Auto Start settings for cluster-owned applications.';
        }
        let transportPlan=null;
        function resetTransport(){transportPlan=null;byId('transport-configs').hidden=true;byId('transport-before').value='';byId('transport-after').value='';byId('transport-status').textContent='';setDisabled('transport-start',true);}
        byId('transport-token').addEventListener('input',resetTransport);
        jQuery(byId('cluster')).on('selectmenuchange change',resetTransport);
        byId('transport-plan').addEventListener('click',guard(async()=>{
            const id=selected?.id;path();resetTransport();byId('transport-status').textContent='Checking every configuration, authentication key digest, quorum and candidate syntax…';
            const data=(await api(path('/transport?token='+byId('transport-token').value))).data;
            if(id!==selected?.id)return;transportPlan=data;
            if(data.pending){byId('transport-status').textContent=`Unfinished migration ${data.pending.id}. Recover the original transport before continuing.`;return;}
            byId('transport-configs').hidden=false;
            byId('transport-before').value=data.previous;byId('transport-after').value=data.candidate;
            byId('transport-status').textContent='Syntax checked on every node; existing authentication key digests match. Compare the complete configurations. Quiesce applications before applying. The current TLS witness and CIB are retained.';
            setDisabled('transport-start',!data.eligible);
        }));
        async function transportControl(operation){
            path();const data=transportPlan;
            if(operation==='migrate'&&(!data?.eligible||data.cluster_id!==selected.id))throw new Error('Review this cluster transport first');
            const explanation={quiesce:'Put every node in standby and wait for applications to stop?',migrate:'Stop cluster communication and apply the reviewed transport? Applications must already be stopped.',recover:'Restore the original transport on all members? Applications will stay in standby.',resume:'Restore the nodes that were online before transport maintenance? Applications can start.'}[operation];
            if(!await confirmAction(explanation,selected.name))return;
            ['transport-plan','transport-start','transport-quiesce','transport-recover','transport-resume'].forEach(item=>setDisabled(item,true));
            try{
                await waitTask(await api(path('/transport'+(operation==='migrate'?'':'/'+operation)),'POST',operation==='migrate'?{token:data.token,plan_digest:data.plan_digest,confirm:selected.name}:{confirm:selected.name}));
                byId('transport-status').textContent=operation==='quiesce'?'All applications stopped; nodes remain in standby. Review and apply transport.':operation==='resume'?'Previous node availability restored. Check application status.':'Transport operation completed. Review cluster health before resuming applications.';
                transportPlan=null;await loadClusters(selected.id);
            }finally{['transport-plan','transport-quiesce','transport-recover','transport-resume'].forEach(item=>setDisabled(item,false));}
        }
        ['quiesce','recover','resume'].forEach(operation=>byId('transport-'+operation).addEventListener('click',guard(()=>transportControl(operation))));
        byId('transport-start').addEventListener('click',guard(()=>transportControl('migrate')));
        byId('autostart-read').addEventListener('click',guard(readAutostart));
        byId('autostart-save').addEventListener('click',guard(async()=>{
            path();const policy=byId('autostart-policy').value;
            if(!await confirmAction(`Apply ${policy} daemon restart policy to ${selected.name}? Cluster-owned applications remain under Pacemaker control; conflicting proxy Auto Start flags are disabled.`,selected.name))return;
            await waitTask(await api(path('/autostart'),'POST',{policy,coordinate_proxy_autostart:true,confirm:selected.name}));
            await readAutostart();
        }));
        byId('monitor').addEventListener('change', guard(async () => {
            await api(path('/monitor'), 'PUT', {enabled: byId('monitor').checked});
            message('Monitoring settings saved. Notifications follow the existing HA cluster alert routing.');
        }));
        function clearMembers() {
            byId('members').querySelectorAll('select').forEach(select => jQuery(select).selectmenu('destroy'));
            byId('members').replaceChildren();
        }
        function registrationMode(adopting) {
            byId('name').readOnly = adopting;
            setDisabled('add-member', adopting);
            setDisabled('registration-save', false);
            byId('registration-title').textContent = adopting ? 'Review discovered cluster and map its nodes' : 'Register a new cluster';
            jQuery(byId('registration-save')).button('option', 'label', adopting ? 'Adopt verified cluster' : 'Save registration');
            byId('registration').hidden = false;
            setDisabled('bootstrap', true);
        }
        function newRegistration() {
            setupMode('new');
            byId('bootstrap-panel').hidden = true;
            discovery = null; byId('discovery').hidden = true;
            byId('name').value = ''; byId('description').value = '';
            clearMembers(); addMember(); addMember(); registrationMode(false);
            byId('registration').scrollIntoView({behavior: 'smooth', block: 'start'});
        }
        function openDiscovery() {
            setupMode('adopt');
            discovery = null; byId('discovery').hidden = false; byId('registration').hidden = true;
            byId('discovery').scrollIntoView({behavior: 'smooth', block: 'start'});
            setDisabled('bootstrap', true);
        }
        byId('register').addEventListener('click', newRegistration);
        byId('registration-cancel').addEventListener('click', () => {
            discovery = null; byId('registration').hidden = true; byId('discovery').hidden = true;
            byId('bootstrap-panel').hidden = new URLSearchParams(window.location.search).get('setup') !== 'new';
            setDisabled('bootstrap', !selected || !!selected.corosync_settings.adopted);
        });
        byId('adopt-open').addEventListener('click', openDiscovery);
        byId('add-member').addEventListener('click', () => addMember());
        jQuery(byId('discovery-server')).on('selectmenuchange change', () => {
            discovery = null; byId('registration').hidden = true; byId('discovery-result').textContent = '';
        });
        byId('discover').addEventListener('click', guard(async () => {
            discovery = null; byId('registration').hidden = true;
            const serverId = Number(byId('discovery-server').value);
            if (!serverId) throw new Error('Select an existing cluster node');
            setDisabled('discover', true);
            try {
                const found = (await api('/discover', 'POST', {server_id: serverId})).data;
                discovery = {...found, seed_server_id: serverId};
                byId('name').value = found.name; byId('description').value = '';
                clearMembers(); found.members.forEach(member => addMember(member)); registrationMode(true);
                byId('discovery-result').textContent = `${found.name}: ${found.members.length} nodes, ${found.state.resources.length} resources, ${found.state.quorate ? 'quorum available' : 'NO QUORUM'}. Review every server mapping. Existing transport and witness settings will be preserved.`;
                setDisabled('registration-save', !!found.existing_cluster_id);
                if (found.existing_cluster_id) byId('discovery-result').textContent += ' This cluster is already registered in Roxy-WI.';
            } finally { setDisabled('discover', false); }
        }));
        byId('register-form').addEventListener('submit', guard(async () => {
            if (!discovery && Array.from(byId('members').rows).some(row => row.dataset.factsReady !== 'true')) throw new Error('Read host facts for every selected empty node before saving registration');
            const members = Array.from(byId('members').rows).map(row => ({
                server_id: Number(row.querySelector('select').value),
                name: row.querySelector('[data-field=name]').value, address: row.querySelector('[data-field=address]').value,
                nodeid: Number(row.querySelector('[data-field=nodeid]').value),
            }));
            if (members.some(member => !member.server_id)) throw new Error('Map every discovered node to a Roxy-WI server');
            const body = {name: byId('name').value, description: byId('description').value, members};
            if (discovery) {
                if (discovery.existing_cluster_id) throw new Error('This cluster is already registered in Roxy-WI');
                if (!await confirmAction(`Adopt ${discovery.name} into Roxy-WI? The running cluster will only be read and verified.`)) return;
                Object.assign(body, {seed_server_id: discovery.seed_server_id, base_digest: discovery.base_digest, topology_digest: discovery.topology_digest});
            }
            setDisabled('registration-save', true);
            try {
                const result = await api(discovery ? '/adopt' : '', 'POST', body);
                byId('registration').hidden = true; byId('discovery').hidden = true;
                const adopted = !!discovery; discovery = null; await loadClusters(result.data.id);
                byId('bootstrap-panel').hidden = adopted;
                message(adopted ? 'Existing cluster adopted without changing its configuration or services.' : 'Registration saved. Review installation options below and install the registered cluster.');
                if (adopted) window.location.assign(pageURL('overview'));
            } finally { setDisabled('registration-save', false); }
        }));
        byId('bootstrap').addEventListener('click', guard(async () => {
            path();
            if (!await confirmAction('Install Corosync and Pacemaker on all registered empty supported Linux nodes. Existing clusters are refused.', selected.name)) return;
            await waitTask(await api(path('/bootstrap'), 'POST', {confirm: selected.name, syn_flood: byId('bootstrap-syn').checked,
                fence_pve: byId('bootstrap-fence-pve').checked}));
            window.location.assign(pageURL('overview'));
        }));
        byId('maintenance-on').addEventListener('click', guard(() => operate('maintenance-on')));
        byId('maintenance-off').addEventListener('click', guard(() => operate('maintenance-off')));
        ['resource', 'constraint', 'property', 'delete'].forEach(kind => {
            byId(`${kind}-form`).addEventListener('submit', guard(async event => {
                const data = Object.fromEntries(new FormData(event.target));
                if (kind === 'resource') {
                    data.parameters = agentUI.resourceParameters();
                    ['wrapper_id', 'start_timeout', 'stop_timeout', 'monitor_timeout'].forEach(key => { if (!data[key]) delete data[key]; });
                }
                const current = (await api(path('/config'))).data;
                digest = current.digest;
                const result = await api(path('/build'), 'POST', {base_digest: digest, kind, data});
                await showChange(result.id); message(`Draft #${result.id} saved. Validate and review the simulation before applying.`);
            }));
        });
        byId('load-config').addEventListener('click', guard(async () => {
            const current = (await api(path('/config'))).data;
            resetDraft(); digest = current.digest; changeKind = 'cib'; setDisabled('save-draft', false); byId('xml').value = current.xml;
        }));
        byId('xml').addEventListener('input', editorChanged);
        byId('save-draft').addEventListener('click', guard(async () => {
            if (!digest) throw new Error('Load the current CIB before saving a draft');
            const result = await api(path('/changes'), 'POST', {xml: byId('xml').value, base_digest: digest}); await showChange(result.id);
        }));
        byId('validate').addEventListener('click', guard(async () => {
            await waitTask(await api(path(`/changes/${changeId}/validate`), 'POST', {}));
        }));
        byId('apply').addEventListener('click', guard(async () => {
            if (!await confirmAction(`Apply reviewed change #${changeId} to ${selected.name}? Resources may stop, move or restart.`)) return;
            await waitTask(await api(path(`/changes/${changeId}/apply`), 'POST', {})); await refresh();
        }));
        byId('corosync').addEventListener('click', guard(async () => {
            const data = (await api(path('/corosync'))).data;
            byId('corosync-output').textContent = data.map(item => `${item.node}\n${item.quorum}\n${item.config}`).join('\n\n');
        }));
        byId('membership-load').addEventListener('click', guard(async () => {
            path();
            selected = (await api('')).data.find(cluster => cluster.id === selected.id);
            byId('membership-json').value = JSON.stringify(selected.members, null, 2);
            byId('membership-members').querySelectorAll('select').forEach(select => jQuery(select).selectmenu('destroy'));
            byId('membership-members').replaceChildren();
            selected.members.forEach(member => addMember(member,'membership-members',true));
            byId('token').value = selected.corosync_settings.token || 1000;
            byId('witness').replaceChildren(new Option('No net qdevice', ''));
            servers.filter(server => !selected.members.some(member => member.server_id === server.id)).forEach(server => option(byId('witness'), server.id, `${server.name} (${server.ip})`));
            byId('witness').value = selected.corosync_settings.qdevice_server_id || '';
            refreshSelect(byId('witness'));
        }));
        byId('membership-add').addEventListener('click',guard(() => {
            path(); if (selected.corosync_settings.membership_managed===false) throw new Error('Adopted transport is preserved');
            addMember(null,'membership-members');
        }));
        byId('membership-form').addEventListener('submit', guard(async () => {
            const rows=Array.from(byId('membership-members').rows);
            if (rows.length<2) throw new Error('Load current membership and retain at least two members');
            if (rows.some(row => row.dataset.factsReady!=='true')) throw new Error('Read and select an empty host for each new node');
            const members=rows.map(row => ({server_id:Number(row.querySelector('select').value),
                name:row.querySelector('[data-field=name]').value,address:row.querySelector('[data-field=address]').value,
                nodeid:Number(row.querySelector('[data-field=nodeid]').value)}));
            const body = {name: selected.name, description: selected.description,
                members, token: Number(byId('token').value),
                qdevice_server_id: byId('witness').value ? Number(byId('witness').value) : null};
            const result = await api(path('/corosync'), 'POST', body); await showChange(result.id);
        }));
        byId('logs').addEventListener('click', guard(async () => {
            byId('log-output').textContent = (await api(path(`/logs/${byId('log-node').value}`))).data;
        }));
    }
    guard(async () => {
        if (operator) { byId('name').pattern = '[A-Za-z][A-Za-z0-9_-]{0,62}'; byId('name').maxLength = 63; byId('description').maxLength = 2000; servers = (await api('/servers')).data;
            byId('discovery-server').replaceChildren(new Option('Select an existing cluster node', ''));
            servers.forEach(server => option(byId('discovery-server'), server.id, `${server.name} (${server.ip})`));
            refreshSelect(byId('discovery-server')); addMember(); addMember(); }
        await loadClusters();
        if (operator && view === 'setup') {
            const mode = root.dataset.setupMode || 'new';
            if (mode === 'new' && !requestedCluster) byId('register').click();
            if (mode === 'adopt') byId('adopt-open').click();
            if (mode === 'witness') byId('witness-open').click();
        }
        const change = new URLSearchParams(window.location.search).get('change');
        if (operator && view === 'configuration' && /^\d+$/.test(change || '')) await showChange(Number(change));
        navigateSection();
    })();
});
