$( function() {
    $("#backup_tabs").tabs();
    $('#add-backup-button').click(function() {
		addBackupDialog.dialog('open');
	});
	let backup_tabel_title = $( "#backup-add-table-overview" ).attr('title');
	let addBackupDialog = $( "#backup-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: backup_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Add": function () {
				addBackup(this);
			},
			Cancel: function () {
				$(this).dialog("close");
				clearTips();
			}
		}
	});
	$('#add-backup-s3-button').click(function() {
		addS3BackupDialog.dialog('open');
	});
	let s3_backup_tabel_title = $( "#s3-backup-add-table-overview" ).attr('title');
	let addS3BackupDialog = $( "#s3-backup-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: s3_backup_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Add": function () {
				addS3Backup(this);
			},
			Cancel: function () {
				$(this).dialog("close");
				clearTips();
			}
		}
	});
	$('#add-git-button').click(function() {
		addGitDialog.dialog('open');
	});
	let git_tabel_title = $( "#git-add-table-overview" ).attr('title');
	let addGitDialog = $( "#git-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: git_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Add": function () {
				addGit(this);
			},
			Cancel: function () {
				$(this).dialog("close");
				clearTips();
			}
		}
	});
	$('#git-init').click(function() {
		if ($('#git-init').is(':checked')) {
			$('.git-init-params').show();
		} else {
			$('.git-init-params').hide();
		}
	});
	$( "#ajax-backup-table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$( "#ajax-backup-table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$("#backup_tabs ul li").click(function() {
		$('.menu li ul li').each(function () {
			$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
			$(this).find('a').css('padding-left', '20px')
			$(this).children(".backup").css('padding-left', '30px');
			$(this).children(".backup").css('border-left', '4px solid var(--right-menu-blue-rolor)');
		});
	});
});
function loadBackup() {
	$.ajax({
		url: "/server/backup",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#backup').html(data);
				$.getScript('/static/js/backup.js');
				$("select").selectmenu();
				$.getScript(awesome);
			}
		}
	});
}
function addBackup(dialog_id) {
	let valid = true;
	toastr.clear();
	let allFields = $([]).add($('#backup-server')).add($('#rserver')).add($('#rpath')).add($('#backup-time')).add($('#backup-credentials'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#backup-server'), "backup server ", 1);
	valid = valid && checkLength($('#rserver'), "remote server", 1);
	valid = valid && checkLength($('#rpath'), "remote path", 1);
	valid = valid && checkLength($('#backup-time'), "backup time", 1);
	valid = valid && checkLength($('#backup-credentials'), "backup credentials", 1);
	if (valid) {
		let jsonData = {
			"server": $('#backup-server').val(),
			"rserver": $('#rserver').val(),
			"rpath": $('#rpath').val(),
			"type": $('#backup-type').val(),
			"time": $('#backup-time').val(),
			"cred_id": $('#backup-credentials').val(),
			"description": $('#backup-description').val()
		}
		$.ajax({
			url: "/server/backup",
			data: JSON.stringify(jsonData),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-table', data.data);
					$("select").selectmenu();
				}
			}
		});
	}
}
function addS3Backup(dialog_id) {
	let valid = true;
	toastr.clear();
	let allFields = $([]).add($('#s3-backup-server')).add($('#s3_server')).add($('#s3_bucket')).add($('#s3_secret_key')).add($('#s3_access_key'))
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#s3-backup-server'), "backup server ", 1);
	valid = valid && checkLength($('#s3_server'), "S3 server", 1);
	valid = valid && checkLength($('#s3_bucket'), "S3 bucket", 1);
	valid = valid && checkLength($('#s3_secret_key'), "S3 secret key", 1);
	valid = valid && checkLength($('#s3_access_key'), "S3 access key", 1);
	if (valid) {
		let json_data = {
			"s3_server": $('#s3-backup-server').val(),
			"server": $('#s3_server').val(),
			"bucket": $('#s3_bucket').val(),
			"secret_key": $('#s3_secret_key').val(),
			"access_key": $('#s3_access_key').val(),
			"time": $('#s3-backup-time').val(),
			"description": $('#s3-backup-description').val(),
		}
		$.ajax({
			url: "/server/backup/s3",
			data: JSON.stringify(json_data),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data);
				} else {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-s3-table', data.data);
					$("select").selectmenu();
				}
			}
		});
	}
}
function addGit(dialog_id) {
	toastr.clear();
	let valid = true;
	let server_div = $('#git-server');
	let service_div = $('#git-service');
	let branch_div = $('#git-branch');
	let time_div = $('#git-time');
	let cred_div = $('#git-credentials');
	let git_init = 0;
	if ($('#git-init').is(':checked')) {
		git_init = '1';
	}
	let allFields = $([]).add(server_div).add(service_div).add(time_div).add(cred_div).add(branch_div);
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength(server_div, "Server ", 1);
	valid = valid && checkLength(service_div, "Service", 1);
	valid = valid && checkLength(cred_div, "Credentials", 1);
	valid = valid && checkLength(branch_div, "Branch name", 1);
	if (valid) {
		let jsonData = {
			"server": server_div.val(),
			"service": service_div.val(),
			"init": git_init,
			"repo": $('#git-repo').val(),
			"branch": branch_div.val(),
			"time": time_div.val(),
			"cred": cred_div.val(),
			"del_job": 0,
			"desc": $('#git-description').text(),
		}
		$.ajax({
			url: "/server/git",
			data: JSON.stringify(jsonData),
			contentType: "application/json; charset=utf-8",
			type: "POST",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					common_ajax_action_after_success(dialog_id, 'newgit', 'ajax-git-table', data.data);
					$("select").selectmenu();
				}
			}
		});
	}
}
function confirmDeleteBackup(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#backup-server-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeBackup(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function confirmDeleteS3Backup(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#backup-s3-server-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeS3Backup(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function confirmDeleteGit(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#git-server-' + id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeGit(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function cloneBackup(id) {
	$( "#add-backup-button" ).trigger( "click" );
	$('#rserver').val($('#backup-rserver-'+id).val())
	$('#rpath').val($('#backup-rpath-'+id).val())
	$('#backup-type').val($('#backup-type-'+id+' option:selected').val()).change()
	$('#backup-type').selectmenu("refresh");
	$('#backup-time').val($('#backup-time-'+id+' option:selected').val()).change()
	$('#backup-time').selectmenu("refresh");
	$('#backup-credentials').val($('#backup-credentials-'+id+' option:selected').val()).change()
	$('#backup-credentials').selectmenu("refresh");
}
function cloneS3Backup(id) {
	$( "#add-backup-s3-button" ).trigger( "click" );
	$('#s3_server').val($('#s3-server-'+id).text())
	$('#s3_bucket').val($('#bucket-'+id).text())
	$('#s3-backup-description').val($('#s3-backup-description--'+id).text())
	$('#s3-backup-server').val($('#backup-s3-server-'+id).text()).change();
	$('#s3-backup-server').selectmenu("refresh");
	$('#s3-backup-time').val($('#s3-backup-time-'+id).text()).change();
	$('#s3-backup-time').selectmenu("refresh");
}
function removeBackup(id) {
	$("#backup-table-" + id).css("background-color", "#f2dede");
	let jsonData = {
		"cred_id": $('#backup-credentials-' + id).val(),
		"server": $('#backup-server-' + id).text(),
	}
	$.ajax({
		url: api_prefix + "/server/backup/fs/" + id,
		data: JSON.stringify(jsonData),
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#backup-table-" + id).remove();
			},
			404: function (xhr) {
				$("#backup-table-" + id).remove();
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
function removeS3Backup(id) {
	$("#backup-table-s3-" + id).css("background-color", "#f2dede");
	let jsonData = {
		"bucket": $('#bucket-' + id).text(),
		"server": $('#backup-s3-server-' + id).text(),
	}
	$.ajax({
		url: api_prefix + "/server/backup/s3/" + id,
		data: JSON.stringify(jsonData),
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#s3-backup-table-" + id).remove();
			},
			404: function (xhr) {
				$("#s3-backup-table-" + id).remove();
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
function removeGit(id) {
	$("#git-table-" + id).css("background-color", "#f2dede");
	let jsonData = {
		"backup_id": id,
		"del_job": 1,
		"init": 0,
		"repo": 0,
		"branch": 0,
		"time": 0,
		"cred": $('#git-credentials-id-' + id).text(),
		"server": $('#git-server-id-' + id).text(),
		"service": $('#git-service-id-' + id).text(),
		"desc": '',
	}
	$.ajax({
		url: "/server/git",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "DELETE",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$("#git-table-" + id).remove();
			}
		}
	});
}
function updateBackup(id) {
	toastr.clear();
	if ($("#backup-type-" + id + " option:selected").val() == "-------" || $('#backup-rserver-' + id).val() == '' || $('#backup-rpath-' + id).val() == '') {
		toastr.error('All fields must be completed');
	} else {
		let jsonData = {
			"server": $('#backup-server-' + id).text(),
			"rserver": $('#backup-rserver-' + id).val(),
			"rpath": $('#backup-rpath-' + id).val(),
			"type": $('#backup-type-' + id).val(),
			"time": $('#backup-time-' + id).val(),
			"cred_id": $('#backup-credentials-' + id).val(),
			"description": $('#backup-description-' + id).val()
		}
		$.ajax({
			url: api_prefix + "/server/backup/fs/" + id,
			data: JSON.stringify(jsonData),
			type: "PUT",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					toastr.clear();
					$("#backup-table-" + id).addClass("update", 1000);
					setTimeout(function () {
						$("#backup-table-" + id).removeClass("update");
					}, 2500);
				}
			}
		});
	}
}
