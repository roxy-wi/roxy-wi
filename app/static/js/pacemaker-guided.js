/* Typed guided forms. Cluster data is rendered as text, never as markup. */
'use strict';
window.RoxywiPacemakerGuided = function ({api, path, showChange}) {
    const byId = key => document.getElementById('pcmk-guided-' + key);
    const form = byId('form');
    if (!form) return {reset() {}};
    const fields = byId('fields'), rows = byId('rows'), actions = byId('actions');
    let snapshot = null, generation = 0, sequence = 0, read = null, loading = false;
    const disabledControls = new Map();
    function setLoading(value) {
        byId('load').disabled = value;
        jQuery(byId('load')).button('option', 'disabled', value);
        form.setAttribute('aria-busy', String(value));
        if (value) {
            form.querySelectorAll('input, select, button').forEach(control => {
                disabledControls.set(control, control.disabled);
                control.disabled = true;
                if (jQuery(control).data('ui-selectmenu')) jQuery(control).selectmenu('option', 'disabled', true);
                if (jQuery(control).data('ui-button')) jQuery(control).button('option', 'disabled', true);
            });
        } else {
            disabledControls.forEach((disabled, control) => {
                if (!control.isConnected) return;
                control.disabled = disabled;
                if (jQuery(control).data('ui-selectmenu')) jQuery(control).selectmenu('option', 'disabled', disabled);
                if (jQuery(control).data('ui-button')) jQuery(control).button('option', 'disabled', disabled);
            });
            disabledControls.clear();
        }
    }
    const status = (text, error = false) => { byId('status').textContent = text; byId('status').className = error ? 'rw-error-state' : 'rw-form-help'; };
    const guard = callback => async event => { event?.preventDefault(); if (loading) return; try { await callback(event); } catch (error) { status(error.message, true); } };
    function labelSelect(control, label) {
        control.setAttribute('aria-label', label);
        const sync = () => { jQuery(control).selectmenu('option', 'width', '100%'); jQuery(control).selectmenu('widget').attr('aria-label', label); };
        jQuery(control).on('selectmenucreate', sync);
        if (jQuery(control).data('ui-selectmenu')) sync();
    }
    labelSelect(byId('kind'), 'Configuration task'); labelSelect(byId('existing'), 'Existing configuration');
    function panelContent(parent, className) {
        if (!parent.hasAttribute('data-guided-panel')) return parent;
        let content = parent.querySelector(':scope > .' + className);
        if (!content) { content = document.createElement('div'); content.className = className; parent.append(content); }
        return content;
    }
    function button(label, callback, parent = actions) {
        parent = panelContent(parent, 'rw-table-toolbar');
        const control = document.createElement('button'); control.type = 'button'; control.className = 'rw-button rw-button-secondary'; control.textContent = label;
        control.addEventListener('click', guard(callback)); parent.append(control); jQuery(control).button(); return control;
    }
    function field(parent, label, value = '', options = null, type = 'text', required = false) {
        parent = panelContent(parent, 'change-advanced-grid');
        const shell = document.createElement('div'); shell.className = 'rw-form-field';
        const control = document.createElement(options ? 'select' : 'input'); control.id = 'pcmk-guided-control-' + (++sequence); control.className = 'form-control';
        const title = document.createElement('label'); title.htmlFor = control.id; title.textContent = label; shell.append(title, control); parent.append(shell);
        if (options) {
            options.forEach(item => control.add(new Option(item.label ?? item.id ?? item, item.id ?? item)));
            if (value !== '' && !Array.from(control.options).some(item => item.value === String(value))) control.add(new Option(String(value) + ' (existing)', String(value)));
            control.value = value ?? ''; jQuery(control).selectmenu({width: '100%'}); labelSelect(control, label);
            jQuery(control).on('selectmenuchange', () => control.dispatchEvent(new Event('change')));
        } else { control.type = type; control.value = value ?? ''; }
        control.required = required; return control;
    }
    function set(control, value) { control.value = value ?? ''; if (control.tagName === 'SELECT') jQuery(control).selectmenu('refresh'); }
    function destroy(parent) { parent.querySelectorAll('select').forEach(control => { if (jQuery(control).hasClass('ui-selectmenu-button')) return; if (jQuery(control).data('ui-selectmenu')) jQuery(control).selectmenu('destroy'); }); parent.replaceChildren(); }
    function panel(label, parent = rows) { const element = document.createElement('section'); element.className = 'rw-panel'; element.setAttribute('data-guided-panel', ''); const title = document.createElement('h4'); title.textContent = label; element.append(title); parent.append(element); return element; }
    function list(parent, title, values, choices, max = 32) {
        const entries = [], holder = document.createElement('div'); parent.append(holder);
        function add(value = '') {
            if (entries.length >= max) throw new Error('This list reached its supported size limit');
            const row = document.createElement('div'); row.className = 'rw-table-toolbar'; holder.append(row);
            const select = field(row, title + ' ' + (entries.length + 1), value, [{id: '', label: 'Select a resource'}, ...choices], 'text', true);
            const entry = {row, select}; entries.push(entry);
            button('Remove', () => { jQuery(select).selectmenu('destroy'); row.remove(); entries.splice(entries.indexOf(entry), 1); }, row);
        }
        values.forEach(add); const addButton = button('Add ' + title.toLowerCase(), () => add(), parent);
        return {values: () => entries.map(item => item.select.value), add, button: addButton};
    }
    const options = values => [{id: '', label: 'Package/default'}, ...values];
    function meta(parent, values, clone = true) {
        const box = panel('Meta-attributes — empty values use defaults', parent); const controls = {};
        const names = ['resource-stickiness', 'migration-threshold', 'failure-timeout', 'priority', 'target-role', 'is-managed'];
        if (clone) names.push('clone-max', 'clone-node-max', 'promoted-max', 'promoted-node-max', 'globally-unique', 'notify', 'ordered', 'interleave');
        names.forEach(name => {
            const choices = ['is-managed', 'globally-unique', 'notify', 'ordered', 'interleave'].includes(name) ? options(['true', 'false']) : name === 'target-role' ? options(['Started', 'Stopped', 'Promoted', 'Unpromoted']) : null;
            controls[name] = field(box, name, values?.[name] ?? '', choices);
        });
        return () => Object.fromEntries(Object.entries(controls).map(([key, value]) => [key, value.value]));
    }
    function render(data = {}) {
        destroy(fields); destroy(rows); destroy(actions); read = null;
        jQuery(byId('create')).button('option', 'disabled', false);
        const kind = byId('kind').value;
        const resourceOptions = predicate => snapshot.resources.filter(predicate).map(item => ({id: item.id, label: item.id + ' · ' + item.type}));
        const identifier = label => { const control = field(fields, label, data.id || '', null, 'text', true); control.readOnly = Boolean(data.id && byId('existing').value !== ''); return control; };
        if (kind === 'topology') {
            byId('help').textContent = 'Levels run from 1 to 9. All devices in one level must succeed; the next level is a fallback. This creates configuration only and does not test fencing.';
            if (!snapshot.topology_supported) { byId('help').textContent = 'The existing fencing topology uses pattern/attribute targets. Retain it in the complete CIB editor.'; jQuery(byId('create')).button('option', 'disabled', true); }
            const node = field(fields, 'Target node', data.node || snapshot.nodes[0], snapshot.nodes, 'text', true);
            const levels = [];
            function addLevel(value = {}) {
                if (levels.length >= 9) throw new Error('At most nine fencing levels are supported');
                const box = panel('Fencing level'); const index = field(box, 'Level index', value.index || levels.length + 1, Array.from({length: 9}, (_, n) => String(n + 1)));
                const devices = list(box, 'Device', value.devices || [''], resourceOptions(item => item.agent.startsWith('stonith:')));
                const entry = {box, index, devices}; levels.push(entry);
                button('Remove level', () => { destroy(box); box.remove(); levels.splice(levels.indexOf(entry), 1); }, box);
            }
            (snapshot.topology[node.value] || []).forEach(addLevel);
            node.addEventListener('change', () => render({node: node.value})); button('Add fencing level', () => addLevel());
            read = () => ({node: node.value, levels: levels.map(item => ({index: Number(item.index.value), devices: item.devices.values()}))});
        } else if (kind === 'location-rule') {
            byId('help').textContent = 'Combine node-attribute comparisons and explicit time windows. Dates use your browser timezone and are sent with an explicit UTC offset. Existing nested/conditional rules stay in the CIB editor.';
            const id = identifier('Constraint ID'); const resource = field(fields, 'Resource', data.resource || '', [{id: '', label: 'Select a resource'}, ...resourceOptions(() => true)], 'text', true);
            const score = field(fields, 'Score', data.score || 'INFINITY', null, 'text', true); const combination = field(fields, 'Combine conditions', data.boolean_op || 'and', ['and', 'or']); const conditions = [];
            function add(value = {}) {
                if (conditions.length >= 32) throw new Error('At most 32 conditions are supported');
                const box = panel('Rule condition');
                const type = field(box, 'Condition kind', value.kind || 'attribute', ['attribute', 'date']);
                const attribute = field(box, 'Node attribute', value.attribute || '#uname'); attribute.setAttribute('list', 'pcmk-guided-attributes');
                const operation = field(box, 'Comparison', value.operation || 'eq', ['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'defined', 'not_defined']);
                const comparisonValue = field(box, 'Comparison value', value.value || ''); const comparisonType = field(box, 'Value type', value.type || 'string', ['string', 'integer', 'number', 'version']);
                const localTime = text => { if (!text) return ''; const date = new Date(text); return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-') + 'T' + date.toTimeString().slice(0, 8); };
                const start = field(box, 'Window start (local time)', localTime(value.start), null, 'datetime-local'); start.step = '1';
                const end = field(box, 'Window end (local time)', localTime(value.end), null, 'datetime-local'); end.step = '1';
                function visibility() { const date = type.value === 'date'; [attribute, operation, comparisonValue, comparisonType].forEach(control => { control.parentElement.hidden = date; control.required = false; }); start.parentElement.hidden = end.parentElement.hidden = !date; start.required = end.required = date; comparisonValue.parentElement.hidden = date || ['defined', 'not_defined'].includes(operation.value); }
                type.addEventListener('change', visibility); operation.addEventListener('change', visibility); visibility();
                const item = {box, read: () => type.value === 'date' ? {kind: 'date', start: new Date(start.value).toISOString(), end: new Date(end.value).toISOString()} : {kind: 'attribute', attribute: attribute.value, operation: operation.value, value: comparisonValue.value, type: comparisonType.value}}; conditions.push(item);
                button('Remove condition', () => { destroy(box); box.remove(); conditions.splice(conditions.indexOf(item), 1); }, box);
            }
            (data.conditions || [{}]).forEach(add); button('Add condition', () => add());
            read = () => ({id: id.value, resource: resource.value, score: score.value, boolean_op: combination.value, conditions: conditions.map(item => item.read())});
        } else if (kind === 'collection') {
            byId('help').textContent = 'Member order controls group startup; shutdown uses the reverse order. A clone wraps one primitive/group. Unselected existing members are retained as standalone resources and may then run independently; inspect simulation before applying.';
            const id = identifier('Group / clone ID'); const type = field(fields, 'Collection kind', data.kind || 'group', ['group', 'clone', 'promotable']);
            const choices = resourceOptions(item => (item.parent === null || item.parent === data.id) && (item.type === 'primitive' || type.value !== 'group' && item.type === 'group'));
            const members = list(panel('Ordered members'), 'Member', data.members || [''], choices);
            type.addEventListener('change', () => { const current = {id: id.value, kind: type.value, members: members.values(), meta: readMeta()}; render(current); });
            const readMeta = meta(rows, data.meta, type.value !== 'group');
            read = () => ({id: id.value, kind: type.value, members: members.values(), meta: readMeta()});
        } else if (kind === 'operation') {
            byId('help').textContent = 'Configure a monitor or lifecycle operation on an existing primitive. Non-monitor operations use interval 0s. Failure policies including fence take effect only after the separately reviewed CIB is applied.';
            const resource = field(fields, 'Primitive', data.resource || '', [{id: '', label: 'Select a primitive'}, ...resourceOptions(item => item.type === 'primitive')], 'text', true);
            const id = field(fields, 'Operation ID (existing)', data.id || ''); id.readOnly = true;
            const name = field(fields, 'Operation', data.name || 'monitor', ['monitor', 'start', 'stop', 'promote', 'demote', 'notify', 'reload', 'reload-agent', 'migrate_to', 'migrate_from']);
            const interval = field(fields, 'Interval', data.interval || '30s', null, 'text', true); const timeout = field(fields, 'Timeout', data.timeout || '60s', null, 'text', true);
            const role = field(fields, 'Role', data.role || '', options(['Started', 'Stopped', 'Promoted', 'Unpromoted'])); const onFail = field(fields, 'On failure', data.on_fail || '', options(['ignore', 'block', 'stop', 'restart', 'fence', 'standby', 'demote']));
            const enabled = field(fields, 'Enabled', data.enabled === false ? 'false' : 'true', ['true', 'false']);
            name.addEventListener('change', () => { if (name.value !== 'monitor') interval.value = '0s'; });
            button('Read agent recommendations', async () => {
                const selected = snapshot.resources.find(item => item.id === resource.value); if (!selected?.agent) throw new Error('Select a primitive with a supported agent');
                const token = generation; const metadata = (await api(path('/agents/metadata?agent=' + encodeURIComponent(selected.agent)))).data;
                if (token !== generation) return;
                const action = metadata.actions.find(item => item.name === name.value && (!item.role || item.role === role.value));
                if (!action) throw new Error('The agent does not advertise this operation/role');
                if (action.timeout) timeout.value = action.timeout; if (action.interval) interval.value = action.interval;
                status('Agent recommendations loaded. Review timings and failure policy before creating a draft.');
            });
            read = () => ({resource: resource.value, ...(id.value ? {id: id.value} : {}), name: name.value, interval: interval.value, timeout: timeout.value, role: role.value, on_fail: onFail.value, enabled: enabled.value === 'true'});
            if (data.id) button('Create operation-removal draft', () => createDraft({...read(), remove: true}));
        } else if (kind === 'bundle') {
            byId('help').textContent = 'Create or edit a static Docker/Podman bundle. Container runtime, agents and a configured image must be available on eligible nodes. A managed primitive needs pacemaker-remoted in the image and an IP range or explicit control port. This form does not install images or start containers.';
            const id = identifier('Bundle ID'); const engine = field(fields, 'Container engine', data.engine || 'podman', ['podman', 'docker']); const image = field(fields, 'Image', data.image || '', null, 'text', true);
            const replicas = field(fields, 'Replicas', data.replicas || 1, null, 'number', true); replicas.min = '1'; replicas.max = '32';
            const perHost = field(fields, 'Replicas per host', data.replicas_per_host || 1, null, 'number', true); perHost.min = '1'; perHost.max = '32';
            const promoted = field(fields, 'Maximum promoted replicas', data.promoted_max || 0, null, 'number', true); promoted.min = '0'; promoted.max = '32';
            const network = field(fields, 'Network mode', data.network || '', options(['host', 'bridge'])); const command = field(fields, 'Container startup command', data.run_command || '');
            const ip = field(fields, 'First replica IPv4 address', data.ip_range_start || ''); const mask = field(fields, 'Host netmask (bits)', data.host_netmask ?? 32, null, 'number'); mask.min = '0'; mask.max = '32';
            const iface = field(fields, 'Host interface', data.host_interface || ''); const controlPort = field(fields, 'Pacemaker Remote control port', data.control_port || '', null, 'number'); controlPort.min = '1'; controlPort.max = '65535';
            const primitive = field(fields, 'Managed primitive (optional)', data.resource || '', [{id: '', label: 'No managed primitive'}, ...resourceOptions(item => item.type === 'primitive' && (item.parent === null || item.parent === data.id))]);
            const ports = [], volumes = [];
            function addPort(value = {}) { if (ports.length >= 32) throw new Error('At most 32 port mappings are supported'); const box = panel('Port mapping'); const host = field(box, 'Host port', value.port || '', null, 'number', true), internal = field(box, 'Container port', value.internal_port || '', null, 'number'); [host, internal].forEach(control => { control.min = '1'; control.max = '65535'; }); const item = {read: () => ({port: Number(host.value), internal_port: internal.value ? Number(internal.value) : null})}; ports.push(item); button('Remove port mapping', () => { destroy(box); box.remove(); ports.splice(ports.indexOf(item), 1); }, box); }
            function addVolume(value = {}) { if (volumes.length >= 32) throw new Error('At most 32 storage mappings are supported'); const box = panel('Storage mapping'); const source = field(box, 'Host source path', value.source || '', null, 'text', true), target = field(box, 'Container target path', value.target || '', null, 'text', true), root = field(box, 'Source path mode', value.source_root ? 'replica-root' : 'directory', ['directory', 'replica-root']), mode = field(box, 'Access / SELinux label', value.options || 'ro', ['ro', 'rw', 'ro,z', 'ro,Z', 'rw,z', 'rw,Z']); const item = {read: () => ({source: source.value, target: target.value, source_root: root.value === 'replica-root', options: mode.value})}; volumes.push(item); button('Remove storage mapping', () => { destroy(box); box.remove(); volumes.splice(volumes.indexOf(item), 1); }, box); }
            (data.ports || []).forEach(addPort); (data.volumes || []).forEach(addVolume); button('Add port mapping', () => addPort()); button('Add storage mapping', () => addVolume());
            read = () => ({id: id.value, engine: engine.value, image: image.value, replicas: Number(replicas.value), replicas_per_host: Number(perHost.value), promoted_max: Number(promoted.value), network: network.value, run_command: command.value, ip_range_start: ip.value, host_netmask: Number(mask.value), host_interface: iface.value, control_port: controlPort.value ? Number(controlPort.value) : null, resource: primitive.value || null, ports: ports.map(item => item.read()), volumes: volumes.map(item => item.read())});
        } else if (kind === 'meta') {
            byId('help').textContent = 'Edit static meta-attributes. Unrelated keys are retained. Empty values clear the selected explicit overrides; conditional/referenced sets remain in the CIB editor.';
            const resource = field(fields, 'Resource / wrapper', data.resource || '', [{id: '', label: 'Select a resource'}, ...resourceOptions(item => item.meta !== null && item.type !== 'master')], 'text', true);
            const selectedResource = snapshot.resources.find(item => item.id === resource.value); const values = selectedResource?.meta || {}; const readMeta = meta(rows, values, selectedResource?.type === 'clone');
            resource.addEventListener('change', () => render({resource: resource.value})); read = () => ({resource: resource.value, values: readMeta()});
        }
    }
    function chooseTask() {
        const kind = byId('kind').value, select = byId('existing');
        select.replaceChildren(new Option('Create new configuration', ''));
        const values = kind === 'collection' ? snapshot.collections : kind === 'bundle' ? snapshot.bundles : kind === 'location-rule' ? snapshot.rules : kind === 'operation' ? snapshot.operations : [];
        values.forEach((item, index) => select.add(new Option(item.resource ? `${item.resource} · ${item.name || item.id}` : item.id, String(index))));
        jQuery(select).selectmenu('refresh'); byId('existing-field').hidden = !['collection', 'bundle', 'location-rule', 'operation'].includes(kind);
        render();
    }
    async function createDraft(data) {
        if (!snapshot || !read) throw new Error('Read the current configuration first');
        const token = generation; jQuery(byId('create')).button('option', 'disabled', true);
        try {
            const result = await api(path('/guided'), 'POST', {kind: byId('kind').value, base_digest: snapshot.base_digest, data});
            if (token === generation) await showChange(result.id);
        } finally { if (token === generation) jQuery(byId('create')).button('option', 'disabled', false); }
    }
    byId('existing').addEventListener('change', () => {
        const values = {collection: snapshot.collections, bundle: snapshot.bundles, 'location-rule': snapshot.rules, operation: snapshot.operations}[byId('kind').value];
        render(byId('existing').value === '' ? {} : values[Number(byId('existing').value)]);
    });
    jQuery(byId('existing')).on('selectmenuchange', () => byId('existing').dispatchEvent(new Event('change')));
    byId('kind').addEventListener('change', guard(chooseTask)); jQuery(byId('kind')).on('selectmenuchange', () => byId('kind').dispatchEvent(new Event('change')));
    byId('load').addEventListener('click', guard(async () => {
        const token = ++generation;
        loading = true; setLoading(true); status('Reading the current cluster configuration…');
        try {
            const result = (await api(path('/guided'))).data;
            if (token !== generation) return;
            setLoading(false);
            snapshot = result; byId('unsupported-panel').hidden = !snapshot.unsupported.length; byId('unsupported').replaceChildren(); snapshot.unsupported.forEach(item => { const entry = document.createElement('li'); entry.textContent = item.kind + ': ' + item.id; byId('unsupported').append(entry); }); const attributes = byId('attributes'); attributes.replaceChildren(); snapshot.attributes.forEach(value => attributes.append(new Option(value, value)));
            form.hidden = false; chooseTask(); status('Configuration loaded. Changes require review.');
        } catch (error) {
            if (token === generation) status(error.message, true);
        } finally {
            if (token === generation) { setLoading(false); loading = false; }
        }
    }));
    form.addEventListener('submit', guard(async () => { if (!form.reportValidity()) return; await createDraft(read()); }));
    return {reset() { generation++; setLoading(false); loading = false; snapshot = null; read = null; form.hidden = true; destroy(fields); destroy(rows); destroy(actions); byId('unsupported-panel').hidden = true; byId('unsupported').replaceChildren(); status('Read the cluster before creating a draft.'); }};
};
