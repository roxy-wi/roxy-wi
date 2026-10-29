/* Shared SSL page: certificate material is never stored in browser storage. */
$(function () {
    const root = $('#runtime-certificates');
    if (!root.length) return;
    const text = JSON.parse(root.attr('data-strings'));
    const translate = key => text[key] || text.operation_failed;
    const server = $('#cert-server');
    const service = root.attr('data-service');
    const hasRuntime = service === 'haproxy';
    const addLabel = root.attr('data-add-label'), historyLabel = root.attr('data-history-label');
    const usesRuntime = () => Boolean(current) || (hasRuntime && $('#cert-upload-mode').val() === 'runtime');
    const base = '/service/' + encodeURIComponent(service) + '/certificates/';
    let rows = [], destinations = [], canCreate = false, catalogReady = false, createError = '', generation = 0, listRequest, pollTimer, previewTimer, previewRequest;
    let current, dialogAddress, dialogServer, dialogDestinations = [], validPem = '', operationId, previewGeneration = 0;
    let submitting = false, fileGeneration = 0;
    let historyPage = 1, historyRequest, historyGeneration = 0, historyTimer;
    const active = operation => ['created', 'published', 'running'].includes(operation.status);
    const historyOpen = () => $('#cert-history-dialog').hasClass('ui-dialog-content') && $('#cert-history-dialog').dialog('isOpen');
    const format = (template, values) => template.replace(/\{(\w+)\}/g, (_, key) => values[key]);
    const errorText = xhr => {
        const code = xhr.responseJSON?.error_code || 'operation_failed';
        return translate(code === 'not_loaded' ? 'not_loaded_error' : code);
    };
    const date = value => value ? new Date(value).toLocaleDateString(document.documentElement.lang) : '—';
    const icon = name => $('<span>', {class: 'fas fa-' + name, 'aria-hidden': 'true'});
    const button = (label, name, action, disabled = false, reason = '') => $('<button>', {
        type: 'button', role: 'menuitem', class: 'admin-action-item', 'aria-label': label, title: disabled ? reason : ''})
        .append(icon(name), document.createTextNode(' ' + label)).prop('disabled', disabled).on('click', action);
    function icons(node) { if (node && window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node}); }
    const summary = item => (item.domains || []).join(', ') + ' · ' + date(item.not_after) +
        (item.fingerprint ? ' · ' + item.fingerprint_algorithm + ': ' + item.fingerprint : '');

    function createButton() {
        $('#cert-add').button({disabled: !server.val() || !catalogReady});
        $('#cert-history').button({disabled: !server.val()});
    }

    function openHistory() {
        historyPage = 1;
        $('#cert-operations, #cert-history-range, #cert-history-page').empty();
        $('#cert-history-server').text(server.find('option:selected').text());
        $('#cert-history-dialog').prop('hidden', false).dialog({modal: true,
            classes: {'ui-dialog': 'rw-dialog-responsive'}, width: Math.min(1050, window.innerWidth - 32),
            maxHeight: window.innerHeight - 32, title: historyLabel,
            close() {
                ++historyGeneration; clearTimeout(historyTimer);
                if (historyRequest) historyRequest.abort();
            },
            buttons: [{text: text.close, click() { $(this).dialog('close'); }}]});
        $('#cert-history-size').selectmenu({width: 80}).selectmenu('refresh');
        loadHistory();
    }

    function fileAction(item, remove = false) {
        const selected = server.val();
        const url = base + selected + '/file/' + encodeURIComponent(item.file_token);
        const dialog = $('#cert-details-dialog').empty().prop('hidden', false);
        dialog.append($('<p>').text(item.path), $('<pre>', {role: 'status'}).text(remove ? text.delete_confirm : text.loading));
        const status = dialog.find('pre');
        let busy = false;
        dialog.dialog({modal: true, classes: {'ui-dialog': 'rw-dialog-responsive'}, width: Math.min(700, window.innerWidth - 32),
            title: item.name, beforeClose: () => !busy, close() { status.empty(); },
            buttons: [{text: text.close, click() { $(this).dialog('close'); }}, ...(remove ? [{text: text.delete, click() {
                if (busy) return;
                busy = true;
                $(this).dialog('widget').find('.ui-dialog-buttonpane button').prop('disabled', true);
                $.ajax({url, method: 'DELETE', global: false, contentType: 'application/json', data: JSON.stringify({revision: item.revision})})
                    .done(() => { busy = false; dialog.dialog('close'); load(); })
                    .fail(xhr => { busy = false; status.text(errorText(xhr)); dialog.dialog('widget').find('.ui-dialog-buttonpane button').prop('disabled', false); });
            }}] : [])]});
        if (!remove) $.ajax({url, global: false}).done(data => {
            if (dialog.dialog('isOpen')) status.text((item.disk ? summary(item.disk) + '\n\n' : '') + data.content);
        }).fail(xhr => status.text(errorText(xhr)));
    }

    function renderRows() {
        const body = $('#cert-list').empty();
        const search = $('#cert-search').val().toLowerCase();
        for (const item of rows.filter(row => (row.name + ' ' + row.path + ' ' + row.domains.join(' ')).toLowerCase().includes(search))) {
            const menu = $('<div>', {class: 'admin-actions-menu', role: 'menu', hidden: true}).append(
                button(text.details, 'info-circle', () => {
                    const dialog = $('#cert-details-dialog').empty().prop('hidden', false);
                    dialog.append($('<p>').text(item.path));
                    if (hasRuntime) dialog.append(
                        $('<p>').text(text.in_haproxy + ': ' + translate(item.runtime_status)),
                        $('<pre>').text(item.runtime ? summary(item.runtime) : '—'));
                    dialog.append($('<p>').text(text.on_disk + ': ' + translate(item.disk_status)),
                        $('<pre>').text(item.disk ? summary(item.disk) : '—'));
                    dialog.dialog({modal: true, classes: {'ui-dialog': 'rw-dialog-responsive'}, width: Math.min(700, window.innerWidth - 32), title: item.name,
                        buttons: [{text: text.close, click() { $(this).dialog('close'); }}]});
                }), button(text.view, 'eye', () => fileAction(item), !item.can_view, text.invalid_path),
                ...(hasRuntime ? [button(text.update, 'edit', () => openUpdate(item), !item.can_update, translate(item.update_error))] : []),
                button(text.delete, 'trash-alt', () => fileAction(item, true), !item.can_delete, translate(item.delete_error)));
            const actions = $('<div>', {class: 'admin-actions'}).append(
                $('<button>', {type: 'button', class: 'rw-icon-button admin-actions-toggle',
                    'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-label': text.actions})
                    .append($('<span>', {class: 'fas fa-ellipsis-v', 'aria-hidden': 'true'})), menu);
            body.append($('<tr>').append($('<td>', {class: 'padding10 first-collumn', title: item.path}).text(item.name),
                $('<td>', {class: 'padding10'}).text(item.domains.join(', ')), $('<td>', {class: 'padding10'}).text(date(item.not_after)),
                ...(hasRuntime ? [$('<td>', {class: 'padding10'}).text(translate(item.runtime_status))] : []),
                $('<td>', {class: 'padding10'}).text(translate(item.disk_status)),
                $('<td>', {class: 'admin-actions-cell'}).append(actions)));
        }
        if (!body.children().length) body.append($('<tr>').append($('<td>', {colspan: hasRuntime ? 6 : 5, class: 'padding10'}).text(text.empty)));
        if (window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node: body[0]});
    }

    function renderOperations(operations) {
        const container = $('#cert-operations').empty();
        const headings = container.closest('table').find('th').map(function () { return $(this).text(); }).get();
        const badge = status => $('<span>', {class: 'rw-status-badge rw-status-' + (
            ['completed', 'applied'].includes(status) ? 'running' : status === 'failed' ? 'stopped' :
                ['created', 'published', 'running', 'pending', 'applying'].includes(status) ? 'unavailable' : 'stale')}).text(translate(status));
        for (const operation of operations) {
            const when = $('<div>', {class: 'rw-form-field'}).append($('<strong>').text('#' + operation.id),
                $('<time>', {datetime: operation.started_at}).text(operation.started_at ? new Date(operation.started_at).toLocaleString(document.documentElement.lang) : '—'));
            const certificate = $('<div>', {class: 'rw-form-field'}).append($('<strong>').text(operation.name),
                $('<span>', {class: 'rw-form-help'}).text(translate(operation.action)));
            const status = $('<div>', {class: 'rw-form-field'}).append(badge(operation.status));
            if (operation.finished_at) status.append($('<time>', {class: 'rw-form-help', datetime: operation.finished_at,
                title: text.history_finished}).text(new Date(operation.finished_at).toLocaleString(document.documentElement.lang)));
            if (operation.error_code) status.append($('<p>', {class: 'rw-form-help'}).text(translate(operation.error_code)));
            if (operation.retryable) status.append(button(text.recover, 'redo', function () {
                $(this).prop('disabled', true);
                $.ajax({url: base + 'operations/' + operation.id, method: 'POST', global: false})
                    .done(() => load()).fail(xhr => {
                        $(this).prop('disabled', false); $('#cert-history-message').text(errorText(xhr));
                    });
            }).removeClass('admin-action-item').removeAttr('role').addClass('ui-button ui-widget ui-corner-all'));
            const targets = $('<div>', {class: 'rw-form-field'});
            for (const target of operation.targets) {
                const targetLine = $('<div>').append($('<strong>').text(target.address), document.createTextNode(' '), badge(target.status));
                if (target.error_code) targetLine.append($('<p>', {class: 'rw-form-help'}).text(translate(target.error_code)));
                targets.append(targetLine);
            }
            container.append($('<tr>', {'data-operation-id': operation.id}).append([when, certificate, status, targets].map((content, index) =>
                $('<td>', {class: 'padding10', 'data-label': headings[index]}).append(content))));
        }
        if (!operations.length) container.append($('<tr>').append($('<td>', {colspan: 4, class: 'padding10'}).text(text.no_operations)));
        icons(container[0]);
    }

    function loadHistory(page = historyPage, quiet = false) {
        if (!hasRuntime || !historyOpen()) return;
        const selected = server.val(), requestGeneration = ++historyGeneration;
        clearTimeout(historyTimer);
        if (historyRequest) historyRequest.abort();
        $('#cert-history-prev, #cert-history-next, #cert-history-refresh').button({disabled: true});
        $('#cert-history-message').text(quiet ? '' : text.loading);
        $('#cert-operations').attr('aria-busy', 'true');
        historyRequest = $.ajax({url: base + selected + '/history', global: false,
            data: {page, per_page: $('#cert-history-size').val()}})
            .done(data => {
                if (requestGeneration !== historyGeneration) return;
                historyPage = data.page;
                renderOperations(data.operations);
                if (!quiet) $('#cert-operations').closest('.rw-table-shell').scrollTop(0);
                $('#cert-history-message').empty();
                $('#cert-history-range').text(format(text.history_range, {
                    first: data.total ? (data.page - 1) * data.per_page + 1 : 0,
                    last: Math.min(data.page * data.per_page, data.total), total: data.total}));
                $('#cert-history-page').text(format(text.history_page, {page: data.page, pages: data.pages}));
                $('#cert-history-prev').button('option', 'disabled', data.page <= 1);
                $('#cert-history-next').button('option', 'disabled', data.page >= data.pages);
                $('#cert-history-dialog').dialog('option', {maxHeight: window.innerHeight - 32,
                    position: {my: 'center', at: 'center', of: window}});
                if (data.operations.some(active)) historyTimer = setTimeout(() => loadHistory(historyPage, true), 3000);
            }).fail(xhr => {
                if (xhr.statusText !== 'abort' && requestGeneration === historyGeneration) $('#cert-history-message').text(errorText(xhr));
            }).always(() => {
                if (requestGeneration !== historyGeneration) return;
                $('#cert-history-refresh').button('option', 'disabled', false);
                $('#cert-operations').attr('aria-busy', 'false');
            });
    }

    function monitorOperations(operations) {
        const pending = operations.filter(active);
        if (pending.length) {
            const currentGeneration = generation;
            pollTimer = setTimeout(() => {
                Promise.all(pending.map(operation => $.ajax({url: base + 'operations/' + operation.id, global: false})))
                    .then(results => {
                        if (currentGeneration !== generation) return;
                        if (results.some(active)) monitorOperations(results);
                        else load();
                    }).catch(xhr => { if (currentGeneration === generation) $('#cert-message').text(errorText(xhr)); });
            }, 3000);
        }
    }

    function load() {
        clearTimeout(pollTimer);
        const selected = server.val(), requestGeneration = ++generation;
        if (listRequest) listRequest.abort();
        destinations = []; canCreate = false; catalogReady = false; createError = ''; createButton();
        if (!selected || selected === '------') {
            rows = []; renderRows(); $('#cert-operations').empty(); $('#cert-message').text(text.select_server); return;
        }
        rows = []; renderRows();
        $('#cert-message').text(text.loading);
        listRequest = $.ajax({url: base + encodeURIComponent(selected), global: false})
            .done(data => {
                if (requestGeneration !== generation) return;
                rows = data.certificates; renderRows(); monitorOperations(data.operations || []);
                if (!historyRequest || historyRequest.readyState === 4) loadHistory();
                destinations = data.destinations || []; canCreate = Boolean(data.can_create);
                catalogReady = true;
                createError = data.runtime_error ? '' : data.create_error ? translate(data.create_error) : !destinations.length ? text.no_destinations : '';
                createButton();
                if ($('#cert-update-dialog').hasClass('ui-dialog-content') && $('#cert-update-dialog').dialog('isOpen') && !submitting) modeChanged();
                $('#cert-message').text(data.runtime_error ? translate(data.runtime_error) : '');
            }).fail(xhr => {
                if (xhr.statusText !== 'abort' && requestGeneration === generation) $('#cert-message').text(errorText(xhr));
            });
    }

    function applyButton(enabled) {
        const name = $('#cert-new-name').val().trim();
        const validName = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(name);
        const validDestination = dialogDestinations[Number($('#cert-destination').val())];
        const runtime = usesRuntime();
        const valid = current ? enabled : validName && (runtime ? enabled && canCreate && $('#new-cert-file-type').val() === 'pem' && validDestination : $('#cert-pem').val().trim());
        $('#cert-update-dialog').dialog('widget').find('[data-cert-apply]').button('option', 'disabled', submitting || !valid);
    }

    function modeChanged() {
        const runtime = usesRuntime(), pem = $('#new-cert-file-type').val() === 'pem';
        $('[data-cert-destination]').prop('hidden', !runtime);
        $('#cert-upload-hint').text(runtime ? text.sync_hint : text.disk_hint);
        $('#cert-create-help').text(runtime ? (!pem ? text.pem_required : createError) : '');
        $('#cert-upload-mode option[value="runtime"]').prop('disabled', !canCreate);
        $('#cert-upload-mode').selectmenu('refresh');
        preview();
    }

    function preview() {
        clearTimeout(previewTimer);
        const version = ++previewGeneration;
        if (previewRequest) previewRequest.abort();
        validPem = ''; operationId = null; applyButton(false);
        const pem = $('#cert-pem').val();
        if (!usesRuntime()) { $('[data-cert-preview]').empty(); applyButton(true); return; }
        if (!pem.trim()) { $('[data-cert-preview]').empty(); return; }
        if (new Blob([pem]).size > 1024 * 1024) { $('[data-cert-preview]').text(text.invalid_pem); return; }
        $('[data-cert-preview]').text(text.checking);
        previewTimer = setTimeout(() => {
            previewRequest = $.ajax({url: base + dialogServer + '/preview', method: 'POST', global: false,
                contentType: 'application/json', data: JSON.stringify({pem})})
                .done(data => {
                    if (version !== previewGeneration) return;
                    validPem = pem; operationId = crypto.randomUUID();
                    $('[data-cert-preview]').text(text.new_certificate + ': ' + summary(data));
                    applyButton(true);
                }).fail(xhr => {
                    if (xhr.statusText !== 'abort' && version === previewGeneration) $('[data-cert-preview]').text(errorText(xhr));
                });
        }, 350);
    }

    function openUpdate(item = null) {
        current = item; dialogServer = server.val(); dialogAddress = server.find('option:selected').attr('data-address');
        validPem = ''; operationId = null; submitting = false;
        dialogDestinations = destinations.slice();
        const dialog = $('#cert-update-dialog').prop('hidden', false);
        dialog.find('input, textarea, select').prop('disabled', false);
        $('#cert-pem, #cert-pem-file, #cert-new-name').val(''); $('[data-cert-preview]').empty();
        $('[data-cert-create]').prop('hidden', Boolean(item));
        $('[data-cert-current]').prop('hidden', !item).text(item ? text.current_certificate + ': ' + item.path + ' · ' + summary(item.disk || item) : '');
        $('#new-cert-file-type').val('pem'); $('#cert-upload-mode').val('disk');
        $('#cert-destination').empty().append(dialogDestinations.map((destination, index) =>
            $('<option>', {value: index}).text(translate(destination.kind) + ' · ' + destination.path)));
        dialog.find('select').selectmenu({width: '100%'}).selectmenu('refresh');
        dialog.dialog({modal: true, classes: {'ui-dialog': 'rw-dialog-responsive'}, width: Math.min(760, window.innerWidth - 32), title: item ? text.update : addLabel,
            beforeClose: () => !submitting,
            close() {
                ++previewGeneration; ++fileGeneration; clearTimeout(previewTimer);
                if (previewRequest) previewRequest.abort();
                validPem = ''; $('#cert-pem, #cert-pem-file').val(''); $('[data-cert-preview]').empty();
            },
            buttons: [{text: text.close, click() { $(this).dialog('close'); }},
                {text: item ? text.save_apply : addLabel, class: item ? '' : 'add-button', 'data-cert-apply': true, disabled: true, click: submit}]});
        dialog.dialog('widget').find('[data-cert-apply]').prepend(icon(item ? 'save' : 'plus'), document.createTextNode(' '));
        icons(dialog.dialog('widget')[0]);
        modeChanged();
    }

    function submit() {
        if (submitting) return;
        const runtime = usesRuntime(), pem = $('#cert-pem').val(), type = $('#new-cert-file-type').val();
        if (runtime && (!validPem || validPem !== pem)) return;
        let name = $('#cert-new-name').val().trim();
        if (name.endsWith('.' + type)) name = name.slice(0, -(type.length + 1));
        let url = base + dialogServer + '/upload', body = {server_ip: dialogAddress, name, cert: pem, cert_type: type};
        if (runtime) {
            body = {pem: validPem, operation_id: operationId};
            if (current) Object.assign(body, {name: current.name, revision: current.revision, directory: current.directory});
            else Object.assign(body, {name: name + '.pem', destination: dialogDestinations[Number($('#cert-destination').val())]});
            url = base + dialogServer + (current ? '' : '/new');
        }
        const dialog = $('#cert-update-dialog');
        const controls = dialog.find('input, textarea, select');
        submitting = true; applyButton(false); controls.prop('disabled', true); dialog.find('select').selectmenu('refresh');
        $.ajax({url, method: 'POST', global: false, contentType: 'application/json', data: JSON.stringify(body)})
            .done(() => { submitting = false; dialog.dialog('close'); load(); if (runtime) openHistory(); })
            .fail(xhr => { submitting = false; controls.prop('disabled', false); dialog.find('select').selectmenu('refresh');
                applyButton(Boolean(validPem)); $('[data-cert-preview]').text(errorText(xhr)); });
    }

    $('#cert-pem').on('input', () => { ++fileGeneration; preview(); });
    $('#cert-new-name, #cert-destination').on('input change selectmenuchange', () => {
        operationId = crypto.randomUUID(); applyButton(Boolean(validPem) && !submitting);
    });
    $('#cert-add').on('click', () => { if (server.val()) openUpdate(); });
    $('#cert-history').on('click', openHistory);
    $('#cert-history-prev').on('click', () => loadHistory(historyPage - 1));
    $('#cert-history-next').on('click', () => loadHistory(historyPage + 1));
    $('#cert-history-refresh').on('click', () => loadHistory());
    $('#cert-history-size').on('change selectmenuchange', () => loadHistory(1));
    $('#cert-upload-mode, #new-cert-file-type').on('selectmenuchange change', modeChanged);
    $('#cert-pem-file').on('change', async function () {
        const version = ++fileGeneration;
        const file = this.files[0];
        if (!file) return;
        ++previewGeneration; clearTimeout(previewTimer);
        if (previewRequest) previewRequest.abort();
        validPem = ''; operationId = null; applyButton(false);
        if (file.size > 1024 * 1024) { $('[data-cert-preview]').text(text.invalid_pem); return; }
        try {
            const contents = await file.text();
            if (version === fileGeneration) { $('#cert-pem').val(contents); preview(); }
        } catch (_) { if (version === fileGeneration) $('[data-cert-preview]').text(text.invalid_pem); }
    });
    server.on('selectmenuchange change', () => {
        if ($('#cert-history-dialog').hasClass('ui-dialog-content')) $('#cert-history-dialog').dialog('close');
        load();
    });
    root.on('certificates:refresh', load);
    $('#cert-refresh').on('click', load);
    $('#cert-search').on('input', renderRows);
    load();
});
