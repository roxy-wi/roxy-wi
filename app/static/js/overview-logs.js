$(function () {
    'use strict';
    const widget = document.getElementById('overview-logs');
    if (!widget) return;
    const text = JSON.parse(widget.dataset.text);
    const output = document.getElementById('overview-log-output');
    const search = document.getElementById('overview-log-search');
    const expand = document.getElementById('overview-log-expand');
    const status = document.getElementById('overview-log-status');
    const notice = document.getElementById('overview-log-notice');
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    let entries = [], expanded = false, query = '';

    function paint() {
        const fragment = document.createDocumentFragment();
        entries.forEach((entry, index) => {
            const row = RoxyLogViewer.createLogRow(entry, {
                search: search.value, utc: false, timezone, labels: text, showDate: true
            });
            row.hidden = !expanded && index >= 3;
            fragment.appendChild(row);
        });
        output.replaceChildren(fragment);
        expand.hidden = entries.length <= 3;
        expand.textContent = expanded ? expand.dataset.hide : `${expand.dataset.show} (${entries.length})`;
        expand.setAttribute('aria-expanded', String(expanded));
    }

    const follower = new RoxyLogViewer.Follower(() => $.ajax({
        url: '/overview/logs', type: 'GET', data: {search: query},
        dataType: 'json', timeout: 15000, global: false
    }), data => {
        entries = data.entries;
        paint();
        status.textContent = entries.length ? `${entries.length} ${text.rows} · ${timezone}` : text.empty;
        document.getElementById('overview-log-source').textContent = data.source === 'runtime' ? text.all_processes : data.source;
        const link = document.getElementById('overview-log-title');
        const url = new URL(link.href);
        url.searchParams.set('log_file', data.source);
        link.href = url.href;
        const notices = [];
        if (data.limited) notices.push(text.limited);
        if (data.unparsed) notices.push(`${text.unparsed} ${data.unparsed}`);
        notice.textContent = notices.join('\n');
        notice.hidden = !notices.length;
        widget.setAttribute('aria-busy', 'false');
    }, () => {
        status.textContent = text.failed;
        widget.setAttribute('aria-busy', 'false');
    });

    function refresh() {
        query = search.value;
        entries = [];
        expanded = false;
        paint();
        notice.hidden = true;
        status.textContent = text.loading;
        widget.setAttribute('aria-busy', 'true');
        follower.start(false, true);
    }
    document.getElementById('overview-log-form').addEventListener('submit', event => {
        event.preventDefault();
        refresh();
    });
    search.addEventListener('input', () => {
        follower.stop();
        widget.setAttribute('aria-busy', 'false');
        status.textContent = text.paused;
        paint();
    });
    expand.addEventListener('click', () => { expanded = !expanded; paint(); });
    window.addEventListener('pagehide', () => follower.stop());
    refresh();
});
