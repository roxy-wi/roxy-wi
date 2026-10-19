$(function () {
    'use strict';
    const widget = document.getElementById('overview-logs');
    if (!widget) return;
    const text = JSON.parse(widget.dataset.text);
    const output = document.getElementById('overview-log-output');
    const expand = document.getElementById('overview-log-expand');
    const status = document.getElementById('overview-log-status');
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    let entries = [], expanded = false;

    function paint() {
        const fragment = document.createDocumentFragment();
        entries.forEach((entry, index) => {
            const row = RoxyLogViewer.createLogRow(entry, {
                utc: false, timezone, labels: text, showDate: true
            });
            row.hidden = !expanded && index >= 3;
            fragment.appendChild(row);
        });
        output.replaceChildren(fragment);
        expand.hidden = entries.length <= 3;
        expand.textContent = expanded ? expand.dataset.hide : expand.dataset.show;
        expand.setAttribute('aria-expanded', String(expanded));
    }

    const follower = new RoxyLogViewer.Follower(() => $.ajax({
        url: '/overview/logs', type: 'GET',
        dataType: 'json', timeout: 15000, global: false
    }), data => {
        entries = data.entries;
        paint();
        status.textContent = entries.length ? '' : text.empty;
        status.hidden = entries.length > 0;
        const link = document.getElementById('overview-log-title');
        const url = new URL(link.href);
        url.searchParams.set('log_file', data.source);
        link.href = url.href;
        widget.setAttribute('aria-busy', 'false');
    }, () => {
        status.textContent = text.failed;
        status.hidden = false;
        widget.setAttribute('aria-busy', 'false');
    });

    function refresh() {
        entries = [];
        expanded = false;
        paint();
        status.textContent = text.loading;
        status.hidden = false;
        widget.setAttribute('aria-busy', 'true');
        follower.start(false, true);
    }
    document.getElementById('overview-log-refresh').addEventListener('click', refresh);
    expand.addEventListener('click', () => { expanded = !expanded; paint(); });
    window.addEventListener('pagehide', () => follower.stop());
    refresh();
});
