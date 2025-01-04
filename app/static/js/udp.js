$( function() {
	$("#cluster_id").on('selectmenuchange', function () {
		let cluster_id = $("#cluster_id option:selected").val();
		if (cluster_id != '------' && cluster_id != '' && cluster_id != undefined) {
			getHAClusterVIPS(cluster_id);
		} else {
			clearUdpVip();
		}
	});
	$("#ip").autocomplete({
		source: function (request, response) {
			if (!checkIsServerFiled('#serv')) return false;
			if (request.term == "") {
				request.term = 1
			}
			$.ajax({
				url: `/server/${$("#serv").val()}/ip`,
				contentType: "application/json; charset=UTF-8",
				success: function (data) {
					response(data);
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
	$('#check_enabled').click(function () {
		if ($('#check_enabled').is(':checked')) {
			$('.check_backends').show();
		} else {
			$('.check_backends').hide();
		}
	});
});
function getHAClusterVIPS(cluster_id) {
	let vip_id = $('#vip');
	$.ajax({
		url: api_prefix + `/ha/cluster/${cluster_id}/vips`,
		async: false,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
				return false;
			} else {
				clearUdpVip();
				vip_id.append('<option value="------" selected>------</option>')
				data.forEach(function (obj) {
					vip_id.append('<option value="' + obj.id + '">' + obj.vip + '</option>')
				});
				vip_id.selectmenu("refresh");
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
			url: `${api_prefix}/udp/listener/${listener_id}`,
			type: "GET",
			async: false,
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				$('#name').val(data.name.replaceAll("'", ""));
				$('#new-listener-type').val(place);
				$('#port').val(data.port);
				$('#delay_loop').val(data.delay_loop);
				$('#delay_before_retry').val(data.delay_before_retry);
				$('#retry').val(data.retry);
				$('#lb_algo').val(data.lb_algo).change();
				$('#lb_algo').selectmenu('refresh');
				$('#desc').val(data.description.replaceAll("'", ""));
				if (data.check_enabled) {
					$('#check_enabled').prop('checked', true);
					$('.check_backends').show();
				} else {
					$('#check_enabled').prop('checked', false);
					$('.check_backends').hide();
				}
				$("#check_enabled").checkboxradio("refresh");
				if (place === 'cluster') {
					$.when(getHAClusterVIPS(data.cluster_id)).done(function () {
						$("#vip option").filter(function () {
							return $(this).text() == data.vip;
						}).attr('selected', true);
						$("#vip").selectmenu('refresh');
					});
					$("#cluster_id").val(data.cluster_id).change();
					$("#cluster_id").attr('disabled', 'disabled');
					$("#cluster_id").selectmenu('refresh');
				} else {
					$("#serv").val(data.server_id).change();
					$("#serv").attr('disabled', 'disabled');
					$("#serv").selectmenu('refresh');
					$('#ip').val(data.vip);
				}
				$('#new-udp-servers-td').empty();
				$('#new-udp-servers-td').append('<a class="link add-server" title="Add backend server" onclick="createBackendServer()"></a>');
				data.config = JSON.stringify(data.config);
				let config = JSON.parse(data.config)
				for (let server of config) {
					createBackendServer(server.backend_ip, server.port, server.weight);
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
				if (!validateUDPListenerForm(place)) {
					return false;
				}
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
	if ($('#name').val() == '') {
		toastr.error('error: Fill in the Name field');
		return false;
	}
	if ($('#port').val() == '') {
		toastr.error('error: Fill in the Port field');
		return false;
	}
	if (place == 'server') {
		if ($('#ip').val() == '') {
			toastr.error('error: Fill in the IP field');
			return false;
		}
		if (!ValidateIPaddress($('#ip').val())) {
			toastr.error('error: Wrong IP');
			return false;
		}
		if ($('#serv option:selected').val().indexOf('--') != '-1') {
			toastr.error('error: Select a server');
			return false;
		}
	} else {
		if ($('#cluster_id option:selected').val().indexOf('--') != '-1') {
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
		if ($('#vip option:selected').val().indexOf('--') != '-1') {
			toastr.error('error: Select the VIP address');
			return false;
		}
		if (!ValidateIPaddress($('#vip option:selected').text())) {
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
	indexed_array['config'] = [];
	indexed_array['check_enabled'] = 0;

	$.map(unindexed_array, function (n, i) {
		if (n['name'] === 'serv') {
			indexed_array['server_id'] = n['value'];
		} else if (n['name'] === 'check_enabled') {
			if ($('#check_enabled').is(':checked')) {
				indexed_array['check_enabled'] = 1;
			}
		} else {
			indexed_array[n['name']] = n['value'];
		}
	});

	$('.servers').each(function () {
		let backend_ip = $(this).children("input[name='new-udp-server']").val();
		if (backend_ip === undefined || backend_ip === '') {
			return;
		}
		let port = $(this).children("input[name='new-udp-port']").val();
		let weight = $(this).children("input[name='new-udp-weight']").val();
		indexed_array['config'].push({backend_ip, port, weight});
	});
	if ($('#cluster_id').val()) {
		indexed_array['cluster_id'] = $('#cluster_id').val();
	} else {
		indexed_array['cluster_id'] = null;
	}
	if ($('#new-listener-type').val() === 'cluster') {
		indexed_array['router_id'] = $('#vip').val();
		indexed_array['vip'] = $('#vip option:selected').text();
	} else {
		indexed_array['vip'] = $('#ip').val();
	}
	$("#serv").attr('disabled', 'disabled');
	$("#serv").selectmenu('refresh');
	return indexed_array;
}
function saveUdpListener(jsonData, dialog_id, listener_id=0, edited=0, reconfigure=0) {
	let req_method = 'POST';
	let url = api_prefix + "/udp/listener";
	if (reconfigure) {
		jsonData['reconfigure'] = 1;
	}
	if (edited) {
		req_method = 'PUT';
		url = api_prefix + "/udp/listener/" + listener_id;
	}
	$.ajax({
		url: url,
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
					listener_id = data.id;
					getUDPListener(listener_id, true);
				}
				dialog_id.dialog("close");
				toastr.success('Listener ' + data.status);
			}
		}
	});
}
function Reconfigure(listener_id) {
	return $.ajax({
		url: "/install/udp",
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
		url: "/udp/listener/" + listener_id,
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
				$.getScript(awesome);
			}
		}
	});
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
	$.ajax({
		url: api_prefix + "/udp/listener/" + listener_id,
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$('#listener-' + listener_id).remove();
			},
			404: function (xhr) {
				$('#listener-' + listener_id).remove();
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data.error);
				}
			}
		}
	});
}
function clearListenerDialog(edited=0) {
	$('#new-listener-name').val('');
	$('#new-listener-desc').val('');
	$('#new-udp-ip').val('');
	$('#vrrp-ip').prop("readonly", false);
	$('#delay_loop').val(10);
	$('#delay_before_retry').val(10);
	$('#retry').val(3);
	$('#new-listener-port').val('');
	$("#cluster_id").attr('disabled', false);
	$("#serv").attr('disabled', false);
	$('#check_enabled').prop('checked', true);
	$('.check_backends').show();
	$("#check_enabled").checkboxradio("refresh");
	clearUdpVip()
	$('#new-udp-servers-td').empty();
	$('#new-udp-servers-td').append('<a class="link add-server" title="Add backend server" onclick="createBackendServer()"></a>');
	createBackendServer();
	let selects = ['new-udp-type', 'cluster_id', 'vip', 'serv']
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
	$('#vip').selectmenu( "destroy" );
	$('#vip').empty();
	$('#vip').selectmenu();
}
function confirmUdpBalancerAction(action, listener_id) {
	let action_word = translate_div.attr('data-'+action);
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
        url: `${api_prefix}/udp/listener/${listener_id}/${action}`,
        type: "GET",
        contentType: "application/json; charset=utf-8",
        success: function (data) {
            if (data.status === 'failed') {
                toastr.error(data.error);
                return false;
            } else {
                toastr.success(`Listener has been ${action}ed`);
				getUDPListener(listener_id);
				checkStatus(listener_id);
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
function checkStatus(listener_id) {
	if (sessionStorage.getItem('check-service-udp-'+listener_id) == 0) {
		return false;
	}
	NProgress.configure({showSpinner: false});
	let listener_div = $('#listener-' + listener_id);
	$.ajax({
		url: api_prefix + "/udp/listener/" + listener_id,
		contentType: "application/json; charset=utf-8",
		statusCode: {
			404: function (xhr) {
				$('#listener-' + listener_id).remove();
			},
			403: function (xhr) {
				sessionStorage.setItem('check-service-udp-'+listener_id, 0);
			},
			500: function (xhr) {
				sessionStorage.setItem('check-service-udp-'+listener_id, 0);
			}
		},
		success: function (data) {
			try {
				if (data.indexOf('logout') != '-1') {
					sessionStorage.setItem('check-service-udp-'+listener_id, 0);
				}
			} catch (e) {}

			if (data.status === 'ok') {
				listener_div.addClass('div-server-head-up');
				listener_div.attr('title', 'All services are UP');
				listener_div.removeClass('div-server-head-down');
				listener_div.removeClass('div-server-head-unknown');
				listener_div.removeClass('div-server-head-dis');
			} else if (data.status === 'failed' || data.status === 'error') {
				listener_div.removeClass('div-server-head-unknown');
				listener_div.removeClass('div-server-head-dis');
				listener_div.removeClass('div-server-head-up');
				listener_div.addClass('div-server-head-down');
				listener_div.attr('title', 'All services are DOWN');
			} else if (data.status === 'warning') {
				listener_div.addClass('div-server-head-unknown');
				listener_div.removeClass('div-server-head-up');
				listener_div.removeClass('div-server-head-down');
				listener_div.removeClass('div-server-head-dis');
				listener_div.attr('title', 'Not all services are UP');
			}
			$(`#listener-name-${listener_id}`).text(data.name.replaceAll("'", ""));
			if (data.description === '') {
				$(`#listener-desc-${listener_id}`).text('');
			} else {
				$(`#listener-desc-${listener_id}`).text(`(${data.description.replaceAll("'", "")})`);
			}
			$(`#port-${listener_id}`).text(data.port);
			$(`#vip-${listener_id}`).text(data.vip);
		}
	});
	NProgress.configure({showSpinner: true});
}
function checkUdpBackendStatus(listener_id, backend_ip) {
	$.ajax({
        url: `/udp/listener/${listener_id}/${backend_ip}`,
        type: "GET",
        contentType: "application/json; charset=utf-8",
        success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
				return false;
			} else {
				let server_div = $('#backend_server_status_' + backend_ip.replaceAll('.', ''));
				if (data.data === 'yes') {
					server_div.removeClass('serverNone');
					server_div.removeClass('serverDown');
					server_div.addClass('serverUp');
					server_div.attr('title', 'Server is reachable');
				} else if (data.data === 'no') {
					server_div.removeClass('serverNone');
					server_div.removeClass('serverUp');
					server_div.addClass('serverDown');
					server_div.attr('title', 'Server is unreachable');
				} else {
					server_div.removeClass('serverDown');
					server_div.removeClass('serverUp');
					server_div.addClass('serverNone');
					server_div.attr('title', 'Cannot get server status');
				}
			}
		}
    });
}
