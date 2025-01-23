$( function() {
	$("select").selectmenu({
		width: 180
	});
	$('#hap').click(function () {
		if ($('#hap').is(':checked')) {
			$('#haproxy_docker_td').show();
			$('#haproxy_docker_td_header').show();
		} else {
			$('#haproxy_docker_td').hide();
			$('#haproxy_docker_td_header').hide();
		}
	});
	$('#nginx').click(function () {
		if ($('#nginx').is(':checked')) {
			$('#nginx_docker_td').show();
			$('#nginx_docker_td_header').show();
		} else {
			$('#nginx_docker_td').hide();
			$('#nginx_docker_td_header').hide();
		}
	});
	$("#ha-cluster-master").on('selectmenuchange', function () {
		let server_ip = $('#ha-cluster-master option:selected').val();
		let div_id = $('#cur_master_ver');
		get_keepalived_ver(div_id, server_ip);
	});
	$("#ha-cluster-master-interface").on('input', function () {
		let server_ip = $('#ha-cluster-master option:selected').val();
		get_interface($(this), server_ip);
	});
	$(".slave_int input").on('input', function () {
		let id = $(this).attr('id').split('-');
		let server_ip = $('#slave_int_div-' + id[1]).attr('data-ip');
		get_interface($(this), server_ip);
	});
});
function cleanProvisioningProccess(div_id, success_div, error_id, warning_id, progres_id) {
    $(div_id).empty();
    $(success_div).empty();
    $(success_div).hide();
    $(error_id).empty();
    $(error_id).hide();
    $(warning_id).empty();
    $(warning_id).hide();
    $(progres_id).css('width', '5%');
    $(div_id).each(function () {
        $(this).remove('');
    });
    $.getScript(awesome);
}
function confirmDeleteCluster(cluster_id) {
	$("#dialog-confirm").dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: delete_word + " " + $('#cluster-name-' + cluster_id).text() + "?",
		buttons: [{
			text: delete_word,
			click: function () {
				$(this).dialog("close");
				deleteCluster(cluster_id);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});
}
function deleteCluster(cluster_id) {
	$.ajax({
		url: api_prefix + "/ha/cluster/" + cluster_id,
		type: "DELETE",
		statusCode: {
			204: function (xhr) {
				$("#cluster-" + cluster_id).remove();
			},
			404: function (xhr) {
				$("#cluster-" + cluster_id).remove();
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
function createHaClusterStep1(edited=false, cluster_id=0, clean=true) {
	let next_word = translate_div.attr('data-next');
	let tabel_title = $("#create-ha-cluster-step-1-overview").attr('title');
	if (clean) {
		clearClusterDialog(edited);
		$.ajax({
			url: "/ha/cluster/masters",
			async: false,
			type: "GET",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
				} else {
					for (let i in data) {
						$('#ha-cluster-master').append('<option value="' + data[i]['ip'] + '" selected="selected" data-id="'+data[i]['server_id']+'">' + data[i]['hostname'] + '</option>');
					}
					$('#ha-cluster-master').selectmenu("refresh");
				}
			}
		});
	}
	if (edited) {
		tabel_title = $("#create-ha-cluster-step-1-overview").attr('data-edit');
	}
	if (edited && clean) {
		let master_name = $('#master-server-'+cluster_id).text();
		let master_ip = $('#master-ip-'+cluster_id).text();
		let master_id = $('#master-id-'+cluster_id).text();
		$("#ha-cluster-master option").not(master_name).each(function (index) {
			$(this).prop('disabled', true);
		});
		$('#ha-cluster-master').append('<option value="' + master_ip + '" selected="selected" data-id="'+master_id+'">' + master_name + '</option>').selectmenu("refresh");
		get_keepalived_ver($('#cur_master_ver'), master_ip);
		$.ajax({
			url: api_prefix + "/ha/cluster/" + cluster_id,
			type: "GET",
			async: false,
			success: function (data) {
				let clusterSettings = JSON.parse(JSON.stringify(data));
				$('#ha-cluster-name').val(clusterSettings.name.replaceAll("'", ""));
				$('#ha-cluster-desc').val(clusterSettings.description.replaceAll("'", ""));
				$('#ha-cluster-master-interface').val(clusterSettings.eth);
				$('#vrrp-ip').val(clusterSettings.vip);
				if (clusterSettings.haproxy) {
					$('#hap').prop('checked', true);
				} else {
					$('#hap').prop('checked', false);
				}
				if (clusterSettings.nginx) {
					$('#nginx').prop('checked', true);
				} else {
					$('#nginx').prop('checked', false);
				}
				if (clusterSettings.return_master) {
					$('#return_master').prop('checked', true);
				} else {
					$('#return_master').prop('checked', false);
				}
				if (clusterSettings.syn_flood) {
					$('#syn_flood').prop('checked', true);
				} else {
					$('#syn_flood').prop('checked', false);
				}
				if (clusterSettings.virt_server) {
					$('#virt_server').prop('checked', true);
				} else {
					$('#virt_server').prop('checked', false);
				}
				if (clusterSettings.use_src) {
					$('#use_src').prop('checked', true);
				} else {
					$('#use_src').prop('checked', false);
				}
				$( "input[type=checkbox]" ).checkboxradio("refresh");
			}
		});
	}
	$.ajax({
		url: "/ha/cluster/slaves/servers/" + cluster_id,
		async: false,
		type: "GET",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$(".checks").html(data);
			}
		}
	});
	$.getScript(ha);
	let regx = /^[a-zA-Z0-9_-]+$/;
	let dialog_div = $("#create-ha-cluster-step-1").dialog({
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
				if ($('#ha-cluster-name').val() == '') {
					toastr.error('error: Fill in the Name field');
					return false;
				}
				if ($('#ha-cluster-master option:selected').val().indexOf('--') != '-1') {
					toastr.error('error: Select a Master server');
					return false;
				}
				if (!regx.test($('#ha-cluster-master-interface').val())) {
					toastr.error('error: Fill in the interface field');
					return false;
				}
				if ($('#vrrp-ip').val() == '') {
					toastr.error('error: Fill in the VIP field');
					return false;
				}
				if (!ValidateIPaddress($('#vrrp-ip').val())) {
					toastr.error('error: Wrong VIP');
					return false;
				}
				let jsonData = createJsonCluster('#enabled-check div div span');
				if (!validateSlaves(jsonData)) {
					return false;
				}
				createHaClusterStep2(edited, cluster_id, jsonData);
				$(this).dialog("close");
				toastr.clear();
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearClusterDialog(edited);
			}
		}]
	});
	dialog_div.dialog('open');
}
function createHaClusterStep2(edited=false, cluster_id=0, jsonData='') {
	let apply_word = translate_div.attr('data-apply');
	let tabel_title = $("#create-ha-cluster-step-2-overview").attr('title');
	if (edited) {
		tabel_title = $("#create-ha-cluster-step-2-overview").attr('data-edit');
	}
	let dialog_div = $("#create-ha-cluster-step-2").dialog({
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
				$(this).dialog("close");
				saveCluster(jsonData, cluster_id, edited);
			}
		}, {
			text: apply_word,
			click: function () {
				$(this).dialog("close");
				saveCluster(jsonData, cluster_id, edited, 1);
			}
		}, {
			text: back_word,
			click: function () {
				$(this).dialog("close");
				createHaClusterStep1(edited, cluster_id, false);
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
				clearClusterDialog(edited);
			}
		}]
	});
	dialog_div.dialog('open');
}
function saveCluster(jsonData, cluster_id=0, edited=0, reconfigure=0) {
	let virt_server = 0;
	let return_master = 0;
	let syn_flood = 0;
	let use_src = 0;
	let hap = 0;
	let hap_docker = 0;
	let nginx = 0;
	let nginx_docker = 0;
	let apache = 0;
	let caddy = 0;
	let apache_docker = 0;
	let req_method = 'POST';
	let url = api_prefix + '/ha/cluster';
	if ($('#virt_server').is(':checked')) {
		virt_server = 1;
	}
	if ($('#return_master').is(':checked')) {
		return_master = '1';
	}
	if ($('#syn_flood').is(':checked')) {
		syn_flood = '1';
	}
	if ($('#use_src').is(':checked')) {
		use_src = '1';
	}
	if ($('#hap').is(':checked')) {
		hap = '1';
	}
	if ($('#hap_docker').is(':checked')) {
		hap_docker = '1';
	}
	if ($('#nginx').is(':checked')) {
		nginx = '1';
	}
	if ($('#nginx_docker').is(':checked')) {
		nginx_docker = '1';
	}
	if ($('#apache').is(':checked')) {
		apache = '1';
	}
	if ($('#caddy').is(':checked')) {
		caddy = '1';
	}
	if ($('#caddy_docker').is(':checked')) {
		caddy_docker = '1';
	}
	if (edited) {
		req_method = 'PUT';
		url = api_prefix + '/ha/cluster/' + cluster_id;
	}
	jsonData['name'] = $('#ha-cluster-name').val();
	jsonData['description'] = $('#ha-cluster-desc').val();
	jsonData['vip'] = $('#vrrp-ip').val();
	jsonData['virt_server'] = virt_server;
	jsonData['return_master'] = return_master;
	jsonData['syn_flood'] = syn_flood;
	jsonData['use_src'] = use_src;
	jsonData['services'] = {'haproxy': {'enabled': hap, 'docker': hap_docker}};
	jsonData['services']['nginx'] = {'enabled': nginx, 'docker': nginx_docker};
	jsonData['services']['apache'] = {'enabled': apache, 'docker': 0};
	jsonData['services']['caddy'] = {'enabled': caddy, 'docker': caddy_docker};
	jsonData['router_id'] = $('#router_id-' + cluster_id).val();
	$.ajax({
		url: url,
		type: req_method,
		async: false,
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				if (!edited) {
					cluster_id = data.id;
					getHaCluster(cluster_id, true);
				} else {
					getHaCluster(cluster_id);
					$("#cluster-" + cluster_id).addClass("update", 1000);
					setTimeout(function () {
						$("#cluster-" + cluster_id).removeClass("update");
					}, 2500);
				}
			}
		}
	});
	if (reconfigure) {
		Reconfigure(jsonData, cluster_id);
	}
}
function Reconfigure(jsonData, cluster_id) {
	let servers = JSON.parse(JSON.stringify(jsonData));
	$("#wait-mess").html(wait_mess);
	$("#wait-mess").show();
	let total_installation = 1;
	if (servers['services']['haproxy']['enabled']) {
		total_installation = total_installation + 1;
	}
	if (servers['services']['nginx']['enabled']) {
		total_installation = total_installation + 1;
	}
	if (servers['services']['apache']['enabled']) {
		total_installation = total_installation + 1;
	}
	if (servers['services']['caddy']['enabled']) {
		total_installation = total_installation + 1;
	}
	let server_creating_title = $("#server_creating1").attr('title');
	let server_creating = $("#server_creating1").dialog({
		autoOpen: false,
		width: 574,
		modal: true,
		title: server_creating_title,
		close: function () {
			cleanProvisioningProccess('#server_creating1 ul li', '#created-mess', '#creating-error', '#creating-warning', '#creating-progress');
		},
		buttons: {
			Close: function () {
				$(this).dialog("close");
				cleanProvisioningProccess('#server_creating1 ul li', '#created-mess', '#creating-error', '#creating-warning', '#creating-progress');
			}
		}
	});
	server_creating.dialog('open');
	let progress_step = 100 / total_installation;
	$.when(installServiceCluster(jsonData, 'keepalived', progress_step, cluster_id)).done(function () {
		if (servers['services']['haproxy']['enabled']) {
			$.when(installServiceCluster(jsonData, 'haproxy', progress_step, cluster_id)).done(function () {
				if (servers['services']['nginx']['enabled']) {
					$.when(installServiceCluster(jsonData, 'nginx', progress_step, cluster_id)).done(function () {
						if (servers['services']['apache']['enabled']) {
							installServiceCluster(jsonData, 'apache', progress_step, cluster_id);
						}
					});
				} else {
					if (servers['services']['apache']['enabled']) {
						installServiceCluster(jsonData, 'apache', progress_step, cluster_id);
					}
				}
			});
		} else {
			if (servers['services']['nginx']['enabled']) {
				$.when(installServiceCluster(jsonData, 'nginx', progress_step, cluster_id)).done(function () {
					if (servers['services']['apache']['enabled']) {
						installServiceCluster(jsonData, 'apache', progress_step, cluster_id);
					}
				});
			} else {
				if (servers['services']['apache']['enabled']) {
					installServiceCluster(jsonData, 'apache', progress_step, cluster_id);
				}
			}
		}
	});
}
function installServiceCluster(jsonData, service, progress_step, cluster_id) {
	let servers = JSON.parse(JSON.stringify(jsonData));
	servers['cluster_id'] = cluster_id;
	let li_id = 'creating-' + service + '-';
	let install_mess = translate_div.attr('data-installing');
	let timeout_mess = translate_div.attr('data-roxywi_timeout');
	let something_wrong = translate_div.attr('data-something_wrong');
	$('#server_creating_list').append('<li id="' + li_id + servers['cluster_id'] + '" class="server-creating proccessing">' + install_mess + ' ' + nice_service_name[service] + '</li>');
	return $.ajax({
		url: "/install/" + service,
		type: "POST",
		data: JSON.stringify(servers),
		contentType: "application/json; charset=utf-8",
		statusCode: {
			500: function () {
				showErrorStatus(nice_service_name[service], servers["name"], li_id, servers['cluster_id'], progress_step, something_wrong);
			},
			504: function () {
				showErrorStatus(nice_service_name[service], servers["name"], li_id, servers['cluster_id'], progress_step, timeout_mess);
			},
		},
		success: function (data) {
			if (data.status === 'failed') {
				showErrorStatus(nice_service_name[service], servers["name"], li_id, servers['cluster_id'], progress_step, something_wrong);
			} else {
				checkInstallResp(data, servers['cluster_id'], progress_step, servers["name"], li_id, nice_service_name[service]);
			}
		}
	});
}
function showErrorStatus(service_name, server_name, li_id, server_id, progress_step, message) {
	let check_apache_log = translate_div.attr('data-check_apache_log');
	$('#' + li_id + server_id).removeClass('proccessing');
	$('#' + li_id + server_id).addClass('processing_error');
	$.getScript(awesome);
	$('#creating-error').show();
	$('#creating-error').append('<div>' + message + ' ' + service_name + ' ' + server_name + '. '+check_apache_log+'</div>');
	increaseProgressValue(progress_step);
}
function checkInstallResp(output, server_id, progress_step, name, li_id, service_name) {
	output = JSON.parse(JSON.stringify(output));
	let was_installed = translate_div.attr('data-was_installed');
	let something_wrong = translate_div.attr('data-something_wrong');
	for (let k in output['ok']) {
		$('#' + li_id + server_id).removeClass('proccessing');
		$('#' + li_id + server_id).addClass('proccessing_done');
		$('#created-mess').show();
		$('#created-mess').append('<div>' + service_name + ' ' + was_installed +' ' + k + '</div>');
	}
	for (let k in output['failures']) {
		showErrorStatus(service_name, k, li_id, server_id, progress_step, something_wrong);
	}
	for (let k in output['dark']) {
		showErrorStatus(service_name, k, li_id, server_id, progress_step, something_wrong);
	}
	increaseProgressValue(progress_step);
	$.getScript(awesome);
}
function increaseProgressValue(progress_step) {
	let progress_id = '#creating-progress';
	let waid_id = '#wait-mess';
	progress_step = Math.ceil(parseFloat(progress_step));
	let cur_proggres_value = $(progress_id).css('width').split('px')[0] / $(progress_id).parent().width() * 100;
	let new_progress = Math.ceil(parseFloat(cur_proggres_value)) + progress_step;
	new_progress = Math.ceil(parseFloat(new_progress));
	if (parseFloat(new_progress) > 90) {
		$(waid_id).hide();
		new_progress = parseFloat(100);
		$('.progress-bar-striped > div').css('animation', '');
	}
	$(progress_id).css('width', new_progress+'%');
}
function add_vip_ha_cluster(cluster_id, cluster_name, vip_id='', vip='', edited=0) {
	let save_word = translate_div.attr('data-save');
	let tabel_title = $("#add-vip-table").attr('title');
	let buttons = [];
	if (edited) {
		$.ajax({
			url: api_prefix + "/ha/cluster/" + cluster_id + "/vip/" + vip_id,
			type: "GET",
			async: false,
			success: function (data) {
				let clusterSettings = JSON.parse(JSON.stringify(data));
				if (clusterSettings.return_master) {
					$('#vrrp-ip-add-return_master').prop('checked', true);
				} else {
					$('#vrrp-ip-add-return_master').prop('checked', false);
				}
				if (clusterSettings.virt_server) {
					$('#vrrp-ip-add-virt_server').prop('checked', true);
				} else {
					$('#vrrp-ip-add-virt_server').prop('checked', false);
				}
				if (clusterSettings.use_src) {
					$('#vrrp-ip-add-use_src').prop('checked', true);
				} else {
					$('#vrrp-ip-add-use_src').prop('checked', false);
				}
				$( "input[type=checkbox]" ).checkboxradio("refresh");
			}
		});
		$('#vrrp-ip-add').val(vip);
		tabel_title = $("#add-vip-table").attr('data-edit');
		buttons = [{
			text: save_word,
			click: function () {
				if (!ValidateIPaddress($('#vrrp-ip-add').val())) {
					toastr.error('error: Wrong VIP');
					return false;
				}
				jsonData = createJsonVip('#vip_servers div span');
				if (!validateSlaves(jsonData)) {
					return false;
				}
				saveVip(jsonData, cluster_id, $(this), edited, vip_id);
				toastr.clear();
			}
		}, {
			text: delete_word,
			click: function () {
				if (!ValidateIPaddress($('#vrrp-ip-add').val())) {
					toastr.error('error: Wrong VIP');
					return false;
				}
				jsonData = createJsonVip('#vip_servers div span');
				saveVip(jsonData, cluster_id, $(this), edited, vip_id, true);
				toastr.clear();
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog('close');
				clearClusterDialog();
				toastr.clear();
			}
		}]
	} else {
		buttons = [{
			text: save_word,
			click: function () {
				if (!ValidateIPaddress($('#vrrp-ip-add').val())) {
					toastr.error('error: Wrong VIP');
					return false;
				}
				jsonData = createJsonVip('#vip_servers div span');
				if (!validateSlaves(jsonData)) {
					return false;
				}
				saveVip(jsonData, cluster_id, $(this), edited, vip_id);
				toastr.clear();
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog('close');
				clearClusterDialog();
				toastr.clear();
			}
		}]
	}
	let url = "/ha/cluster/slaves/" + cluster_id;
	if (vip_id) {
		url = "/ha/cluster/slaves/" + cluster_id + "/" + vip_id;
	}
	$.ajax({
		url: url,
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#vip_servers').html(data);
			}
		}
	});
	$.getScript(ha);
	let dialog_div = $("#add-vip").dialog({
		autoOpen: false,
		resizable: false,
		height: "auto",
		width: 630,
		modal: true,
		title: tabel_title + ' ' + cluster_name,
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		close: function () {
			clearClusterDialog($(this));
		},
		buttons: buttons
	});
	dialog_div.dialog('open');
}
function saveVip(jsonData, cluster_id, dialog_id, edited, vip_id='', deleted=false) {
	let req_type = 'POST'
	let return_master = 0
	let virt_server = 0
	let use_src = 0
	if ($('#vrrp-ip-add-return_master').is(':checked')) {
		return_master = '1';
	}
	if ($('#vrrp-ip-add-virt_server').is(':checked')) {
		virt_server = true;
	}
	if ($('#vrrp-ip-add-use_src').is(':checked')) {
		use_src = '1';
	}
	jsonData['vip'] = $('#vrrp-ip-add').val();
	jsonData['return_master'] = return_master;
	jsonData['virt_server'] = virt_server;
	jsonData['use_src'] = use_src;
	let url = api_prefix + "/ha/cluster/" + cluster_id + "/vip";
	if (edited) {
		req_type = 'PUT';
		url = api_prefix + "/ha/cluster/" + cluster_id + "/vip/" + vip_id;
	}
	if (deleted) {
		req_type = 'DELETE';
		url = api_prefix + "/ha/cluster/" + cluster_id + "/vip/" + vip_id;
	}
	$.ajax({
		url: url,
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: req_type,
		statusCode: {
			204: function (xhr) {
				getHaCluster(cluster_id);
				dialog_id.dialog('destroy');
				clearClusterDialog();
			},
			404: function (xhr) {
				getHaCluster(cluster_id);
				dialog_id.dialog('destroy');
				clearClusterDialog();
			}
		},
		success: function (data) {
			if (data) {
				if (data.status === "failed") {
					toastr.error(data);
				} else {
					getHaCluster(cluster_id);
					dialog_id.dialog('destroy');
					clearClusterDialog();
				}
			}
		}
	});
}
function get_interface(input_id, server_ip) {
	input_id.autocomplete({
		source: function (request, response) {
			$.ajax({
				url: "/server/show/if/" + server_ip,
				success: function (data) {
					data = data.replace(/\s+/g, ' ');
					if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
						toastr.error(data);
					} else {
						response(data.split(" "));
					}
				}
			});
		},
		autoFocus: true,
		minLength: -1
	});
}
function get_keepalived_ver(div_id, server_ip) {
	$.ajax({
		url: api_prefix + "/service/keepalived/" + server_ip + "/status",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			404: function (xhr) {
				div_id.text('Keepalived has not installed');
			}
		},
		success: function (data) {
			if (!data.Version) {
				div_id.text('Keepalived has not installed');
			} else {
				div_id.text(data.Version);
				div_id.css('font-weight', 'bold');
			}
		}
	});
}
function addCheckToStatus(server_id, server_ip) {
	let hostname = $('#add_check-' + server_id).attr('data-name');
	let service_word = translate_div.attr('data-service');
	let start_enter = translate_div.attr('data-start_enter');
	let length_tr = $('#all-checks').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<div class="' + tr_class + '" id="remove_check-' + server_id + '" data-name="' + hostname + '">' +
		'<div class="check-name"><div style="display: inline-block; width: 150px;">' + hostname + '</div>' +
		'<span class="slave_int" id="slave_int_div-' + server_id + '" data-ip="' + server_ip + '">' +
		'<input id="slave_int-' + server_id + '" title="'+start_enter+'" placeholder="eth0" size="7" class="form-control"></span></div>' +
		'<div class="add_user_group check-button" onclick="removeCheckFromStatus(' + server_id + ', \'' + server_ip + '\')" title="' + delete_word + ' ' + service_word + '">-</div>' +

		'</div>';
	$('#add_check-' + server_id).remove();
	$("#enabled-check").append(html_tag);
	$.getScript(ha);
}
function removeCheckFromStatus(server_id, server_ip) {
	let hostname = $('#remove_check-' + server_id).attr('data-name');
	let add_word = translate_div.attr('data-add');
	let service_word = translate_div.attr('data-service');
	let length_tr = $('#all_services tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<div class="' + tr_class + ' all-checks" id="add_check-' + server_id + '" data-name="' + hostname + '">' +
		'<div class="check-name">' + hostname + '</div>' +
		'<div class="add_user_group check-button" onclick="addCheckToStatus(' + server_id + ',  \'' + server_ip + '\')" title="' + add_word + ' ' + service_word + '">+</div></div>';
	$('#remove_check-' + server_id).remove();
	$("#all-checks").append(html_tag);
}
function createJsonCluster(div_id) {
	let jsonData = {};
	jsonData = {'servers': []};
	jsonData['servers'].push({
		'id': $('#ha-cluster-master option:selected').attr('data-id'),
		'eth': $('#ha-cluster-master-interface').val(),
		'master': 1
	});
	$(div_id).each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		let eth = $('#slave_int-' + this_id).val();
		jsonData['servers'].push({'id': this_id, 'eth': eth, 'master': 0});
	});
	return jsonData;
}
function createJsonVip(div_id) {
	let jsonData = {};
	jsonData = {'servers': []};
	$(div_id).each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		let eth1 = $('#slave_int-' + this_id).val();
		let eth = $('#master_int-' + this_id).val();
		if (eth) {
			jsonData['servers'].push({'id': this_id, 'eth': eth, 'master': 1});
		} else {
			jsonData['servers'].push({'id': this_id,'eth': eth1, 'master': 0});
		}
	});

	return jsonData;
}
function validateSlaves(jsonData) {
	console.log(jsonData)
	if (Object.keys(jsonData['servers']).length === 1) {
		toastr.error('error: There is must be at least one slave server');
		return false;
	}
	for (const [key, value] of Object.entries(jsonData['servers'])) {
		for (const [key1, value1] of Object.entries(value)) {
			if (value1.length === 0) {
				toastr.error('error: Enter interface for slave server');
				return false;
			}
		}
	}
	return true;
}
function clearClusterDialog(edited=0) {
	$('#ha-cluster-name').val('');
	$('#ha-cluster-desc').val('');
	$('#ha-cluster-master-interface').val('');
	$('#vrrp-ip').val('');
	$('#vrrp-ip').prop("readonly", false);
	$('#vrrp-ip-add').val('');
	$('#vrrp-ip-edit').val('');
	$('#cur_master_ver').text('');
	$('#virt_server').prop('checked', true);
	$('#return_master').prop('checked', true);
	$('#use_src').prop('checked', false);
	$('#hap').prop('checked', false);
	$('#hap_docker').prop('checked', false);
	$('#nginx').prop('checked', false);
	$('#nginx_docker').prop('checked', false);
	$("input[type=checkbox]").checkboxradio("refresh");
	$('#ha-cluster-master option:selected').remove();
	$("#ha-cluster-master option").each(function (index) {
		$(this).remove();
		$(this).prop('disabled', false);
	});
	$('#ha-cluster-master option').attr('selected', false);
	$('#ha-cluster-master option:first').attr('selected', 'selected');
	$('#ha-cluster-master').selectmenu("refresh");
}
function getHaCluster(cluster_id, new_cluster=false) {
	$.ajax({
		url: "/ha/cluster/get/" + cluster_id,
		success: function (data) {
			data = data.replace(/^\s+|\s+$/g, '');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				if (new_cluster) {
					$('.up-pannel').append(data);
				} else {
					$('#cluster-' + cluster_id).replaceWith(data);
				}
				$.getScript(awesome);
				$('#cluster-' + cluster_id).removeClass('animated-background');
			}
		}
	});
}
