/* Cluster-scoped audit dialog. Closing it never cancels a queued operation. */
document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('ha-readiness');
    if (!root) return;
    const el = id => document.getElementById(id), role = Number(root.dataset.role);
    const tabs = jQuery('#ha-readiness-tabs').tabs(), reports = new Map(), requests = new Set();
    let revision = 0, reportId = null, selectedReport = null, timer, sequence = 0, generation = 0;
    let testRecords = [], dirty = false, editVersion = 0, context = null, registration = null;
    let opened = false, pending = false, nextBefore = null, moreLoading = false;
    let renderedReport = null, renderedHistory = null, renderedDomains = null;
    const kinds = ['hypervisor', 'power', 'uplink', 'storage'];
    const element = (tag, text) => {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        return node;
    };
    const base = () => root.dataset.api + '/' + el('ha-audit-cluster').value;
    const message = (text, busy = pending || requests.has(base()), disabled = false) => {
        RoxywiUI.operationStatus(el('ha-audit-message'), el('ha-audit-run'), text, busy, disabled);
    };
    async function api(url, body) {
        try {
            return await jQuery.ajax({url, method: body === undefined ? 'GET' : 'POST', contentType: 'application/json',
                global: false, data: body === undefined ? undefined : JSON.stringify(body)});
        } catch (error) {
            throw new Error(error.responseJSON?.error || 'Assessment request failed');
        }
    }
    function display(item = {}) {
        const report = item.report;
        reportId = report ? item.id : null;
        const snapshot = JSON.stringify([item.id, report, item.error, testRecords]);
        if (snapshot === renderedReport) return;
        renderedReport = snapshot;
        el('ha-audit-checks').replaceChildren();
        el('ha-audit-tests').replaceChildren();
        el('ha-audit-time').textContent = report ? 'Observed ' + new Date(report.observed_at).toLocaleString() : '';
        el('ha-audit-time').title = report ? 'Audit #' + item.id : '';
        el('ha-audit-verification').textContent = 'Last automatically verified HA test: ' +
            (report?.last_verified_test ? JSON.stringify(report.last_verified_test) : 'unknown');
        if (!report) {
            if (item.error) {
                const row = element('tr'), cell = element('td', `Audit #${item.id}: ${item.error}`);
                cell.colSpan = 3; row.append(cell); el('ha-audit-checks').append(row);
            }
            return;
        }
        report.checks.forEach(check => {
            const row = element('tr'), detail = element('td', check.message), more = element('details');
            more.append(element('summary', 'Observed details'), element('pre', JSON.stringify(check.evidence, null, 2)));
            detail.append(more);
            row.append(element('td', check.key), detail, element('td', check.state));
            el('ha-audit-checks').append(row);
        });
        testRecords.forEach(test => el('ha-audit-tests').append(element('p',
            `${test.kind}: ${test.result} · ${new Date(test.tested_at).toLocaleString()} · operator attestation · ${test.fingerprint === report.fingerprint ? 'matching configuration' : 'configuration changed'} · ${test.note}`)));
    }
    function history() {
        const list = el('ha-audit-history');
        el('ha-audit-more').hidden = !nextBefore;
        const items = [...reports.values()].sort((a, b) => b.id - a.id);
        const snapshot = JSON.stringify(items.map(item => [item.id, item.status, item.error, Boolean(item.report)]));
        if (snapshot === renderedHistory) return;
        renderedHistory = snapshot;
        list.replaceChildren();
        if (!reports.size) list.append(element('p', 'No audits yet.'));
        items.forEach(item => {
            const button = element('button', `#${item.id} · ${new Date(item.created_at).toLocaleString()} · ${item.status}`);
            button.type = 'button'; button.className = 'rw-button rw-button-secondary';
            button.disabled = !item.report && !item.error;
            button.addEventListener('click', () => {
                selectedReport = item.id; display(item); tabs.tabs('option', 'active', 0);
                if (!pending) message(`Audit #${item.id}: ${item.status}.`);
            });
            list.append(button);
        });
    }
    function domains(profile) {
        if (dirty) return;
        const snapshot = JSON.stringify([profile.registration_key, profile.revision, profile.nodes, profile.domains]);
        if (snapshot === renderedDomains) return;
        renderedDomains = snapshot;
        revision = profile.revision;
        const nodes = el('ha-audit-nodes');
        nodes.replaceChildren();
        profile.nodes.forEach(node => {
            const section = element('fieldset');
            section.dataset.server = node.id; section.append(element('legend', node.name));
            kinds.forEach(kind => {
                const field = element('div'), label = element('label', kind), input = element('input');
                field.className = 'rw-form-field'; input.id = `ha-domain-${node.id}-${kind}`; label.htmlFor = input.id;
                input.className = 'form-control'; input.maxLength = 128; input.dataset.kind = kind;
                input.value = (profile.domains[String(node.id)] || {})[kind] || ''; input.disabled = role > 2;
                field.append(label, input); section.append(field);
            });
            nodes.append(section);
        });
    }
    async function refresh() {
        clearTimeout(timer);
        if (!opened) return;
        const version = ++sequence;
        try {
            const data = await api(base());
            if (version !== sequence || !opened) return;
            if (registration !== data.profile.registration_key) {
                dirty = false; editVersion++; registration = data.profile.registration_key;
                reports.clear(); selectedReport = null;
            }
            testRecords = data.profile.attestations; domains(data.profile);
            data.assessments.forEach(item => reports.set(item.id, item));
            // Keep older pages and a selected historical report during background updates.
            if (reports.size <= data.assessments.length) nextBefore = data.next_before;
            history();
            display(reports.get(selectedReport) || data.assessments.find(item => item.report));
            const active = data.assessments.find(item => ['created', 'published', 'running'].includes(item.status));
            pending = Boolean(active);
            const latest = active || reports.get(selectedReport) || data.assessments[0];
            const status = latest && ['created', 'published'].includes(latest.status) ? 'queued, waiting for a worker' : latest?.status;
            message(latest ? `Audit #${latest.id}: ${status}${latest.error ? ' — ' + latest.error : '.'}` : 'Ready to run an audit.');
            if (pending || requests.has(base())) timer = setTimeout(refresh, 3000);
        } catch (error) {
            if (version !== sequence || !opened) return;
            message('Unable to refresh audit status: ' + error.message, false, pending);
            timer = setTimeout(refresh, 5000);
        }
    }
    el('ha-audit-nodes').addEventListener('input', () => { dirty = true; editVersion++; });
    el('ha-audit-run')?.addEventListener('click', async () => {
        const url = base(), version = generation;
        if (pending || requests.has(url)) return;
        requests.add(url); sequence++; clearTimeout(timer); selectedReport = null;
        message('Starting readiness audit…');
        let failed = false;
        try {
            const data = await api(url + '/run', {});
            if (version !== generation || !opened) return;
            pending = true; message(`Audit #${data.id}: queued, waiting for a worker…`);
        } catch (error) {
            failed = true;
            if (version === generation && opened) message(error.message, false);
        } finally {
            requests.delete(url);
            if (opened && base() === url && (!failed || version !== generation)) refresh();
        }
    });
    el('ha-audit-more').addEventListener('click', async () => {
        if (!nextBefore || moreLoading) return;
        const version = generation; moreLoading = true; el('ha-audit-more').disabled = true;
        try {
            const data = await api(base() + '?before=' + nextBefore);
            if (version !== generation || !opened) return;
            data.assessments.forEach(item => reports.set(item.id, item)); nextBefore = data.next_before; history();
        } catch (error) { if (version === generation && opened) message(error.message); }
        finally { moreLoading = false; el('ha-audit-more').disabled = false; }
    });
    el('ha-audit-domains').addEventListener('submit', async event => {
        event.preventDefault();
        const values = {}, version = generation, savedVersion = editVersion, savedRegistration = registration;
        root.querySelectorAll('[data-server]').forEach(node => {
            values[node.dataset.server] = {};
            node.querySelectorAll('[data-kind]').forEach(input => { values[node.dataset.server][input.dataset.kind] = input.value; });
        });
        try {
            const result = await api(base() + '/profile', {revision, domains: values, registration_key: registration});
            if (version !== generation || !opened || registration !== savedRegistration) return;
            revision = result.profile.revision;
            if (savedVersion === editVersion) dirty = false;
            await refresh();
        } catch (error) { if (version === generation && opened) message(error.message); }
    });
    el('ha-audit-attest')?.addEventListener('submit', async event => {
        event.preventDefault();
        if (!reportId) { message('Select a completed audit first.'); return; }
        const version = generation;
        try {
            await api(base() + '/attest', {kind: el('ha-test-kind').value, result: el('ha-test-result').value,
                tested_at: new Date(el('ha-test-at').value).toISOString(), note: el('ha-test-note').value, assessment_id: reportId});
            if (version === generation && opened) await refresh();
        } catch (error) { if (version === generation && opened) message(error.message); }
    });
    window.RoxywiHAReadiness = {
        open(cluster) {
            const key = cluster.provider + '/' + cluster.id;
            opened = true; generation++;
            if (context !== key) {
                context = key; registration = null; dirty = false; editVersion++; pending = false; renderedDomains = null;
                reports.clear(); selectedReport = null; nextBefore = null;
                el('ha-audit-cluster').value = key; el('ha-audit-nodes').replaceChildren();
                el('ha-audit-attest')?.reset(); testRecords = []; display(); history();
                tabs.tabs('option', 'active', 0);
            }
            message('Loading audit history…', false, true); refresh();
        },
        close() { opened = false; generation++; sequence++; clearTimeout(timer); }
    };
});
