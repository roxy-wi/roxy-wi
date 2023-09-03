function sort_by_status() {
	$('<div id="err_services" style="clear: both;"></div>').appendTo('.main');
	$('<div id="good_services" style="clear: both;"></div>').appendTo('.main');
	$('<div id="dis_services" style="clear: both;"></div>').appendTo('.main');
	$(".good").prependTo("#good_services");
	$(".err").prependTo("#err_services");
	$(".dis").prependTo("#dis_services");
	$('.group').remove();
	$('.group_name').detach();
	window.history.pushState("SMON Dashboard", "SMON Dashboard", cur_url[0]+"?action=view&sort=by_status");
}
function showSmon(action) {
	var sort = '';
	var location = window.location.href;
	var cur_url = '/app/' + location.split('/').pop();
	cur_url = cur_url.split('?');
	cur_url[1] = cur_url[1].split('#')[0];
	if (action == 'refresh') {
		try {
			sort = cur_url[1].split('&')[1];
			sort = sort.split('=')[1];
		} catch (e) {
			sort = '';
		}
	}
	$.ajax( {
		url: "options.py",
		data: {
			showsmon: 1,
			sort: sort,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('SMON error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#smon_dashboard").html(data);
				if (action == 'not_sort') {
					window.history.pushState("SMON Dashboard", document.title, "smon.py?action=view");
				} else {
					window.history.pushState("SMON Dashboard", document.title, cur_url[0] + "?" + cur_url[1]);
				}
			}
		}
	} );
}
function addNewSmonServer(dialog_id) {
	var valid = true;
	var check_type = $('#check_type').val();
	if (check_type == 'tcp') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-port')).add($('#new-smon-name'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
		valid = valid && checkLength($('#new-smon-name'), "Name", 1);
		valid = valid && checkLength($('#new-smon-port'), "Port", 1);
	}
	if (check_type == 'http') {
		allFields = $([]).add($('#new-smon-url')).add($('#new-smon-name'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-name'), "Name", 1);
		valid = valid && checkLength($('#new-smon-url'), "URL", 1);
	}
	if (check_type == 'ping') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-name')).add($('#new-smon-packet_size'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-name'), "Name", 1);
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
		valid = valid && checkLength($('#new-smon-packet_size'), "Packet size", 1);
	}
	if (check_type == 'dns') {
		allFields = $([]).add($('#new-smon-ip')).add($('#new-smon-port')).add($('#new-smon-name')).add($('#new-smon-resolver-server'))
		allFields.removeClass("ui-state-error");
		valid = valid && checkLength($('#new-smon-name'), "Name", 1);
		valid = valid && checkLength($('#new-smon-ip'), "Hostname", 1);
		valid = valid && checkLength($('#new-smon-port'), "Port", 1);
		valid = valid && checkLength($('#new-smon-resolver-server'), "Resolver server", 1);
	}
	var enable = 0;
	if ($('#new-smon-enable').is(':checked')) {
		enable = '1';
	}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newsmonname: $('#new-smon-name').val(),
				newsmon: $('#new-smon-ip').val(),
				newsmonport: $('#new-smon-port').val(),
				newsmonresserver: $('#new-smon-resolver-server').val(),
				newsmondns_record_type: $('#new-smon-dns_record_type').val(),
				newsmonenable: enable,
				newsmonurl: $('#new-smon-url').val(),
				newsmonbody: $('#new-smon-body').val(),
				newsmongroup: $('#new-smon-group').val(),
				newsmondescription: $('#new-smon-description').val(),
				newsmontelegram: $('#new-smon-telegram').val(),
				newsmonslack: $('#new-smon-slack').val(),
				newsmonpd: $('#new-smon-pd').val(),
				newsmonpacket_size: $('#new-smon-packet_size').val(),
				newsmon_http_method: $('#new-smon-method').val(),
				newsmonchecktype: check_type,
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else {
					if (check_type == 'ping') {
						table_id = 'ajax-smon-ping';
					} else if (check_type == 'tcp') {
						table_id = 'ajax-smon-tcp';
					} else if (check_type == 'dns') {
						table_id = 'ajax-smon-dns';
					}
					 else {
						table_id = 'ajax-smon-http';
					}
					common_ajax_action_after_success(dialog_id, 'newserver', table_id, data);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( "select" ).selectmenu();
					$.getScript('/inc/users.js');
				}
			}
		} );
	}
}
function confirmDeleteSmon(id, check_type) {
	var delete_word = $('#translate').attr('data-delete');
	var cancel_word = $('#translate').attr('data-cancel');
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word+" " +$('#smon-ip-'+id).val() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				removeSmon(id, check_type);
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function removeSmon(id, check_type) {
	$("#smon-"+id).css("background-color", "#f2dede");
	$.ajax( {
		url: "options.py",
		data: {
			smondel: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if(data == "Ok ") {
				$("#smon-"+check_type+"-"+id).remove();
			} else {
				toastr.error(data);
			}
		}
	} );
}

function updateSmon(id, check_type) {
	toastr.clear();
	var enable = 0;
	if ($('#smon-enable-'+id).is(':checked')) {
		enable = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateSmonName: $('#smon-name-'+id).val(),
			updateSmonIp: $('#smon-ip-'+id).val(),
			updateSmonResServer: $('#smon-resolver-'+id).val(),
			updateSmonRecordType: $('#smon-record_type-'+id).val(),
			updateSmonPort: $('#smon-port-'+id).val(),
			updateSmonUrl: $('#smon-url-'+id).val(),
			updateSmonEn: enable,
			updateSmonBody: $('#smon-body-'+id).val(),
			updateSmonTelegram: $('#smon-telegram-'+id).val(),
			updateSmonSlack: $('#smon-slack-'+id).val(),
			updateSmonPD: $('#smon-pd-'+id).val(),
			updateSmonGroup: $('#smon-group-'+id).val(),
			updateSmonDesc: $('#smon-desc-'+id).val(),
			updateSmonPacket_size: $('#smon-packet_size-'+id).val(),
			updateSmon_http_method: $('#smon-http_method-'+id).val(),
			check_type: check_type,
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
				$("#smon-"+check_type+"-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$("#smon-"+check_type+"-"+id).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function cloneSmom(id, check_type) {
	check_and_clear_check_type(check_type);
	$( "#add-smon-button-"+check_type ).trigger( "click" );
	if ($('#smon-enable-'+id).is(':checked')) {
		$('#new-smon-enable').prop('checked', true)
	} else {
		$('#new-smon-enable').prop('checked', false)
	}
	$('#new-smon-enable').checkboxradio("refresh");
	$('#new-smon-name').val($('#smon-name-'+id).val());
	$('#new-smon-ip').val($('#smon-ip-'+id).val());
	$('#new-smon-port').val($('#smon-port-'+id).val());
	$('#new-smon-resolver-server').val($('#smon-resolver-'+id).val());
	$('#new-smon-dns_record_typer').val($('#smon-record_type-'+id).val());
	$('#new-smon-url').val($('#smon-url-'+id).val());
	$('#new-smon-group').val($('#smon-group-'+id).val());
	$('#new-smon-description').val($('#smon-desc-'+id).val())
	$('#new-smon-packet_size').val($('#smon-packet_size-'+id).val())
	$('#new-smon-telegram').val($('#smon-telegram-'+id+' option:selected').val()).change()
	$('#new-smon-slack').val($('#smon-slack-'+id+' option:selected').val()).change()
	$('#new-smon-pd').val($('#smon-pd-'+id+' option:selected').val()).change()
	$('#new-smon-telegram').selectmenu("refresh");
	$('#new-smon-slack').selectmenu("refresh");
	$('#new-smon-pd').selectmenu("refresh");
}
$( function() {
	$('#add-smon-button-http').click(function() {
		addSmonServer.dialog('open');
		check_and_clear_check_type('http');
	});
	$('#add-smon-button-tcp').click(function() {
		addSmonServer.dialog('open');
		check_and_clear_check_type('tcp');
	});
	$('#add-smon-button-ping').click(function() {
		addSmonServer.dialog('open');
		check_and_clear_check_type('ping');
	});
	$('#add-smon-button-dns').click(function() {
		addSmonServer.dialog('open');
		check_and_clear_check_type('dns');
	});
	$( "#ajax-smon-http input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'http');
	});
	$( "#ajax-smon-http select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'http');
	});
	$( "#ajax-smon-tcp input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'tcp');
	});
	$( "#ajax-smon-tcp select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'tcp');
	});
	$( "#ajax-smon-ping input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'ping');
	});
	$( "#ajax-smon-ping select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'ping');
	});
	$( "#ajax-smon-dns input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'dns');
	});
	$( "#ajax-smon-dns select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2], 'dns');
	});
	$( "#check_type" ).on('selectmenuchange',function() {
		check_and_clear_check_type($('#check_type').val());
	});
	var add_word = $('#translate').attr('data-add');
	var cancel_word = $('#translate').attr('data-cancel');
	var smon_add_tabel_title = $( "#smon-add-table-overview" ).attr('title');
	var addSmonServer = $( "#smon-add-table" ).dialog({
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
				addNewSmonServer(this);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
});
function check_and_clear_check_type(check_type) {
	if (check_type == 'http') {
		$('.new_smon_hostname').hide();
		$("#check_type").val('http');
		$('#check_type').selectmenu("refresh");
		$('.smon_tcp_check').hide();
		$('.smon_ping_check').hide();
		$('.smon_dns_check').hide();
		clear_check_vals();
		$('.smon_http_check').show();
	} else if (check_type == 'tcp') {
		$("#check_type").val('tcp');
		$('#check_type').selectmenu("refresh");
		$('.new_smon_hostname').show();
		$('.smon_http_check').hide();
		$('.smon_dns_check').hide();
		$('.smon_ping_check').hide();
		clear_check_vals();
		$('.smon_tcp_check').show();
	} else if (check_type == 'dns') {
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
		$('#check_type').selectmenu("refresh");
		clear_check_vals();

	}
}
function clear_check_vals() {
	$('#new_smon_hostname').val('');
	$('#new-smon-url').val('');
	$('#new-smon-body').val('');
	$('#new-smon-port').val('');
	$('#new-smon-packet_size').val('');
}
function show_statuses(dashboard_id, check_id) {
	$.ajax({
		url: "options.py",
		data: {
			smon_history_statuses: 1,
			dashboard_id: dashboard_id,
			check_id: check_id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#smon_history_statuses").html(data);
				$( "[title]" ).tooltip({
					"content": function () {
						return $(this).attr("data-help");
					},
					show: {"delay": 1000}
				});
			}
		}
	});
	$.ajax({
		url: "options.py",
		data: {
			smon_cur_status: 1,
			dashboard_id: dashboard_id,
			check_id: check_id,
			token: $('#token').val()
		},
		type: "POST",
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
