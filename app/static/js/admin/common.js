$( function() {
    $("#tabs ul li").click(function () {
        let activeTab = $(this).find("a").attr("href");
        let activeTabClass = activeTab.replace('#', '');
        $('.menu li ul li').each(function () {
            $(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
            $(this).find('a').css('padding-left', '20px')
            $(this).find('a').css('background-color', '#48505A');
            $(this).children("." + activeTabClass).css('padding-left', '30px');
            $(this).children("." + activeTabClass).css('border-left', '4px solid var(--right-menu-blue-rolor)');
            $(this).children("." + activeTabClass).css('background-color', 'var(--right-menu-blue-rolor)');
        });
        if (activeTab == '#tools') {
            loadServices();
        } else if (activeTab == '#settings') {
            loadSettings();
        } else if (activeTab == '#updatehapwi') {
            loadupdatehapwi();
        } else if (activeTab == '#openvpn') {
            loadopenvpn();
        } else if (activeTab == '#backup') {
            loadBackup();
        }
    });
} );
window.onload = function() {
	$('#tabs').tabs();
	let activeTabIdx = $('#tabs').tabs('option','active')
	if (cur_url[0].split('#')[0] == 'admin') {
		if (activeTabIdx == 6) {
			loadServices();
		} else if (activeTabIdx == 3) {
			loadSettings();
		} else if (activeTabIdx == 4) {
			loadBackup();
		} else if (activeTabIdx == 7) {
			loadupdatehapwi();
		} else if (activeTabIdx == 8) {
			loadopenvpn();
		}
	}
}
function updateService(service, action='update') {
	$("#ajax-update").html('')
	$("#ajax-update").html(wait_mess);
	$.ajax({
		url: "/app/admin/tools/update/" + service,
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('Complete!') != '-1' || data.indexOf('Unpacking') != '-1') {
				toastr.clear();
				toastr.success(service + ' has been ' + action + 'ed');
			} else if (data.indexOf('Unauthorized') != '-1' || data.indexOf('Status code: 401') != '-1') {
				toastr.clear();
				toastr.error('It looks like there is no authorization in the Roxy-WI repository. Your subscription may have expired or there is no subscription. How to get the <b><a href="https://roxy-wi.org/pricing" title="Pricing" target="_blank">subscription</a></b>');
			} else if (data.indexOf('but not installed') != '-1') {
				toastr.clear();
				toastr.error('There is setting for Roxy-WI repository, but Roxy-WI is installed without repository. Please reinstall with package manager');
			} else if (data.indexOf('No Match for argument') != '-1' || data.indexOf('Unable to find a match') != '-1') {
				toastr.clear();
				toastr.error('It seems like Roxy-WI repository is not set. Please read docs for <b><a href="https://roxy-wi.org/updates">detail</a></b>');
			} else if (data.indexOf('password for') != '-1') {
				toastr.clear();
				toastr.error('It seems like apache user needs to be add to sudoers. Please read docs for <b><a href="https://roxy-wi.org/installation#ansible">detail</a></b>');
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
			} else if (data.indexOf('0 upgraded, 0 newly installed') != '-1') {
				toastr.info('There is no a new version of ' + service);
			} else {
				toastr.clear();
				toastr.success(service + ' has been ' + action + 'ed');
			}
			$("#ajax-update").html('');
			loadupdatehapwi();
			loadServices();
			show_version();
		}
	});
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
	$("#" + id).css("background-color", "#f2dede");
	$.ajax({
		url: "/app/admin/openvpn/delete",
		data: {
			openvpndel: id
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data == "ok") {
				$("#" + id).remove();
			} else if (data.indexOf('error:') != '-1' || data.indexOf('unique') != '-1') {
				toastr.error(data);
			}
		}
	});
}
function uploadOvpn() {
	toastr.clear();
	if ($("#ovpn_upload_name").val() == '' || $('#ovpn_upload_file').val() == '') {
		toastr.error('All fields must be completed');
	} else {
		$.ajax({
			url: "/app/admin/openvpn/upload",
			data: {
				uploadovpn: $('#ovpn_upload_file').val(),
				ovpnname: $('#ovpn_upload_name').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('danger') != '-1' || data.indexOf('unique') != '-1' || data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (data.indexOf('success') != '-1') {
					toastr.clear();
					toastr.success(data);
					location.reload();
				} else {
					toastr.error('Something wrong, check and try again');
				}
			}
		});
	}
}
function OpenVpnSess(id, action) {
	$.ajax({
		url: "/app/admin/openvpn/" + action + "/" + id,
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
	});
}
function loadSettings() {
	$.ajax({
		url: "/app/admin/settings",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$('#settings').html(data);
				$.getScript(awesome);
				$( "input[type=checkbox]" ).checkboxradio();
				$( "select" ).selectmenu();
			}
		}
	} );
}
function loadServices() {
	$.ajax({
		url: "/app/admin/tools",
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
		url: "/app/admin/update",
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
function checkUpdateRoxy() {
	$.ajax({
		url: "/app/admin/update/check",
		success: function (data) {
			loadupdatehapwi();
		}
	} );
}
function loadopenvpn() {
	$.ajax({
		url: "/app/admin/openvpn",
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
function confirmAjaxServiceAction(action, service) {
	let action_word = translate_div.attr('data-'+action);
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
				ajaxActionServices(action, service);
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function ajaxActionServices(action, service) {
	$.ajax( {
		url: "/app/admin/tools/action/" + service + "/" + action,
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('Failed') != '-1') {
				toastr.error(data);
			} else if (data.indexOf('warning: ') != '-1') {
				toastr.warning(data);
			} else {
				window.history.pushState("services", "services", cur_url[0].split("#")[0] + "#tools");
				toastr.success('The ' + service + ' has been ' + action +'ed');
				loadServices();
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function showApacheLog(serv) {
	let rows = $('#rows').val();
	let grep = $('#grep').val();
	let exgrep = $('#exgrep').val();
	let hour = $('#time_range_out_hour').val();
	let minute = $('#time_range_out_minut').val();
	let hour1 = $('#time_range_out_hour1').val();
	let minute1 = $('#time_range_out_minut1').val();
	let url = "/app/logs/apache_internal/" + serv + "/" + rows;
	$.ajax( {
		url: url,
		data: {
			rows: rows,
			serv: serv,
			grep: grep,
			exgrep: exgrep,
			hour: hour,
			minute: minute,
			hour1: hour1,
			minute1: minute1
		},
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
		}
	} );
}
