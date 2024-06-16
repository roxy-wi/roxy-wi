$( function() {
	$( "#ha-cluster" ).on('selectmenuchange',function()  {
		let cluster_id = $( "#ha-cluster option:selected" ).val();
		if (cluster_id != '------') {
			getHAClusterVIPS(cluster_id);
		} else {
			clearUdpVip();
		}
	});
	$("#new-udp-ip").autocomplete({
		source: function (request, response) {
			if (!checkIsServerFiled('#serv')) return false;
			if (request.term == "") {
				request.term = 1
			}
			$.ajax({
				url: "/app/server/show/ip/" + $("#serv").val(),
				success: function (data) {
					data = data.replace(/\s+/g, ' ');
					response(data.split(" "));
				}
			});
		},
		appendTo: "#create-udp-step-2",
		autoFocus: true,
		minLength: -1,
		select: function (event, ui) {
			$('#new-listener-port').focus();
		}
	});
});
function getHAClusterVIPS(cluster_id) {
	$.ajax({
		url: `/app/ha/cluster/${cluster_id}/vips`,
		async: false,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
				return false;
			} else {
				clearUdpVip();
				$('#new-udp-vip').append('<option value="------" selected>------</option>')
				data.forEach(function (obj) {
					$('#new-udp-vip').append('<option value="' + obj.id + '">' + obj.vip + '</option>')
				});
				$('#new-udp-vip').selectmenu("refresh");
			}
		}
	});
	return true;
}
function createUDPListener(edited=false, listener_id=0, clean=true) {
	let next_word = translate_div.attr('data-next');
	let tabel_title = $("#create-udp-step-1-overview").attr('title');
	clearListenerDialog();
	if (edited) {
		tabel_title = $("#create-udp-step-1-overview").attr('data-edit');
	}
	if (edited && clean) {
		let place = $('#listener-type-'+ listener_id).val();
		if (place === 'cluster') {
			$('.new-udp-ha-cluster-tr').show();
			$('.new-udp-servers-tr').hide();
		} else {
			$('.new-udp-ha-cluster-tr').hide();
			$('.new-udp-servers-tr').show();
		}
		$.ajax({
			url: `/app/udp/listener/${listener_id}/settings`,
			type: "GET",
			async: false,
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				$('#new-listener-name').val(data.name.replaceAll("'", ""));
				$('#new-listener-type').val(place);
				$('#new-listener-port').val(data.port);
				$('#new-listener-desc').val(data.desc.replaceAll("'", ""));
				if (place === 'cluster') {
					$.when(getHAClusterVIPS(data.cluster_id)).done(function () {
						$("#new-udp-vip option").filter(function () {
							return $(this).text() == data.vip;
						}).attr('selected', true);
						$("#new-udp-vip").selectmenu('refresh');
					});
					$("#ha-cluster").val(data.cluster_id).change();
					$("#ha-cluster").attr('disabled', 'disabled');
					$("#ha-cluster").selectmenu('refresh');
				} else {
					$("#serv").val(data.server_id).change();
					$("#serv").attr('disabled', 'disabled');
					$("#serv").selectmenu('refresh');
					$('#new-udp-ip').val(data.vip);
				}
				$('#new-udp-servers-td').empty();
				$('#new-udp-servers-td').append('<a class="link add-server" title="Add backend server" onclick="createBackendServer()"></a>');
				for(let server in data.config) {
					createBackendServer(server, data.config[server]['port'], data.config[server]['weight']);
				}
			}
		});
		createUDPListenerStep2(edited, listener_id, place);
		return false;
	}
	let dialog_div = $("#create-udp-step-1").dialog({
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
			text: next_word,
			click: function () {
				if ($('#new-udp-type option:selected').val().indexOf('--') != '-1') {
					toastr.error('error: Select Listener type');
					return false;
				}
				let place = '';
				if ($('#new-udp-type option:selected').val() == 'cluster') {
					$('.new-udp-ha-cluster-tr').show();
					$('.new-udp-servers-tr').hide();
					place = 'cluster';
				} else {
					$('.new-udp-ha-cluster-tr').hide();
					$('.new-udp-servers-tr').show();
					place = 'server';
				}
				$('#new-listener-type').val(place);
				createUDPListenerStep2(edited, listener_id, place);
				$(this).dialog("close");
				toastr.clear();
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearListenerDialog(edited);
			}
		}]
	});
	dialog_div.dialog('open');
}
function createUDPListenerStep2(edited, listener_id, place) {
	let apply_word = translate_div.attr('data-apply');
	let back_word = translate_div.attr('data-back');
	let tabel_title = $("#create-udp-step-2-overview").attr('title');
	if (edited) {
		tabel_title = $("#create-udp-step-1-overview").attr('data-edit');
	}
	let dialog_div = $("#create-udp-step-2").dialog({
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
			text: save_word,
			click: function () {
				if (!validateUDPListenerForm(place)) {
					return false;
				}
				jsonData = getFormData($("#create_udp_listener"));
				saveUdpListener(jsonData, $(this), listener_id, edited);
			}
		}, {
			text: apply_word,
			click: function () {
				jsonData = getFormData($("#create_udp_listener"));
				saveUdpListener(jsonData, $(this), listener_id, edited, 1);
			}
		}, {
			text: back_word,
			click: function () {
				$(this).dialog("close");
				createUDPListener(edited, listener_id, false);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearListenerDialog(edited);
			}
		}]
	});
	dialog_div.dialog('open');
}
function validateUDPListenerForm(place) {
	if ($('#new-listener-name').val() == '') {
		toastr.error('error: Fill in the Name field');
		return false;
	}
	if ($('#new-listener-port').val() == '') {
		toastr.error('error: Fill in the Port field');
		return false;
	}
	if (place == 'server') {
		if ($('#new-udp-ip').val() == '') {
			toastr.error('error: Fill in the IP field');
			return false;
		}
		if (!ValidateIPaddress($('#new-udp-ip').val())) {
			toastr.error('error: Wrong IP');
			return false;
		}
		if ($('#serv option:selected').val().indexOf('--') != '-1') {
			toastr.error('error: Select a server');
			return false;
		}
	} else {
		if ($('#ha-cluster option:selected').val().indexOf('--') != '-1') {
			toastr.error('error: Select a HA cluster');
			return false;
		}
		if ($('#new-udp-ha-ports').val() == '') {
			toastr.error('error: Fill in the Port field');
			return false;
		}
		if ($('#new-udp-ha-weight').val() == '') {
			toastr.error('error: Fill in the Weight field');
			return false;
		}
		if ($('#new-udp-vip option:selected').val().indexOf('--') != '-1') {
			toastr.error('error: Select the VIP address');
			return false;
		}
		if (!ValidateIPaddress($('#new-udp-vip option:selected').text())) {
			toastr.error('error: Wrong VIP');
			return false;
		}
	}
	return true;
}
function getFormData($form) {
	$("#serv").attr('disabled', false);
	$("#serv").selectmenu('refresh');
	let unindexed_array = $form.serializeArray();
	let indexed_array = {};
	indexed_array['servers'] = {};
	console.log(unindexed_array)

	$.map(unindexed_array, function (n, i) {
		indexed_array[n['name']] = n['value'];
	});
	$('.servers').each(function () {
		let ip = $(this).children("input[name='new-udp-server']").val();
		if (ip === undefined || ip === '') {
			return;
		}
		let port = $(this).children("input[name='new-udp-port']").val();
		let weight = $(this).children("input[name='new-udp-weight']").val();
		indexed_array['servers'][ip] = {port, weight};
	});
	indexed_array['ha-cluster'] = $('#ha-cluster').val();
	indexed_array['new-udp-router_id'] = $('#new-udp-vip').val();
	indexed_array['new-udp-vip'] = $('#new-udp-vip option:selected').text();
	$("#serv").attr('disabled', 'disabled');
	$("#serv").selectmenu('refresh');
	return indexed_array;
}
function saveUdpListener(jsonData, dialog_id, listener_id=0, edited=0, reconfigure=0) {
	let req_method = 'POST';
	if (edited) {
		req_method = 'PUT';
		jsonData['listener_id'] = listener_id;
	}
	$.ajax({
		url: "/app/udp/listener",
		type: req_method,
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				if (edited) {
					getUDPListener(listener_id);
					$("#listener-" + listener_id).addClass("update", 1000);
					setTimeout(function () {
						$("#listener-" + listener_id).removeClass("update");
					}, 2500);
				} else {
					listener_id = data.listener_id;
					getUDPListener(data.listener_id, true);
				}
				if (reconfigure) {
					NProgress.start();
					$.when(Reconfigure(listener_id)).done(function () {
						dialog_id.dialog("close");
						NProgress.done();
					});
				} else {
					dialog_id.dialog("close");
				}
				toastr.success('Listener ' + data.status);
			}
		}
	});
}
function Reconfigure(listener_id) {
	return $.ajax({
		url: "/app/install/udp",
		data: JSON.stringify({listener_id: listener_id}),
		contentType: "application/json; charset=utf-8",
		async: false,
		type: "POST",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				parseAnsibleJsonOutput(data, 'UDP listener', '');
			}
		}
	});
}
function getUDPListener(listener_id, new_listener=false) {
	$.ajax({
		url: "/app/udp/listener/" + listener_id,
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				if (new_listener) {
					$('.up-pannel').append(data);
				} else {
					$('#listener-' + listener_id).replaceWith(data);
				}
				$('#listener-'+listener_id).removeClass('animated-background');
			}
		}
	});
	$.getScript(awesome);
}
function confirmDeleteListener(listener_id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#listener-name-' + listener_id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				deleteListener(listener_id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function deleteListener(listener_id) {
	let jsonData = {'listener_id': listener_id}
	$.ajax({
		url: "/app/udp/listener",
		type: "DELETE",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				$('#listener-' + listener_id).remove();
			}
		}
	});
}
function clearListenerDialog(edited=0) {
	$('#new-listener-name').val('');
	$('#new-listener-desc').val('');
	$('#ha-cluster-master-interface').val('');
	$('#new-udp-ip').val('');
	$('#vrrp-ip').prop("readonly", false);
	$('#new-listener-port').val('');
	$("#ha-cluster").attr('disabled', false);
	$("#serv").attr('disabled', false);
	clearUdpVip()
	$('#new-udp-servers-td').empty();
	$('#new-udp-servers-td').append('<a class="link add-server" title="Add backend server" onclick="createBackendServer()"></a>');
	createBackendServer();
	let selects = ['new-udp-type', 'ha-cluster', 'new-udp-vip', 'serv']
	for (let select of selects) {
		unselectSelectMenu(select);
	}
}
function unselectSelectMenu(select_id) {
	$('#' + select_id + ' option').attr('selected', false);
	$('#' + select_id + ' option:first').attr('selected', 'selected');
	$('#' + select_id).selectmenu("refresh");
}
function clearUdpVip() {
	$('#new-udp-vip').selectmenu( "destroy" );
	$('#new-udp-vip').empty();
	$('#new-udp-vip').selectmenu();
}
function confirmUdpBalancerAction(action, listener_id) {
	let action_word = translate_div.attr('data-'+action);
	console.log('#litener-name-'+listener_id);
	let l_name = $('#listener-name-'+listener_id).text();
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + l_name + "?",
		buttons: [{
			text: action_word,
			click: function () {
				$(this).dialog("close");
				ajaxActionListener(action, listener_id);
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function ajaxActionListener(action, listener_id) {
	$.ajax({
        url: `/app/udp/listener/${listener_id}/${action}`,
        type: "GET",
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data.error);
                return false;
            } else {
                toastr.success(`Listener has been ${action}ed`);
				getUDPListener(listener_id);
            }
        }
    });
}
function createBackendServer(server='', port='', weight='1') {
	let server_word = translate_div.attr('data-server');
	let port_word = translate_div.attr('data-port');
	let weight_word = translate_div.attr('data-weight');
	let delete_word = translate_div.attr('data-delete');
	$('<div class="servers">' +
		server_word+': <input name="new-udp-server" value="' + server + '" class="form-control" placeholder="10.0.0.1">' +
		port_word + ': <input name="new-udp-port" value="' + port + '" type="number" class="form-control" placeholder="443" style="width: 50px">' +
		weight_word + ': <input name="new-udp-weight" value="' + weight + '" type="number" class="form-control" style="width: 30px">' +
		'<span class="minus minus-style" title="'+delete_word+' '+server_word+'" onclick="$(this).parent().remove()"></span>' +
		'</div>').insertBefore('.add-server');
	$.getScript(awesome);
}
