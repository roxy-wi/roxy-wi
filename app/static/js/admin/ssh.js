$( function() {
	$('#add-ssh-button').click(function () {
		addCredsDialog.dialog('open');
	});
	let ssh_tabel_title = $("#ssh-add-table-overview").attr('title');
	let addCredsDialog = $("#ssh-add-table").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: ssh_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [{
			text: add_word,
			click: function () {
				addCreds(this);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	$("#ssh_enable_table input").change(function () {
		let id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$("#ssh_enable_table select").on('selectmenuchange', function () {
		let id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$('#new-ssh_enable').click(function () {
		if ($('#new-ssh_enable').is(':checked')) {
			$('#ssh_pass').css('display', 'none');
		} else {
			$('#ssh_pass').css('display', 'block');
		}
	});
	if ($('#new-ssh_enable').is(':checked')) {
		$('#ssh_pass').css('display', 'none');
	} else {
		$('#ssh_pass').css('display', 'block');
	}
});
function addCreds(dialog_id) {
	toastr.clear();
    let ssh_add_div = $('#new-ssh-add');
	let ssh_enable = 0;
	if ($('#new-ssh_enable').is(':checked')) {
		ssh_enable = '1';
	}
	let ssh_shared = 0;
	if ($('#new-ssh_shared').is(':checked')) {
		ssh_shared = '1';
	}
	let valid = true;
    let allFields = $([]).add(ssh_add_div).add($('#ssh_user'))
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength(ssh_add_div, "Name", 1);
	valid = valid && checkLength($('#ssh_user'), "Credentials", 1);
	if (valid) {
        let jsonData = {
            "name": ssh_add_div.val(),
            "group_id": $('#new-sshgroup').val(),
            "username": $('#ssh_user').val(),
            "password": $('#ssh_pass').val(),
            "shared": ssh_shared,
            "key_enabled": ssh_enable,
        }
		$.ajax({
			url: "/server/cred",
			type: "POST",
            data: JSON.stringify(jsonData),
            contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					let group_name = getGroupNameById($('#new-sshgroup').val());
					let id = data.id;
					common_ajax_action_after_success(dialog_id, 'ssh-table-' + id, 'ssh_enable_table', data.data);
					$('select:regex(id, credentials)').append('<option value=' + id + '>' + ssh_add_div.val() + '</option>').selectmenu("refresh");
					$('select:regex(id, ssh-key-name)').append('<option value=' + id + '>' + ssh_add_div.val() + '_' + group_name + '</option>').selectmenu("refresh");
					$("input[type=submit], button").button();
					$("input[type=checkbox]").checkboxradio();
					$("select").selectmenu();
				}
			}
		});
	}
}
function sshKeyEnableShow(id) {
	$('#ssh_enable-' + id).click(function () {
		if ($('#ssh_enable-' + id).is(':checked')) {
			$('#ssh_pass-' + id).css('display', 'none');
		} else {
			$('#ssh_pass-' + id).css('display', 'block');
		}
	});
	if ($('#ssh_enable-' + id).is(':checked')) {
		$('#ssh_pass-' + id).css('display', 'none');
	} else {
		$('#ssh_pass-' + id).css('display', 'block');
	}
}
function updateSSH(id) {
	toastr.clear();
	let ssh_enable = 0;
	let ssh_shared = 0;
	let ssh_name_val = $('#ssh_name-' + id).val();
	if ($('#ssh_enable-' + id).is(':checked')) {
		ssh_enable = '1';
	}
	if ($('#ssh_shared-' + id).is(':checked')) {
		ssh_shared = '1';
	}
	let group = $('#sshgroup-' + id).val();
	if (group === undefined || group === null) {
		group = $('#new-sshgroup').val();
	}
	let jsonData = {
		"name": ssh_name_val,
		"group_id": group,
		"key_enabled": ssh_enable,
		"username": $('#ssh_user-' + id).val(),
		"password": $('#ssh_pass-' + id).val(),
		"shared": ssh_shared,
	}
	$.ajax({
		url: "/server/cred/" + id,
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "PUT",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				$("#ssh-table-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#ssh-table-" + id).removeClass("update");
				}, 2500);
				$('select:regex(id, credentials) option[value=' + id + ']').remove();
				$('select:regex(id, ssh-key-name) option[value=' + ssh_name_val + ']').remove();
				$('select:regex(id, credentials)').append('<option value=' + id + '>' + ssh_name_val + '</option>').selectmenu("refresh");
				$('select:regex(id, ssh-key-name)').append('<option value=' + ssh_name_val + '>' + ssh_name_val + '</option>').selectmenu("refresh");
			}
		}
	});
}
function confirmDeleteSsh(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word +" " + $('#ssh_name-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeSsh(id);
			}
		},{
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function removeSsh(id) {
	$("#ssh-table-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/server/cred/" + id,
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#ssh-table-" + id).remove();
				$('select:regex(id, credentials) option[value=' + id + ']').remove();
				$('select:regex(id, credentials)').selectmenu("refresh");
			},
			404: function (xhr) {
				$("#ssh-table-" + id).remove();
				$('select:regex(id, credentials) option[value=' + id + ']').remove();
				$('select:regex(id, credentials)').selectmenu("refresh");
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data);
				}
			}
		}
	});
}
function uploadSsh() {
    toastr.clear();
    if ($("#ssh-key-name option:selected").val() == "------" || $('#ssh_cert').val() == '') {
        toastr.error('All fields must be completed');
        return false;
    }
	let jsonData = {
		"private_key": $('#ssh_cert').val(),
		"passphrase": $('#ssh-key-pass').val(),
	}
    $.ajax({
        url: "/server/cred/" + $('#ssh-key-name').val().split("_")[0],
        data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
        type: "PATCH",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data.error);
            } else {
                toastr.clear();
                toastr.success('The SSH key has been loaded')
            }
        }
    });
}
function checkSshConnect(ip) {
	$.ajax({
		url: "/server/check/ssh/" + ip,
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data)
			} else if (data.indexOf('failed') != '-1') {
				toastr.error(data)
			} else if (data.indexOf('Errno') != '-1') {
				toastr.error(data)
			} else {
				toastr.clear();
				toastr.success('Connect is accepted');
			}
		}
	});
}
