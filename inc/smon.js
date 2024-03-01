let add_word = $('#translate').attr('data-add');
const delete_word = $('#translate').attr('data-delete');
const cancel_word = $('#translate').attr('data-cancel');
const check_types = {'tcp': 1, 'http': 2, 'ping': 4, 'dns': 5};
$(function () {
	$( "#check_type" ).on('selectmenuchange',function() {
		check_and_clear_check_type($('#check_type').val());
	});
});
function sort_by_status() {
	$('<div id="err_services" style="clear: both;"></div>').appendTo('.main');
	$('<div id="good_services" style="clear: both;"></div>').appendTo('.main');
	$('<div id="dis_services" style="clear: both;"></div>').appendTo('.main');
	$(".good").prependTo("#good_services");
	$(".err").prependTo("#err_services");
	$(".dis").prependTo("#dis_services");
	$('.group').remove();
	$('.group_name').detach();
	window.history.pushState("SMON Dashboard", "SMON Dashboard", "?sort=by_status");
}
function showSmon(action) {
	let sort = '';
	let location = window.location.href;
	let cur_url = '/app/' + location.split('/').pop();
	if (action === 'refresh') {
		try {
			sort = cur_url[1].split('&')[1];
			sort = sort.split('=')[1];
		} catch (e) {
			sort = '';
		}
	}
	if (action === 'not_sort') {
		window.history.pushState("SMON Dashboard", "SMON Dashboard", "/app/smon/dashboard");
	}
	$.ajax({
		url: "/app/smon/refresh",
		data: {
			sort: sort,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('SMON error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#smon_dashboard").html(data);
			}
		}
	});
}
function addNewSmonServer(dialog_id, smon_id=0, edit=false) {
	let valid = true;
	let check_type = $('#check_type').val();
	if (check_type === 'tcp') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-port')).add($('#new-smon-name')).add($('#new-smon-interval'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-port'), "Port", 1);
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
	}
	if (check_type === 'http') {
		allFields = $([]).add($('#new-smon-url')).add($('#new-smon-name')).add($('#new-smon-interval'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-url'), "URL", 1);
	}
	if (check_type === 'ping') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-name')).add($('#new-smon-packet_size')).add($('#new-smon-interval'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
	}
	if (check_type === 'dns') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-port')).add($('#new-smon-name')).add($('#new-smon-resolver-server')).add($('#new-smon-interval'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-port'), "Port", 1);
		valid = valid && checkLength($('#new-smon-resolver-server'), "Resolver server", 1);
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
	}
	valid = valid && checkLength($('#new-smon-name'), "Name", 1);
	valid = valid && checkLength($('#new-smon-interval'), "Check interval", 1);
	let enable = 0;
	if ($('#new-smon-enable').is(':checked')) {
		enable = '1';
	}
	let jsonData = {
		'name': $('#new-smon-name').val(),
		'ip': $('#new-smon-ip').val(),
		'port': $('#new-smon-port').val(),
		'resolver': $('#new-smon-resolver-server').val(),
		'record_type': $('#new-smon-dns_record_type').val(),
		'enabled': enable,
		'url': $('#new-smon-url').val(),
		'body': $('#new-smon-body').val(),
		'group': $('#new-smon-group').val(),
		'desc': $('#new-smon-description').val(),
		'tg': $('#new-smon-telegram').val(),
		'slack': $('#new-smon-slack').val(),
		'pd': $('#new-smon-pd').val(),
		'packet_size': $('#new-smon-packet_size').val(),
		'http_method': $('#new-smon-method').val(),
		'check_type': check_type,
		'interval': $('#new-smon-interval').val(),
		'agent_id': $('#new-smon-agent-id').val(),
		'token': $('#token').val()
	}
	let method = "post";
	if (edit) {
		method = "put";
		jsonData['check_id'] = smon_id;
	}
	if (valid) {
		$.ajax( {
			url: '/app/smon/check',
            data: JSON.stringify(jsonData),
            contentType: "application/json; charset=utf-8",
			type: method,
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('warning:') != '-1') {
					toastr.warning(data);
				} else {
					let check_id = check_types[check_type];
					if (edit) {
						getSmonCheck(smon_id, check_id, dialog_id);
					} else {
						getSmonCheck(data, check_id, dialog_id, true);
					}
				}
			}
		} );
	}
}
function confirmDeleteSmon(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word+" " +$('#smon-name-'+id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeSmon(id);
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function removeSmon(smon_id) {
	$("#smon-"+smon_id).css("background-color", "#f2dede");
	let jsonData = {'check_id': smon_id}
	$.ajax( {
		url: "/app/smon/check",
		type: "DELETE",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data === "Ok") {
				$("#smon-"+smon_id).remove();
			} else {
				toastr.error(data);
			}
		}
	} );
}
function openSmonDialog(check_type, smon_id=0, edit=false) {
	check_and_clear_check_type(check_type);
	let smon_add_tabel_title = $("#smon-add-table-overview").attr('title');
	if (edit) {
		add_word = $('#translate').attr('data-edit');
		smon_add_tabel_title = $("#smon-add-table-overview").attr('data-edit');
		$('#check_type').attr('disabled', 'disabled');
		$('#check_type').selectmenu("refresh");
	} else {
		$('#check_type').removeAttr('disabled');
		$('#check_type').selectmenu("refresh");
		$('#new-smon-name').val('');
	}
	let addSmonServer = $("#smon-add-table").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: smon_add_tabel_title,
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
				if (edit) {
					addNewSmonServer(this, smon_id, check_type);
				} else {
					addNewSmonServer(this);
				}
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	addSmonServer.dialog('open');
}
function getCheckSettings(smon_id, check_type) {
	$.ajax( {
		url: "/app/smon/check/settings/" + smon_id + "/" + check_types[check_type],
		type: "get",
		async: false,
		dataType: "json",
		success: function( data ) {
			$('#new-smon-name').val(data['name']);
			$('#new-smon-ip').val(data['server_ip']);
			$('#new-smon-port').val(data['port']);
			$('#new-smon-resolver-server').val(data['resolver']);
			$('#new-smon-dns_record_typer').val(data['record_type']);
			$('#new-smon-url').val(data['url']);
			$('#new-smon-group').val(data['group']);
			$('#new-smon-description').val(data['desc'])
			$('#new-smon-packet_size').val(data['packet_size'])
			$('#new-smon-interval').val(data['interval'])
			$('#new-smon-body').val(data['body'])
			$('#new-smon-agent-id').val(data['agent_id']).change()
			$('#new-smon-telegram').val(data['tg']).change()
			$('#new-smon-slack').val(data['slack']).change()
			$('#new-smon-pd').val(data['pd']).change()
			$('#new-smon-telegram').selectmenu("refresh");
			$('#new-smon-slack').selectmenu("refresh");
			$('#new-smon-pd').selectmenu("refresh");
			$('#new-smon-agent-id').selectmenu("refresh");
			if (data['enabled']) {
				$('#new-smon-enable').prop('checked', true)
			} else {
				$('#new-smon-enable').prop('checked', false)
			}
			$('#new-smon-enable').checkboxradio("refresh");
		}
	} );
}
function editSmon(smon_id, check_type) {
	check_and_clear_check_type(check_type);
	openSmonDialog(check_type, smon_id, true);
	getCheckSettings(smon_id, check_type);

}
function cloneSmom(id, check_type) {
	check_and_clear_check_type(check_type);
	getCheckSettings(id, check_type);
	openSmonDialog(check_type);
}
function getSmonCheck(smon_id, check_id, dialog_id, new_check=false) {
	$.ajax({
		url: "/app/smon/check/" + smon_id + "/" + check_id,
		type: "get",
		success: function (data) {
			if (new_check) {
				if ( !$( "#dashboards" ).length ) {
					location.reload();
				}
				$('#dashboards').prepend(data);
			} else {
				$('#smon-' + smon_id).replaceWith(data);
			}
			$(dialog_id).dialog("close");
			// $.getScript("/inc/fontawesome.min.js");
		}
	});
}
function check_and_clear_check_type(check_type) {
	if (check_type === 'http') {
		$('.new_smon_hostname').hide();
		$("#check_type").val('http');
		$('#check_type').selectmenu("refresh");
		$('.smon_tcp_check').hide();
		$('.smon_ping_check').hide();
		$('.smon_dns_check').hide();
		clear_check_vals();
		$('.smon_http_check').show();
	} else if (check_type === 'tcp') {
		$("#check_type").val('tcp');
		$('#check_type').selectmenu("refresh");
		$('.new_smon_hostname').show();
		$('.smon_http_check').hide();
		$('.smon_dns_check').hide();
		$('.smon_ping_check').hide();
		clear_check_vals();
		$('.smon_tcp_check').show();
	} else if (check_type === 'dns') {
		$("#check_type").val('dns');
		$('#check_type').selectmenu("refresh");
		$('.smon_tcp_check').hide();
		$('.new_smon_hostname').show();
		$('.smon_http_check').hide();
		$('.smon_ping_check').hide();
		clear_check_vals();
		$('#new-smon-port').val('53');
		$('.smon_dns_check').show();
	} else {
		$('.smon_http_check').hide();
		$('.new_smon_hostname').show();
		$('.smon_tcp_check').hide();
		$('.smon_dns_check').hide();
		$('.smon_ping_check').show();
		$("#check_type").val('ping');
		clear_check_vals();
		$('#new-smon-packet_size').val('56');
		$('#check_type').selectmenu("refresh");
	}
}
function clear_check_vals() {
	$('#new-smon-url').val('');
	$('#new-smon-body').val('');
	$('#new-smon-port').val('');
	$('#new-smon-packet_size').val('');
	$('#new-smon-ip').val('');
}
function show_statuses(dashboard_id, check_id, id_for_history_replace) {
	show_smon_history_statuses(dashboard_id, id_for_history_replace);
	$.ajax({
		url: "/app/smon/history/cur_status/" + dashboard_id + "/" + check_id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#cur_status").html(data);
			}
		}
	});
}
function show_smon_history_statuses(dashboard_id, id_for_history_replace) {
	$.ajax({
		url: "/app/smon/history/statuses/" + dashboard_id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$(id_for_history_replace).html(data);
				$("[title]").tooltip({
					"content": function () {
						return $(this).attr("data-help");
					},
					show: {"delay": 1000}
				});
			}
		}
	});
}
function smon_status_page_avg_status(page_id) {
	$.ajax({
		url: "/app/smon/status/avg/" + page_id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				if (data == '1') {
					$('#page_status').html('<i class="far fa-check-circle page_icon page_icon_all_ok"></i><span>All Systems Operational</span>');
				} else {
					$('#page_status').html('<i class="far fa-times-circle page_icon page_icon_not_ok"></i><span>Not all Systems Operational</span>')
				}
			}
		}
	});
}
function smon_manage_status_page_avg_status(page_id) {
	$.ajax({
		url: "/app/smon/status/avg/" + page_id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				if (data == '1') {
					$('#page_status-'+page_id).html('<i class="far fa-check-circle status-page-icon status-page-icon-ok"></i>');
				} else {
					$('#page_status-'+page_id).html('<i class="far fa-times-circle status-page-icon status-page-icon-not-ok"></i>')
				}
			}
		}
	});
}
function createStatusPageStep1(edited=false, page_id=0) {
	var next_word = $('#translate').attr('data-next');
	var smon_add_tabel_title = $("#create-status-page-step-1-overview").attr('title');
	if (edited) {
		smon_add_tabel_title = $("#create-status-page-step-1-overview").attr('data-edit');
		$('#new-status-page-name').val($('#page_name-'+page_id).text());
		$('#new-status-page-slug').val($('#page_slug-'+page_id).text().split('/').pop());
		$('#new-status-page-desc').val($('#page_desc-'+page_id).text().replace('(','').replace(')',''));
	}
	var regx = /^[a-z0-9_-]+$/;
	var addSmonStatus = $("#create-status-page-step-1").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 630,
		modal: true,
		title: smon_add_tabel_title,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: [{
			text: next_word,
			click: function () {
				if ($('#new-status-page-name').val() == '') {
					toastr.error('error: Fill in the Name field');
					return false;
				}
				if (!regx.test($('#new-status-page-slug').val())) {
					toastr.error('error: Incorrect Slug');
					return false;
				}
				if ($('#new-status-page-slug').val().indexOf('--') != '-1') {
					toastr.error('error: "--" are prohibeted in Slug');
					return false;
				}
				if ($('#new-status-page-slug').val() == '') {
					toastr.error('error: Fill in the Slug field');
					return false;
				}
				createStatusPageStep2(edited, page_id);
				$(this).dialog("close");
				toastr.clear();
			}
		}, {
			text: cancel_word,
			click: function () {
				clearStatusPageDialog($(this));
			}
		}]
	});
	addSmonStatus.dialog('open');
}
function createStatusPageStep2(edited, page_id) {
	var back_word = $('#translate').attr('data-back');
	var smon_add_tabel_title = $("#create-status-page-step-2-overview").attr('title');
	if (edited) {
		smon_add_tabel_title = $("#create-status-page-step-2-overview").attr('data-edit');
		add_word = $('#translate').attr('data-edit');
		if ($("#enabled-check > div").length == 0) {
			$.ajax({
				url: "/app/smon/status/checks/" + page_id,
				async: false,
				type: "GET",
				success: function (data) {
					if (data.indexOf('error:') != '-1') {
						toastr.error(data);
					} else {
						for (let i = 0; i < data.length; i++) {
							addCheckToStatus(data[i]);
						}
					}
				}
			});
		}
	}
	var addSmonStatus = $("#create-status-page-step-2").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 630,
		modal: true,
		title: smon_add_tabel_title,
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
				if (edited) {
					editStatusPage($(this), page_id);
				} else {
					createStatusPage($(this));
				}
			}
		}, {
			text: back_word,
			click: function () {
				$(this).dialog("close");
				createStatusPageStep1(edited, page_id);
			}
		}, {
			text: cancel_word,
			click: function () {
				clearStatusPageDialog($(this));
			}
		}]
	});
	addSmonStatus.dialog('open');
}
function clearStatusPageDialog(dialog_id) {
	dialog_id.dialog("close");
	clearTips();
	$('#new-status-page-name').val('');
	$('#new-status-page-slug').val('');
	$('#new-status-page-desc').val('');
	$("#enabled-check > div").each((index, elem) => {
		check_id = elem.id.split('-')[1]
		removeCheckFromStatus(check_id);
	});
}
function createStatusPage(dialog_id) {
	let name_id = $('#new-status-page-name');
	let slug_id = $('#new-status-page-slug');
	let desc_id = $('#new-status-page-desc');
	let checks = [];
	let check_id = '';
	$("#enabled-check > div").each((index, elem) => {
		check_id = elem.id.split('-')[1]
		checks.push(check_id);
	});
	$.ajax({
		url: '/app/smon/status-page',
		type: 'POST',
		data: {
			name: name_id.val(),
			slug: slug_id.val(),
			desc: desc_id.val(),
			checks: JSON.stringify({'checks': checks})
		},
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				clearStatusPageDialog(dialog_id);
				$("#pages").append(data);
				$.getScript("/inc/fontawesome.min.js");
			}
		}
	});
}
function editStatusPage(dialog_id, page_id) {
	let name_id = $('#new-status-page-name');
	let slug_id = $('#new-status-page-slug');
	let desc_id = $('#new-status-page-desc');
	let checks = [];
	let check_id = '';
	$("#enabled-check > div").each((index, elem) => {
		check_id = elem.id.split('-')[1]
		checks.push(check_id);
	});
	$.ajax({
		url: '/app/smon/status-page',
		type: 'PUT',
		data: {
			page_id: page_id,
			name: name_id.val(),
			slug: slug_id.val(),
			desc: desc_id.val(),
			checks: JSON.stringify({'checks': checks})
		},
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				clearStatusPageDialog(dialog_id);
				$("#page_" + page_id).replaceWith(data);
				$("#page_" + page_id).addClass("update", 1000);
				setTimeout(function () {
					$("#page_" + page_id).removeClass("update");
				}, 2500);
				$.getScript("/inc/fontawesome.min.js");
			}
		}
	});
}
function addCheckToStatus(service_id) {
	var service_name = $('#add_check-' + service_id).attr('data-service_name');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#all-checks').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<div class="' + tr_class + '" id="remove_check-' + service_id + '" data-service_name="' + service_name + '">' +
		'<div class="check-name">' + service_name + '</div>' +
		'<div class="add_user_group check-button" onclick="removeCheckFromStatus(' + service_id + ')" title="' + delete_word + ' ' + service_word + '">-</div></div>';
	$('#add_check-' + service_id).remove();
	$("#enabled-check").append(html_tag);
}
function removeCheckFromStatus(service_id) {
	var service_name = $('#remove_check-' + service_id).attr('data-service_name');
	var service_word = $('#translate').attr('data-service');
	var length_tr = $('#all_services tbody tr').length;
	var tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	var html_tag = '<div class="' + tr_class + ' all-checks" id="add_check-' + service_id + '" data-service_name="' + service_name + '">' +
		'<div class="check-name">' + service_name + '</div>' +
		'<div class="add_user_group check-button" onclick="addCheckToStatus(' + service_id + ')" title="' + add_word + ' ' + service_word + '">+</div></div>';
	$('#remove_check-' + service_id).remove();
	$("#all-checks").append(html_tag);
}
function confirmDeleteStatusPage(id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#page_name-' + id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				deleteStatusPage(id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function deleteStatusPage(page_id) {
	$.ajax({
		url: '/app/smon/status-page',
		type: 'DELETE',
		data: {
			page_id: page_id,
		},
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				$('#page_' + page_id).remove();
			}
		}
	});
}
function checkAgentLimit() {
	let return_value = false;
	$.ajax({
		url: '/app/smon/agent/count',
		async: false,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				return_value = true;
			}
		}
	});
	return return_value;
}
function addAgentDialog(agent_id=0, edit=false) {
	cleanAgentAddForm();
	let tabel_title = $("#add-agent-page-overview").attr('title');
	if (edit) {
		add_word = $('#translate').attr('data-edit');
		tabel_title = $("#add-agent-page-overview").attr('data-edit');
		getAgentSettings(agent_id);
	} else {
		if (!checkAgentLimit()) {
			return false;
		}
		getFreeServers();
	}
	let dialogTable = $("#add-agent-page").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 630,
		modal: true,
		title: tabel_title,
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
				if (edit) {
					addAgent($(this), agent_id, true);
				} else {
					addAgent($(this));
				}
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
	dialogTable.dialog('open');
}
function addAgent(dialog_id, agent_id=0, edit=false) {
	let valid = true;
	allFields = $([]).add($('#new-agent-name'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#new-agent-name'), "Name", 1);
	let agent_name = $('#new-agent-name').val();
    let agent_server_id = $('#new-agent-server-id').val();
    let agent_desc = $('#new-agent-desc').val();
    let agent_enabled = $('#new-agent-enabled').is(':checked') ? 1 : 0;
    let agent_data = {
        'name': agent_name,
        'server_id': agent_server_id,
        'desc': agent_desc,
        'enabled': agent_enabled
    };
	let method = 'POST';
	if (edit) {
		method = 'PUT'
		agent_data['agent_id'] = agent_id;
	}
	if (valid) {
		$.ajax({
			url: "/app/smon/agent",
			type: method,
			data: JSON.stringify(agent_data),
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$(dialog_id).dialog("close");
					if (edit) {
						getAgent(agent_id, false);
					} else {
						getAgent(data, new_agent = true);
					}
				}
			}
		});
	}
}
function getAgentSettings(agent_id) {
	$.ajax({
		url: "/app/smon/agent/settings/" + agent_id,
		async: false,
		success: function (data) {
			$('#new-agent-name').val(data['name']);
			$('#new-agent-server-id').append('<option value="' + data['server_id'] + '" selected="selected">' + data['hostname'] + '</option>');
			$('#new-agent-server-id').attr('disabled', 'disabled');
			$('#new-agent-desc').val(data['desc']);
			$('#new-agent-enabled').checkboxradio("refresh");
			if (data['enabled']) {
				$('#new-agent-enabled').prop('checked', true)
			} else {
				$('#new-agent-enabled').prop('checked', false)
			}
			$('#new-agent-enabled').checkboxradio("refresh");
			$('#new-agent-server-id').selectmenu("refresh");
		}
	});
}
function getFreeServers() {
	$.ajax({
		url: "/app/smon/agent/free",
		async: false,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			$("#new-agent-server-id option[value!='------']").remove();
			for (k in data) {
				$('#new-agent-server-id').append('<option value="' + k + '" selected="selected">' + data[k] + '</option>');
			}
			$('#new-agent-server-id').selectmenu("refresh");
		}
	});
}
function cleanAgentAddForm() {
	$('#new-agent-name').val('');
	$('#new-agent-server-id').val('------').change();
	$('#new-agent-desc').val('');
	$('#new-agent-enabled').prop('checked', true);
	$('#new-agent-enabled').checkboxradio("refresh");
	$('#new-agent-server-id').removeAttr('disabled');
	$('#new-agent-server-id').selectmenu("refresh");
}
function getAgent(agent_id, new_agent=false) {
	$.ajax({
		url: "/app/smon/agent/" + agent_id,
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				if (new_agent) {
					$('.up-pannel').append(data);
				} else {
					$('#agent-' + agent_id).replaceWith(data);
				}
				$.getScript("/inc/fontawesome.min.js");
				$('#agent-' + agent_id).removeClass('animated-background');
			}
		}
	});
}
function getAgentVersion(server_ip, agent_id){
	$.ajax({
		url: '/app/smon/agent/version/' + server_ip,
		type: 'get',
		data: {agent_id: agent_id},
		success: function (data){
			try {
				data = JSON.parse(data);
				$('#agent-version-' + agent_id).text(data['version'])
			} catch (e) {
				console.log(e)
			}
		}
	});
}
function getAgentUptime(server_ip, agent_id){
	$.ajax({
		url: '/app/smon/agent/uptime/' + server_ip,
		type: 'get',
		data: {agent_id: agent_id},
		success: function (data){
			try {
				data = JSON.parse(data);
				$('#agent-uptime-' + agent_id).text(data['uptime']);
				$('#agent-uptime-' + agent_id).attr('datetime', data['uptime']);
				$("#agent-uptime-"+agent_id).timeago();
			} catch (e) {
				console.log(e)
			}
		}
	});
}
function getAgentStatus(server_ip, agent_id){
	$.ajax({
		url: '/app/smon/agent/status/' + server_ip,
		type: 'get',
		data: {agent_id: agent_id},
		success: function (data){
			try {
				data = JSON.parse(data);
				if (data['running']) {
					$('#agent-'+agent_id).addClass('div-server-head-up');
					$('#start-'+agent_id).children().addClass('disabled-button');
					$('#start-'+agent_id).children().removeAttr('onclick');
					$('#agent-'+agent_id).removeClass('div-server-head-down');
				} else {
					$('#agent-'+agent_id).removeClass('div-server-head-up');
					$('#agent-'+agent_id).addClass('div-server-head-pause');
					$('#pause-'+agent_id).children().addClass('disabled-button');
					$('#pause-'+agent_id).children().removeAttr('onclick');
				}
			} catch (e) {
				console.log(e);
				$('#agent-'+agent_id).addClass('div-server-head-down');
				$('#stop-'+agent_id).children().addClass('disabled-button');
				$('#pause-'+agent_id).children().addClass('disabled-button');
				$('#pause-'+agent_id).children().removeAttr('onclick');
				$('#stop-'+agent_id).children().removeAttr('onclick');
			}
		}
	});
}
function getAgentTotalChecks(server_ip, agent_id){
	$.ajax({
		url: '/app/smon/agent/checks/' + server_ip,
		type: 'get',
		data: {agent_id: agent_id},
		success: function (data){
			try {
				data = JSON.parse(data);
				$('#agent-total-checks-'+agent_id).text(Object.keys(data).length)
			} catch (e) {
				console.log(e);
				$('#agent-'+agent_id).addClass('div-server-head-down')
			}
		}
	});
}
function confirmDeleteAgent(id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word+" " +$('#agent-name-'+id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeAgent(id, $(this));
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function removeAgent(id, dialog_id) {
	$.ajax({
        url: "/app/smon/agent",
        type: "delete",
        data: {agent_id: id},
        success: function (data){
            data = data.replace(/\s+/g, ' ');
            if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
                toastr.error(data);
            } else {
                toastr.clear();
                $(dialog_id).dialog("close");
				$('#agent-'+id).remove();
            }
        }
    });
}
function confirmAjaxAction(action, id, server_ip) {
	let action_word = $('#translate').attr('data-'+action);
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + $('#agent-name-'+id).text() + "?",
		buttons: [{
			text: action_word,
			click: function (){
				agentAction(action, id, server_ip, $(this));
			}
		}, {
			text: cancel_word,
			click: function(){
				$( this ).dialog( "close" );
			}
		}]
	});
}
function agentAction(action, id, server_ip, dialog_id) {
	$.ajax({
		url: "/app/smon/agent/action/"+ action,
		type: "post",
		data: {agent_id: id, server_ip: server_ip},
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$(dialog_id).dialog("close");
				getAgent(id, false);
			}
		}
	});
}
var charts = []
function getSmonHistoryCheckData(server) {
    $.ajax({
        url: "/app/smon/history/metric/" + server,
        success: function (result) {
            let data = [];
            data.push(result.chartData.curr_con);
            let labels = result.chartData.labels;
            renderSMONChart(data[0], labels, '3');
        }
    });
}
function renderSMONChart(data, labels, server) {
    const resp_time_word = $('#translate').attr('data-resp_time');
    const ctx = document.getElementById('metrics_' + server);

    // Преобразование данных в массивы
    const labelArray = labels.split(',');
    const dataArray = data.split(',');

    // Удаление последнего пустого элемента в каждом массиве
    labelArray.pop();
    dataArray.pop();

    // Создание объекта dataset
    const dataset = {
        label: resp_time_word + ' (ms)',
        data: dataArray,
        borderColor: 'rgba(92, 184, 92, 1)',
        backgroundColor: 'rgba(92, 184, 92, 0.2)',
        tension: 0.4,
        pointRadius: 3,
        borderWidth: 1,
        fill: true
    };

    const config = {
        type: 'line',
        data: {
            labels: labelArray,
            datasets: [dataset]
        },
        options: {
            animation: true,
			maintainAspectRatio: false,
			plugins: {
				title: {
					display: true,
					font: { size: 15 },
					padding: { top: 10 }
				},
				legend: {
					display: false,
					position: 'left',
					align: 'end',
					labels: {
						color: 'rgb(255, 99, 132)',
						font: { size: 10, family: 'BlinkMacSystemFont' },
						boxWidth: 13,
						padding: 5
					},
				}
			},
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    },
                    ticks: {
                        source: 'data',
                        autoSkip: true,
                        autoSkipPadding: 45,
                        maxRotation: 0
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: resp_time_word + ' (ms)'
                    },
                    ticks: {
                        font: {
                            size: 10
                        }
                    }
                }
            }
        }
    };

    const myChart = new Chart(ctx, config);
    charts.push(myChart);
}
