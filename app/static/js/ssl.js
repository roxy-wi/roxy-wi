$( function() {
    $("#ssl_key_or_crt_upload").click(function () {
        if (!checkIsServerFiled('#serv6')) return false;
        if (!checkIsServerFiled('#ssl_key_name', 'Enter the Certificate name')) return false;
        if (!checkIsServerFiled('#ssl_key_or_crt', 'Paste the contents of the certificate file')) return false;
        let jsonData = {
            server_ip: $('#serv6').val(),
            cert_type: $('#new-cert-file-type').val(),
            cert: $('#ssl_key_or_crt').val(),
            name: $('#ssl_key_name').val()
        }
        $.ajax({
            url: "/add/cert/add",
            data: JSON.stringify(jsonData),
            contentType: "application/json; charset=utf-8",
            type: "POST",
            success: function (data) {
                if (data.error === 'failed') {
                    toastr.error(data.error);
                } else {
                    for (let i = 0; i < data.length; i++) {
                        if (data[i]) {
                            if (data[i].indexOf('error: ') != '-1' || data[i].indexOf('Errno') != '-1') {
                                toastr.error(data[i]);
                            } else {
                                toastr.success(data[i]);
                            }
                        }
                    }
                }
            }
        });
    });
    $('#ssl_key_view').click(function () {
        if (!checkIsServerFiled('#serv5')) return false;
        $.ajax({
            url: "/add/certs/" + $('#serv5').val(),
            success: function (data) {
                if (data.indexOf('error:') != '-1') {
                    toastr.error(data);
                } else {
                    let i;
                    let new_data = "";
                    data = data.split("\n");
                    let j = 1
                    for (i = 0; i < data.length; i++) {
                        data[i] = data[i].replace(/\s+/g, ' ');
                        if (data[i] != '') {
                            if (j % 2) {
                                if (j != 0) {
                                    new_data += '</span>'
                                }
                                new_data += '<span class="list_of_lists">'
                            } else {
                                new_data += '</span><span class="list_of_lists">'

                            }
                            j += 1
                            new_data += ' <a onclick="view_ssl(\'' + data[i] + '\')" title="View ' + data[i] + ' cert">' + data[i] + '</a> '
                        }
                    }
                    $("#ajax-show-ssl").html(new_data);
                }
            }
        });
    });
});
function view_ssl(id) {
	let raw_word = translate_div.attr('data-raw');
	if(!checkIsServerFiled('#serv5')) return false;
	$.ajax( {
		url: "/add/cert/" + $('#serv5').val() + '/' + id,
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$( "#dialog-confirm-cert" ).dialog({
					resizable: false,
					height: "auto",
					width: 670,
					modal: true,
					title: "Certificate from "+$('#serv5').val()+", name: "+id,
					buttons: [{
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}, {
						text: raw_word,
						click: function () {
							showRawSSL(id);
						}
					}, {
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting("SSL cert", id, $(this), "");
						}
					}]
				});
			}
		}
	} );
}
function showRawSSL(id) {
	$.ajax({
		url: "/add/cert/get/raw/" + $('#serv5').val() + "/" + id,
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				$('#dialog-confirm-body').text(data);
				$("#dialog-confirm-cert").dialog({
					resizable: false,
					height: "auto",
					width: 670,
					modal: true,
					title: "Certificate from " + $('#serv5').val() + ", name: " + id,
					buttons: [{
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}, {
						text: "Human readable",
						click: function () {
							view_ssl(id);
						}
					}, {
						text: delete_word,
						click: function () {
							$(this).dialog("close");
							confirmDeleting("SSL cert", id, $(this), "");
						}
					}]
				});
			}
		}
	});
}
function deleteSsl(id) {
	if (!checkIsServerFiled('#serv5')) return false;
	$.ajax({
		url: "/add/cert/" + $("#serv5").val() + "/" + id,
		type: "DELETE",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				toastr.success('SSL cert ' + id + ' has been deleted');
				$("#ssl_key_view").trigger("click");
			}
		}
	});
}
let provides = {'standalone': "Stand alone", 'route53': 'Route53', 'linode': 'Linode', 'cloudflare': 'Cloudflare', 'digitalocean': 'Digitalocean'};
let leEditingId = null;
$( function() {
    if ($('#le_table').length) {
        getLes();
        setInterval(function () {
            if (!document.hidden && $('#le_table').length) getLes();
        }, 15000);
    }
    let typeSelect = $( "#new-le-type" );
    typeSelect.on('selectmenuchange',function()  {
       if (typeSelect.val() === 'standalone') {
            $('.le-standalone').show();
            $('.le-dns').hide();
            $('.le-aws').hide();
       } else if (typeSelect.val() === 'cloudflare' || typeSelect.val() === 'digitalocean' || typeSelect.val() === 'linode') {
           $('.le-standalone').hide();
           $('.le-dns').show();
           $('.le-aws').hide();
       } else if (typeSelect.val() === 'route53' ) {
           $('.le-standalone').hide();
           $('.le-dns').hide();
           $('.le-aws').show();
       }
    });
});
function addLe(dialogId) {
    let domain = $('#new-le-domain').val();
    let email = $('#new-le-email').val();
    let type = $('#new-le-type').val();
    let api_key = '';
    let api_token = $('#new-le-token').val();
    let valid = true;
    let allFields = '';
    if (type === 'standalone') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-email'));
        allFields.removeClass("ui-state-error");
        valid = valid && checkLength($('#new-le-email'), "Email", 1);
    }
    if (type === 'cloudflare' || type === 'digitalocean' || type === 'linode') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-token'));
        allFields.removeClass("ui-state-error");
        if (!leEditingId) valid = valid && checkLength($('#new-le-token'), "Token", 1);
    }
    if (type === 'route53') {
        allFields = $([]).add($('#new-le-domain')).add($('#new-le-access_key_id')).add($('#new-le-secret_access_key'));
        allFields.removeClass("ui-state-error");
        if (!leEditingId) {
            valid = valid && checkLength($('#new-le-access_key_id'), "Access key ID", 1);
            valid = valid && checkLength($('#new-le-secret_access_key'), "Access key", 1);
        }
    }
    valid = valid && checkLength($('#new-le-domain'), "Domains", 1);
    if ($('#new-le-server_id').val() === '------' || $('#new-le-server_id').val() === null) {
        toastr.warning('Select server firts')
        return false;
    }
    if (!valid) {
        return false;
    }
    if (type === 'standalone') {
        if (!validateEmail(email)) {
            toastr.warning('Invalid email format');
            return false;
        }
    }
    if (type === 'route53') {
        api_key = $('#new-le-access_key_id').val();
        api_token = $('#new-le-secret_access_key').val();
    }
    let domains = [];
    if (domain.includes(',')) {
        domains = domain.split(',').filter(function (item) {
            return item.trim() !== '';
        });
    } else if (domain.includes(' ')) {
        domains = domain.split(' ').filter(function (item) {
            return item.trim() !== '';
        });
    } else {
        domains.push(domain);
    }
    let jsonData = {
        'server_id': $('#new-le-server_id').val(),
        'domains': domains.map(item => item.trim()),
        'email': email,
        'type': type,
        'api_key': api_key || null,
        'api_token': api_token || null,
        'description': $('#new-le-description').val(),
    }
    $.ajax({
        url: '/service/letsencrypt' + (leEditingId ? '/' + leEditingId : ''),
        method: leEditingId ? 'PUT' : 'POST',
        data: JSON.stringify(jsonData),
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                getLe(data['id'], dialogId);
                runInstallationTaskCheck(data.tasks_ids);
            }
        },
    });
}
function removeLe(leId) {
    $("#lets-" + leId).css("background-color", "#f2dede");
    $.ajax({
        url: '/service/letsencrypt/' + leId,
        method: 'DELETE',
        contentType: "application/json; charset=utf-8",
        statusCode: {
			202: function () { getLes(); },
			204: function (xhr) {
				$("#lets-" + leId).remove();
			},
			404: function (xhr) {
				$("#lets-" + leId).remove();
			}
		},
        success: function (data) {
            if (data) {
                if (data.status === "failed") {
					toastr.error(data);
				} else if (data.tasks_ids) {
					runInstallationTaskCheck(data.tasks_ids);
				}
			}
        },
    });
}
function confirmDeleteLe(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: 'Stop renewal? Deployed certificates will be kept.',
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeLe(id);
			}
		},{
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function openLeDialog(leId = null) {
    leEditingId = leId;
    $('#new-le-token, #new-le-access_key_id, #new-le-secret_access_key').val('');
    if (leId) {
        $.getJSON('/service/letsencrypt/' + leId, function (data) {
            if (leEditingId !== leId) return;
            $('#new-le-server_id').val(data.server_id).selectmenu('refresh');
            $('#new-le-type').val(data.type).selectmenu('refresh').trigger('selectmenuchange');
            $('#new-le-domain').val(data.domains.join(', '));
            $('#new-le-email').val(data.email || '');
            $('#new-le-description').val(data.description || '');
            $('#new-le-token, #new-le-access_key_id, #new-le-secret_access_key').attr('placeholder', 'Leave empty to keep existing credentials');
            openLeForm(leId);
        });
        return;
    } else {
        $('#new-le-domain, #new-le-email, #new-le-description').val('');
        $('#new-le-token, #new-le-access_key_id, #new-le-secret_access_key').attr('placeholder', '');
    }
    openLeForm(leId);
}
function openLeForm(leId) {
    $("#le-add-table").dialog({
        autoOpen: true,
        resizable: false,
        height: "auto",
        width: 500,
        modal: true,
        title: (leId ? 'Edit' : $('#translate').attr('data-create')) + " Let's Encrypt",
        show: {
            effect: "fade",
            duration: 200
        },
        hide: {
            effect: "fade",
            duration: 200
        },
        buttons: [
			{
				text: leId ? 'Save' : $('#translate').attr('data-create'),
				click: function () {
					addLe($(this));
				}
			}, {
				text: cancel_word,
				click: function () {
					$(this).dialog("close");
				}
			}
		]
    });
}
function getLe(leId, dialogId) {
    $.ajax({
        url: '/service/letsencrypt/' + leId + "?recurse=True",
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                showLe(data);
                $.getScript(awesome);
                $(dialogId).dialog("close");
            }
        },
    });
}
function getLes() {
    $.ajax({
        url: '/service/letsencrypts?recurse=True',
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data);
            } else {
                $('#le_table_body').empty();
                for (let k in data) {
                    showLe(data[k]);
                }
                $.getScript(awesome);
            }
        },
    });
}
function showLe(data) {
    const domains = Array.isArray(data['domains']) ? data['domains'] : [];
    const list_domains = domains.join(', ');
    const state = data.state || {};
    const busy = ['queued', 'running', 'deleting'].includes(state.status) || state.legacy_pending;
    const date = value => value ? new Date(value).toLocaleString() : '—';
    const item = (label, action, disabled = busy) => {
        const button = elem('button', {type: 'button', class: 'admin-action-item', onclick: action}, label);
        button.disabled = disabled;
        return button;
    };
    const status = [elem('div', null, state.legacy_pending ? 'Waiting for migration' : state.status || 'pending'),
        elem('div', null, 'Expires: ' + date(state.not_after)),
        elem('div', null, 'PEM: ' + (state.pem_name || ''))];
    if (state.last_error) status.push(elem('div', {class: 'text-danger'}, state.last_error));
    for (const [server, target] of Object.entries(state.targets || {})) {
        status.push(elem('div', null, 'Server #' + server + ': ' + target.status));
    }
    let le_tag = elem("tr", {"id":"lets-" + data['id']}, [
	elem("td", {"class":"padding10 first-collumn"}, data.server_id.hostname || String(data.server_id)),
	elem("td", {"style": "width: 10%;"}, provides[data['type']]),
	elem("td", null, list_domains),
	elem("td", null, data['description'] || ''),
    elem('td', null, status),
    elem('td', null, date(state.retry_at || state.next_run_at)),
    elem('td', {class: 'admin-actions-cell'}, [elem('div', {class: 'admin-actions'}, [
        elem('button', {type: 'button', class: 'rw-icon-button admin-actions-toggle',
            'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-label': 'Actions'},
            [elem('span', {class: 'fas fa-ellipsis-v', 'aria-hidden': 'true'})]),
        elem('div', {class: 'admin-actions-menu', role: 'menu', hidden: 'hidden'}, [
            item('Edit', () => openLeDialog(data.id)),
            item('Check renewal', () => runLeAction(data.id, 'renew')),
            item('Test renewal (staging)', () => runLeAction(data.id, 'test')),
            item('Retry', () => runLeAction(data.id, 'retry'), busy || !state.can_retry),
            item('History', () => showLeHistory(data.id), false),
            item('Delete', () => confirmDeleteLe(data.id))
        ])
    ])])
    ])
    $('#lets-' + data.id).remove();
    $('#le_table_body').append(le_tag);
}

function runLeAction(id, action) {
    $.ajax({url: '/service/letsencrypt/' + id, method: 'PATCH',
        contentType: 'application/json', data: JSON.stringify({action}),
        success: function (data) { runInstallationTaskCheck(data.tasks_ids); getLes(); }
    });
}

function showLeHistory(id) {
    $.getJSON('/service/letsencrypt/' + id, function (data) {
        const dialog = $('#le-history-dialog').empty();
        for (const task of data.state.history || []) {
            dialog.append(elem('p', null, '#' + task.id + ' · ' + task.status + ' · ' +
                (task.started_at || '') + (task.error ? '\n' + task.error : '')));
        }
        dialog.dialog({title: "Let's Encrypt history", width: 650, modal: true});
    });
}

