document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('tool-install-form');
    if (!form) return;
    const text = JSON.parse(document.getElementById('tool-install-messages').textContent);
    const field = name => form.elements.namedItem(name);
    const result = document.getElementById('tool-install-check-result');
    const installed = document.getElementById('tool-install-current');
    const options = JSON.parse(document.getElementById('tool-install-options').textContent);
    const labels = {checker: 'Checker', metrics: 'Metrics', portscanner: 'Portscanner', socket: 'Socket', keep_alive: 'Keep Alive'};
    let checking = false, generation = 0, inspection = 0, currentTask;
    const message = code => text[code] || text.command_failed;
    const error = response => {
        const data = response.responseJSON || {};
        const detail = data.error_code ? message(data.error_code) : (data.error || text.command_failed);
        toastr.error(jQuery('<span>').text(detail).html());
    };
    function payload() {
        const component = field('component').value, engine = field('engine').value;
        return {component, engine, version: engine === 'native' ? '' : field('version').value,
            server_id: field('server_id').value ? Number(field('server_id').value) : null,
            database_url: ['socket', 'keep_alive'].includes(component) ? '' : field('database_url').value.trim(),
            socket_port: Number(field('socket_port').value)};
    }
    function fields() {
        const component = field('component').value, localOnly = component === 'keep_alive';
        document.getElementById('tool-install-worker-options').hidden = localOnly;
        document.getElementById('tool-install-state-db').hidden = component === 'socket';
        document.getElementById('tool-install-socket-options').hidden = component !== 'socket';
        document.getElementById('tool-install-socket-help').hidden = component !== 'socket';
        field('server_id').disabled = localOnly;
        field('engine').disabled = localOnly;
        if (localOnly) { field('engine').value = 'native'; field('server_id').value = ''; }
        document.getElementById('tool-install-container-options').hidden = field('engine').value === 'native';
        jQuery(field('server_id')).selectmenu('refresh');
        jQuery(field('engine')).selectmenu('refresh');
    }
    function busy(value) {
        checking = value;
        dialog.dialog('widget').find('.ui-dialog-buttonpane button').first().prop('disabled', value);
        field('server_id').disabled = value || field('component').value === 'keep_alive';
        field('engine').disabled = value || field('component').value === 'keep_alive';
        field('version').disabled = value;
        for (const name of ['server_id', 'engine', 'version']) {
            if (jQuery(field(name)).selectmenu('instance')) jQuery(field(name)).selectmenu('refresh');
        }
    }
    async function inspectServer() {
        const requestGeneration = generation, attempt = ++inspection;
        installed.textContent = text.checking;
        busy(true);
        try {
            const data = await jQuery.ajax({url: '/admin/tools/install/check', method: 'POST',
                contentType: 'application/json', data: JSON.stringify(payload()), suppressGlobalError: true});
            if (requestGeneration !== generation || attempt !== inspection) return;
            if (data.installed) {
                field('engine').value = data.engine;
                fields();
                const version = data.engine === 'native' ? data.version : data.version.split(':').pop();
                installed.textContent = `${text.installed} · ${data.engine} · ${text.version}: ${version} · ${message(data.state)}`;
            } else installed.textContent = text.not_installed;
        } catch (response) {
            if (requestGeneration === generation && attempt === inspection) { installed.textContent = text.unknown; error(response); }
        } finally { if (requestGeneration === generation && attempt === inspection) busy(false); }
    }
    async function submit() {
        if (checking || !form.reportValidity()) return;
        if (!options.local && !field('server_id').value) { toastr.error(text.local_systemd_required); return; }
        if (field('engine').value !== 'native' && !field('version').value) {
            toastr.error(text.version_unavailable); return;
        }
        const requestGeneration = generation;
        busy(true); result.textContent = text.started;
        try {
            const data = await jQuery.ajax({url: '/admin/tools/update/roxy-wi-' + field('component').value, method: 'POST',
                contentType: 'application/json', data: JSON.stringify(payload()), suppressGlobalError: true});
            runInstallationTaskCheck(data.tasks_ids);
            if (requestGeneration !== generation) return;
            currentTask = data.tasks_ids[0];
        } catch (response) {
            if (requestGeneration === generation) { result.textContent = ''; error(response); }
        } finally { if (requestGeneration === generation) busy(false); }
    }
    const dialog = jQuery('#tool-install-dialog').removeAttr('hidden').hide().dialog({
        autoOpen: false, modal: true, resizable: false, width: Math.min(600, window.innerWidth - 24),
        classes: {'ui-dialog': 'rw-dialog-responsive tool-install-dialog'},
        open() {
            jQuery(this).find('select').selectmenu({width: '100%', appendTo: jQuery(this).dialog('widget')});
            jQuery(this).find('select').selectmenu('refresh');
            fields();
        },
        close() { generation++; form.reset(); },
        buttons: [
            {text: text.install, click: () => submit()},
            {text: text.close, click: () => dialog.dialog('close')}
        ]
    });
    async function open(component) {
        if (!Object.hasOwn(labels, component)) return;
        const requestGeneration = ++generation;
        try {
            if (requestGeneration !== generation) return;
            form.reset(); result.textContent = ''; installed.textContent = ''; currentTask = null;
            document.getElementById('tool-install-state-db').open = false;
            field('component').value = component;
            field('server_id').replaceChildren(new Option(text.local, ''));
            field('server_id').firstElementChild.disabled = !options.local;
            for (const server of options.servers) field('server_id').add(new Option(server.name + ' · ' + server.address, server.id));
            if (!options.local && component !== 'keep_alive' && options.servers.length) field('server_id').value = options.servers[0].id;
            field('version').replaceChildren(...(options.versions[component] || []).map(value => new Option(value, value)));
            dialog.dialog('option', 'title', text.title + ' · ' + labels[component]);
            busy(false); dialog.dialog('open');
            await inspectServer();
        } catch (response) { if (requestGeneration === generation) error(response); }
    }
    form.addEventListener('submit', event => { event.preventDefault(); submit(); });
    jQuery(field('engine')).on('selectmenuchange', fields);
    jQuery(field('server_id')).on('selectmenuchange', inspectServer);
    document.addEventListener('roxywi:installation-finished', event => {
        const task = event.detail;
        if (task.service_name.startsWith('roxy-wi-')) loadServices();
        if (task.task_id === currentTask && dialog.dialog('isOpen')) {
            currentTask = null;
            result.textContent = message(task.status);
            inspectServer();
        }
    });
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-tool-install]');
        if (button) open(button.dataset.toolInstall);
    });
    window.RoxywiToolInstall = {open};
});
