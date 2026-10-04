$(function () {
    'use strict';
    const root = document.getElementById('service-diagnostics');
    if (!root) return;
    const content = root.querySelector('.sd-content');
    let request = null, generation = 0, url = '', trigger = null;
    function cancel() {
        generation += 1;
        if (request) request.abort();
        request = null;
    }
    function refresh() {
        cancel();
        const current = generation;
        content.textContent = root.dataset.loading;
        content.setAttribute('aria-busy', 'true');
        request = $.ajax({url, dataType: 'html', timeout: 15000, global: false})
            .done(html => {
                if (current !== generation) return;
                $(content).html(html);
                content.querySelectorAll('time[datetime]').forEach(node => {
                    const date = new Date(node.dateTime);
                    if (!Number.isNaN(date.getTime())) node.textContent = date.toLocaleString();
                });
            })
            .fail((_xhr, status) => {
                if (current === generation && status !== 'abort') content.textContent = root.dataset.failed;
            })
            .always(() => {
                if (current === generation) { request = null; content.setAttribute('aria-busy', 'false'); }
            });
    }
    const dialog = $(root).dialog({
        autoOpen: false, modal: true, resizable: false, width: Math.min(880, window.innerWidth - 32),
        maxHeight: window.innerHeight - 40,
        close() { cancel(); if (trigger && trigger.isConnected) trigger.focus(); }
    });
    root.hidden = false;
    $(document).on('click', '.service-diagnostics-trigger', function () {
        trigger = this;
        url = this.dataset.diagnosticsUrl;
        dialog.dialog('option', 'title', `${root.dataset.title}: ${this.dataset.serviceName}`);
        dialog.dialog('open');
        refresh();
    });
    root.querySelector('.sd-refresh').addEventListener('click', refresh);
    $(root).on('click', '.sd-admin-link', function (event) {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.which > 1) return;
        const destination = new URL(this.href);
        const tab = Array.from(document.querySelectorAll('#admin-tabs a'))
            .find(link => link.hash === destination.hash);
        if (destination.origin !== window.location.origin || destination.pathname !== window.location.pathname || !tab) return;
        event.preventDefault();
        dialog.dialog('close');
        window.history.replaceState(null, '', destination.href);
        tab.click();
        // The selected tab may already be active, so give it focus explicitly.
        if (destination.hash !== '#servers') tab.focus();
    });
    window.addEventListener('resize', () => {
        dialog.dialog('option', {width: Math.min(880, window.innerWidth - 32), maxHeight: window.innerHeight - 40});
    });
    window.addEventListener('pagehide', cancel);
});
