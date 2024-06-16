let cur_url = window.location.href.split('/app/').pop();
cur_url = cur_url.split('/');
$( function() {
   	$('#add-telegram-button').click(function() {
		addTelegramDialog.dialog('open');
	});
	$('#add-slack-button').click(function() {
		addSlackDialog.dialog('open');
	});
	$('#add-pd-button').click(function() {
		addPDDialog.dialog('open');
	});
	$('#add-mm-button').click(function() {
		addMMDialog.dialog('open');
	});
	let telegram_tabel_title = $( "#telegram-add-table-overview" ).attr('title');
	let addTelegramDialog = $( "#telegram-add-table" ).dialog({
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
	let slack_tabel_title = $( "#slack-add-table-overview" ).attr('title');
	let addSlackDialog = $( "#slack-add-table" ).dialog({
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
	let pd_tabel_title = $( "#pd-add-table-overview" ).attr('title');
	let addPDDialog = $( "#pd-add-table" ).dialog({
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
	let mm_tabel_title = $( "#mm-add-table-overview" ).attr('title');
	let addMMDialog = $( "#mm-add-table" ).dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: mm_tabel_title,
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
				addRecevier(this, 'mm');
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearTips();
			}
		}]
	});
	$( "#checker_telegram_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'telegram')
	});
	$( "#checker_telegram_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'telegram')
	});
   $( "#checker_slack_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'slack')
	});
	$( "#checker_slack_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'slack')
	});
   $( "#checker_pd_table input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[2], 'pd')
	});
	$( "#checker_pd_table select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateReceiver(id[1], 'pd')
	});
});
function loadChannel() {
	$.ajax({
		url: "/app/channel/load",
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
				$.getScript('/app/static/js/channel.js');
				$.getScript(awesome);
			}
		}
	} );
}
function updateReceiver(id, receiver_name) {
	if (cur_url[0].indexOf('servers') != '-1') {
		let group = $('#new-group').val();
	} else {
		let group = $('#' + receiver_name + 'group-' + id).val();
	}
	toastr.clear();
	$.ajax({
		url: "/app/channel/receiver/" + receiver_name,
		data: {
			receiver_token: $('#' + receiver_name + '-token-' + id).val(),
			channel: $('#' + receiver_name + '-chanel-' + id).val(),
			group: group,
			id: id,
			token: $('#token').val()
		},
		type: "PUT",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#" + receiver_name + "-table-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#" + receiver_name + "-table-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function checkReceiver(channel_id, receiver_name) {
	$.ajax({
		url: "/app/channel/check/" + channel_id + "/" + receiver_name,
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
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
function addRecevier(dialog_id, receiver_name) {
	let valid = true;
	toastr.clear();
	let allFields = $([]).add($('#' + receiver_name + '-token-add')).add($('#' + receiver_name + '-chanel-add'));
	allFields.removeClass("ui-state-error");
	valid = valid && checkLength($('#' + receiver_name + '-token-add'), "token", 1);
	valid = valid && checkLength($('#' + receiver_name + '-chanel-add'), "channel name", 1);
	if (valid) {
		toastr.clear();
		$.ajax({
			url: "/app/channel/receiver/" + receiver_name,
			data: {
				receiver: $('#' + receiver_name + '-token-add').val(),
				channel: $('#' + receiver_name + '-chanel-add').val(),
				group: $('#new-' + receiver_name + '-group-add').val(),
				page: cur_url[0].split('#')[0],
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					let getId = new RegExp(receiver_name + '-table-[0-9]+');
					let id = data.match(getId) + '';
					id = id.split('-').pop();
					$('select:regex(id, ' + receiver_name + '_channel)').append('<option value=' + id + '>' + $('#' + receiver_name + '-chanel-add').val() + '</option>').selectmenu("refresh");
					common_ajax_action_after_success(dialog_id, 'newgroup', 'checker_' + receiver_name + '_table', data);
					$("input[type=submit], button").button();
					$("input[type=checkbox]").checkboxradio();
					$("select").selectmenu();
				}
			}
		});
	}
}
function confirmDeleteReceiver(id, receiver_name) {
	 $( "#dialog-confirm-services" ).dialog({
		 resizable: false,
		 height: "auto",
		 width: 400,
		 modal: true,
		 title: delete_word + " " + $('#' + receiver_name + '-chanel-' + id).val() + "?",
		 buttons: [{
			 text: delete_word,
			 click: function () {
				 $(this).dialog("close");
				 removeReceiver(receiver_name, id);
			 }
		 }, {
			 text: cancel_word,
			 click: function () {
				 $(this).dialog("close");
			 }
		 }]
	 });
}
function cloneReceiver(id, receiver_name) {
	$('#add-'+receiver_name+'-button').trigger( "click" );
	$('#'+receiver_name+'-token-add').val($('#'+receiver_name+'-token-'+id).val());
	$('#'+receiver_name+'-chanel-add').val($('#'+receiver_name+'-chanel-'+id).val());
}
function removeReceiver(receiver_name, receiver_id) {
	$("#" + receiver_name + "-table-" + receiver_id).css("background-color", "#f2dede");
	$.ajax({
		url: "/app/channel/receiver/" + receiver_name,
		data: {
			channel_id: receiver_id,
			token: $('#token').val()
		},
		type: "DELETE",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data == "ok") {
				$("#" + receiver_name + "-table-" + receiver_id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	});
}
function checkWebPanel() {
	$.ajax({
		url: "/app/channel/check/rabbit",
		// data: {
		//   token: $('#token').val()
		// },
		// type: "POST",
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
		url: "/app/channel/check/email",
		// data: {
		//   token: $('#token').val()
		// },
		// type: "POST",
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
