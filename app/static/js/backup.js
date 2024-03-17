$( function() {
    $("#backup_tabs").tabs();
    $('#add-backup-button').click(function() {
		addBackupDialog.dialog('open');
	});
	var backup_tabel_title = $( "#backup-add-table-overview" ).attr('title');
	var addBackupDialog = $( "#backup-add-table" ).dialog({
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
	var s3_backup_tabel_title = $( "#s3-backup-add-table-overview" ).attr('title');
	var addS3BackupDialog = $( "#s3-backup-add-table" ).dialog({
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
	var git_tabel_title = $( "#git-add-table-overview" ).attr('title');
	var addGitDialog = $( "#git-add-table" ).dialog({
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
		var id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$( "#ajax-backup-table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
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
		url: "/app/server/backup",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#backup').html(data);
				$.getScript('/app/static/js/backup.js');
				$("select").selectmenu();
				$.getScript(awesome);
			}
		}
	});
}
function addBackup(dialog_id) {
	var valid = true;
	toastr.clear();
	let allFields = $([]).add($('#backup-server')).add($('#rserver')).add($('#rpath')).add($('#backup-time')).add($('#backup-credentials'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#backup-server'), "backup server ", 1);
	valid = valid && checkLength($('#rserver'), "remote server", 1);
	valid = valid && checkLength($('#rpath'), "remote path", 1);
	valid = valid && checkLength($('#backup-time'), "backup time", 1);
	valid = valid && checkLength($('#backup-credentials'), "backup credentials", 1);
	if (valid) {
		$.ajax({
			url: "/app/server/backup/create",
			data: {
				server: $('#backup-server').val(),
				rserver: $('#rserver').val(),
				rpath: $('#rpath').val(),
				type: $('#backup-type').val(),
				time: $('#backup-time').val(),
				cred: $('#backup-credentials').val(),
				description: $('#backup-description').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
				} else {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-table', data);
					$("select").selectmenu();
				}
			}
		});
	}
}
function addS3Backup(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $([]).add($('#s3-backup-server')).add($('#s3_server')).add($('#s3_bucket')).add($('#s3_secret_key')).add($('#s3_access_key'))
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#s3-backup-server'), "backup server ", 1);
	valid = valid && checkLength($('#s3_server'), "S3 server", 1);
	valid = valid && checkLength($('#s3_bucket'), "S3 bucket", 1);
	valid = valid && checkLength($('#s3_secret_key'), "S3 secret key", 1);
	valid = valid && checkLength($('#s3_access_key'), "S3 access key", 1);
	if (valid) {
		$.ajax({
			url: "/app/server/s3backup/create",
			data: {
				s3_backup_server: $('#s3-backup-server').val(),
				s3_server: $('#s3_server').val(),
				s3_bucket: $('#s3_bucket').val(),
				s3_secret_key: $('#s3_secret_key').val(),
				s3_access_key: $('#s3_access_key').val(),
				time: $('#s3-backup-time').val(),
				description: $('#s3-backup-description').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
				} else if (data.indexOf('error: ') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-s3-table', data);
					$("select").selectmenu();
				}
			}
		});
	}
}
function addGit(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $([]).add($('#git-server')).add($('#git-service')).add($('#git-time')).add($('#git-credentials')).add($('#git-branch'))
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#git-server'), "Server ", 1);
	valid = valid && checkLength($('#git-service'), "Service", 1);
	valid = valid && checkLength($('#git-credentials'), "Credentials", 1);
	valid = valid && checkLength($('#git-branch'), "Branch name", 1);
	var git_init = 0;
	if ($('#git-init').is(':checked')) {
		git_init = '1';
	}
	if (valid) {
		$.ajax({
			url: "/app/server/git/create",
			data: {
				server: $('#git-server').val(),
				git_service: $('#git-service').val(),
				git_init: git_init,
				git_repo: $('#git-repo').val(),
				git_branch: $('#git-branch').val(),
				time: $('#git-time').val(),
				cred: $('#git-credentials').val(),
				description: $('#git-description').val(),
				git_deljob: 0,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success: ') != '-1') {
					common_ajax_action_after_success(dialog_id, 'newgit', 'ajax-git-table', data);
					$("select").selectmenu();
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
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
function removeBackup(id) {
	$("#backup-table-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/app/server/backup/delete",
		data: {
			deljob: id,
			cred: $('#backup-credentials-' + id).val(),
			server: $('#backup-server-' + id).text(),
			rserver: $('#backup-rserver-' + id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('ok') != '-1') {
				$("#backup-table-" + id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	});
}
function removeS3Backup(id) {
	$("#backup-table-s3-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/app/server/s3backup/delete",
		data: {
			dels3job: id,
			s3_bucket: $('#bucket-' + id).text(),
			s3_backup_server: $('#backup-s3-server-' + id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('ok') != '-1') {
				$("#s3-backup-table-" + id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	});
}
function removeGit(id) {
	$("#git-table-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/app/server/git/delete",
		data: {
			git_backup: id,
			git_deljob: 1,
			git_init: 0,
			repo: 0,
			branch: 0,
			time: 0,
			cred: $('#git-credentials-id-' + id).text(),
			server: $('#git-server-id-' + id).text(),
			git_service: $('#git-service-id-' + id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('ok') != '-1') {
				$("#git-table-" + id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	});
}
function updateBackup(id) {
	toastr.clear();
	if ($("#backup-type-" + id + " option:selected").val() == "-------" || $('#backup-rserver-' + id).val() == '' || $('#backup-rpath-' + id).val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax({
			url: "/app/server/backup/update",
			data: {
				backupupdate: id,
				server: $('#backup-server-' + id).text(),
				rserver: $('#backup-rserver-' + id).val(),
				rpath: $('#backup-rpath-' + id).val(),
				type: $('#backup-type-' + id).val(),
				time: $('#backup-time-' + id).val(),
				cred: $('#backup-credentials-' + id).val(),
				description: $('#backup-description-' + id).val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
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
