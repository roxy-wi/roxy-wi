var awesome = "/inc/fontawesome.min.js"
$( function() {
	var add_word = $('#translate').attr('data-add');
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	$( "#backup_tabs" ).tabs();
	$('#install').click(function() {
		$("#ajax").html('')
		var syn_flood = 0;
		var docker = 0;
		if ($('#syn_flood').is(':checked')) {
			syn_flood = '1';
		}
		if ($('#haproxy_docker').is(':checked')) {
			docker = '1';
		}
		if ($('#haproxyaddserv').val() == '------' || $('#haproxyaddserv').val() === null) {
			var select_server = $('#translate').attr('data-select_server');
			toastr.warning(select_server);
			return false
		}
		$("#ajax").html(wait_mess);
		$.ajax( {
			url: "options.py",
			data: {
				haproxyaddserv: $('#haproxyaddserv').val(),
				syn_flood: syn_flood,
				hapver: $('#hapver option:selected' ).val(),
				docker: docker,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajax").html('')
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.remove();
					toastr.success(data);
					$( "#haproxyaddserv" ).trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.remove();
					toastr.info(data);
				} else {
					toastr.remove();
					toastr.info(data);
				}
			}
		} );
	});
	$('#nginx_install').click(function() {
		installService('nginx');
	});
	$('#apache_install').click(function() {
		installService('apache');
	});
	$('#grafna_install').click(function() {
		$("#ajaxmon").html('');
		$("#ajaxmon").html(wait_mess);
		$.ajax( {
			url: "options.py",
			data: {
				install_grafana: '1',
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1' || data.indexOf('ERROR') != '-1') {
					toastr.clear();
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$('#haproxy_exp_install').click(function() {
		$("#ajaxmon").html('')
		$("#ajaxmon").html(wait_mess);
		var ext_prom = 0;
		if ($('#haproxy_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				haproxy_exp_install: $('#haproxy_exp_addserv').val(),
				exporter_v: $('#hapexpver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					toastr.clear();
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$('#cur_haproxy_exp_ver').text('HAProxy exporter is installed');
					$("#haproxy_exp_addserv").trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$('#nginx_exp_install').click(function() {
		$("#ajaxmon").html('')
		$("#ajaxmon").html(wait_mess);
		var ext_prom = 0;
		if ($('#nginx_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				nginx_exp_install: 1,
				serv: $('#nginx_exp_addserv').val(),
				exporter_v: $('#nginxexpver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$('#cur_nginx_exp_ver').text('NGINX exporter is installed');
					$("#nginx_exp_addserv").trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$('#apache_exp_install').click(function() {
		$("#ajaxmon").html('')
		$("#ajaxmon").html(wait_mess);
		var ext_prom = 0;
		if ($('#apache_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				apache_exp_install: 1,
				serv: $('#apache_exp_addserv').val(),
				exporter_v: $('#apacheexpver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$('#cur_apache_exp_ver').text('Apache exporter is installed');
					$("#apache_exp_addserv").trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$('#keepalived_exp_install').click(function() {
		$("#ajaxmon").html('')
		$("#ajaxmon").html(wait_mess);
		var ext_prom = 0;
		if ($('#keepalived_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				keepalived_exp_install: $('#keepalived_exp_addserv').val(),
				exporter_v: $('#keepalivedexpver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$('#cur_keepalived_exp_ver').text('Keepalived exporter is installed');
					$("#keepalived_exp_addserv").trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$('#node_exp_install').click(function() {
		$("#ajaxmon").html('')
		$("#ajaxmon").html(wait_mess);
		var ext_prom = 0;
		if ($('#node_ext_prom').is(':checked')) {
			ext_prom = '1';
		}
		$.ajax( {
			url: "options.py",
			data: {
				node_exp_install: $('#node_exp_addserv').val(),
				exporter_v: $('#nodeexpver').val(),
				ext_prom: ext_prom,
				token: $('#token').val()
				},
			type: "POST",
			success: function( data ) {
			data = data.replace(/\s+/g,' ');
				$("#ajaxmon").html('');
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$('#cur_node_exp_ver').text('Node exporter is installed');
					$("#node_exp_addserv").trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$( "#haproxyaddserv" ).on('selectmenuchange',function() {
		showServiceVersion('haproxy');
	});
	$( "#nginxaddserv" ).on('selectmenuchange',function() {
		showServiceVersion('nginx');
	});
	$( "#apacheaddserv" ).on('selectmenuchange',function() {
		showServiceVersion('apache');
	});
	$( "#haproxy_exp_addserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_exporter_v: 'haproxy_exporter',
				serv: $('#haproxy_exp_addserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if(data == 'no' || data == '' || data.indexOf('No') != '-1') {
					$('#cur_haproxy_exp_ver').text('HAProxy exporter has been not installed');
				} else {
					$('#cur_haproxy_exp_ver').text(data);
				}
			}
		} );
	});
	$( "#nginx_exp_addserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_exporter_v: 'nginx_exporter',
				serv: $('#nginx_exp_addserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if(data == 'no' || data == '' || data.indexOf('No') != '-1') {
					$('#cur_nginx_exp_ver').text('NGINX exporter has not been installed');
				} else {
					$('#cur_nginx_exp_ver').text(data);
				}
			}
		} );
	});
	$( "#apache_exp_addserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_exporter_v: 'apache_exporter',
				serv: $('#apache_exp_addserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if(data == 'no' || data == '' || data.indexOf('No') != '-1') {
					$('#cur_apache_exp_ver').text('Apache exporter has not been installed');
				} else {
					$('#cur_apache_exp_ver').text(data);
				}
			}
		} );
	});
	$( "#keepalived_exp_addserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_exporter_v: 'keepalived_exporter',
				serv: $('#keepalived_exp_addserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if (data.indexOf('keepalived_exporter.service') != '-1') {
					$('#cur_keepalived_exp_ver').text('Keepalived exporter has been installed');
				} else if(data == 'no' || data == '' || data.indexOf('No') != '-1') {
					$('#cur_keepalived_exp_ver').text('Keepalived exporter has not been installed');
				} else {
					$('#cur_keepalived_exp_ver').text(data);
				}
			}
		} );
	});
	$( "#node_exp_addserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_exporter_v: 'node_exporter',
				serv: $('#node_exp_addserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				if (data.indexOf('error:') != '-1') {
					toastr.clear();
					toastr.error(data);
				} else if(data == 'no' || data.indexOf('command') != '-1' || data == '') {
					$('#cur_node_exp_ver').text('Node exporter has not been installed');
				} else {
					$('#cur_node_exp_ver').text(data);
				}
			}
		} );
	});
	$('#add-group-button').click(function() {
		addGroupDialog.dialog('open');
	});
	var group_tabel_title = $( "#group-add-table-overview" ).attr('title');
	var addGroupDialog = $( "#group-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: group_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Add": function() {
				addGroup(this);
			},
			Cancel: function() {
				$( this ).dialog( "close" );
				clearTips();
			}
		}
	});
	$('#add-user-button').click(function() {
		addUserDialog.dialog('open');
	});
	var user_tabel_title = $( "#user-add-table-overview" ).attr('title');
	var add_word = $('#translate').attr('data-add');
	var canerl_word = $('#translate').attr('data-cancel');
	var addUserDialog = $( "#user-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: user_tabel_title,
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
				addUser(this);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	$('#add-server-button').click(function() {
		addServerDialog.dialog('open');
	});
	var server_tabel_title = $( "#server-add-table-overview" ).attr('title');
	var addServerDialog = $( "#server-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: server_tabel_title,
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
				addServer(this);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	$('#add-ssh-button').click(function() {
		addCredsDialog.dialog('open');
	});
	var ssh_tabel_title = $( "#ssh-add-table-overview" ).attr('title');
	var addCredsDialog = $( "#ssh-add-table" ).dialog({
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
	$('#add-telegram-button').click(function() {
		addTelegramDialog.dialog('open');
	});
	$('#add-slack-button').click(function() {
		addSlackDialog.dialog('open');
	});
	$('#add-pd-button').click(function() {
		addPDDialog.dialog('open');
	});
	var telegram_tabel_title = $( "#telegram-add-table-overview" ).attr('title');
	var addTelegramDialog = $( "#telegram-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: telegram_tabel_title,
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
				addRecevier(this, 'telegram');
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	var slack_tabel_title = $( "#slack-add-table-overview" ).attr('title');
	var addSlackDialog = $( "#slack-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: slack_tabel_title,
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
				addRecevier(this, 'slack');
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	var pd_tabel_title = $( "#pd-add-table-overview" ).attr('title');
	var addPDDialog = $( "#pd-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: pd_tabel_title,
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
				addRecevier(this, 'pd');
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
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
	$( "#ajax-users input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateUser(id[1])
	});
	$( "#ajax-users select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateUser(id[1])
	});
	$( "#ajax-group input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateGroup(id[1])
	});
	$( "#ajax-servers input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#ajax-servers select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#ssh_enable_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$( "#ssh_enable_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSSH(id[1])
		sshKeyEnableShow(id[1])
	});
	$( "#settings select" ).on('select2:select',function() {
		var id = $(this).attr('id');
		var val = $(this).val();
		updateSettings(id, val);
		updateSettings(id[1])
	});
	$( "#settings input" ).change(function() {
		var id = $(this).attr('id');
		var val = $(this).val();
		if($('#'+id).is(':checkbox')) {
			if ($('#'+id).is(':checked')){
				val = 1;
			} else {
				val = 0;
			}
		}
		updateSettings(id, val);
	});
	$('#new-ssh_enable').click(function() {
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
   $( "#checker_telegram_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'telegram')
	});
	$( "#checker_telegram_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'telegram')
	});
   $( "#checker_slack_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'slack')
	});
	$( "#checker_slack_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'slack')
	});
   $( "#checker_pd_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'pd')
	});
	$( "#checker_pd_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'pd')
	});
	$( "#ajax-backup-table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$( "#ajax-backup-table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateBackup(id[2])
	});
	$( "#scan_server" ).change(function() {
		if ($('#scan_server').is(':checked')) {
			$('.services_for_scan').hide();
		} else {
			$('.services_for_scan').show();
		}
	});
	$( "#checker_haproxy_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateHaproxyCheckerSettings(id[1])
	});
	$( "#checker_haproxy_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateHaproxyCheckerSettings(id[1])
	});
	$( "#checker_nginx_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'nginx')
	});
	$( "#checker_nginx_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'nginx')
	});
	$( "#checker_apache_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'apache')
	});
	$( "#checker_apache_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'apache')
	});
	$( "#checker_keepalived_table select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateKeepalivedCheckerSettings(id[1])
	});
	$( "#checker_keepalived_table input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateKeepalivedCheckerSettings(id[1])
	});
	$('#search_ldap_user').click(function() {
		var valid = true;
		toastr.clear();
		allFields = $( [] ).add( $('#new-username') );
		allFields.removeClass( "ui-state-error" );
		valid = valid && checkLength( $('#new-username'), "user name", 1 );
		user = $('#new-username').val()
		if (valid) {
			$.ajax( {
				url: "options.py",
				data: {
					get_ldap_email: $('#new-username').val(),
					token: $('#token').val()
				},
				type: "POST",
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if (data.indexOf('error:') != '-1') {
						toastr.error(data);
						$('#new-email').val('');
						$('#new-password').attr('readonly', false);
						$('#new-password').val('');
					} else {
						var json = $.parseJSON(data);
						toastr.clear();
						if (!$('#new-username').val().includes('@')) {
							$('#new-username').val(user + '@' + json[1]);
						}
						$('#new-email').val(json[0]);
						$('#new-password').val('aduser');
						$('#new-password').attr('readonly', true);
					}
				}
			} );
			clearTips();
		}
	});
	$( "#geoipserv" ).on('selectmenuchange',function() {
		if($('#geoip_service option:selected').val() != '------') {
			checkGeoipInstallation();
		}

	});
	$( "#geoip_service" ).on('selectmenuchange',function() {
		if($('#geoipserv option:selected').val() != '------') {
			checkGeoipInstallation();
		}
	});
	$( "#geoip_install" ).click(function() {
		var updating_geoip = 0;
		if ($('#updating_geoip').is(':checked')) {
			updating_geoip = '1';
		}
		$("#ajax-geoip").html(wait_mess);
		$.ajax( {
			url: "options.py",
			data: {
				geoip_install: $('#geoipserv option:selected').val(),
				geoip_service: $('#geoip_service option:selected').val(),
				geoip_update: updating_geoip,
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/^\s+|\s+$/g,'');
				$("#ajax-geoip").html('')
				if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1') {
					toastr.clear();
					var p_err = show_pretty_ansible_error(data);
					toastr.error(p_err);
				} else if (data.indexOf('success:') != '-1' ){
					toastr.clear();
					toastr.success(data);
					$( "#geoip_service" ).trigger( "selectmenuchange" );
				} else if (data.indexOf('Info') != '-1' ){
					toastr.clear();
					toastr.info(data);
				} else {
					toastr.clear();
					toastr.info(data);
				}
			}
		} );
	});
	$("#tabs ul li").click(function() {
		var activeTab = $(this).find("a").attr("href");
		var activeTabClass = activeTab.replace('#', '');
		$('.menu li ul li').each(function () {
			$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
			$(this).find('a').css('padding-left', '20px')
			$(this).children("."+activeTabClass).css('padding-left', '30px');
			$(this).children("."+activeTabClass).css('border-left', '4px solid var(--right-menu-blue-rolor)');
		});
		if (activeTab == '#services') {
			loadServices();
		} else if (activeTab == '#updatehapwi') {
			loadupdatehapwi();
		} else if (activeTab == '#checker'){
			loadchecker();
		} else if (activeTab == '#openvpn'){
			loadopenvpn();
		}
	});
	$("#checker_tabs ul li").click(function() {
		$('.menu li ul li').each(function () {
			$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
			$(this).find('a').css('padding-left', '20px')
			$(this).children(".checker").css('padding-left', '30px');
			$(this).children(".checker").css('border-left', '4px solid var(--right-menu-blue-rolor)');
		});
	});
	$("#backup_tabs ul li").click(function() {
		$('.menu li ul li').each(function () {
			$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
			$(this).find('a').css('padding-left', '20px')
			$(this).children(".backup").css('padding-left', '30px');
			$(this).children(".backup").css('border-left', '4px solid var(--right-menu-blue-rolor)');
		});
	});
} );
window.onload = function() {
	$('#tabs').tabs();
	var activeTabIdx = $('#tabs').tabs('option','active')
	if (cur_url[0].split('#')[0] == 'users.py') {
		if (activeTabIdx == 7) {
			loadServices();
		} else if (activeTabIdx == 8) {
			loadupdatehapwi();
		} else if (activeTabIdx == 4) {
			loadchecker();
		} else if (activeTabIdx == 5) {
			loadopenvpn();
		}
	} else if (cur_url[0].split('#')[0] == 'servers.py') {
		if (activeTabIdx == 3) {
			loadchecker();
		}
	}
}
function common_ajax_action_after_success(dialog_id, new_group, ajax_append_id, data) {
	toastr.clear();
	$("#"+ajax_append_id).append(data);
	$( "."+new_group ).addClass( "update", 1000);
	$.getScript(awesome);
	clearTips();
	$( dialog_id ).dialog("close" );
	setTimeout(function() {
		$( "."+new_group ).removeClass( "update" );
	}, 2500 );
}
function addUser(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#new-username') ).add( $('#new-password') ).add( $('#new-email') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-username'), "user name", 1 );
	valid = valid && checkLength( $('#new-password'), "password", 1 );
	valid = valid && checkLength( $('#new-email'), "Email", 1 );
	var activeuser = 0;
	if ($('#activeuser').is(':checked')) {
		activeuser = '1';
	}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newuser: "1",
				newusername: $('#new-username').val(),
				newpassword: $('#new-password').val(),
				newemail: $('#new-email').val(),
				newrole: $('#new-role').val(),
				activeuser: activeuser,
				page: cur_url[0].split('#')[0],
				newgroupuser: $('#new-group').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var getId = new RegExp('[0-9]+');
					var id = data.match(getId);
					common_ajax_action_after_success(dialog_id, 'user-'+id, 'ajax-users', data);
				}
			}
		} );
	}
}
function addGroup(dialog_id) {
	toastr.clear();
	var valid = true;
	allFields = $( [] ).add( $('#new-group-add') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-group-add'), "new group name", 1 );
	if(valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newgroup: "1",
				groupname: $('#new-group-add').val(),
				newdesc: $('#new-desc').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var getId = new RegExp('[0-9]+');
					var id = data.match(getId);
					$('select:regex(id, group)').append('<option value='+id+'>'+$('#new-group-add').val()+'</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newgroup', 'ajax-group', data);
				}
			}
		} );
	}
}
function addServer(dialog_id) {
	toastr.clear()
	var valid = true;
	var servername = $('#new-server-add').val();
	var newip = $('#new-ip').val();
	var newservergroup = $('#new-server-group-add').val();
	var cred = $('#credentials').val();
	var scan_server = 0;
	var typeip = 0;
	var enable = 0;
	var haproxy = 0;
	var nginx = 0;
	var apache = 0;
	var firewall = 0;
	var add_to_smon = 0;
	if ($('#scan_server').is(':checked')) {
		scan_server = '1';
	}
	if ($('#typeip').is(':checked')) {
		typeip = '1';
	}
	if ($('#enable').is(':checked')) {
		enable = '1';
	}
	if ($('#haproxy').is(':checked')) {
		haproxy = '1';
	}
	if ($('#nginx').is(':checked')) {
		nginx = '1';
	}
	if ($('#apache').is(':checked')) {
		apache = '1';
	}
	if ($('#firewall').is(':checked')) {
		firewall = '1';
	}
	if ($('#add_to_smon').is(':checked')) {
		add_to_smon = '1';
	}
	allFields = $( [] ).add( $('#new-server-add') ).add( $('#new-ip') ).add( $('#new-port') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-server-add'), "Hostname", 1 );
	valid = valid && checkLength( $('#new-ip'), "IP", 1 );
	valid = valid && checkLength( $('#new-port'), "Port", 1 );
	if (cred == null) {
		toastr.error('First select credentials');
		return false;
	}
	if (newservergroup == null) {
		toastr.error('First select a group');
		return false;
	}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newserver: "1",
				servername: servername,
				newip: newip,
				newport: $('#new-port').val(),
				newservergroup: newservergroup,
				typeip: typeip,
				haproxy: haproxy,
				nginx: nginx,
				apache: apache,
				firewall: firewall,
				add_to_smon: add_to_smon,
				enable: enable,
				slave: $('#slavefor' ).val(),
				cred: cred,
				page: cur_url[0].split('#')[0],
				desc: $('#desc').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					common_ajax_action_after_success(dialog_id, 'newserver', 'ajax-servers', data);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( ".controlgroup" ).controlgroup();
					$( "select" ).selectmenu();
					var getId = new RegExp('server-[0-9]+');
					var id = data.match(getId) + '';
					id = id.split('-').pop();
					$('select:regex(id, git-server)').append('<option value=' + id + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, backup-server)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, haproxy_exp_addserv)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, nginx_exp_addserv)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, apache_exp_addserv)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, node_exp_addserv)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, geoipserv)').append('<option value=' + $('#ip-'+id).text() + '>' + $('#hostname-'+id).val() + '</option>').selectmenu("refresh");
					$('select:regex(id, haproxyaddserv)').append('<option value=' + newip + '>' + servername + '</option>').selectmenu("refresh");
					$('select:regex(id, nginxaddserv)').append('<option value=' + newip + '>' + servername + '</option>').selectmenu("refresh");
					$('select:regex(id, apacheaddserv)').append('<option value=' + newip + '>' + servername + '</option>').selectmenu("refresh");
					after_server_creating(servername, newip, scan_server);
				}
			}
		} );
	}
}
function after_server_creating(servername, newip, scan_server) {
	$.ajax({
		url: "options.py",
		data: {
			act: 'after_adding',
			servername: servername,
			newip: newip,
			scan_server: scan_server,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('You should install lshw on the server') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function addCreds(dialog_id) {
	toastr.clear();
	var ssh_enable = 0;
	if ($('#new-ssh_enable').is(':checked')) {
		ssh_enable = '1';
	}
	var valid = true;
	allFields = $( [] ).add( $('#new-ssh-add') ).add( $('#ssh_user') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-ssh-add'), "Name", 1 );
	valid = valid && checkLength( $('#ssh_user'), "Credentials", 1 );
	if(valid) {
		$.ajax({
			url: "options.py",
			data: {
				new_ssh: $('#new-ssh-add').val(),
				new_group: $('#new-sshgroup').val(),
				ssh_user: $('#ssh_user').val(),
				ssh_pass: $('#ssh_pass').val(),
				ssh_enable: ssh_enable,
				page: cur_url[0].split('#')[0],
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var group_name = getGroupNameById($('#new-sshgroup').val());
					var getId = new RegExp('ssh-table-[0-9]+');
					var id = data.match(getId) + '';
					id = id.split('-').pop();
					common_ajax_action_after_success(dialog_id, 'ssh-table-'+id, 'ssh_enable_table', data);
					$('select:regex(id, credentials)').append('<option value=' + id + '>' + $('#new-ssh-add').val() + '</option>').selectmenu("refresh");
					$('select:regex(id, ssh-key-name)').append('<option value=' + $('#new-ssh-add').val() + '_'+group_name+'>' + $('#new-ssh-add').val() + '_'+group_name+'</option>').selectmenu("refresh");
					$("input[type=submit], button").button();
					$("input[type=checkbox]").checkboxradio();
					$("select").selectmenu();
				}
			}
		});
	}
}
function getGroupNameById(group_id) {
	var group_name = ''
	$.ajax({
		url: "options.py",
		async: false,
		data: {
			get_group_name_by_id: group_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				group_name = data;
			}
		}
	});
	return group_name;
}
function addRecevier(dialog_id, receiver_name) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#'+receiver_name+'-token-add') ).add( $('#'+receiver_name+'-chanel-add') );
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#'+receiver_name+'-token-add'), "token", 1 );
	valid = valid && checkLength( $('#'+receiver_name+'-chanel-add'), "channel name", 1 );
	if(valid) {
		toastr.clear();
		$.ajax( {
			url: "options.py",
			data: {
				new_receiver: $('#'+receiver_name+'-token-add').val(),
				receiver_name: receiver_name,
				chanel: $('#'+receiver_name+'-chanel-add').val(),
				group_receiver: $('#new-'+receiver_name+'-group-add').val(),
				page: cur_url[0].split('#')[0],
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					var getId = new RegExp(receiver_name+'-table-[0-9]+');
					var id = data.match(getId) + '';
					id = id.split('-').pop();
					$('select:regex(id, '+receiver_name+'_channel)').append('<option value=' + id + '>' + $('#'+receiver_name+'-chanel-add').val() + '</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newgroup', 'checker_'+receiver_name+'_table', data);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( "select" ).selectmenu();
				}
			}
		} );
	}
}
function addBackup(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#backup-server') ).add( $('#rserver') ).add( $('#rpath') ).add( $('#backup-time') ).add( $('#backup-credentials') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#backup-server'), "backup server ", 1 );
	valid = valid && checkLength( $('#rserver'), "remote server", 1 );
	valid = valid && checkLength( $('#rpath'), "remote path", 1 );
	valid = valid && checkLength( $('#backup-time'), "backup time", 1 );
	valid = valid && checkLength( $('#backup-credentials'), "backup credentials", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				backup: '1',
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
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success: ') != '-1') {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-table', data);
					$( "select" ).selectmenu();
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
				}
			}
		} );
	}
}
function addS3Backup(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#s3-backup-server') ).add( $('#s3_server') ).add( $('#s3_bucket') ).add( $('#s3_secret_key') ).add( $('#s3_access_key') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#s3-backup-server'), "backup server ", 1 );
	valid = valid && checkLength( $('#s3_server'), "S3 server", 1 );
	valid = valid && checkLength( $('#s3_bucket'), "S3 bucket", 1 );
	valid = valid && checkLength( $('#s3_secret_key'), "S3 secret key", 1 );
	valid = valid && checkLength( $('#s3_access_key'), "S3 access key", 1 );
	if (valid) {
		$.ajax( {
			url: "options.py",
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
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success: ') != '-1') {
					common_ajax_action_after_success(dialog_id, 'newbackup', 'ajax-backup-s3-table', data);
					$( "select" ).selectmenu();
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
				} else if (data.indexOf('error: ') != '-1') {
					toastr.clear();
					toastr.error(data);
				}
			}
		} );
	}
}
function addGit(dialog_id) {
	var valid = true;
	toastr.clear();
	allFields = $( [] ).add( $('#git-server') ).add( $('#git-service') ).add( $('#git-time')).add( $('#git-credentials') ).add( $('#git-branch') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#git-server'), "Server ", 1 );
	valid = valid && checkLength( $('#git-service'), "Service", 1 );
	valid = valid && checkLength( $('#git-credentials'), "Credentials", 1 );
	valid = valid && checkLength( $('#git-branch'), "Branch name", 1 );
	var git_init = 0;
	if ($('#git-init').is(':checked')) {
			git_init = '1';
		}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				git_backup: '1',
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
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success: ') != '-1') {
					common_ajax_action_after_success(dialog_id, 'newgit', 'ajax-git-table', data);
					$( "select" ).selectmenu();
				} else if (data.indexOf('info: ') != '-1') {
					toastr.clear();
					toastr.info(data);
				} else if (data.indexOf('warning: ') != '-1') {
					toastr.clear();
					toastr.warning(data);
				}
			}
		} );
	}
}
function updateSettings(param, val) {
	toastr.clear();
	$.ajax( {
		url: "options.py",
		data: {
			updatesettings: param,
			val: val,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#"+param).parent().parent().addClass( "update", 1000 );
			setTimeout(function() {
				$( "#"+param ).parent().parent().removeClass( "update" );
			}, 2500 );
			}
		}
	} );
}
function sshKeyEnableShow(id) {
	$('#ssh_enable-'+id).click(function() {
		if ($('#ssh_enable-'+id).is(':checked')) {
			$('#ssh_pass-'+id).css('display', 'none');
		} else {
			$('#ssh_pass-'+id).css('display', 'block');
		}
	});
	if ($('#ssh_enable-'+id).is(':checked')) {
		$('#ssh_pass-'+id).css('display', 'none');
	} else {
		$('#ssh_pass-'+id).css('display', 'block');
	}
}

function confirmDeleteUser(id) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word + " " +$('#login-'+id).val() + "?",
      buttons: [{
		  text: delete_word,
		  click: function () {
			  $(this).dialog("close");
			  removeUser(id);
		  }
	  }, {
		  text: cancel_word,
		  click: function () {
			  $(this).dialog("close");
		  }
	  }]
    });
}
function confirmDeleteGroup(id) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word+ " " +$('#name-'+id).val() + "?",
      buttons:  [{
		  text: delete_word,
		  click: function() {
			  $(this).dialog("close");
			  removeGroup(id);
		  }
        }, {
		  text: cancel_word,
		  click: function () {
			  $(this).dialog("close");
		  }
	  }]
    });
}
function confirmDeleteServer(id) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#hostname-' + id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeServer(id);
			}
		},{
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function confirmDeleteSsh(id) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
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
function confirmDeleteReceiver(id, reciever_name) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
		 resizable: false,
		 height: "auto",
		 width: 400,
		 modal: true,
		 title: delete_word + " " + $('#' + reciever_name + '-chanel-' + id).val() + "?",
		 buttons: [{
			 text: delete_word,
			 click: function () {
				 $(this).dialog("close");
				 removeReciver(reciever_name, id);
			 }
		 }, {
			 text: cancel_word,
			 click: function () {
				 $(this).dialog("close");
			 }
		 }]
	 });
}
function confirmDeleteBackup(id) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word + " " +$('#backup-server-'+id).val() + "?",
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
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word + " " +$('#backup-s3-server-'+id).val() + "?",
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
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	 $( "#dialog-confirm" ).dialog({
      resizable: false,
      height: "auto",
      width: 400,
      modal: true,
	  title: delete_word + " " +$('#git-server-'+id).text() + "?",
      buttons: [{
		  text: delete_word,
		  click: function () {
			  $(this).dialog("close");
			  removeGit(id);
		  }
	  },{
		  text: cancel_word,
		  click: function () {
			  $(this).dialog("close");
		  }
	  }]
    });
}
function cloneServer(id) {
	$( "#add-server-button" ).trigger( "click" );
	if ($('#enable-'+id).is(':checked')) {
		$('#enable').prop('checked', true)
	} else {
		$('#enable').prop('checked', false)
	}
	if ($('#typeip-'+id).is(':checked')) {
		$('#typeip').prop('checked', true)
	} else {
		$('#typeip').prop('checked', false)
	}
	if ($('#haproxy-'+id).is(':checked')) {
		$('#haproxy').prop('checked', true)
	} else {
		$('#haproxy').prop('checked', false)
	}
	if ($('#nginx-'+id).is(':checked')) {
		$('#nginx').prop('checked', true)
	} else {
		$('#nginx').prop('checked', false)
	}
	$('#enable').checkboxradio("refresh");
	$('#typeip').checkboxradio("refresh");
	$('#haproxy').checkboxradio("refresh");
	$('#nginx').checkboxradio("refresh");
	$('#new-server-add').val($('#hostname-'+id).val())
	$('#new-ip').val($('#ip-'+id).val())
	$('#new-port').val($('#port-'+id).val())
	$('#desc').val($('#desc-'+id).val())
	$('#slavefor').val($('#slavefor-'+id+' option:selected').val()).change()
	$('#slavefor').selectmenu("refresh");
	$('#credentials').val($('#credentials-'+id+' option:selected').val()).change()
	$('#credentials').selectmenu("refresh");
	cur_url = cur_url[0].split('#')[0]
	if (cur_url == 'users.py') {
		$('#new-server-group-add').val($('#servergroup-'+id+' option:selected').val()).change()
		$('#new-server-group-add').selectmenu("refresh");
	}
}
function cloneReceiver(id, reciever_name) {
	$('#add-'+reciever_name+'-button').trigger( "click" );
	$('#'+reciever_name+'-token-add').val($('#'+reciever_name+'-token-'+id).val());
	$('#'+reciever_name+'-chanel-add').val($('#'+reciever_name+'-chanel-'+id).val());
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
function removeUser(id) {
	$("#user-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			userdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#user-"+id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeServer(id) {
	$("#server-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			serverdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#server-"+id).remove();
			} else if (data.indexOf('error: ') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.clear();
				toastr.warning(data);
			}
		}
	} );
}
function removeGroup(id) {
	$("#group-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			groupdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#group-"+id).remove();
				$('select:regex(id, group) option[value='+id+']').remove();
				$('select:regex(id, group)').selectmenu("refresh");
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeSsh(id) {
	$("#ssh-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			sshdel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#ssh-table-"+id).remove();
				$('select:regex(id, credentials) option[value='+id+']').remove();
				$('select:regex(id, credentials)').selectmenu("refresh");
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeReciver(receiver_name, receiver_id) {
	$("#"+receiver_name+"-table-"+receiver_id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			receiver_del: receiver_id,
			receiver_name: receiver_name,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#"+receiver_name+"-table-"+receiver_id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeBackup(id) {
	$("#backup-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			deljob: id,
			cred: $('#backup-credentials-'+id).val(),
			server: $('#backup-server-'+id).text(),
			rserver: $('#backup-rserver-'+id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data.indexOf('Ok') != '-1') {
				$("#backup-table-"+id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeS3Backup(id) {
	$("#backup-table-s3-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			dels3job: id,
			s3_backet: $('#backup-s3-backet-'+id).val(),
			s3_backup_server: $('#backup-s3-server-'+id).text(),
			s3_bucket: $('#s3-bucket-'+id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data.indexOf('Ok') != '-1') {
				$("#s3-backup-table-"+id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function removeGit(id) {
	$("#git-table-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			git_backup: id,
			git_deljob: 1,
			git_init: 0,
			repo: 0,
			branch: 0,
			time: 0,
			cred: $('#git-credentials-id-'+id).text(),
			server: $('#git-server-id-'+id).text(),
			git_service: $('#git-service-id-'+id).text(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data.indexOf('Ok') != '-1') {
				$("#git-table-"+id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function updateUser(id) {
	toastr.remove();
	cur_url[0] = cur_url[0].split('#')[0]
	var usergroup = Cookies.get('group');
	var role = $('#role-'+id).val();
	var activeuser = 0;
	if ($('#activeuser-'+id).is(':checked')) {
		activeuser = '1';
	}
	if (role == null && role !== undefined){
		toastr.warning('Please edit this user only on the Admin area');
		return false;
	}
	toastr.remove();
	$.ajax( {
		url: "options.py",
		data: {
			updateuser: $('#login-'+id).val(),
			email: $('#email-'+id).val(),
			role: role,
			usergroup: usergroup,
			activeuser: activeuser,
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.remove();
				$("#user-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#user-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateGroup(id) {
	toastr.clear();
	$.ajax( {
		url: "options.py",
		data: {
			updategroup: $('#name-'+id).val(),
			descript: $('#descript-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#group-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#group-"+id ).removeClass( "update" );
				}, 2500 );
				$('select:regex(id, group) option[value='+id+']').remove();
				$('select:regex(id, group)').append('<option value='+id+'>'+$('#name-'+id).val()+'</option>').selectmenu("refresh");
			}
		}
	} );
}
function updateServer(id) {
	toastr.clear();
	let typeip = 0;
	let enable = 0;
	let firewall = 0;
	let protected_serv = 0;
	if ($('#typeip-'+id).is(':checked')) {
		typeip = '1';
	}
	if ($('#enable-'+id).is(':checked')) {
		enable = '1';
	}
	if ($('#firewall-'+id).is(':checked')) {
		firewall = '1';
	}
	if ($('#protected-'+id).is(':checked')) {
		protected_serv = '1';
	}
	var servergroup = $('#servergroup-'+id+' option:selected' ).val();
	if (cur_url[0].split('#')[0] == "servers.py") {
		 servergroup = $('#new-server-group-add').val();
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateserver: $('#hostname-'+id).val(),
			port: $('#port-'+id).val(),
			servergroup: servergroup,
			typeip: typeip,
			firewall: firewall,
			enable: enable,
			slave: $('#slavefor-'+id+' option:selected' ).val(),
			cred: $('#credentials-'+id+' option:selected').val(),
			id: id,
			desc: $('#desc-'+id).val(),
			protected: protected_serv,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#server-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#server-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function uploadSsh() {
	toastr.clear();
	if ($( "#ssh-key-name option:selected" ).val() == "------" || $('#ssh_cert').val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				ssh_cert: $('#ssh_cert').val(),
				name: $('#ssh-key-name').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1')  {
						toastr.error(data);
					} else if (data.indexOf('success') != '-1') {
						toastr.clear();
						toastr.success(data)
					} else {
						toastr.error('Something wrong, check and try again');
					}
			}
		} );
	}
}
function updateSSH(id) {
	toastr.clear();
	var ssh_enable = 0;
	if ($('#ssh_enable-'+id).is(':checked')) {
		ssh_enable = '1';
	}
	var group = $('#sshgroup-'+id).val();
	if (cur_url[0].split('#')[0] == "servers.py") {
		 group = $('#new-server-group-add').val();
	}
	$.ajax( {
		url: "options.py",
		data: {
			updatessh: 1,
			name: $('#ssh_name-'+id).val(),
			group: group,
			ssh_enable: ssh_enable,
			ssh_user: $('#ssh_user-'+id).val(),
			ssh_pass: $('#ssh_pass-'+id).val(),
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ssh-table-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#ssh-table-"+id ).removeClass( "update" );
				}, 2500 );
				$('select:regex(id, credentials) option[value='+id+']').remove();
				$('select:regex(id, ssh-key-name) option[value='+$('#ssh_name-'+id).val()+']').remove();
				$('select:regex(id, credentials)').append('<option value='+id+'>'+$('#ssh_name-'+id).val()+'</option>').selectmenu("refresh");
				$('select:regex(id, ssh-key-name)').append('<option value='+$('#ssh_name-'+id).val()+'>'+$('#ssh_name-'+id).val()+'</option>').selectmenu("refresh");
			}
		}
	} );
}
function updateReceiver(id, receiver_name) {
	if (cur_url[0].split('#')[0] == 'servers.py') {
		var group = $('#new-group').val();
	} else {
		var group = $('#'+receiver_name+'group-'+id).val();
	}
	toastr.clear();
	$.ajax( {
		url: "options.py",
		data: {
			receiver_name: receiver_name,
			update_receiver_token: $('#'+receiver_name+'-token-'+id).val(),
			update_receiver_channel: $('#'+receiver_name+'-chanel-'+id).val(),
			update_receiver_group: group,
			id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#"+receiver_name+"-table-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#"+receiver_name+"-table-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateBackup(id) {
	toastr.clear();
	if ($( "#backup-type-"+id+" option:selected" ).val() == "-------" || $('#backup-rserver-'+id).val() == '' || $('#backup-rpath-'+id).val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				backupupdate: id,
				server: $('#backup-server-'+id).text(),
				rserver: $('#backup-rserver-'+id).val(),
				rpath: $('#backup-rpath-'+id).val(),
				type: $('#backup-type-'+id).val(),
				time: $('#backup-time-'+id).val(),
				cred: $('#backup-credentials-'+id).val(),
				description: $('#backup-description-'+id).val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#backup-table-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#backup-table-"+id ).removeClass( "update" );
					}, 2500 );
				}
			}
		} );
	}
}
function updateS3Backup(id) {
	toastr.clear();
	if ($( "#backup-type-"+id+" option:selected" ).val() == "-------" || $('#backup-rserver-'+id).val() == '' || $('#backup-rpath-'+id).val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				s3_backupupdate: id,
				server: $('#backup-server-'+id).text(),
				rserver: $('#backup-rserver-'+id).val(),
				rpath: $('#backup-rpath-'+id).val(),
				type: $('#backup-type-'+id).val(),
				time: $('#backup-time-'+id).val(),
				cred: $('#backup-credentials-'+id).val(),
				description: $('#backup-description-'+id).val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#backup-table-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#backup-table-"+id ).removeClass( "update" );
					}, 2500 );
				}
			}
		} );
	}
}
function showApacheLog(serv) {
	var rows = $('#rows').val()
	var grep = $('#grep').val()
	var exgrep = $('#exgrep').val()
	var hour = $('#time_range_out_hour').val()
	var minut = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minut1 = $('#time_range_out_minut1').val()
	$.ajax( {
		url: "options.py",
		data: {
			rows1: rows,
			serv: serv,
			grep: grep,
			exgrep: exgrep,
			hour: hour,
			minut:minut,
			hour1: hour1,
			minut1: minut1,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0] + "?serv=" + serv + "&rows1=" + rows + "&grep=" + grep +
					'&exgrep=' + exgrep +
					'&hour=' + hour +
					'&minut=' + minut +
					'&hour1=' + hour1 +
					'&minut1=' + minut1);
		}
	} );
}
function checkSshConnect(ip) {
	$.ajax( {
		url: "options.py",
		data: {
			checkSshConnect: 1,
			serv: ip,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data)
			} else if(data.indexOf('failed') != '-1') {
				toastr.error(data)
			} else if(data.indexOf('Errno') != '-1') {
				toastr.error(data)
			} else {
				toastr.clear();
				toastr.success('Connect is accepted');
			}
		}
	} );
}
function openChangeUserPasswordDialog(id) {
	changeUserPasswordDialog(id);
}
function openChangeUserServiceDialog(id) {
	changeUserServiceDialog(id);
}
function changeUserPasswordDialog(id) {
	var cancel_word = $('#translate').attr('data-cancel');
	var superAdmin_pass = $('#translate').attr('data-superAdmin_pass');
	var change_word = $('#translate').attr('data-change2');
	var password_word = $('#translate').attr('data-password');
	if ($('#role-'+id + ' option:selected' ).val() == 'Select a role') {
		toastr.warning(superAdmin_pass);
		return false;
	}
	$( "#user-change-password-table" ).dialog({
			autoOpen: true,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: change_word+ " "+$('#login-'+id).val()+" " +password_word,
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: [{
				text: change_word,
				click: function () {
					changeUserPassword(id, $(this));
				}
			}, {
				text: cancel_word,
				click: function() {
					$(this).dialog("close");
					$('#missmatchpass').hide();
				}
			}]
		});
}
function changeUserPassword(id, d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if(pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		toastr.clear();
		$.ajax( {
			url: "options.py",
			data: {
				updatepassowrd: pass,
				id: id,
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#user-"+id).addClass( "update", 1000 );
					setTimeout(function() {
						$( "#user-"+id ).removeClass( "update" );
					}, 2500 );
					d.dialog( "close" );
				}
			}
		} );
	}
}
function changeUserServiceDialog(id) {
	var cancel_word = $('#translate').attr('data-cancel');
	var manage_word = $('#translate').attr('data-manage');
	var services_word = $('#translate').attr('data-services3');
	var save_word = $('#translate').attr('data-save');
	var superAdmin_services = $('#translate').attr('data-superAdmin_services');
	if ($('#role-'+id + ' option:selected' ).val() == 'Select a role') {
		toastr.warning(superAdmin_services);
		return false;
	}
	$.ajax( {
		url: "options.py",
		data: {
			getuserservices: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('danger') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$('#change-user-service-form').html(data);
				$( "#change-user-service-dialog" ).dialog({
					resizable: false,
					height: "auto",
					width: 700,
					modal: true,
					title: manage_word+" "+$('#login-'+id).val()+" "+services_word,
					buttons: [{
						text: save_word,
						click: function () {
							$(this).dialog("close");
							changeUserServices(id);
						}
					}, {
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}]
				});
			}
		}
	} );
}
function changeUserServices(user_id) {
	var jsonData = {};
	jsonData[user_id] = {};
	$('#checked_services tbody tr').each(function () {
		var this_id = $(this).attr('id').split('-')[1];
		jsonData[user_id][this_id] = {}
	});
	$.ajax( {
		url: "options.py",
		data: {
			changeUserServicesId: user_id,
			jsonDatas: JSON.stringify(jsonData),
			changeUserServicesUser: $('#login-'+user_id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			} else {
				$("#user-" + user_id).addClass("update", 1000);
				setTimeout(function () {
					$("#user-" + user_id).removeClass("update");
				}, 2500);
			}
		}
	} );
}
function addServiceToUser(service_id) {
	var service_name = $('#add_service-'+service_id).attr('data-service_name');
	var delete_word = $('#translate').attr('data-delete');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#checked_services tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="remove_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="removeServiceFromUser('+service_id+')" title="'+delete_word+' '+service_word+'">-</span></td></tr>';
	$('#add_service-'+service_id).remove();
	$("#checked_services tbody").append(html_tag);
}
function removeServiceFromUser(service_id) {
	var service_name = $('#remove_service-'+service_id).attr('data-service_name');
	var add_word = $('#translate').attr('data-add');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#all_services tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="add_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="addServiceToUser('+service_id+')" title="'+add_word+' '+service_word+'">+</span></td></tr>';
	$('#remove_service-'+service_id).remove();
	$("#all_services tbody").append(html_tag);
}
function confirmAjaxServiceAction(action, service) {
	var cancel_word = $('#translate').attr('data-cancel');
	var action_word = $('#translate').attr('data-'+action);
	$( "#dialog-confirm-services" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + service+"?",
		buttons: [{
			text: action_word,
			click: function () {
				$(this).dialog("close");
				ajaxActionServies(action, service)
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function ajaxActionServies(action, service) {
	$.ajax( {
		url: "options.py",
		data: {
			action_service: action,
			serv: service,
			token: $('#token').val()
		},
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.warning(data);
			} else {
				window.history.pushState("services", "services", cur_url[0].split("#")[0] + "#services");
				toastr.success('The ' + service + ' has been ' + action +'ed');
				loadServices();
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function updateService(service, action='update') {
	$("#ajax-update").html('')
	$("#ajax-update").html(wait_mess);
	$.ajax( {
		url: "options.py",
		data: {
			update_roxy_wi: 1,
			service: service,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('Complete!') != '-1' || data.indexOf('Unpacking') != '-1'){
				toastr.clear();
				toastr.success(service + ' has been '+action+'ed');
			} else if (data.indexOf('Unauthorized') != '-1' || data.indexOf('Status code: 401') != '-1') {
				toastr.clear();
				toastr.error('It looks like there is no authorization in the Roxy-WI repository. Your subscription may have expired or there is no subscription. How to get the <b><a href="https://roxy-wi.org/pricing.py" title="Pricing" target="_blank">subscription</a></b>');
			} else if (data.indexOf('but not installed') != '-1') {
				toastr.clear();
				toastr.error('There is setting for Roxy-WI repository, but Roxy-WI is installed without repository. Please reinstall with package manager');
			} else if (data.indexOf('No Match for argument') != '-1' || data.indexOf('Unable to find a match') != '-1') {
				toastr.clear();
				toastr.error('It seems like Roxy-WI repository is not set. Please read docs for <b><a href="https://roxy-wi.org/updates.py">detail</a></b>');
			} else if (data.indexOf('password for') != '-1') {
				toastr.clear();
				toastr.error('It seems like apache user needs to be add to sudoers. Please read docs for <b><a href="https://roxy-wi.org/updates.py">detail</a></b>');
			} else if (data.indexOf('No packages marked for update') != '-1') {
				toastr.clear();
				toastr.info('It seems like the lastest version Roxy-WI is installed');
			} else if (data.indexOf('Connection timed out') != '-1') {
				toastr.clear();
				toastr.error('Cannot connect to Roxy-WI repository. Connection timed out');
			} else if (data.indexOf('--disable') != '-1') {
				toastr.clear();
				toastr.error('It seems like there is a problem with repositories');
			} else if (data.indexOf('Error: Package') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else if (data.indexOf('conflicts with file from') != '-1') {
				toastr.clear();
				toastr.error(data);
			} else if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			}
			$("#ajax-update").html('');
			loadupdatehapwi();
			show_version();
		}
	} );
}
function confirmDeleteOpenVpnProfile(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: "Are you sure you want to delete profile " +id+ "?",
		buttons: {
			"Delete": function() {
				$( this ).dialog( "close" );
				removeOpenVpnProfile(id);
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}

function removeOpenVpnProfile(id) {
	$("#"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			openvpndel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#"+id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	} );
}
function uploadOvpn() {
	toastr.clear();
	if ($( "#ovpn_upload_name" ).val() == '' || $('#ovpn_upload_file').val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				uploadovpn: $('#ovpn_upload_file').val(),
				ovpnname: $('#ovpn_upload_name').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1')  {
					toastr.error(data);
				} else if (data.indexOf('success') != '-1') {
					toastr.clear();
					toastr.success(data)
					location.reload()
				} else {
					toastr.error('Something wrong, check and try again');
				}
			}
		} );
	}
}
function OpenVpnSess(id, action) {
	$.ajax({
		url: "options.py",
		data: {
			actionvpn: action,
			openvpnprofile: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('success') != '-1') {
				toastr.clear();
				toastr.success(data)
				location.reload()
			} else {
				toastr.error('Something wrong, check and try again');
			}
		}
	} );
}
function scanPorts(id) {
	$.ajax({
		url: "options.py",
		data: {
			scan_ports: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#show_scans_ports_body").html(data);
				$("#show_scans_ports" ).dialog({
					resizable: false,
					height: "auto",
					width: 360,
					modal: true,
					title: "Openned ports",
					buttons: {
						Close: function() {
							$( this ).dialog( "close" );
							$("#show_scans_ports_body").html('');
						}
					}
				});
			}
		}
	} );
}
function viewFirewallRules(id) {
	$.ajax({
		url: "options.py",
		data: {
			viewFirewallRules: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#firewall_rules_body").html(data);
				$("#firewall_rules" ).dialog({
					resizable: false,
					height: "auto",
					width: 860,
					modal: true,
					title: "Firewall rules",
					buttons: {
						Close: function() {
							$( this ).dialog( "close" );
							$("#firewall_rules_body").html('');
						}
					}
				});
			}
		}
	} );
}
function loadServices() {
	$.ajax({
		url: "options.py",
		data: {
			loadservices: 1,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#ajax-services-body').html(data);
				$.getScript(awesome);
			}
		}
	} );
}
function loadupdatehapwi() {
	$.ajax({
		url: "options.py",
		data: {
			load_update_hapwi: 1,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#ajax-updatehapwi-body').html(data);
			}
		}
	} );
}
function loadchecker(tab = 0) {
	$.ajax({
		url: "options.py",
		data: {
			loadchecker: 1,
			page: cur_url[0].split('#')[0],
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('group_error') == '-1' && data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#checker').html(data);
				$( "select" ).selectmenu();
				$("button").button();
				$( "input[type=checkbox]" ).checkboxradio();
				$.getScript('/inc/users.js');
				$.getScript(awesome);
				$( "#checker_tabs" ).tabs( "option", "active", tab );
			}
		}
	} );
}
function loadopenvpn() {
	$.ajax({
		url: "options.py",
		data: {
			loadopenvpn: 1,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('group_error') == '-1' && data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#openvpn').html(data);
				$.getScript(awesome);
			}
		}
	} );
}
function checkReceiver(channel_id, receiver_name) {
	$.ajax({
		url: "options.py",
		data: {
			check_receiver: 1,
			receiver_channel_id: channel_id,
			receiver_name: receiver_name,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
				toastr.error(data);
			} else {
				toastr.success('Test message has been sent');
			}
		}
	} );
}
function updateServerInfo(ip, id) {
	$.ajax({
			url: "options.py",
			data: {
				act: 'updateSystemInfo',
				server_ip: ip,
				server_id: id,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
					toastr.error(data);
				} else {
					$("#server_info-"+id).html(data);
					$('#server_info-'+id).show();
					$('#server_info_link-'+id).attr('title', 'Hide System info');
					$.getScript(awesome);
				}
			}
		} );
}
function showServerInfo(id, ip) {
	var close_word = $('#translate').attr('data-close');
	var server_info = $('#translate').attr('data-server_info');
	$.ajax({
		url: "options.py",
		data: {
			act: 'getSystemInfo',
			server_ip: ip,
			server_id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
				toastr.error(data);
			} else {
				$("#server-info").html(data);
				$("#dialog-server-info").dialog({
					resizable: false,
					height: "auto",
					width: 1000,
					modal: true,
					title: server_info + " (" + ip + ")",
					buttons: [{
						text: close_word,
						click: function () {
							$(this).dialog("close");
						}
					}]
				});
				$.getScript(awesome);
			}
		}
	} );
}
function updateHaproxyCheckerSettings(id) {
	toastr.clear();
	let email = 0;
	let server = 0;
	let backend = 0;
	let maxconn = 0;
	if ($('#haproxy_server_email-'+id).is(':checked')) {
		email = '1';
	}
	if ($('#haproxy_server_status-'+id).is(':checked')) {
		server = '1';
	}
	if ($('#haproxy_server_backend-'+id).is(':checked')) {
		backend = '1';
	}
	if ($('#haproxy_server_maxconn-'+id).is(':checked')) {
		maxconn = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateHaproxyCheckerSettings: id,
			email: email,
			server: server,
			backend: backend,
			maxconn: maxconn,
			telegram_id: $('#haproxy_server_telegram_channel-'+id+' option:selected' ).val(),
			slack_id: $('#haproxy_server_slack_channel-'+id+' option:selected').val(),
			pd_id: $('#haproxy_server_pd_channel-'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$("#haproxy_server_tr_id-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#haproxy_server_tr_id-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateKeepalivedCheckerSettings(id) {
	toastr.clear();
	let email = 0;
	let server = 0;
	let backend = 0;
	if ($('#keepalived_server_email-'+id).is(':checked')) {
		email = '1';
	}
	if ($('#keepalived_server_status-'+id).is(':checked')) {
		server = '1';
	}
	if ($('#keepalived_server_backend-'+id).is(':checked')) {
		backend = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateKeepalivedCheckerSettings: id,
			email: email,
			server: server,
			backend: backend,
			telegram_id: $('#keepalived_server_telegram_channel-'+id+' option:selected' ).val(),
			slack_id: $('#keepalived_server_slack_channel-'+id+' option:selected').val(),
			pd_id: $('#keepalived_server_pd_channel-'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$("#keepalived_server_tr_id-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#keepalived_server_tr_id-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function updateServiceCheckerSettings(id, service_name) {
	toastr.clear();
	let email = 0;
	let server = 0;
	if ($('#'+service_name+'_server_email-'+id).is(':checked')) {
		email = '1';
	}
	if ($('#'+service_name+'_server_status-'+id).is(':checked')) {
		server = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateServiceCheckerSettings: id,
			email: email,
			server: server,
			telegram_id: $('#'+service_name+'_server_telegram_channel-'+id+' option:selected' ).val(),
			slack_id: $('#'+service_name+'_server_slack_channel-'+id+' option:selected').val(),
			pd_id: $('#'+service_name+'_server_pd_channel-'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$('#'+service_name+'_server_tr_id-'+id).addClass( "update", 1000 );
				setTimeout(function() {
					$('#'+service_name+'_server_tr_id-'+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function checkWebPanel() {
	$.ajax({
	  url: "options.py",
	  data: {
		  check_rabbitmq_alert: 1,
		  token: $('#token').val()
	  },
	  type: "POST",
	  success: function (data) {
		  data = data.replace(/\s+/g, ' ');
		  if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
			  toastr.error(data);
		  } else {
			  toastr.success('Test message has been sent');
		  }
	  }
	});
}
function checkEmail() {
	$.ajax({
	  url: "options.py",
	  data: {
		  check_email_alert: 1,
		  token: $('#token').val()
	  },
	  type: "POST",
	  success: function (data) {
		  data = data.replace(/\s+/g, ' ');
		  if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
			  toastr.error(data);
		  } else {
			  toastr.success('Test message has been sent');
		  }
	  }
	});
}
function checkGeoipInstallation() {
	$.ajax( {
		url: "options.py",
		data: {
			geoipserv: $('#geoipserv option:selected').val(),
			geoip_service: $('#geoip_service option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/^\s+|\s+$/g,'');
			if(data.indexOf('No such file or directory') != '-1' || data.indexOf('cannot access') != '-1') {
				$('#cur_geoip').html('<b style="color: var(--red-color)">GeoIPLite is not installed</b>');
				$('#geoip_install').show();
			} else {
				$('#cur_geoip').html('<b style="color: var(--green-color)">GeoIPLite is installed<b>');
				$('#geoip_install').hide();
			}
		}
	} );
}
function installService(service){
	$("#ajax").html('')
	var syn_flood = 0;
	var docker = 0;
	if ($('#'+service+'_syn_flood').is(':checked')) {
		syn_flood = '1';
	}
	if ($('#'+service+'_docker').is(':checked')) {
		docker = '1';
	}
	if ($('#'+service+'addserv').val() == '------') {
		var select_server = $('#translate').attr('data-select_server');
		toastr.warning(select_server);
		return false
	}
	$("#ajax").html(wait_mess);
	$.ajax( {
		url: "options.py",
		data: {
			install_service: $('#' + service + 'addserv').val(),
			service: service,
			syn_flood: syn_flood,
			docker: docker,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			$("#ajax").html('')
			if (data.indexOf('error:') != '-1' || data.indexOf('FAILED') != '-1' || data.indexOf('UNREACHABLE') != '-1') {
				toastr.clear();
				var p_err = show_pretty_ansible_error(data);
				toastr.error(p_err);
			} else if (data.indexOf('success') != '-1' ){
				toastr.clear();
				toastr.success(data);
				$('#'+service+'addserv').trigger( "selectmenuchange" );
			} else if (data.indexOf('Info') != '-1' ){
				toastr.clear();
				toastr.info(data);
			} else {
				toastr.clear();
				toastr.info(data);
			}
		}
	} );
}
function showServiceVersion(service) {
	$.ajax({
		url: "options.py",
		data: {
			get_service_v: service,
			serv: $('#'+service+'addserv option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('bash') != '-1' || data.indexOf('such') != '-1' || data.indexOf('command not found') != '-1' || data.indexOf('from') != '-1') {
				$('#cur_'+service+'_ver').text(service+' has not installed');
				$('#'+service+'_install').text('Install');
				$('#'+service+'_install').attr('title', 'Install');
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.warning(data);
			} else if (data == '') {
				$('#cur_'+service+'_ver').text(service+' has not installed');
				$('#'+service+'_install').text('Install');
				$('#'+service+'_install').attr('title', 'Install');
			} else {
				$('#cur_'+service+'_ver').text(data);
				$('#cur_'+service+'_ver').css('font-weight', 'bold');
				$('#'+service+'_install').text('Update');
				$('#'+service+'_install').attr('title', 'Update');
			}
		}
	} );
}
function serverIsUp(server_ip, server_id) {
	var cur_url = window.location.href.split('/').pop();
	if (cur_url.split('#')[1] == 'servers') {
		$.ajax({
			url: "options.py",
			data: {
				act: 'server_is_up',
				server_is_up: server_ip,
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/^\s+|\s+$/g, '');
				if (data.indexOf('up') != '-1') {
					$('#server_status-' + server_id).removeClass('serverNone');
					$('#server_status-' + server_id).removeClass('serverDown');
					$('#server_status-' + server_id).addClass('serverUp');
					$('#server_status-' + server_id).attr('title', 'Server is reachable');
				} else if (data.indexOf('down') != '-1') {
					$('#server_status-' + server_id).removeClass('serverNone');
					$('#server_status-' + server_id).removeClass('serverUp');
					$('#server_status-' + server_id).addClass('serverDown');
					$('#server_status-' + server_id).attr('title', 'Server is unreachable');
				} else {
					$('#server_status-' + server_id).removeClass('serverDown');
					$('#server_status-' + server_id).removeClass('serverUp');
					$('#server_status-' + server_id).addClass('serverNone');
					$('#server_status-' + server_id).attr('title', 'Cannot get server status');
				}
			}
		});
	}
}
function confirmChangeGroupsAndRoles(user_id) {
	var cancel_word = $('#translate').attr('data-cancel');
	var action_word = $('#translate').attr('data-save');
	var user_groups_word = $('#translate').attr('data-user_groups');
	var username = $('#login-'+user_id).val();
	$.ajax({
		url: "options.py",
		data: {
			act: 'show_user_group_and_role',
			user_id: user_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			$("#groups-roles").html(data);
			$("#groups-roles").dialog({
				resizable: false,
				height: "auto",
				width: 700,
				modal: true,
				title: user_groups_word + ' ' + username,
				buttons: [{
					text: action_word,
					click: function () {
						saveGroupsAndRoles(user_id);
						$(this).dialog("close");
					}
				}, {
					text: cancel_word,
					click: function () {
						$(this).dialog("close");
					}
				}]
			});
		}
	});
}
function addGroupToUser(group_id) {
	var group_name = $('#add_group-'+group_id).attr('data-group_name');
	var delete_word = $('#translate').attr('data-delete');
	var group2_word = $('#translate').attr('data-group2');
	var length_tr = $('#all_groups tbody tr').length;
	const roles = {1: 'superAdmin', 2: 'amdin', 3: 'user', 4: 'guest'};
	var options_roles = '';
	for (const [role_id, role_name] of Object.entries(roles)) {
		options_roles += '<option value="'+role_id+'">'+role_name+'</option>';
	}
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="remove_group-'+group_id+'" data-group_name="'+group_name+'">\n' +
		'        <td class="padding20" style="width: 50%;">'+group_name+'</td>\n' +
		'        <td style="width: 50%;">\n' +
		'            <select id="add_role-'+group_id+'">'+options_roles+'</select></td>\n' +
		'        <td><span class="remove_user_group" onclick="removeGroupFromUser('+group_id+')" title="'+delete_word+' '+group2_word+'">-</span></td></tr>'
	$('#add_group-'+group_id).remove();
	$("#checked_groups tbody").append(html_tag);
}
function removeGroupFromUser(group_id) {
	var group_name = $('#remove_group-'+group_id).attr('data-group_name');
	var add_word = $('#translate').attr('data-add');
	var group2_word = $('#translate').attr('data-group2');
	var length_tr = $('#all_groups tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="add_group-'+group_id+'" data-group_name='+group_name+'>\n' +
		'    <td class="padding20" style="width: 100%">'+group_name+'</td>\n' +
		'    <td><span class="add_user_group" title="'+add_word+' '+group2_word+'" onclick="addGroupToUser('+group_id+')">+</span></td></tr>'
	$('#remove_group-'+group_id).remove();
	$("#all_groups tbody").append(html_tag);
}
function saveGroupsAndRoles(user_id) {
	var length_tr = $('#checked_groups tbody tr').length;
	var jsonData = {};
	jsonData[user_id] = {};
	$('#checked_groups tbody tr').each(function () {
		var this_id = $(this).attr('id').split('-')[1];
		var role_id = $('#add_role-'+this_id).val();
		jsonData[user_id][this_id] = {'role_id': role_id};
	});
	$.ajax({
		url: "options.py",
		data: {
			act: 'save_user_group_and_role',
			changeUserGroupsUser: $('#login-'+user_id).val(),
			jsonDatas: JSON.stringify(jsonData),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.warning(data);
			} else {
				$("#user-"+user_id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#user-"+user_id ).removeClass( "update" );
				}, 2500 );
			}
		}
	});
}
function openChangeServerServiceDialog(server_id) {
	var cancel_word = $('#translate').attr('data-cancel');
	var action_word = $('#translate').attr('data-save');
	var user_groups_word = $('#translate').attr('data-user_groups');
	var hostname = $('#hostname-'+server_id).val();
	$.ajax({
		url: "options.py",
		data: {
			act: 'show_server_services',
			server_id: server_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			$("#groups-roles").html(data);
			$("#groups-roles").dialog({
				resizable: false,
				height: "auto",
				width: 700,
				modal: true,
				title: user_groups_word + ' ' + hostname,
				buttons: [{
					text: action_word,
					click: function () {
						changeServerServices(server_id);
						$(this).dialog("close");
					}
				}, {
					text: cancel_word,
					click: function () {
						$(this).dialog("close");
					}
				}]
			});
		}
	});
}
function addServiceToServer(service_id) {
	var service_name = $('#add_service-'+service_id).attr('data-service_name');
	var delete_word = $('#translate').attr('data-delete');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#checked_services tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="remove_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="removeServiceFromUser('+service_id+')" title="'+delete_word+' '+service_word+'">-</span></td></tr>';
	$('#add_service-'+service_id).remove();
	$("#checked_services tbody").append(html_tag);
}
function removeServiceFromServer(service_id) {
	var service_name = $('#remove_service-'+service_id).attr('data-service_name');
	var add_word = $('#translate').attr('data-add');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#all_services tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<tr class="'+tr_class+'" id="add_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="addServiceToUser('+service_id+')" title="'+add_word+' '+service_word+'">+</span></td></tr>';
	$('#remove_service-'+service_id).remove();
	$("#all_services tbody").append(html_tag);
}
function changeServerServices(server_id) {
	var jsonData = {};
	$('#checked_services tbody tr').each(function () {
		var this_id = $(this).attr('id').split('-')[1];
		jsonData[this_id] = 1
	});
	$('#all_services tbody tr').each(function () {
		var this_id = $(this).attr('id').split('-')[1];
		jsonData[this_id] = 0
	});
	$.ajax( {
		url: "options.py",
		data: {
			changeServerServicesId: server_id,
			jsonDatas: JSON.stringify(jsonData),
			changeServerServicesServer: $('#hostname-'+server_id).val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			} else {
				$("#server-" + server_id).addClass("update", 1000);
				setTimeout(function () {
					$("#server-" + server_id).removeClass("update");
				}, 2500);
			}
		}
	} );
}
