$( function() {
    $( "#checker_haproxy_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateHaproxyCheckerSettings(id[1])
	});
	$( "#checker_haproxy_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateHaproxyCheckerSettings(id[1])
	});
	$( "#checker_nginx_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'nginx')
	});
	$( "#checker_nginx_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'nginx')
	});
	$( "#checker_apache_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'apache')
	});
	$( "#checker_apache_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateServiceCheckerSettings(id[1], 'apache')
	});
	$( "#checker_keepalived_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateKeepalivedCheckerSettings(id[1])
	});
	$( "#checker_keepalived_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateKeepalivedCheckerSettings(id[1])
	});
});
function updateHaproxyCheckerSettings(id) {
	toastr.clear();
	let email = 0;
	let server = 0;
	let backend = 0;
	let maxconn = 0;
	if ($('#haproxy_server_email-' + id).is(':checked')) {
		email = '1';
	}
	if ($('#haproxy_server_status-' + id).is(':checked')) {
		server = '1';
	}
	if ($('#haproxy_server_backend-' + id).is(':checked')) {
		backend = '1';
	}
	if ($('#haproxy_server_maxconn-' + id).is(':checked')) {
		maxconn = '1';
	}
	$.ajax({
		url: "/app/checker/settings/update",
		data: {
			service: 'haproxy',
			setting_id: id,
			email: email,
			server: server,
			backend: backend,
			maxconn: maxconn,
			telegram_id: $('#haproxy_server_telegram_channel-' + id + ' option:selected').val(),
			slack_id: $('#haproxy_server_slack_channel-' + id + ' option:selected').val(),
			pd_id: $('#haproxy_server_pd_channel-' + id + ' option:selected').val(),
			mm_id: $('#haproxy_server_mm_channel-' + id + ' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$("#haproxy_server_tr_id-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#haproxy_server_tr_id-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function updateKeepalivedCheckerSettings(id) {
	toastr.clear();
	let email = 0;
	let server = 0;
	let backend = 0;
	if ($('#keepalived_server_email-' + id).is(':checked')) {
		email = '1';
	}
	if ($('#keepalived_server_status-' + id).is(':checked')) {
		server = '1';
	}
	if ($('#keepalived_server_backend-' + id).is(':checked')) {
		backend = '1';
	}
	$.ajax({
		url: "/app/checker/settings/update",
		data: {
			service: 'keepavlied',
			setting_id: id,
			email: email,
			server: server,
			backend: backend,
			telegram_id: $('#keepalived_server_telegram_channel-' + id + ' option:selected').val(),
			slack_id: $('#keepalived_server_slack_channel-' + id + ' option:selected').val(),
			pd_id: $('#keepalived_server_pd_channel-' + id + ' option:selected').val(),
			mm_id: $('#keepalived_server_mm_channel-' + id + ' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$("#keepalived_server_tr_id-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#keepalived_server_tr_id-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function updateServiceCheckerSettings(id, service_name) {
	toastr.clear();
	let email = 0;
	let server = 0;
	if ($('#' + service_name + '_server_email-' + id).is(':checked')) {
		email = '1';
	}
	if ($('#' + service_name + '_server_status-' + id).is(':checked')) {
		server = '1';
	}
	$.ajax({
		url: "/app/checker/settings/update",
		data: {
			service: service_name,
			setting_id: id,
			email: email,
			server: server,
			telegram_id: $('#' + service_name + '_server_telegram_channel-' + id + ' option:selected').val(),
			slack_id: $('#' + service_name + '_server_slack_channel-' + id + ' option:selected').val(),
			pd_id: $('#' + service_name + '_server_pd_channel-' + id + ' option:selected').val(),
			mm_id: $('#' + service_name + '_server_mm_channel-' + id + ' option:selected').val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('ok') != '-1') {
				toastr.clear();
				$('#' + service_name + '_server_tr_id-' + id).addClass("update", 1000);
				setTimeout(function () {
					$('#' + service_name + '_server_tr_id-' + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function loadchecker() {
	$.ajax({
		url: "/app/checker/settings/load",
		type: "GET",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('group_error') == '-1' && data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#checker').html(data);
				$( "select" ).selectmenu();
				$("button").button();
				$( "input[type=checkbox]" ).checkboxradio();
				$.getScript('/app/static/js/checker.js');
				$.getScript(awesome);
			}
		}
	} );
}
