/* Shared request and confirmation lifecycle for transient Runtime operations. */
window.HaproxyStatsRuntime = function (options) {
    'use strict';
    const {make, get, labels} = options;
    let controller = null, dialog = null;
    const result = (message, error = false) => {
        const element = get('action-result');
        element.hidden = false;
        element.dataset.error = String(error);
        element.textContent = message;
    };
    const request = async (url, body) => {
        const abort = new AbortController();
        controller = abort;
        const timeout = setTimeout(() => abort.abort(), 20000);
        try {
            const response = await fetch(url, {method: body ? 'POST' : 'GET', cache: 'no-store', signal: abort.signal,
                headers: {'Accept': 'application/json', 'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest', ...(body ? {'X-CSRF-TOKEN': csrf_token} : {})},
                ...(body ? {body: JSON.stringify(body)} : {})});
            const data = await response.json();
            if (!response.ok || data.status !== 'ok') throw new Error(response.status === 401 ? 'auth_required' :
                data.code || (response.status === 403 ? 'permission_denied' : 'operation_failed'));
            return data;
        } finally { clearTimeout(timeout); if (controller === abort) controller = null; }
    };
    const confirm = (title, lines) => new Promise(resolve => {
        const element = make('div', 'hs-action-dialog');
        lines.forEach((line, index) => element.append(make('p', index ? 'hs-action-note' : 'hs-action-target', line)));
        document.body.append(element);
        let confirmed = false;
        dialog = element;
        $(element).dialog({modal: true, width: Math.min(520, window.innerWidth - 32), title,
            classes: {'ui-dialog': 'rw-dialog-responsive hs-stats-dialog'},
            buttons: [{text: labels.cancel, click: () => $(element).dialog('close')},
                {text: title, click: () => { confirmed = true; $(element).dialog('close'); }}],
            close: () => { if (dialog === element) dialog = null; $(element).dialog('destroy').remove(); resolve(confirmed); }
        });
    });
    return {request, confirm, result, deactivate() {
        if (controller) controller.abort();
        controller = null;
        if (dialog) $(dialog).dialog('close');
    }};
};
