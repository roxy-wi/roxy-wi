document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('ha-clusters');
    if (!root) return;
    const grid = root.querySelector('.ha-clusters-grid'), snapshots = new Map(), health = new Map();
    const healthRequests = new Set(), serviceHealth = new Map();
    const controllers = {readiness: window.RoxywiHAReadiness, maintenance: window.RoxywiHAMaintenance};
    const dialogs = {}, feedback = document.getElementById('ha-clusters-message');
    let plans = [], cardsLoading = false, plansLoading = false, plansTimer, cardsTimer, initial = true;
    let activePanel = null;
    const key = card => card.dataset.haProvider + '/' + card.dataset.haCluster;
    const errorText = (error, fallback) => error.responseJSON?.error || fallback;

    function sizeDialog(dialog) {
        dialog.dialog('option', {width: Math.min(1100, window.innerWidth - 24),
            maxHeight: window.innerHeight - 24, position: {my: 'center', at: 'center', of: window}});
    }
    Object.entries(controllers).forEach(([name, controller]) => {
        dialogs[name] = jQuery('#ha-' + name + '-dialog').dialog({
            autoOpen: false, modal: true, resizable: false, draggable: false,
            classes: {'ui-dialog': 'rw-dialog-responsive ha-cluster-dialog'},
            open() { jQuery('.ui-widget-overlay').last().addClass('ha-cluster-overlay'); },
            close() {
                controller.close(); activePanel = null;
                const url = new URL(window.location.href);
                ['panel', 'provider', 'cluster', 'change'].forEach(param => url.searchParams.delete(param));
                window.history.replaceState(null, '', url);
                refreshPlans();
            }
        });
    });
    function openPanel(card, panel, change) {
        if (!controllers[panel]) return;
        if (activePanel) dialogs[activePanel].dialog('close');
        const context = {provider: card.dataset.haProvider, id: card.dataset.haCluster, name: card.dataset.haName, change};
        const dialog = dialogs[panel];
        sizeDialog(dialog);
        dialog.dialog('widget').find('.ui-dialog-title').text(
            (panel === 'readiness' ? 'HA readiness' : 'Node maintenance') + ' · ' + context.name);
        activePanel = panel;
        dialog.dialog('open'); controllers[panel].open(context);
        const url = new URL(window.location.href);
        url.searchParams.set('panel', panel); url.searchParams.set('provider', context.provider); url.searchParams.set('cluster', context.id);
        if (change) url.searchParams.set('change', change); else url.searchParams.delete('change');
        window.history.replaceState(null, '', url);
    }
    window.addEventListener('resize', () => { if (activePanel) sizeDialog(dialogs[activePanel]); });
    grid.addEventListener('click', event => {
        const action = event.target.closest('[data-ha-action]'), card = action?.closest('[data-ha-cluster]');
        if (!card) return;
        const id = Number(card.dataset.haCluster), name = card.dataset.haName;
        switch (action.dataset.haAction) {
            case 'readiness': case 'maintenance': openPanel(card, action.dataset.haAction, action.dataset.change); break;
            case 'edit': createHaClusterStep1(true, id); break;
            case 'delete': confirmDeleteCluster(id); break;
            case 'vip': add_vip_ha_cluster(id, name); break;
            case 'edit-vip': add_vip_ha_cluster(id, name, action.dataset.vipId, action.dataset.vip, 1); break;
        }
    });
    function showPlans() {
        for (const card of grid.children) {
            const related = plans.filter(plan => plan.provider + '/' + plan.cluster_id === key(card));
            // A node already draining or reserved takes precedence over an unused draft.
            const priority = plan => plan.operation || ['draining', 'ready', 'unknown', 'resuming', 'return-reviewed'].includes(plan.status) ? 0 : 1;
            related.sort((a, b) => priority(a) - priority(b) || b.id - a.id);
            const badge = card.querySelector('.ha-plan-status'), plan = related[0];
            badge.hidden = !plan;
            if (!plan) continue;
            badge.textContent = plan.node_name + ' · ' + RoxywiMaintenance.status(plan) + (related.length > 1 ? ` (+${related.length - 1})` : '');
            badge.dataset.change = plan.change_id; badge.dataset.status = plan.status;
            badge.title = 'Open maintenance plan #' + plan.id;
        }
    }
    async function refreshPlans() {
        clearTimeout(plansTimer);
        if (plansLoading || document.hidden || !root.dataset.plans) return;
        plansLoading = true;
        try {
            const response = await jQuery.ajax({url: root.dataset.plans, global: false});
            plans = response.data; showPlans();
            if (feedback.dataset.error === 'plans') { feedback.textContent = ''; delete feedback.dataset.error; }
        } catch (error) {
            feedback.textContent = errorText(error, 'Unable to refresh maintenance status. Retrying automatically.');
            feedback.dataset.error = 'plans';
            grid.querySelectorAll('.ha-plan-status:not([hidden])').forEach(badge => { badge.title = 'Status may be outdated. Open the plan to check.'; });
        } finally {
            plansLoading = false;
            if (!document.hidden) plansTimer = setTimeout(refreshPlans, 10000);
        }
    }
    function showPacemakerStatus(card, state) {
        if (card.dataset.haProvider !== 'pacemaker') return;
        const isTrue = value => value === true || value === 'true';
        const nodes = new Map((state?.nodes || []).map(node => [node.name, node]));
        for (const row of card.querySelectorAll('[data-ha-node]')) {
            const node = nodes.get(row.dataset.haNode), badge = row.querySelector('[data-ha-node-status]');
            const [label, tone] = !node ? ['Unknown', 'stale']
                : isTrue(node.unclean) ? ['Unclean', 'stopped']
                : !isTrue(node.online) ? ['Offline', 'stopped']
                : isTrue(node.maintenance) ? ['Maintenance', 'unavailable']
                : isTrue(node.standby) ? ['Standby', 'unavailable'] : ['Online', 'running'];
            badge.textContent = label;
            badge.className = 'rw-status-badge rw-status-' + tone;
        }
        const quorum = card.querySelector('[data-ha-quorum]');
        quorum.textContent = !state ? 'Unknown' : state.quorate ? 'Available' : 'No quorum';
        quorum.className = 'rw-status-badge rw-status-' + (!state ? 'stale' : state.quorate ? 'running' : 'stopped');
        card.querySelector('[data-ha-coordinator]').textContent = state?.dc || '—';
        card.querySelector('[data-ha-failures]').textContent = state?.failures ?? '—';
        const resources = card.querySelector('[data-ha-resources]');
        if (!state) { resources.textContent = '—'; return; }
        const active = state.resources.filter(resource => isTrue(resource.active)).length;
        const failed = state.resources.filter(resource => isTrue(resource.failed) || isTrue(resource.blocked)).length;
        resources.textContent = `${active} / ${state.resources.length} active` + (failed ? ` · ${failed} failed / blocked` : '');
    }
    function showHealth(card, status, title, state) {
        const [label, tone, border] = ({
            ok: ['UP', 'running', 'up'], healthy: ['UP', 'running', 'up'],
            error: ['DOWN', 'stopped', 'down'], failed: ['DOWN', 'stopped', 'down'],
            'quorum-lost': ['No quorum', 'stopped', 'down'],
            'node-unavailable': ['Node unavailable', 'unavailable', 'unknown'],
            'resource-failed': ['Resource failed', 'stopped', 'down'],
            'witness-unavailable': ['Witness unavailable', 'unavailable', 'unknown'],
            warning: ['Degraded', 'unavailable', 'unknown']
        })[status] || ['Unknown', 'stale', 'dis'];
        const badge = card.querySelector('[data-ha-health]');
        badge.dataset.haHealth = status;
        badge.className = 'rw-status-badge service-status-badge rw-status-' + tone;
        badge.textContent = label;
        badge.title = title;
        card.classList.remove('div-server-head-up', 'div-server-head-down', 'div-server-head-unknown', 'div-server-head-dis');
        card.classList.add('div-server-head-' + border);
        showPacemakerStatus(card, state);
    }
    async function checkHealth(card) {
        if (!card.querySelector('.ha-card-member') || healthRequests.has(key(card))) return;
        healthRequests.add(key(card));
        let status, title, state;
        try {
            const response = await jQuery.ajax({url: card.dataset.haStatusUrl, global: false});
            status = card.dataset.haProvider === 'pacemaker' ? response.health : response.status;
            state = response.data;
            title = 'Last checked: ' + new Date().toLocaleString();
        } catch (error) { status = 'unknown'; title = errorText(error, 'Unable to check cluster status'); }
        health.set(key(card), {status, title, state});
        healthRequests.delete(key(card));
        const current = document.getElementById(card.id);
        if (current) showHealth(current, status, title, state);
    }
    async function checkServices(card) {
        if (!card.dataset.haVip) return;
        for (const badge of card.querySelectorAll('[data-ha-service]')) {
            const service = badge.dataset.haService, requestKey = key(card) + '/' + service;
            if (healthRequests.has(requestKey)) continue;
            healthRequests.add(requestKey);
            let status, title;
            try {
                const response = await jQuery.ajax({url: api_prefix + '/service/' + service + '/' + encodeURIComponent(card.dataset.haVip) + '/status', global: false});
                status = response.status === 'running' ? 'up' : response.status === 'failed' ? 'down' : 'unknown';
                title = service + ': ' + status;
            } catch (error) { status = 'unknown'; title = errorText(error, 'Unable to check ' + service); }
            serviceHealth.set(requestKey, {status, title}); healthRequests.delete(requestKey);
            const current = document.getElementById(card.id)?.querySelector('[data-ha-service="' + service + '"]');
            if (current) { current.dataset.state = status; current.title = title; }
        }
    }
    async function refresh() {
        clearTimeout(cardsTimer);
        if (cardsLoading || document.hidden) return;
        cardsLoading = true;
        try {
            const html = await jQuery.ajax({url: root.dataset.cards, dataType: 'html', global: false});
            const template = document.createElement('template'); template.innerHTML = html;
            const incoming = Array.from(template.content.querySelectorAll('.ha-cluster-card'));
            const ids = new Set(incoming.map(card => card.id));
            for (const card of Array.from(grid.children)) {
                if (!ids.has(card.id)) { snapshots.delete(card.id); health.delete(key(card)); card.remove(); }
            }
            for (const card of incoming) {
                const current = document.getElementById(card.id), snapshot = card.outerHTML;
                if (!current) { grid.append(card); snapshots.set(card.id, snapshot); }
                else if (snapshots.get(card.id) !== snapshot && !current.contains(document.activeElement) &&
                    !current.querySelector('.admin-actions-toggle[aria-expanded="true"]')) {
                    current.replaceWith(card); snapshots.set(card.id, snapshot);
                }
                const saved = health.get(key(card));
                if (saved) showHealth(document.getElementById(card.id), saved.status, saved.title, saved.state);
                document.getElementById(card.id).querySelectorAll('[data-ha-service]').forEach(badge => {
                    const cached = serviceHealth.get(key(card) + '/' + badge.dataset.haService);
                    if (cached) { badge.dataset.state = cached.status; badge.title = cached.title; }
                });
                checkHealth(card);
                checkServices(card);
            }
            if (window.FontAwesome) await FontAwesome.dom.i2svg({node: grid});
            document.getElementById('ha-clusters-empty').hidden = Boolean(incoming.length);
            if (feedback.dataset.error === 'cards') { feedback.textContent = ''; delete feedback.dataset.error; }
            showPlans();
            if (initial) {
                initial = false;
                const query = new URLSearchParams(window.location.search), panel = query.get('panel');
                if (controllers[panel]) {
                    const card = Array.from(grid.children).find(item => key(item) === query.get('provider') + '/' + query.get('cluster'));
                    if (card) openPanel(card, panel, query.get('change'));
                    else if (!query.has('cluster') && grid.children.length === 1) openPanel(grid.firstElementChild, panel, query.get('change'));
                    else feedback.textContent = 'Open Actions on the cluster to view ' + panel + '.';
                }
            }
        } catch (error) {
            feedback.textContent = errorText(error, 'Unable to load HA clusters. Retrying automatically.');
            feedback.dataset.error = 'cards';
        } finally {
            cardsLoading = false;
            if (!document.hidden) cardsTimer = setTimeout(refresh, 60000);
        }
    }
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) { refresh(); refreshPlans(); }
        else { clearTimeout(cardsTimer); clearTimeout(plansTimer); }
    });
    window.RoxywiHAClusters = {refresh, refreshPlans};
    refresh(); refreshPlans();
});
