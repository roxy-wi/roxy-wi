document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('ha-maintenance');
    if (!root) return;
    const ui = window.RoxywiMaintenance, node = ui.node, el = id => document.getElementById(id);
    const userId = Number(root.dataset.userId), role = Number(root.dataset.role), snapshots = new Map();
    const form = el('ha-maintenance-create');
    let invalidSelection = null;
    let timer, selection = 0, generation = 0, loading = false, posting = false, refreshAgain = false, loadError = false;
    const tabs = jQuery('#ha-maintenance-tabs').tabs(), history = new Map();
    let requestedChange = null, context = null, registration = null, opened = false, nextBefore = null, moreLoading = false;

    function message(text, busy = false, button = null) {
        RoxywiUI.operationStatus(el('ha-maintenance-message'), button, text, busy);
        el('ha-maintenance-message').parentElement.hidden = !text && !busy;
    }

    async function api(url, data) {
        try {
            return await jQuery.ajax({url, method: data === undefined ? 'GET' : 'POST', contentType: 'application/json',
                data: data === undefined ? undefined : JSON.stringify(data), global: false});
        } catch (error) {
            throw new Error(error.responseJSON?.error || 'Maintenance request failed');
        }
    }

    function select(input, values) {
        const placeholder = 'Select node';
        input.replaceChildren(new Option(placeholder, ''), ...values.map(value => new Option(value.name, value.id)));
        if (jQuery(input).selectmenu('instance')) jQuery(input).selectmenu('refresh');
        else jQuery(input).selectmenu();
    }

    async function members() {
        const value = el('maintenance-cluster').value, version = ++selection;
        select(el('maintenance-node'), []);
        if (!value) return;
        try {
            const data = await api(root.dataset.subjects + '/' + value);
            if (version !== selection) return;
            select(el('maintenance-node'), data.profile.nodes.filter(member => !member.name.startsWith('Witness: ')));
        } catch (error) {
            if (version === selection) message(error.message);
        }
    }

    async function submit(url, data, label, button) {
        if (posting) return;
        posting = true;
        const version = ++generation;
        clearTimeout(timer); loadError = false;
        message(label + '…', true, button);
        let failure = '';
        try {
            const response = await api(url, data);
            if (version === generation && response.data?.change_id) requestedChange = response.data.change_id;
        } catch (error) { failure = error.message; }
        finally {
            posting = false;
            // Always release the original button, without sending a stale result to another cluster.
            if (button) {
                button.disabled = false; button.setAttribute('aria-busy', 'false');
                if (jQuery(button).button('instance')) jQuery(button).button('refresh');
            }
            if (opened) {
                if (version === generation) message(failure);
                snapshots.clear(); refresh();
            }
            window.RoxywiHAClusters.refreshPlans();
        }
    }

    function actionButton(plan, action, label, primary = false) {
        const button = node('button', label);
        button.type = 'button';
        button.className = 'rw-button rw-button-' + (primary ? 'primary' : 'secondary');
        button.disabled = Boolean(plan.operation);
        const url = ['approve', 'cancel'].includes(action)
            ? '/changes/api/' + plan.change_id + '/' + action : root.dataset.api + '/' + plan.id + '/' + action;
        button.addEventListener('click', () => submit(url, {}, label, button));
        return button;
    }

    function panel(plan) {
        const section = node('section');
        section.className = 'rw-panel';
        section.dataset.plan = plan.id;
        section.append(node('h3', 'Plan #' + plan.id + ' · ' + plan.title),
            node('p', plan.cluster_name + ' · ' + plan.provider + ' · ' + plan.node_name + ' · Created by ' + (plan.created_by || 'deleted user')),
            node('p', ui.status(plan)), node('p', ui.nextStep(plan, userId)));
        const approval = ui.approval(plan, userId);
        if (approval) section.append(node('p', approval));
        const capacity = node('p', 'Capacity evidence (operator): ' + plan.capacity_evidence);
        capacity.className = 'maintenance-capacity';
        section.append(capacity);
        const review = ui.review(plan);
        if (review) section.append(review);
        const latest = plan.events.at(-1);
        if (['review-failed', 'unknown'].includes(plan.status) && latest) {
            const error = node('p', latest.message);
            error.className = 'alert alert-warning';
            section.append(error);
        }
        const actions = node('div');
        actions.className = 'rw-table-toolbar';
        const choices = {draft: [['review', 'Run drain checks']], 'review-failed': [['review', 'Retry drain checks']],
            reviewed: [['review', 'Re-run drain checks']], draining: [['verify', 'Verify drain'], ['review-return', 'Run return checks']],
            unknown: [['verify', 'Verify drain'], ['review-return', 'Run return checks']], ready: [['review-return', 'Run return checks']],
            'return-reviewed': [['review-return', 'Re-run return checks']]};
        if (role <= 3) {
            (choices[plan.status] || []).forEach(([action, label]) => actions.append(actionButton(plan, action, label)));
            if (ui.canApprove(plan, userId)) actions.append(actionButton(plan, 'approve',
                plan.status === 'return-reviewed' ? 'Approve return' : 'Approve drain', true));
            if (plan.change_status === 'approved' && ['reviewed', 'return-reviewed'].includes(plan.status)) {
                const returning = plan.status === 'return-reviewed';
                actions.append(actionButton(plan, returning ? 'resume' : 'drain', returning ? 'Return node' : 'Drain node', true));
            }
            if (plan.can_cancel) actions.append(actionButton(plan, 'cancel', 'Cancel plan'));
        }
        section.append(actions);
        const history = node('details');
        history.dataset.maintenanceDetail = 'history';
        history.append(node('summary', 'History'));
        plan.events.forEach(event => history.append(node('p', new Date(event.at).toLocaleString() + ' · ' + event.message)));
        const link = node('a', 'Change #' + plan.change_id);
        link.href = '/changes?change=' + plan.change_id;
        history.append(link);
        section.append(history);
        return section;
    }

    function renderPlans(container, plans) {
        if (plans.length && !container.children.length) container.replaceChildren();
        const ids = new Set(plans.map(plan => plan.id));
        for (const existing of Array.from(container.children)) {
            if (!ids.has(Number(existing.dataset.plan))) {
                snapshots.delete(Number(existing.dataset.plan)); existing.remove();
            }
        }
        plans.forEach(plan => {
            const snapshot = JSON.stringify(plan), existing = container.querySelector('[data-plan="' + plan.id + '"]');
            if (!existing || snapshots.get(plan.id) !== snapshot) {
                const replacement = panel(plan);
                existing?.querySelectorAll('[data-maintenance-detail]').forEach(detail => {
                    const target = replacement.querySelector('[data-maintenance-detail="' + detail.dataset.maintenanceDetail + '"]');
                    if (target) target.open = detail.open;
                });
                if (existing) existing.replaceWith(replacement);
                else container.append(replacement);
                snapshots.set(plan.id, snapshot);
            }
            if (requestedChange === plan.change_id) {
                tabs.tabs('option', 'active', container.id === 'maintenance-history' ? 1 : 0);
                container.querySelector('[data-plan="' + plan.id + '"]').scrollIntoView({block: 'nearest'});
                requestedChange = null;
            }
        });
    }
    function listURL(before) {
        const [provider, cluster] = context.split('/');
        const query = new URLSearchParams({provider, cluster_id: cluster});
        if (before) query.set('before', before);
        if (requestedChange) query.set('change_id', requestedChange);
        return root.dataset.api + '?' + query;
    }
    async function refresh() {
        clearTimeout(timer);
        if (!opened || posting) return;
        if (loading) { refreshAgain = true; return; }
        loading = true;
        const version = generation;
        let interval = 10000;
        try {
            const response = await api(listURL());
            if (version !== generation || !opened) return;
            if (registration !== response.registration_key) {
                if (registration !== null) { form?.reset(); if (el('maintenance-node')) members(); }
                registration = response.registration_key;
                history.clear(); snapshots.clear(); nextBefore = null;
            }
            if (loadError) { message(''); loadError = false; }
            const plans = response.data, active = plans.filter(plan => !['completed', 'cancelled'].includes(plan.status));
            const completed = plans.filter(plan => ['completed', 'cancelled'].includes(plan.status));
            completed.forEach(plan => history.set(plan.id, plan));
            if (history.size <= completed.length) nextBefore = response.next_before;
            renderPlans(el('maintenance-plans'), active);
            renderPlans(el('maintenance-history'), [...history.values()].sort((a, b) => b.id - a.id));
            if (!history.size) el('maintenance-history').textContent = 'No completed or cancelled plans.';
            el('maintenance-more').hidden = !nextBefore;
            if (el('maintenance-new')) el('maintenance-new').hidden = active.length > 0;
            if (plans.some(plan => plan.operation)) interval = 3000;
            else if (plans.some(plan => plan.change_status === 'pending_approval')) interval = 5000;
        } catch (error) {
            if (version === generation && opened) { message(error.message + '. Retrying automatically.'); loadError = true; }
        } finally {
            loading = false;
            if (opened && !posting) {
                if (refreshAgain || version !== generation) { refreshAgain = false; refresh(); }
                else timer = setTimeout(refresh, interval);
            }
        }
    }
    el('maintenance-more').addEventListener('click', async () => {
        if (!nextBefore || moreLoading) return;
        const version = generation, savedRegistration = registration;
        moreLoading = true; el('maintenance-more').disabled = true;
        try {
            const response = await api(listURL(nextBefore));
            if (version !== generation || !opened || registration !== savedRegistration || response.registration_key !== registration) return;
            response.data.filter(plan => ['completed', 'cancelled'].includes(plan.status)).forEach(plan => history.set(plan.id, plan));
            nextBefore = response.next_before;
            renderPlans(el('maintenance-history'), [...history.values()].sort((a, b) => b.id - a.id));
            el('maintenance-more').hidden = !nextBefore;
        } catch (error) { if (version === generation && opened) message(error.message); }
        finally { moreLoading = false; el('maintenance-more').disabled = false; }
    });

    form?.addEventListener('invalid', event => {
        const field = event.target;
        if (field.tagName !== 'SELECT' || !jQuery(field).selectmenu('instance')) return;
        // Selectmenu hides the native control. Keep its required validation, but
        // direct the browser's error and focus to the visible control instead.
        event.preventDefault();
        if (Array.from(form.elements).find(input => input.willValidate && !input.validity.valid) !== field) return;
        invalidSelection = field;
        message('Select a node.');
        jQuery(field).selectmenu('widget').attr({
            'aria-invalid': 'true', 'aria-describedby': 'ha-maintenance-message',
        }).trigger('focus');
    }, true);
    jQuery(form).find('select').on('selectmenuchange change', () => {
        if (!invalidSelection || !invalidSelection.validity.valid) return;
        jQuery(invalidSelection).selectmenu('widget').removeAttr('aria-invalid aria-describedby');
        invalidSelection = null;
        message('');
    });
    form?.addEventListener('submit', event => {
        event.preventDefault();
        const [provider, cluster] = el('maintenance-cluster').value.split('/');
        submit(root.dataset.api, {provider, cluster_id: Number(cluster), server_id: Number(el('maintenance-node').value),
            title: el('maintenance-title').value, capacity_confirmed: el('maintenance-confirm-capacity').checked,
            capacity_evidence: el('maintenance-capacity').value}, 'Creating maintenance plan', el('maintenance-create'));
    });
    window.RoxywiHAMaintenance = {
        open(cluster) {
            const key = cluster.provider + '/' + cluster.id;
            opened = true; generation++; requestedChange = Number(cluster.change) || null;
            if (context !== key) {
                context = key; registration = null; selection++; snapshots.clear(); history.clear(); nextBefore = null;
                form?.reset(); invalidSelection = null;
                el('maintenance-cluster').value = key;
                el('maintenance-plans').replaceChildren(); el('maintenance-history').replaceChildren();
                if (el('maintenance-new')) el('maintenance-new').hidden = true;
                tabs.tabs('option', 'active', 0);
            }
            if (el('maintenance-node')) {
                jQuery(el('maintenance-node')).selectmenu('widget').removeAttr('aria-invalid aria-describedby');
                const selected = el('maintenance-node').value;
                members().then(() => {
                    if (!opened || context !== key) return;
                    if ([...el('maintenance-node').options].some(option => option.value === selected)) {
                        el('maintenance-node').value = selected;
                        jQuery(el('maintenance-node')).selectmenu('refresh');
                    }
                });
            }
            message(''); refresh();
        },
        close() { opened = false; generation++; selection++; clearTimeout(timer); }
    };
    document.addEventListener('visibilitychange', () => { if (!document.hidden && opened) refresh(); });
});
