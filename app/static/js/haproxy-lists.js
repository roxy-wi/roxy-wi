(function (window, $) {
    'use strict';
    $(function () {
        const root = $('#haproxy-lists');
        if (!root.length) return;
        const labels = JSON.parse(document.getElementById('haproxy-lists-language').textContent);
        const text = key => labels[key] || key;
        const editor = $('#lists-editor');
        let snapshot = null, editingServer = '', busy = false, generation = 0, dialogGeneration = 0;
        const endpoint = server => '/add/haproxy/lists/' + encodeURIComponent(server);
        function fitDialog() {
            if (!editor.dialog('isOpen')) return;
            editor.dialog('option', {height: 'auto', maxHeight: window.innerHeight - 32,
                width: Math.min(850, window.innerWidth - 32), position: {my: 'center', at: 'center', of: window}});
        }
        function disable(elements, value) {
            elements.prop('disabled', value).each(function () {
                if ($(this).is('button') && $(this).button('instance')) $(this).button('option', 'disabled', value);
            });
        }
        function message(element, value, error) {
            element.text(value || '').toggleClass('lists-error', !!error);
        }
        function errorMessage(xhr) {
            const data = xhr.responseJSON || {};
            if (data.code) return text(data.code);
            if (data.validation_error) {
                const errors = data.validation_error.body_params || data.validation_error;
                if (Array.isArray(errors)) return errors.map(item => item.msg).join('\n');
            }
            return RoxywiUI.parseResponse(data.error || xhr.responseText || text('failed')).summary;
        }
        function results(nodes) {
            const box = $('#lists-results').empty();
            if (!nodes || !nodes.length) return;
            const table = $('<table class="overview"></table>').appendTo(box);
            const head = $('<tr></tr>').appendTo($('<thead></thead>').appendTo(table));
            ['server', 'file', 'runtime'].forEach(key => $('<th></th>').text(text(key)).appendTo(head));
            const body = $('<tbody></tbody>').appendTo(table);
            nodes.forEach(node => {
                const row = $('<tr></tr>').appendTo(body);
                [node.server, text(node.file), text(node.runtime)].forEach(value => $('<td></td>').text(value).appendTo(row));
            });
        }
        function setBusy(value) {
            busy = value;
            editor.attr('aria-busy', String(value));
            disable(editor.find('input, textarea, button').not('[data-page]'), value);
            disable(editor.dialog('widget').find('.ui-dialog-buttonpane button'), value);
            $('#lists-name').prop('disabled', value || !!snapshot);
            $('#lists-color').prop('disabled', value || !!snapshot).selectmenu('refresh');
            fitDialog();
        }
        function exportContent(content, name) {
            const url = URL.createObjectURL(new Blob([content || ''], {type: 'text/plain;charset=utf-8'}));
            const link = $('<a></a>').attr({href: url, download: name || 'list.lst'}).appendTo(document.body);
            link[0].click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        function renderEntries() {
            const body = $('#lists-entries tbody').empty();
            const lines = $('#lists-content').val().split(/\r?\n/);
            lines.forEach((line, index) => {
                if (!line.trim() || line.trim().startsWith('#')) return;
                const row = $('<tr></tr>').appendTo(body);
                $('<td></td>').text(line).appendTo(row);
                $('<button type="button" class="rw-icon-button"><i class="fas fa-trash" aria-hidden="true"></i></button>')
                    .attr('aria-label', text('delete') + ' ' + line).prop('disabled', busy)
                    .on('click', () => {
                        const current = $('#lists-content').val().split(/\r?\n/);
                        current.splice(index, 1); $('#lists-content').val(current.join('\n')); renderEntries();
                    }).appendTo($('<td></td>').appendTo(row));
            });
            if (window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node: body[0]});
        }
        function renderSources(data) {
            const container = $('#lists-sources').empty();
            data.nodes.forEach(node => {
                const panel = $('<div class="rw-panel"></div>').appendTo(container);
                $('<h4></h4>').text(node.server + ' — ' + text(node.state)).appendTo(panel);
                $('<p class="lists-muted"></p>').text(node.used.join(', ') || text('unused')).appendTo(panel);
                [['file', node.content], ['runtime', node.runtime_content]].forEach(([key, value]) => {
                    $('<p></p>').text(text(key)).appendTo(panel);
                    if (value === null) { $('<p class="lists-muted"></p>').text(text('absent')).appendTo(panel); return; }
                    $('<textarea readonly rows="4"></textarea>').attr('aria-label', node.server + ' ' + text(key)).val(value).appendTo(panel);
                    $('<button type="button" class="rw-button rw-button-secondary"></button>').text(text('use_content'))
                        .on('click', () => { $('#lists-content').val(value); renderEntries(); }).appendTo(panel);
                });
            });
            $('#lists-comparison').prop('hidden', false).prop('open', data.nodes.some(node => node.state === 'different'));
        }
        async function fetchDetail(server, identity) {
            return $.ajax({url: endpoint(server), dataType: 'json', suppressGlobalError: true,
                data: {name: identity.name, color: identity.color}});
        }
        async function openEditor(item) {
            const token = ++dialogGeneration;
            editingServer = $('#lists-server').val(); snapshot = null;
            $('#lists-name').val(item ? item.name : '').prop('disabled', !!item);
            $('#lists-color').val(item ? item.color : 'black').prop('disabled', !!item).selectmenu('refresh');
            $('#lists-content, #lists-entry').val(''); $('#lists-results, #lists-sources').empty();
            $('#lists-comparison').prop('hidden', true); renderEntries();
            message($('#lists-editor-status'), item ? text('loading') : '');
            editor.dialog('option', 'title', item ? item.name : text('create')).dialog('open');
            if (!item) { setBusy(false); return; }
            setBusy(true);
            try {
                const data = await fetchDetail(editingServer, item);
                if (token !== dialogGeneration) return;
                snapshot = data;
                $('#lists-content').val(data.content === null ? (data.nodes[0].content || data.nodes[0].runtime_content || '') : data.content);
                renderSources(data); renderEntries(); message($('#lists-editor-status'), '');
            } catch (xhr) { message($('#lists-editor-status'), errorMessage(xhr), true); }
            finally { if (token === dialogGeneration) setBusy(false); }
        }
        async function save() {
            if (busy) return;
            const identity = {name: $('#lists-name').val().trim(), color: $('#lists-color').val()};
            const content = $('#lists-content').val();
            if (!identity.name) { $('#lists-name').trigger('focus'); return; }
            if (identity.color === 'white' && !content.split(/\r?\n/).some(line => line.trim() && !line.trim().startsWith('#'))) {
                if (!await RoxywiUI.confirm({message: text('empty_white'), confirmText: text('apply')})) return;
            }
            setBusy(true); message($('#lists-editor-status'), text('applying')); results([]);
            try {
                if (!snapshot) {
                    const data = await fetchDetail(editingServer, identity);
                    if (data.content !== null || data.nodes.some(node => node.content !== null || node.runtime_content !== null)) {
                        message($('#lists-editor-status'), text('already_exists'), true); return;
                    }
                    snapshot = data;
                }
                const data = await $.ajax({url: endpoint(editingServer), type: 'PUT', contentType: 'application/json', suppressGlobalError: true,
                    data: JSON.stringify({...identity, content: content, revision: snapshot.revision, operation: 'save'})});
                results(data.nodes); message($('#lists-editor-status'), text('saved'));
                snapshot = await fetchDetail(editingServer, identity);
                renderSources(snapshot); await load();
            } catch (xhr) {
                message($('#lists-editor-status'), errorMessage(xhr), true); results((xhr.responseJSON || {}).nodes);
            } finally { setBusy(false); }
        }
        async function reloadState() {
            if (busy || !snapshot) return;
            setBusy(true); message($('#lists-editor-status'), text('loading'));
            try {
                snapshot = await fetchDetail(editingServer, snapshot);
                renderSources(snapshot);
                $('#lists-comparison').prop('open', true);
                message($('#lists-editor-status'), text('compare'));
            } catch (xhr) { message($('#lists-editor-status'), errorMessage(xhr), true); }
            finally { setBusy(false); }
        }
        async function remove(item) {
            if (!await RoxywiUI.confirm({message: text('delete_confirm') + ' ' + item.name, confirmText: text('delete')})) return;
            const server = $('#lists-server').val();
            message($('#lists-status'), text('applying'));
            try {
                const data = await fetchDetail(server, item);
                await $.ajax({url: endpoint(server), type: 'PUT', contentType: 'application/json', suppressGlobalError: true,
                    data: JSON.stringify({name: item.name, color: item.color, operation: 'delete', revision: data.revision})});
                await load();
            } catch (xhr) { message($('#lists-status'), errorMessage(xhr), true); RoxywiUI.error(xhr.responseJSON || xhr.responseText); }
        }
        function render(items) {
            const body = $('#lists-table tbody').empty();
            items.forEach(item => {
                const row = $('<tr></tr>').appendTo(body);
                $('<button type="button" class="lists-name-button"></button>').text(item.name).on('click', () => openEditor(item)).appendTo($('<td></td>').appendTo(row));
                $('<td></td>').text(item.color === 'black' ? 'Blacklist' : 'Whitelist').appendTo(row);
                $('<td></td>').text(item.count === null ? '—' : item.count).appendTo(row);
                $('<td></td>').text(item.used.join(', ') || '—').appendTo(row);
                $('<span class="rw-status-badge"></span>').addClass(item.state === 'loaded' ? 'rw-status-running' : 'rw-status-stale').text(text(item.state)).appendTo($('<td></td>').appendTo(row));
                const actions = $('<div class="admin-actions"></div>').appendTo($('<td></td>').appendTo(row));
                $('<button type="button" class="rw-icon-button admin-actions-toggle" aria-haspopup="true" aria-expanded="false"><i class="fas fa-ellipsis-v" aria-hidden="true"></i></button>').attr('aria-label', text('actions')).appendTo(actions);
                const menu = $('<div class="admin-actions-menu" hidden></div>').appendTo(actions);
                [['edit', 'edit', () => openEditor(item)], ['compare', 'exchange-alt', async () => { await openEditor(item); $('#lists-comparison').prop('open', true); }],
                 ['export', 'download', async () => { try { const data = await fetchDetail($('#lists-server').val(), item); exportContent(data.content === null ? data.nodes[0].content || '' : data.content, item.name); } catch (xhr) { RoxywiUI.error(errorMessage(xhr)); } }],
                 ['delete', 'trash', () => remove(item)]].forEach(([key, icon, action]) => {
                    const button = $('<button type="button" class="admin-action-item"></button>').on('click', action).appendTo(menu);
                    $('<i aria-hidden="true"></i>').addClass('fas fa-' + icon).appendTo(button); $('<span></span>').text(text(key)).appendTo(button);
                    if (key === 'delete') button.addClass('admin-action-item-danger');
                });
            });
            if (window.FontAwesome?.dom) window.FontAwesome.dom.i2svg({node: body[0]});
        }
        async function load() {
            const server = $('#lists-server').val(), token = ++generation;
            disable($('#lists-create'), true); $('#lists-table tbody').empty(); $('#lists-targets').empty();
            if (!server) { message($('#lists-status'), text('select_server')); return; }
            message($('#lists-status'), text('loading'));
            try {
                const data = await $.ajax({url: endpoint(server), dataType: 'json', suppressGlobalError: true});
                if (token !== generation) return;
                render(data.items); $('#lists-targets').text(text('targets') + ': ' + data.targets.join(', '));
                message($('#lists-status'), data.items.length ? '' : text('no_lists')); disable($('#lists-create'), false);
            } catch (xhr) { if (token === generation) message($('#lists-status'), errorMessage(xhr), true); }
        }
        editor.removeAttr('hidden').dialog({autoOpen: false, modal: true, width: Math.min(850, window.innerWidth - 32),
            maxHeight: window.innerHeight - 32, classes: {'ui-dialog': 'rw-dialog-responsive lists-dialog'},
            beforeClose: () => !busy, close: () => { dialogGeneration++; },
            buttons: [{text: text('apply'), class: 'rw-button rw-button-primary', click: save}, {text: text('reload_state'), click: reloadState},
                      {text: text('close'), click: () => editor.dialog('close')}]
        });
        RoxywiUI.enhanceTable($('#lists-entries')[0]);
        editor[0].addEventListener('toggle', fitDialog, true);
        $(window).on('resize', fitDialog);
        $('#lists-content').on('change', renderEntries);
        $('#lists-add-entry').on('click', () => { const value = $('#lists-entry').val().trim(); if (!value) return;
            $('#lists-content').val($('#lists-content').val().trimEnd() + '\n' + value + '\n'); $('#lists-entry').val(''); renderEntries(); });
        $('#lists-entry').on('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); $('#lists-add-entry').trigger('click'); } });
        $('#lists-export').on('click', () => exportContent($('#lists-content').val(), $('#lists-name').val()));
        $('#lists-create').on('click', () => openEditor(null)); $('#lists-refresh').on('click', load);
        $('#lists-server').on('selectmenuchange change', load);
        $('#tabs').on('tabsactivate', function (event, ui) { if (ui.newPanel.attr('id') === 'lists' && !generation) load(); });
        if (window.location.hash === '#lists') load();
    });
})(window, window.jQuery);
