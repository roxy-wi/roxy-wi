$(function () {
    const form = $('#waf-wizard');
    if (!form.length) return;
    const error = $('#wizard-error');
    const list = $('#wizard-condition-list');
    const autoId = $('#wizard-auto-id');
    const server = $('#wizard-server');
    const targets = JSON.parse(document.getElementById('wizard-server-targets').textContent);
    let currentServer = server.val();
    let serverLocked = form.attr('data-existing-rule') === '1';
    let nextCondition = list.children().length;
    let saving = false;
    function refreshSelects() {
        form.find('select').each(function () { if ($(this).selectmenu('instance')) $(this).selectmenu('refresh'); });
        form.find('input[type="checkbox"]').each(function () {
            if ($(this).checkboxradio('instance')) $(this).checkboxradio('refresh');
        });
    }
    function fields() {
        const exclusion = form.find('[name="kind"]').val() === 'exclusion';
        const global = exclusion && $('#wizard-all-requests').prop('checked');
        form.find('[data-field="action"]').prop('hidden', exclusion);
        form.find('[data-global-scope]').prop('hidden', !exclusion);
        form.find('[data-field="match"]').prop('hidden', global);
        list.prop('hidden', global);
        list.find('[data-condition]').each(function () {
            const row = $(this);
            const field = row.find('[name="field"]').val();
            const keyNeeded = ['header', 'arg'].includes(field);
            row.find('[data-field="key"]').prop('hidden', !keyNeeded);
            row.find('[data-field="operator"]').prop('hidden', field === 'ip');
            row.find('input, select, button').prop('disabled', global || saving);
            row.find('[name="key"]').prop('required', keyNeeded && !global).prop('disabled', global || saving || !keyNeeded);
            row.find('[name="value"]').prop('required', !global);
            row.find('[name="field"] option[value="arg"]').prop('disabled', exclusion);
            row.find('[data-remove-condition]').prop('hidden', list.children().length === 1);
        });
        $('#wizard-add-condition').prop('hidden', global).prop('disabled', saving || list.children().length >= 10);
        form.find('[data-field="exclusion"], [data-exclusion-hint]').prop('hidden', !exclusion);
        form.find('[name="exclude_id"]').prop('required', exclusion).prop('disabled', !exclusion || saving);
        form.find('[name="exclude_parameter"]').prop('disabled', !exclusion || saving);
        $('#wizard-id').prop('disabled', autoId.prop('checked') || saving).prop('required', !autoId.prop('checked'));
        server.prop('disabled', serverLocked || saving);
        refreshSelects();
    }
    function changed(event) {
        // Refreshing a selectmenu on a text input's blur can close the menu
        // the user has just opened. Only structural changes need a refresh.
        if (!event || $(event.target).is('select, input[type="checkbox"]')) fields();
        $(window).on('beforeunload.wafWizard', function () { return ''; });
    }
    form.on('input change selectmenuchange', 'input, select', changed);
    server.on('change selectmenuchange', function () {
        if (saving || serverLocked || !targets[server.val()]) {
            server.val(currentServer);
            refreshSelects();
            return;
        }
        if (server.val() === currentServer) return;
        currentServer = server.val();
        const target = targets[currentServer];
        form.attr('action', target.wizard);
        window.history.replaceState(null, '', target.wizard);
        $('[data-waf-rules-link]').attr('href', target.rules);
        $('[data-waf-sync-hint]').prop('hidden', !target.sync);
        error.prop('hidden', true).text('');
        if (autoId.prop('checked')) $('#wizard-id').val('');
        const panel = $('[data-waf-apply]');
        panel.attr('data-state-url', target.state).attr('data-state', 'unknown');
        panel.find('[data-waf-apply-label]').text(panel.attr('data-unknown')).attr('title', panel.attr('data-scope'));
        // The shared refresh discards earlier requests after another server is selected.
        refreshWafState(panel);
    });
    $('#wizard-add-condition').on('click', function () {
        if (saving || list.children().length >= 10) return;
        const row = $($('#wizard-condition-template').html().replaceAll('__index__', String(nextCondition++)));
        list.append(row);
        row.find('select').selectmenu();
        changed();
        row.find('[name="value"]').trigger('focus');
    });
    list.on('click', '[data-remove-condition]', function () {
        if (saving || list.children().length <= 1) return;
        const row = $(this).closest('[data-condition]');
        row.find('select').each(function () { if ($(this).selectmenu('instance')) $(this).selectmenu('destroy'); });
        row.remove();
        changed();
    });
    fields();
    function send(action) {
        if (saving || !form[0].reportValidity()) return;
        const spec = {version: 2, conditions: [], id: autoId.prop('checked') ? null : Number($('#wizard-id').val())};
        ['kind', 'match', 'action', 'exclude_id', 'exclude_parameter'].forEach(function (name) {
            const value = form.find('[name="' + name + '"]').val();
            spec[name] = name === 'exclude_id' ? Number(value) : value;
        });
        if (!(spec.kind === 'exclusion' && $('#wizard-all-requests').prop('checked'))) {
            list.children('[data-condition]').each(function () {
                const row = $(this), condition = {};
                ['field', 'key', 'operator', 'value'].forEach(function (name) {
                    condition[name] = row.find('[name="' + name + '"]').val();
                });
                if (!['header', 'arg'].includes(condition.field)) condition.key = '';
                spec.conditions.push(condition);
            });
        }
        const payload = {spec: spec, action: action};
        ['new_waf_rule', 'new_rule_file', 'new_rule_description'].forEach(function (name) {
            payload[name] = form.find('[name="' + name + '"]').val();
        });
        saving = true;
        error.prop('hidden', true).text('');
        form.find('input, button, select').prop('disabled', true);
        refreshSelects();
        $.ajax({
            url: form.attr('action'), type: 'POST', dataType: 'json', contentType: 'application/json',
            data: JSON.stringify(payload), suppressGlobalError: true,
            success: function (data) {
                if (!data || data.status !== 'ok') { error.text(form.attr('data-failed')).prop('hidden', false); return; }
                if (data.rule_ids && data.rule_ids.length) $('#wizard-id').val(data.rule_ids[0]);
                if (action === 'preview') {
                    RoxywiUI.showGeneratedConfig(data.config, data.previous, form.attr('data-previous-label'));
                } else {
                    serverLocked = true;
                    autoId.prop('checked', false);
                    form.attr('action', data.edit_url);
                    window.history.replaceState(null, '', data.edit_url);
                    form.find('[name^="new_"]').each(function () {
                        $(this).val($(this).val().trim()).prop('readonly', true);
                    });
                    // Keep the normalized filename used by the backend on later edits.
                    const filename = form.find('[name="new_rule_file"]');
                    if (!filename.val().endsWith('.conf')) filename.val(filename.val() + '.conf');
                    toastr.success(form.attr('data-' + action + '-success'));
                    $(window).off('beforeunload.wafWizard');
                }
            },
            error: function (xhr) {
                // jQuery text() keeps remote/localized error text out of HTML.
                error.text(xhr.responseJSON && xhr.responseJSON.error || form.attr('data-failed')).prop('hidden', false);
            },
            complete: function () {
                saving = false;
                form.find('input, button, select').prop('disabled', false);
                fields();
                if (action !== 'preview') refreshWafState(document);
            }
        });
    }
    $('#wizard-preview-button').on('click', function () { send('preview'); });
    form.on('submit', function (event) {
        event.preventDefault();
        const button = event.originalEvent && event.originalEvent.submitter;
        send(button ? button.value : 'save');
    });
});
