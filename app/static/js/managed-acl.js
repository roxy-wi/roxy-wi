document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('managed-acl');
    if (!root) return;
    const el = id => document.getElementById('acl-' + id);
    const node = (tag, text) => {
        const value = document.createElement(tag);
        if (text !== undefined) value.textContent = text;
        return value;
    };
    const notifyError = (error, operation) => window.RoxywiUI.toastError(error.message || error, {operation});
    const icons = parent => window.FontAwesome?.dom?.i2svg({node: parent});
    const linkedChange = new URLSearchParams(window.location.search).get('change');
    const reportedErrors = new Map();
    let providers = [], servers = [], editing = null, targets = [], selected = null, timer;
    let linkedVersion = null, linkOpened = false, choicesReady = false, saving = false;
    let formGeneration = 0, refreshGeneration = 0, versionsGeneration = 0, evidenceGeneration = 0;
    const dialog = el('dialog') ? jQuery(el('dialog')).removeClass('ui-helper-hidden').dialog({
        autoOpen: false, modal: true, resizable: false, draggable: false, title: 'New managed feed',
        width: Math.min(800, window.innerWidth - 32), maxHeight: window.innerHeight - 32,
        classes: {'ui-dialog': 'rw-dialog-responsive acl-feed-dialog'},
        beforeClose: () => !saving,
        close() { formGeneration++; },
        open() { jQuery('.ui-widget-overlay').last().addClass('acl-feed-overlay'); el('name').focus(); }
    }) : null;

    function disabled(control, value) {
        if (!control) return;
        control.disabled = value;
        if (jQuery(control).button('instance')) jQuery(control).button('refresh');
    }
    async function api(path = '', data, method) {
        try {
            return await jQuery.ajax({url: root.dataset.api + path, method: method || (data === undefined ? 'GET' : 'POST'),
                contentType: 'application/json', global: false, data: data === undefined ? undefined : JSON.stringify(data)});
        } catch (error) {
            throw new Error(error.responseJSON?.error || 'Managed ACL request failed');
        }
    }
    function button(label, action, icon) {
        const control = node('button', icon ? undefined : label);
        control.type = 'button';
        control.className = icon ? 'rw-icon-button' : 'rw-button rw-button-secondary';
        if (icon) {
            control.title = label;
            control.setAttribute('aria-label', label);
            const glyph = node('span');
            glyph.className = 'fas fa-' + icon;
            glyph.setAttribute('aria-hidden', 'true');
            control.append(glyph);
        }
        control.addEventListener('click', async () => {
            if (control.disabled) return;
            disabled(control, true);
            try { await action(); }
            catch (error) { notifyError(error, label); }
            finally { disabled(control, false); }
        });
        return control;
    }
    function select(input, values, first, value) {
        const previous = value === undefined ? input.value : String(value);
        input.replaceChildren(...(first ? [new Option(first, '')] : []), ...values.map(item => new Option(item.name, item.id)));
        if (values.some(item => String(item.id) === previous) || (first && previous === '')) input.value = previous;
        const options = {appendTo: el('dialog'), width: '100%'};
        if (jQuery(input).selectmenu('instance')) jQuery(input).selectmenu('option', options).selectmenu('refresh');
        else jQuery(input).selectmenu(options);
    }
    function badge(label, state) {
        const value = node('span', label);
        value.className = 'rw-status-badge rw-status-' + state;
        return value;
    }
    function actionCell() {
        const cell = node('td'), group = node('div');
        cell.className = 'acl-actions-cell';
        group.className = 'acl-row-actions';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', 'Actions');
        cell.append(group);
        return {cell, group};
    }
    function wrapCells(row) {
        // Shared mobile tables expect a single content wrapper per cell.
        for (const cell of row.children) {
            if (cell.childNodes.length > 1) {
                const wrapper = node('div');
                wrapper.append(...cell.childNodes);
                cell.append(wrapper);
            }
        }
    }
    function showTargets() {
        el('targets').replaceChildren();
        if (!targets.length) {
            const empty = node('p', 'No targets added. Select a node and discover its IP lists.');
            empty.className = 'rw-form-help';
            el('targets').append(empty);
        }
        targets.forEach((target, index) => {
            const line = node('div');
            line.className = 'acl-target';
            line.append(node('span', (servers.find(server => server.id === target.server_id)?.name || 'Node #' + target.server_id) + ' · ' + target.path),
                button('Remove target', () => { targets.splice(index, 1); showTargets(); }, 'times'));
            el('targets').append(line);
        });
        icons(el('targets'));
    }
    function edit(item) {
        formGeneration++;
        editing = item || null;
        targets = item ? item.targets.map(target => ({...target})) : [];
        el('form').reset();
        el('advanced').open = false;
        el('name').value = item?.name || '';
        el('url').value = item?.settings.url || '';
        el('interval').value = item?.interval_minutes || 360;
        el('stale').value = item?.stale_hours || 24;
        el('max').value = item?.settings.max_entries || 50000;
        el('v4').value = item?.settings.min_ipv4_prefix ?? 8;
        el('v6').value = item?.settings.min_ipv6_prefix ?? 16;
        el('ca').value = item?.settings.ca_pem || '';
        for (const [id, checked] of [['private', item?.settings.allow_private], ['enabled', item?.enabled]]) {
            el(id).checked = Boolean(checked);
            if (jQuery(el(id)).checkboxradio('instance')) jQuery(el(id)).checkboxradio('refresh');
        }
        select(el('provider'), providers, null, item?.provider || providers[0]?.id || '');
        select(el('server'), servers.map(server => ({id: server.id, name: server.name + ' (' + server.ip + ')'})), 'Select node', '');
        select(el('path'), [], 'Discover lists first');
        disabled(el('discover'), false);
        showTargets();
        dialog.dialog('option', {title: item ? 'Edit managed feed' : 'New managed feed',
            width: Math.min(800, window.innerWidth - 32), maxHeight: window.innerHeight - 32}).dialog('open');
    }
    async function action(feed, name, version) {
        await api('/' + feed.id + '/' + name, version ? {version_id: version.id} : {});
        el('message').textContent = 'ACL ' + name + ' queued in Operations.';
        await refresh();
    }
    async function evidence(feed, value) {
        const generation = ++evidenceGeneration;
        const content = await api('/' + feed.id + '/versions/' + value.id + '/content');
        if (generation !== evidenceGeneration || selected?.id !== feed.id) return;
        el('evidence').hidden = false;
        el('diff').textContent = (value.diff || 'No deployment review yet. Downloaded candidate is immutable.') +
            (value.diff_truncated ? '\nDiff display is truncated; review the full candidate and baselines below.' : '') +
            '\n\nOperation evidence:\n' + JSON.stringify(value.events, null, 2);
        el('content').replaceChildren();
        const add = (label, text) => {
            el('content').append(node('h4', label));
            const area = node('textarea');
            area.className = 'form-control'; area.readOnly = true; area.rows = 12; area.value = text;
            area.setAttribute('aria-label', label);
            el('content').append(area);
        };
        add('Candidate · SHA-256 ' + content.fingerprint, content.candidate);
        content.baselines.forEach(target => add('Reviewed node #' + target.server_id + ' · ' + target.path, target.content));
    }
    async function versions(feed) {
        const generation = ++versionsGeneration;
        if (selected?.id !== feed.id) { evidenceGeneration++; el('evidence').hidden = true; }
        selected = feed;
        const result = await api('/' + feed.id + '/versions' + (linkedVersion ? '?include_version=' + linkedVersion : ''));
        if (generation !== versionsGeneration) return;
        el('versions-panel').hidden = false;
        el('selected').textContent = feed.name + ' · versions';
        el('versions').replaceChildren();
        result.data.forEach(value => {
            const row = node('tr'), identity = node('td'), state = node('td'), actions = actionCell();
            identity.append(node('strong', 'Version #' + value.id), node('p', value.created_at));
            const fingerprint = node('code', value.fingerprint);
            fingerprint.className = 'acl-fingerprint'; identity.append(fingerprint);
            state.append(badge(value.status, value.status === 'deployed' ? 'running' : value.status === 'recovery-required' ? 'unavailable' : 'stale'),
                node('p', value.entries + ' entries'));
            actions.group.append(button('View content / diff', () => evidence(feed, value), 'file-alt'));
            if (value.change_id) {
                const link = node('a', 'Change #' + value.change_id + ' · ' + value.change_status);
                link.href = '/changes?change=' + value.change_id;
                const paragraph = node('p'); paragraph.append(link); state.append(paragraph);
            }
            if (root.dataset.write === '1') {
                if (['downloaded', 'reviewed', 'rolled-back', 'deployed'].includes(value.status))
                    actions.group.append(button('Review deployment', () => action(feed, 'review', value), 'clipboard-check'));
                if (value.status === 'reviewed' && value.change_status === 'approved')
                    actions.group.append(button('Apply approved version', () => action(feed, 'apply', value), 'play'));
                if (['deployed', 'reviewed', 'rolled-back'].includes(value.status))
                    actions.group.append(button('Prepare rollback to this version', () => action(feed, 'rollback-version', value), 'undo'));
                if (['deploying', 'recovery-required'].includes(value.status))
                    actions.group.append(button('Recover transaction', () => action(feed, 'recover', value), 'sync-alt'));
            }
            row.append(identity, state, node('td', value.targets.map(target => 'Node #' + target.server_id + ': +' + target.added + ' / −' + target.removed).join('; ') || 'Not reviewed on targets'), actions.cell);
            wrapCells(row);
            el('versions').append(row);
        });
        icons(el('versions'));
        if (linkedVersion && !linkOpened) {
            const value = result.data.find(version => version.id === linkedVersion);
            if (value) { linkOpened = true; await evidence(feed, value); el('versions-panel').scrollIntoView({block: 'nearest'}); }
        }
    }
    async function refresh() {
        clearTimeout(timer);
        const generation = ++refreshGeneration;
        disabled(el('refresh'), true);
        root.setAttribute('aria-busy', 'true');
        try {
            if (!choicesReady) {
                const choices = await jQuery.ajax({url: root.dataset.choices, global: false});
                servers = choices.servers.filter(server => server.services.includes('haproxy'));
                choicesReady = true;
            }
            const result = await api(linkedChange ? '?change=' + encodeURIComponent(linkedChange) : '');
            if (generation !== refreshGeneration) return;
            providers = result.providers;
            disabled(el('new'), !providers.length);
            if (!linkOpened && result.selected_feed_id) {
                selected = result.data.find(feed => feed.id === result.selected_feed_id) || selected;
                linkedVersion = result.selected_version_id;
            }
            el('rows').replaceChildren();
            let pending = false;
            result.data.forEach(feed => {
                const row = node('tr'), actions = actionCell(), source = node('td'), status = node('td'), deployment = node('td');
                source.append(node('strong', feed.name), node('p', feed.settings.url));
                const approved = feed.approved_revision === feed.revision;
                status.append(badge(approved ? 'Source revision approved' : 'Source approval required', approved ? 'running' : 'unavailable'),
                    node('p', feed.stale ? 'STALE / not downloaded' : new Date(feed.last_check).toLocaleString()));
                if (feed.error) {
                    status.append(button('Show last error', () => notifyError(feed.error, feed.name)));
                    const errorKey = String(feed.operation?.id || '') + ':' + feed.error;
                    if (reportedErrors.get(feed.id) !== errorKey) { reportedErrors.set(feed.id, errorKey); notifyError(feed.error, feed.name); }
                } else reportedErrors.delete(feed.id);
                actions.group.append(button('Versions', () => versions(feed), 'history'));
                if (root.dataset.write === '1') {
                    actions.group.append(button('Edit', () => edit(feed), 'pen'));
                    if (root.dataset.admin === '1' && !approved) actions.group.append(button('Approve source and targets', async () => {
                        await api('/' + feed.id + '/approve-source', {revision: feed.revision}); await refresh();
                    }, 'check'));
                    if (approved) actions.group.append(button('Fetch candidate', () => action(feed, 'fetch'), 'download'));
                    const remove = button('Delete feed', async () => {
                        await api('/' + feed.id, undefined, 'DELETE');
                        if (selected?.id === feed.id) {
                            selected = null; versionsGeneration++; evidenceGeneration++;
                            el('versions-panel').hidden = true; el('evidence').hidden = true;
                        }
                        await refresh();
                    }, 'trash-alt');
                    remove.classList.add('acl-delete'); actions.group.append(remove);
                }
                const running = feed.operation && ['created', 'published', 'running'].includes(feed.operation.status);
                pending = pending || running;
                if (running) deployment.append(badge('Operation ' + feed.operation.status, 'stale'));
                deployment.append(node('p', feed.deployed_version_id ? 'Deployed version #' + feed.deployed_version_id : 'No feed version deployed'));
                row.append(source, status, deployment, actions.cell);
                wrapCells(row);
                el('rows').append(row);
                if (selected?.id === feed.id) selected = feed;
            });
            icons(el('rows'));
            el('message').textContent = result.data.length ? result.data.length + ' managed feed(s)' : 'No managed feeds yet.';
            if (selected) await versions(selected);
            if (pending && generation === refreshGeneration) timer = setTimeout(refresh, 2000);
        } catch (error) {
            if (generation === refreshGeneration) {
                el('message').textContent = el('rows').children.length ? 'Showing the last loaded feeds.' : 'Feeds have not been loaded yet.';
                notifyError(error.responseJSON?.error || error, 'Refresh feeds');
            }
        } finally {
            if (generation === refreshGeneration) { disabled(el('refresh'), false); root.setAttribute('aria-busy', 'false'); }
        }
    }
    el('refresh').addEventListener('click', refresh);
    if (dialog) {
        el('new').addEventListener('click', () => edit(null));
        el('cancel').addEventListener('click', () => dialog.dialog('close'));
        el('discover').addEventListener('click', async () => {
            if (!el('server').value) { notifyError('Select a HAProxy node first.', 'Discover IP lists'); return; }
            const generation = ++formGeneration, serverId = Number(el('server').value);
            disabled(el('discover'), true);
            try {
                const result = await api('/discover', {server_id: serverId});
                if (generation !== formGeneration) return;
                select(el('path'), result.lists.map(item => ({id: item.path, name: item.path + ' · ' + item.entries + ' entries'})), 'Select loaded IP list');
                if (!result.lists.length) notifyError('No eligible persistent src IP ACL was found. Check HAProxy list/rule configuration and Runtime API access.', 'Discover IP lists');
            } catch (error) {
                if (generation === formGeneration) notifyError(error, 'Discover IP lists');
            } finally {
                if (generation === formGeneration) disabled(el('discover'), false);
            }
        });
        const reset = () => {
            formGeneration++; select(el('path'), [], 'Discover lists first'); disabled(el('discover'), false);
        };
        el('server').addEventListener('change', reset);
        jQuery(el('server')).selectmenu({change: reset, appendTo: el('dialog'), width: '100%'});
        el('add-target').addEventListener('click', () => {
            if (!el('server').value || !el('path').value) { notifyError('Select a node and a discovered IP list.', 'Add target'); return; }
            const target = {server_id: Number(el('server').value), path: el('path').value};
            if (targets.some(item => item.server_id === target.server_id)) { notifyError('Select one ACL per node in this feed.', 'Add target'); return; }
            targets.push(target); showTargets();
        });
        el('form').addEventListener('invalid', event => {
            if (el('advanced').contains(event.target)) el('advanced').open = true;
        }, true);
        el('form').addEventListener('submit', async event => {
            event.preventDefault();
            if (saving || !el('form').reportValidity()) return;
            if (!targets.length) { notifyError('Add at least one discovered ACL target.', 'Save feed'); return; }
            saving = true; disabled(el('save'), true); disabled(el('cancel'), true);
            try {
                await api(editing ? '/' + editing.id : '', {
                    name: el('name').value, provider: el('provider').value,
                    settings: {url: el('url').value, ca_pem: el('ca').value, allow_private: el('private').checked,
                        max_entries: Number(el('max').value), min_ipv4_prefix: Number(el('v4').value), min_ipv6_prefix: Number(el('v6').value)},
                    targets, interval_minutes: Number(el('interval').value), stale_hours: Number(el('stale').value),
                    enabled: el('enabled').checked, ...(editing ? {revision: editing.revision} : {})
                }, editing ? 'PUT' : 'POST');
                saving = false; dialog.dialog('close');
                toastr.success('Feed saved; an administrator must approve its source revision.');
                await refresh();
            } catch (error) { notifyError(error, 'Save feed'); }
            finally { saving = false; disabled(el('save'), false); disabled(el('cancel'), false); }
        });
    }
    window.addEventListener('pagehide', () => { clearTimeout(timer); refreshGeneration++; formGeneration++; versionsGeneration++; evidenceGeneration++; });
    refresh();
});
