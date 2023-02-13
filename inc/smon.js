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
	allFields = $( [] ).add( $('#new-smon-ip') ).add( $('#new-smon-port') )
	allFields.removeClass( "ui-state-error" );
	valid = valid && checkLength( $('#new-smon-ip'), "IP", 1 );
	valid = valid && checkLength( $('#new-smon-port'), "Port", 1 );
	if ($('#new-smon-proto').val() != '' || $('#new-smon-uri').val() != '') {
		allFields = $( [] ).add( $('#new-smon-ip') ).add( $('#new-smon-port') )
			.add( $('#new-smon-proto') ).add( $('#new-smon-uri') );
		allFields.removeClass( "ui-state-error" );
		valid = valid && checkLength( $('#new-smon-ip'), "IP", 1 );
		valid = valid && checkLength( $('#new-smon-port'), "Port", 1 );
		valid = valid && checkLength( $('#new-smon-proto'), "Protocol", 1 );
		valid = valid && checkLength( $('#new-smon-uri'), "URI", 1 );
	}
	if( $('#new-smon-body').val() != '') {
		allFields = $( [] ).add( $('#new-smon-ip') ).add( $('#new-smon-port') )
			.add( $('#new-smon-proto') ).add( $('#new-smon-uri') );
		allFields.removeClass( "ui-state-error" );
		valid = valid && checkLength( $('#new-smon-ip'), "IP", 1 );
		valid = valid && checkLength( $('#new-smon-port'), "Port", 1 );
		valid = valid && checkLength( $('#new-smon-proto'), "Protocol", 1 );
		valid = valid && checkLength( $('#new-smon-uri'), "URI", 1 );
		valid = valid && checkLength( $('#new-smon-body'), "Body", 1 );
	}
	var enable = 0;
	if ($('#new-smon-enable').is(':checked')) {
		enable = '1';
	}
	if (valid) {
		$.ajax( {
			url: "options.py",
			data: {
				newsmon: $('#new-smon-ip').val(),
				newsmonport: $('#new-smon-port').val(),
				newsmonenable: enable,
				newsmonproto: $('#new-smon-proto').val(),
				newsmonuri: $('#new-smon-uri').val(),
				newsmonbody: $('#new-smon-body').val(),
				newsmongroup: $('#new-smon-group').val(),
				newsmondescription: $('#new-smon-description').val(),
				newsmontelegram: $('#new-smon-telegram').val(),
				newsmonslack: $('#new-smon-slack').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
					toastr.error(data);
				} else {
					common_ajax_action_after_success(dialog_id, 'newserver', 'ajax-smon', data);
					$( "input[type=submit], button" ).button();
					$( "input[type=checkbox]" ).checkboxradio();
					$( "select" ).selectmenu();
					$.getScript('/inc/users.js');
				}
			}
		} );
	}
}
function confirmDeleteSmon(id) {
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
function removeSmon(id) {
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
				$("#smon-"+id).remove();
			} else {
				toastr.error(data);
			}
		}
	} );
}

function updateSmon(id) {
	toastr.clear();
	var enable = 0;
	if ($('#smon-enable-'+id).is(':checked')) {
		enable = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updateSmonIp: $('#smon-ip-'+id).val(),
			updateSmonPort: $('#smon-port-'+id).val(),
			updateSmonEn: enable,
			updateSmonHttp: $('#smon-proto1-'+id).text(),
			updateSmonBody: $('#smon-body-'+id).text(),
			updateSmonTelegram: $('#smon-telegram-'+id).val(),
			updateSmonSlack: $('#smon-slack-'+id).val(),
			updateSmonGroup: $('#smon-group-'+id).val(),
			updateSmonDesc: $('#smon-desc-'+id).val(),
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
				$("#smon-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#smon-"+id ).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function cloneSmom(id) {
	$( "#add-smon-button" ).trigger( "click" );
	if ($('#smon-enable-'+id).is(':checked')) {
		$('#new-smon-enable').prop('checked', true)
	} else {
		$('#new-smon-enable').prop('checked', false)
	}
	$('#new-smon-enable').checkboxradio("refresh");
	$('#new-smon-ip').val($('#smon-ip-'+id).val());
	$('#new-smon-port').val($('#smon-port-'+id).val());
	$('#new-smon-group').val($('#smon-group-'+id).val());
	$('#new-smon-description').val($('#smon-desc-'+id).val())
	$('#new-smon-telegram').val($('#smon-telegram-'+id+' option:selected').val()).change()
	$('#new-smon-slack').val($('#smon-slack-'+id+' option:selected').val()).change()
	$('#new-smon-slack').selectmenu("refresh");
}
$( function() {
	$('#add-smon-button').click(function() {
		addSmonServer.dialog('open');
	});
	$( "#ajax-smon input" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2])
	});
	$( "#ajax-smon select" ).on('selectmenuchange',function() {
		var id = $(this).attr('id').split('-');
		updateSmon(id[2])
	});
	var add_word = $('#translate').attr('data-add');
	var cancel_word = $('#translate').attr('data-cancel_word');
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
