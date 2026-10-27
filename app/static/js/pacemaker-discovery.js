/* Native host discovery drives the forms; metadata is rendered only as text. */
'use strict';
window.RoxywiPacemakerDiscovery = function ({byId, api, guard, selected, waitTask, refreshSelect, setDisabled, message}) {
    let inventory = null, agentMetadata = null, packageData = [], choices = null, generation = 0;
    const path = suffix => {
        const cluster = selected();
        if (!cluster) throw new Error('Select a cluster');
        return `/${cluster.id}${suffix}`;
    };
    const option = (select, value, label) => select.add(new Option(label, value));
    const duration = value => /^\d+(ms|s|min|h)$/.test(value || '') ? value : /^\d+$/.test(value || '') ? `${value}s` : '';
    function resetMetadata() {
        generation++; agentMetadata = null;
        ['agent-parameters', 'agent-optional-fields'].forEach(id => {
            byId(id).querySelectorAll('select').forEach(select => jQuery(select).selectmenu('destroy')); byId(id).replaceChildren();
        });
        byId('agent-optional').hidden = true; byId('agent-optional').open = false;
        setDisabled('resource-create', true);
    }
    function reset() {
        inventory = null; packageData = []; choices = null; resetMetadata();
        byId('resource-agent').replaceChildren(new Option('Discover installed agents', '')); refreshSelect(byId('resource-agent'));
        byId('agent-package').replaceChildren(); refreshSelect(byId('agent-package')); setDisabled('package-install', true);
        byId('agent-nodes').replaceChildren(); byId('agent-inventory-status').textContent = '';
        byId('package-plan').textContent = '';
        ['constraint-resource', 'constraint-other', 'delete-id'].forEach(id => {
            byId(id).replaceChildren(new Option('Load current choices', '')); refreshSelect(byId(id));
        });
    }
    function renderAgents() {
        const select = byId('resource-agent'), previous = select.value;
        select.replaceChildren(new Option('Select an agent installed on every node', ''));
        const filter = byId('agent-filter').value.toLowerCase();
        (inventory?.agents || []).filter(agent => agent.ready && agent.id.toLowerCase().includes(filter)).forEach(agent => option(select, agent.id, agent.id));
        if (Array.from(select.options).some(item => item.value === previous)) select.value = previous;
        refreshSelect(select);
        if (select.value !== agentMetadata?.agent) resetMetadata();
    }
    async function scan() {
        const clusterId = selected()?.id; path(''); resetMetadata(); setDisabled('agents-scan', true); setDisabled('resource-agents-refresh', true);
        byId('agent-inventory-status').textContent = 'Reading installed agents from every node…';
        byId('agent-help').textContent = 'Reading installed agents from every node…';
        try {
            const data = (await api(path('/agents'))).data;
            if (selected()?.id !== clusterId) return;
            inventory = data;
            byId('agent-nodes').replaceChildren();
            data.nodes.forEach(node => {
                const row = byId('agent-nodes').insertRow();
                [node.name, node.agents.length, node.error || 'Read successfully'].forEach(value => { const cell = row.insertCell(); cell.className = 'padding10'; cell.textContent = value; });
            });
            const types = ['ocf', 'systemd', 'stonith'].map(type => `${type}: ${data.agents.filter(agent => agent.ready && agent.id.startsWith(type + ':')).length}`).join(' · ');
            byId('agent-inventory-status').textContent = `${data.agents.length} agents discovered; ${data.agents.filter(agent => agent.ready).length} available on every node (${types}). This is an inventory of available adapters, not running services. Unreachable nodes prevent verifying availability.`;
            renderAgents();
            byId('agent-help').textContent = `${data.agents.filter(agent => agent.ready).length} available adapters verified on every node. Selecting an agent creates no service; create and apply a resource to use it.`;
            if (byId('resource-agent').value) await loadMetadata();
        } finally { setDisabled('agents-scan', false); setDisabled('resource-agents-refresh', false); }
    }
    async function loadMetadata() {
        resetMetadata();
        const agent = byId('resource-agent').value, version = generation, clusterId = selected()?.id;
        if (!agent) return;
        byId('agent-help').textContent = 'Reading agent metadata from every node…';
        const data = (await api(path(`/agents/metadata?agent=${encodeURIComponent(agent)}`))).data;
        if (generation !== version || clusterId !== selected()?.id || byId('resource-agent').value !== agent) return;
        agentMetadata = data;
        byId('agent-help').textContent = `${data.description} · Verified on: ${data.nodes.join(', ')}`;
        const optionalFields = byId('agent-optional-fields');
        data.parameters.forEach(parameter => {
            const wrapper = document.createElement('div'); wrapper.className = 'rw-form-field';
            const label = document.createElement('label'), id = `pcmk-agent-param-${parameter.name}`;
            label.htmlFor = id; label.textContent = `${parameter.label} (${parameter.name})${parameter.required ? ' *' : ''}`;
            let input;
            if (parameter.options.length || parameter.type === 'boolean') {
                input = document.createElement('select'); option(input, '', `Agent default${parameter.default ? `: ${parameter.default}` : ''}`);
                (parameter.options.length ? parameter.options : ['true', 'false']).forEach(value => option(input, value, value));
            } else {
                input = document.createElement('input'); input.type = parameter.secret ? 'password' : 'text'; input.className = 'form-control';
                input.autocomplete = parameter.secret ? 'new-password' : 'off';
                input.placeholder = parameter.default || (parameter.required ? 'Required parameter' : 'Use agent default');
            }
            input.id = id; input.dataset.agentParameter = parameter.name;
            const help = document.createElement('p'); help.className = 'rw-form-help'; help.textContent = parameter.description;
            wrapper.append(label, input, help);
            (parameter.required || parameter.name.startsWith('pcmk_') ? byId('agent-parameters') : optionalFields).append(wrapper);
            if (parameter.name === 'pcmk_host_list') {
                const fill = document.createElement('button'); fill.type = 'button'; fill.className = 'rw-button rw-button-secondary'; fill.textContent = 'Use registered node names';
                fill.addEventListener('click', () => { input.value = selected().members.map(member => member.name).join(' '); }); wrapper.append(fill); jQuery(fill).button();
            }
            if (input.tagName === 'SELECT') jQuery(input).selectmenu();
        });
        byId('agent-optional').hidden = !optionalFields.children.length;
        ['start', 'stop', 'monitor'].forEach(action => {
            const definition = data.actions.find(item => item.name === action && !item.role) || data.actions.find(item => item.name === action);
            byId(`resource-${action}_timeout`).value = duration(definition?.timeout);
            if (action === 'monitor' && definition?.interval && !/^0(?:s|ms)?$/.test(definition.interval)) byId('resource-monitor_interval').value = duration(definition.interval) || '30s';
        });
        setDisabled('resource-create', false);
    }
    function resourceParameters() {
        if (!agentMetadata || agentMetadata.agent !== byId('resource-agent').value) throw new Error('Discover and select a verified agent first');
        const extra = JSON.parse(byId('parameters').value || '{}');
        if (!extra || Array.isArray(extra) || typeof extra !== 'object') throw new Error('Additional parameters must be a JSON object');
        const values = {};
        ['agent-parameters', 'agent-optional-fields'].forEach(id => byId(id).querySelectorAll('[data-agent-parameter]').forEach(input => { if (input.value !== '') values[input.dataset.agentParameter] = input.value; }));
        const result = {...values, ...extra};
        const missing = agentMetadata.parameters.filter(parameter => parameter.required && !parameter.default && !result[parameter.name]
            && !(agentMetadata.agent.startsWith('stonith:') && ['port', 'plug'].includes(parameter.name) && (result.pcmk_host_map || result.pcmk_host_list)));
        if (missing.length) throw new Error(`Fill required parameters: ${missing.map(p => p.name).join(', ')}`);
        return result;
    }
    function packagePlan() {
        const item = packageData.find(item => item.package === byId('agent-package').value);
        byId('package-plan').textContent = item ? item.nodes.map(node => `${node.node}: ${node.installed || 'not installed'} → ${node.candidate || 'unavailable'}`).join('\n') : '';
        setDisabled('package-install', !item || !item.ready || !item.needed);
    }
    function renderPackages() {
        const select = byId('agent-package'), previous = select.value, filter = byId('package-filter').value.toLowerCase();
        select.replaceChildren(new Option('Select a repository agent package', ''));
        packageData.filter(item => item.package.toLowerCase().includes(filter)).forEach(item => option(select, item.package,
            `${item.package}${!item.ready ? ' — unavailable on some nodes' : !item.needed ? ' — already installed' : ''}`));
        if (Array.from(select.options).some(option => option.value === previous)) select.value = previous;
        refreshSelect(select); packagePlan();
    }
    async function readPackages() {
        const id = selected()?.id;
        byId('package-plan').textContent = 'Reading enabled repository caches…'; setDisabled('package-install', true);
        const result = (await api(path('/agents/packages'))).data;
        if (id !== selected()?.id) return;
        packageData = result.packages; renderPackages();
        const errors = result.nodes.filter(node => node.error);
        if (errors.length) byId('package-plan').textContent = errors.map(node => `${node.name}: ${node.error}`).join('\n');
    }
    function otherChoices() {
        if (!choices) return;
        const select = byId('constraint-other'), previous = select.value;
        select.replaceChildren(new Option('Select a node or resource', ''));
        const values = byId('type').value === 'location' ? choices.nodes : choices.resources.map(item => item.id);
        values.forEach(value => option(select, value, value));
        if (values.includes(previous)) select.value = previous;
        refreshSelect(select);
    }
    async function readChoices() {
        const id = selected()?.id;
        const data = (await api(path('/choices'))).data;
        if (id !== selected()?.id) return;
        choices = data;
        const resources = byId('constraint-resource'), removal = byId('delete-id');
        resources.replaceChildren(new Option('Select a resource', '')); removal.replaceChildren(new Option('Select a resource or constraint', ''));
        data.resources.forEach(item => option(resources, item.id, `${item.id} (${item.type})`));
        [...data.resources, ...data.constraints].forEach(item => option(removal, item.id, `${item.id} (${item.type})`));
        refreshSelect(resources); refreshSelect(removal); otherChoices();
    }
    byId('agents-scan').addEventListener('click', guard(scan)); byId('resource-agents-refresh').addEventListener('click', guard(scan));
    byId('agent-filter').addEventListener('input', renderAgents);
    jQuery(byId('resource-agent')).on('selectmenuchange change', guard(loadMetadata));
    byId('resource-builder').addEventListener('toggle', guard(async () => { if (byId('resource-builder').open && !inventory) await scan(); }));
    byId('packages-read').addEventListener('click', guard(readPackages));
    byId('package-filter').addEventListener('input', renderPackages);
    jQuery(byId('agent-package')).on('selectmenuchange change', packagePlan);
    byId('packages-refresh').addEventListener('click', guard(async () => {
        if (!await RoxywiUI.confirm({title:'Refresh package repositories', message:`Refresh native repository metadata on every node of ${selected().name}?`, confirmText:'Refresh'})) return;
        await waitTask(await api(path('/agents/repositories'), 'POST', {confirm:selected().name})); await readPackages();
    }));
    byId('package-install').addEventListener('click', guard(async () => {
        const item = packageData.find(item => item.package === byId('agent-package').value);
        if (!item?.ready || !item.needed) throw new Error('Select an available package needing installation or update');
        if (!await RoxywiUI.confirm({title:'Install agent package', message:`Install/update ${item.package} on ${selected().name}?\n${byId('package-plan').textContent}\nNative dependencies may be updated.`, confirmText:'Install', requiredText:selected().name})) return;
        setDisabled('package-install', true);
        try { await waitTask(await api(path('/agents/packages'), 'POST', {package:item.package, plan_digest:item.plan_digest, confirm:selected().name})); }
        finally { await readPackages(); await scan(); }
    }));
    byId('choices-refresh').addEventListener('click', guard(readChoices)); byId('delete-refresh').addEventListener('click', guard(readChoices));
    jQuery(byId('type')).on('selectmenuchange change', otherChoices);
    ['constraint-form', 'delete-form'].forEach(id => byId(id).closest('details').addEventListener('toggle', guard(async event => { if (event.target.open) await readChoices(); })));
    return {reset, resourceParameters};
};
