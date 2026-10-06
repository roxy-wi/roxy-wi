/* File selection for Add forms. A late response must not change another server's target. */
$(function () {
    const messages = JSON.parse(document.getElementById('haproxy-file-messages').textContent);
    const servers = JSON.parse(document.getElementById('haproxy-file-servers').textContent);
    const params = new URLSearchParams(window.location.search);
    const initialServer = servers.find(row => [String(row[0]), String(row[2])].includes(params.get('server_id')));
    const token = params.get('file_path') || '';
    const initialFile = token ? decodeConfigPath(token) : '';
    ['listen', 'frontend', 'backend', 'userlist', 'peers'].forEach(kind => {
        const form = $('#add-' + kind);
        const server = form.find('select[name="server"]');
        const id = kind + '-config-target';
        const file = $('<select>', {id, name: 'config_target', required: true}).css('width', '100%');
        const row = $('<tr>').append(
            $('<td>', {class: 'addName'}).append($('<label>', {for: id, text: messages.target})),
            $('<td>', {class: 'addOption'}).append(file)
        );
        server.closest('tr').after(row);
        file.select2({width: 'resolve'});
        let revision = 0;
        function refresh() {
            const current = ++revision;
            const selected = server.val();
            file.empty().prop('disabled', true).trigger('change');
            if (!selected || selected === '------') return;
            $.ajax({
                url: '/config/haproxy/' + encodeURIComponent(selected) + '/files',
                success(result) {
                    if (current !== revision) return;
                    for (const path of result.data) file.append(new Option(path, path));
                    row.toggle(result.multiple_files !== false);
                    if (initialFile && initialServer && [String(initialServer[0]), String(initialServer[2])].includes(selected)
                        && result.data.includes(initialFile)) file.val(initialFile);
                    file.prop('disabled', false).trigger('change');
                },
                error() { if (current === revision) toastr.error(messages.failed); }
            });
        }
        server.on('change selectmenuchange', refresh);
        if (initialServer) {
            const value = kind === 'userlist' ? initialServer[2] : initialServer[0];
            server.val(String(value));
            if (server.data('ui-selectmenu')) server.selectmenu('refresh');
        }
        refresh();
    });
});
