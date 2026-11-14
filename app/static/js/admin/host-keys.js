/* Explicit SSH host-key approval shared by server creation and Check SSH. */
function confirmSshHostKey(response) {
    const text = JSON.parse(document.getElementById('ssh-host-key-translations').textContent);
    const key = response.host_key;
    return new Promise(resolve => {
        let approval = null;
        const dialog = $('<div>', {class: 'ssh-host-key-dialog'});
        $('<p>').text(key.changed ? text.changed : text.intro).appendTo(dialog);
        const details = $('<dl>').appendTo(dialog);
        function field(label, value) {
            $('<dt>').text(label).appendTo(details);
            $('<dd>').css({marginLeft: 0, overflowWrap: 'anywhere'}).text(value).appendTo(details);
        }
        field(text.address, key.host);
        field(text.port, key.port);
        field(text.algorithm, key.algorithm);
        if (key.changed && key.previous_fingerprint) field(text.previous, key.previous_fingerprint);
        field('SHA-256 fingerprint', key.fingerprint);
        $('<p>').text(text.verify).appendTo(dialog);
        dialog.appendTo(document.body).dialog({
            title: text.title, modal: true, resizable: false,
            width: Math.min(560, window.innerWidth - 32), height: 'auto',
            buttons: [{
                text: text.confirm,
                click: function () { approval = response.confirmation; dialog.dialog('close'); }
            }, {
                text: text.cancel,
                click: function () { dialog.dialog('close'); }
            }],
            open: function () {
                dialog.parent().find('.ui-dialog-buttonpane button').last().trigger('focus');
            },
            close: function () {
                dialog.dialog('destroy').remove();
                resolve(approval);
            }
        });
    });
}

function requestWithSshConfirmation(options, owner) {
    const source = $(owner);
    if (source.data('sshRequestPending')) return;
    source.data('sshRequestPending', true).attr('aria-busy', 'true');
    const frozen = source.add(source.closest('.ui-dialog').find('.ui-dialog-buttonpane'));
    frozen.prop('inert', true);
    function release() {
        source.removeData('sshRequestPending').removeAttr('aria-busy');
        frozen.prop('inert', false);
    }
    function send(payload) {
        $.ajax(Object.assign({}, options, {
            data: JSON.stringify(payload), suppressGlobalError: true,
            success: function (data) {
                release();
                if (options.success) options.success(data);
            },
            error: function (xhr) {
                const response = xhr.responseJSON || {};
                if (xhr.status === 409 && response.code === 'ssh_host_key_confirmation_required') {
                    confirmSshHostKey(response).then(token => {
                        if (token) send(Object.assign({}, payload, {ssh_host_key_confirmation: token}));
                        else release();
                    });
                } else {
                    release();
                    toastr.error(escapeHtml(response.error || 'Cannot complete the SSH host key check. Retry the request.'));
                }
            }
        }));
    }
    send(JSON.parse(options.data));
}
