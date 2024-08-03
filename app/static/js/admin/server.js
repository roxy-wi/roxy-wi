$( function() {
   $('#add-server-button').click(function() {
		addServerDialog.dialog('open');
	});
	let server_tabel_title = $( "#server-add-table-overview" ).attr('title');
	let addServerDialog = $( "#server-add-table" ).dialog({
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
    $( "#ajax-servers input" ).change(function() {
		let id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#ajax-servers select" ).on('selectmenuchange',function() {
		let id = $(this).attr('id').split('-');
		updateServer(id[1])
	});
	$( "#scan_server" ).change(function() {
		if ($('#scan_server').is(':checked')) {
			$('.services_for_scan').hide();
		} else {
			$('.services_for_scan').show();
		}
	});
});
function addServer(dialog_id) {
    toastr.clear()
    let valid = true;
    let servername = $('#new-server-add').val();
    let ip = $('#new-ip').val();
    let server_group = $('#new-server-group-add').val();
    let cred = $('#credentials').val();
    let scan_server = 0;
    let type_ip = 0;
    let enable = 0;
    let haproxy = 0;
    let nginx = 0;
    let apache = 0;
    let firewall = 0;
    let add_to_smon = 0;
    if ($('#scan_server').is(':checked')) {
        scan_server = '1';
    }
    if ($('#type_ip').is(':checked')) {
        type_ip = '1';
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
    let allFields = $([]).add($('#new-server-add')).add($('#new-ip')).add($('#new-port'))
    allFields.removeClass("ui-state-error");
    valid = valid && checkLength($('#new-server-add'), "Hostname", 1);
    valid = valid && checkLength($('#new-ip'), "IP", 1);
    valid = valid && checkLength($('#new-port'), "Port", 1);
    if (cred == null) {
        toastr.error('First select credentials');
        return false;
    }
    if (server_group === '------') {
        toastr.error('First select a group');
        return false;
    }
	if (server_group === undefined || server_group === null) {
		server_group = $('#new-sshgroup').val();
	}
    if (valid) {
        let json_data = {
            "hostname": servername,
            "ip": ip,
            "port": $('#new-port').val(),
            "group_id": server_group,
            "type_ip": type_ip,
            "haproxy": haproxy,
            'nginx': nginx,
            "apache": apache,
            "firewall_enable": firewall,
            "add_to_smon": add_to_smon,
            "enabled": enable,
            "master": $('#slavefor').val(),
            "cred_id": cred,
            "description": $('#desc').val(),
            "protected": 0
        }
        $.ajax({
            url: "/server",
            type: "POST",
            data: JSON.stringify(json_data),
            contentType: "application/json; charset=utf-8",
            success: function (data) {
                if (data.status === 'failed') {
                    toastr.error(data.error);
                } else {
                    common_ajax_action_after_success(dialog_id, 'newserver', 'ajax-servers', data.data);
                    $("input[type=submit], button").button();
                    $("input[type=checkbox]").checkboxradio();
                    $(".controlgroup").controlgroup();
                    $("select").selectmenu();
                    let id = data.id;
                    $('select:regex(id, git-server)').append('<option value=' + id + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, backup-server)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, haproxy_exp_addserv)').append('<option value=' +ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, nginx_exp_addserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, apache_exp_addserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, node_exp_addserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, geoipserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, haproxyaddserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, nginxaddserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                    $('select:regex(id, apacheaddserv)').append('<option value=' + ip + '>' + servername + '</option>').selectmenu("refresh");
                }
            }
        });
    }
}
function updateServer(id) {
	toastr.clear();
	let type_ip = 0;
	let enable = 0;
	let firewall = 0;
	let protected_serv = 0;
	if ($('#type_ip-' + id).is(':checked')) {
		type_ip = '1';
	}
	if ($('#enable-' + id).is(':checked')) {
		enable = '1';
	}
	if ($('#firewall-' + id).is(':checked')) {
		firewall = '1';
	}
	if ($('#protected-' + id).is(':checked')) {
		protected_serv = '1';
	}
	let group = $('#servergroup-' + id + ' option:selected').val();
	if (group === undefined || group === null) {
		group = $('#new-sshgroup').val();
	}
	let json_data = {
		"hostname": $('#hostname-' + id).val(),
		"port": $('#port-' + id).val(),
		"ip": $('#ip-' + id).text(),
		"group_id": group,
		"type_ip": type_ip,
		"firewall_enable": firewall,
		"enabled": enable,
		"master": $('#slavefor-' + id + ' option:selected').val(),
		"cred_id": $('#credentials-' + id + ' option:selected').val(),
		"description": $('#desc-' + id).val(),
		"protected": protected_serv
	}
	$.ajax({
		url: "/server/" + id,
		type: 'PUT',
		contentType: "application/json; charset=utf-8",
		data: JSON.stringify(json_data),
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				$("#server-" + id).addClass("update", 1000);
				setTimeout(function () {
					$("#server-" + id).removeClass("update");
				}, 2500);
			}
		}
	});
}
function confirmDeleteServer(id) {
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
function cloneServer(id) {
	$( "#add-server-button" ).trigger( "click" );
	if ($('#enable-'+id).is(':checked')) {
		$('#enable').prop('checked', true)
	} else {
		$('#enable').prop('checked', false)
	}
	if ($('#type_ip-'+id).is(':checked')) {
		$('#type_ip').prop('checked', true)
	} else {
		$('#type_ip').prop('checked', false)
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
	$('#type_ip').checkboxradio("refresh");
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
	if (cur_url[0].indexOf('admin') != '-1') {
		$('#new-server-group-add').val($('#servergroup-'+id+' option:selected').val()).change()
		$('#new-server-group-add').selectmenu("refresh");
	}
}
function removeServer(id) {
	$("#server-" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/server/" + id,
		type: "DELETE",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			204: function (xhr) {
				$("#server-" + id).remove();
			},
			404: function (xhr) {
				$("#server-" + id).remove();
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
function viewFirewallRules(ip) {
	$.ajax({
		url: "/server/firewall/" + ip,
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
function updateServerInfo(ip, id) {
	$.ajax({
		url: "/server/system_info/update/" + ip + "/" + id,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1' || data.indexOf('error_code') != '-1') {
				toastr.error(data);
			} else {
				$("#server-info").html(data);
				$('#server-info').show();
				$.getScript(awesome);
			}
		}
	});
}
function showServerInfo(id, ip) {
	let server_info = translate_div.attr('data-server_info');
	$.ajax({
		url: "/server/system_info/get/" + ip + "/" +id,
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
	});
}
async function serverIsUp(server_id) {
	let server_div = $('#server_status-' + server_id);
	$.ajax({
		url: "/server/check/server/" + server_id,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'up') {
				server_div.removeClass('serverNone');
				server_div.removeClass('serverDown');
				server_div.addClass('serverUp');
				server_div.attr('title', 'Server is reachable');
			} else if (data.status === 'down') {
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
			$('#hostname-' + server_id).val(data.name);
			$('#ip-' + server_id).val(data.ip);
			$('#port-' + server_id).val(data.port);
			$('#desc-' + server_id).val(data.description);
			if (data.enabled === 1) {
				$('#enable-' + server_id).prop('checked', true);
			} else {
				$('#enable-' + server_id).prop('checked', false);
			}
			if (data.protected === 1) {
				$('#protected-' + server_id).prop('checked', true);
			} else {
				$('#protected-' + server_id).prop('checked', false);
			}
			if (data.type_ip === 1) {
				$('#type_ip-' + server_id).prop('checked', true);
			} else {
				$('#type_ip-' + server_id).prop('checked', false);
			}
			$('#type_ip-' + server_id).checkboxradio("refresh");
			$('#protected-' + server_id).checkboxradio("refresh");
			$('#enable-' + server_id).checkboxradio("refresh");
			$('#servergroup-' + server_id).val(data.group_id).change();
			$('#credentials-' + server_id).val(data.creds_id).change();
			$('#slavefor-' + server_id).val(data.slave).change();
			$('#servergroup-' + server_id).selectmenu("refresh");
			$('#credentials-' + server_id).selectmenu("refresh");
			$('#slavefor-' + server_id).selectmenu("refresh");
		}
	});
}
function openChangeServerServiceDialog(server_id) {
	let user_groups_word = translate_div.attr('data-user_groups');
	let hostname = $('#hostname-' + server_id).val();
	$.ajax({
		url: "/server/services/" + server_id,
		success: function (data) {
			$("#groups-roles").html(data);
			$("#groups-roles").dialog({
				resizable: false,
				height: "auto",
				width: 700,
				modal: true,
				title: user_groups_word + ' ' + hostname,
				buttons: [{
					text: save_word,
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
	let service_name = $('#add_service-'+service_id).attr('data-service_name');
	let length_tr = $('#checked_services tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="'+tr_class+'" id="remove_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="removeServiceFromUser('+service_id+')" title="'+delete_word+' '+service_word+'">-</span></td></tr>';
	$('#add_service-'+service_id).remove();
	$("#checked_services tbody").append(html_tag);
}
function removeServiceFromServer(service_id) {
	let service_name = $('#remove_service-'+service_id).attr('data-service_name');
	let length_tr = $('#all_services tbody tr').length;
	let tr_class = 'odd';
	if (length_tr % 2 != 0) {
		tr_class = 'even';
	}
	let html_tag = '<tr class="'+tr_class+'" id="add_service-'+service_id+'" data-service_name="'+service_name+'">' +
		'<td class="padding20" style="width: 100%;">'+service_name+'</td>' +
		'<td><span class="add_user_group" onclick="addServiceToUser('+service_id+')" title="'+add_word+' '+service_word+'">+</span></td></tr>';
	$('#remove_service-'+service_id).remove();
	$("#all_services tbody").append(html_tag);
}
function changeServerServices(server_id) {
	let jsonData = {};
	$('#checked_services tbody tr').each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		jsonData[this_id] = 1
	});
	$('#all_services tbody tr').each(function () {
		let this_id = $(this).attr('id').split('-')[1];
		jsonData[this_id] = 0
	});
	$.ajax({
		url: "/server/services/" + server_id,
		data: {
			jsonDatas: JSON.stringify(jsonData),
			changeServerServicesServer: $('#hostname-' + server_id).val(),
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			} else {
				$("#server-" + server_id).addClass("update", 1000);
				setTimeout(function () {
					$("#server-" + server_id).removeClass("update");
				}, 2500);
			}
		}
	});
}
