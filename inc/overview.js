var cur_url = window.location.href.split('/app/').pop();
cur_url = cur_url.split('/');
function showHapservers(serv, hostnamea, service) {
	var i;
	for (i = 0; i < serv.length; i++) {
		showHapserversCallBack(serv[i], hostnamea[i], service)
	}
}
function showHapserversCallBack(serv, hostnamea, service) {
	$.ajax( {
		url: "/app/service/" + service + "/" + serv + "/last-edit",
		beforeSend: function() {
			$("#edit_date_"+hostnamea).html('<img class="loading_small_haproxyservers" src="/app/static/images/loading.gif" />');
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				if (data.indexOf('ls: cannot access') != '-1') {
					$("#edit_date_" + hostnamea).empty();
					$("#edit_date_" + hostnamea).html();
				} else {
					$("#edit_date_" + hostnamea).empty();
					$("#edit_date_" + hostnamea).html(data);
				}
			}
		}
	} );
}
function overviewHapserverBackends(serv, hostnamea, service) {
	$.ajax( {
		url: "/app/service/" + service + "/backends/" + serv[0],
		beforeSend: function() {
			$("#top-"+hostnamea).html('<img class="loading_small" style="padding-left: 45%;" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#top-" + hostnamea).empty();
				$("#top-" + hostnamea).html(data);
			}
		}
	} );
}
function showOverview(serv, hostnamea) {
	showOverviewHapWI();
	showUsersOverview();
	var i;
	for (i = 0; i < serv.length; i++) {
		showOverviewCallBack(serv[i], hostnamea[i])
	}
	showSubOverview();
	showServicesOverview();
	updatingCpuRamCharts();
}
function showOverviewCallBack(serv, hostnamea) {
	$.ajax( {
		url: "/app/overview/server/"+serv,
		beforeSend: function() {
			$("#"+hostnamea).html('<img class="loading_small" src="/app/static/images/loading.gif" />');
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#" + hostnamea).empty();
				$("#" + hostnamea).html(data);
			}
		}
	} );
}
function showServicesOverview() {
	$.ajax( {
		url: "/app/overview/services",
		beforeSend: function() {
			$("#services_ovw").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/app/static/images/loading.gif" />');

		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#services_ovw").empty();
				$("#services_ovw").html(data);
			}
		}
	} );
}
function showOverviewServer(name, ip, id, service) {
	$.ajax( {
		url: "/app/service/cpu-ram-metrics/" + ip + "/" + id + "/" + name + "/" + service,
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#ajax-server-" + id).empty();
				$("#ajax-server-" + id).css('display', 'block');
				$("#ajax-server-" + id).css('background-color', '#fbfbfb');
				$("#ajax-server-" + id).css('border', '1px solid #A4C7F5');
				$(".ajax-server").css('display', 'block');
				$(".div-server").css('clear', 'both');
				$(".div-pannel").css('clear', 'both');
				$(".div-pannel").css('display', 'block');
				$(".div-pannel").css('padding-top', '10px');
				$(".div-pannel").css('height', '70px');
				$("#div-pannel-" + id).insertBefore('#up-pannel')
				$("#ajax-server-" + id).html(data);
				$.getScript("/inc/fontawesome.min.js")
				getChartDataHapWiRam()
				getChartDataHapWiCpu()
			}
		}					
	} );
}
function ajaxActionServers(action, id, service) {
	// var cur_url = window.location.href.split('/app/').pop();
	// cur_url = cur_url.split('/');
	$.ajax( {
		url: "/app/service/action/" + service + "/" + id + "/" + action,
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if( data ==  'Bad config, check please ' ) {
				toastr.error(data);
			} else {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					if (data.indexOf('warning: ') != '-1') {
						toastr.warning(data);
					} else {
						location.reload();
					}
				}
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
$( function() {
	try {
		if ((cur_url[0] == 'service' && cur_url[2] != '') || cur_url[0] == '') {
			ChartsIntervalId = setInterval(updatingCpuRamCharts, 30000);
			$(window).focus(function () {
				ChartsIntervalId = setInterval(updatingCpuRamCharts, 30000);
			});
			$(window).blur(function () {
				clearInterval(ChartsIntervalId);
			});
		}
	} catch (e) {
		console.log(e);
	}
	try {
		if (cur_url[0] == '') {
			UsersShowIntervalId = setInterval(showUsersOverview, 600000);
			$(window).focus(function () {
				UsersShowIntervalId = setInterval(showUsersOverview, 600000);
			});
			$(window).blur(function () {
				clearInterval(UsersShowIntervalId);
			});
		}
	} catch (e) {
		console.log(e);
	}
	$( "#show-all-users" ).click( function() {
		$(".show-users").show("fast");
		$("#hide-all-users").css("display", "block");
		$("#show-all-users").css("display", "none");
	});
	$("#hide-all-users").click(function() {
		$(".show-users").hide("fast");
		$("#hide-all-users").css("display", "none");
		$("#show-all-users").css("display", "block");
	});

	$( "#show-all-groups" ).click( function() {
		$(".show-groups").show("fast");
		$("#hide-all-groups").css("display", "block");
		$("#show-all-groups").css("display", "none");
	});
	$( "#hide-all-groups" ).click( function() {
		$(".show-groups").hide("fast");
		$("#hide-all-groups").css("display", "none");
		$("#show-all-groups").css("display", "block");
	});

	$( "#show-all-haproxy-wi-log" ).click( function() {
		$(".show-haproxy-wi-log").show("fast");
		$("#hide-all-haproxy-wi-log").css("display", "block");
		$("#show-all-haproxy-wi-log").css("display", "none");
	});
	$( "#hide-all-haproxy-wi-log" ).click( function() {
		$(".show-haproxy-wi-log").hide("fast");
		$("#hide-all-haproxy-wi-log").css("display", "none");
		$("#show-all-haproxy-wi-log").css("display", "block");
	});

	if (cur_url[0] == "" || cur_url[0] == "waf" || cur_url[0] == "metrics") {
		$('#secIntervals').css('display', 'none');
	}
	$('#apply_close').click( function() {
		$("#apply").css('display', 'none');
		localStorage.removeItem('restart');
	});
	$( ".server-act-links" ).change(function() {
		var id = $(this).attr('id').split('-');

		if (cur_url[0] != 'portscanner') {
			try {
				var service_name = id[2]
			} catch (err) {
				var service_name = 'haproxy'
			}

			updateHapWIServer(id[1], service_name)
		}
	});
});
function confirmAjaxAction(action, service, id) {
	var cancel_word = $('#translate').attr('data-cancel');
	var action_word = $('#translate').attr('data-'+action);
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + id + "?",
		buttons: [{
			text: action_word,
			click: function () {
				$(this).dialog("close");
				if (service == "haproxy") {
					ajaxActionServers(action, id, service);
					if (action == "restart" || action == "reload") {
						if (localStorage.getItem('restart')) {
							localStorage.removeItem('restart');
							$("#apply").css('display', 'none');
						}
					}
				} else if (service == "waf") {
					ajaxActionServers(action, id, 'waf_haproxy');
				} else if (service == "nginx") {
					ajaxActionServers(action, id, service);
				} else if (service == "keepalived") {
					ajaxActionServers(action, id, service);
				} else if (service == "apache") {
					ajaxActionServers(action, id, service);
				} else if (service == "waf_nginx") {
					ajaxActionServers(action, id, service);
				}
			}
		}, {
			text: cancel_word,
			click: function() {
				$( this ).dialog( "close" );
			}
		}]
	});
}
function updateHapWIServer(id, service_name) {
	var alert_en = 0;
	var metrics = 0;
	var active = 0;
	if ($('#alert-' + id).is(':checked')) {
		alert_en = '1';
	}
	if ($('#metrics-' + id).is(':checked')) {
		metrics = '1';
	}
	if ($('#active-' + id).is(':checked')) {
		active = '1';
	}
	$.ajax({
		url: "/app/service/" + service_name + "/tools/update",
		data: {
			server_id: id,
			name: $('#server-name-' + id).val(),
			metrics: metrics,
			alert_en: alert_en,
			active: active,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#server-" + id + "-" + service_name).addClass("update", 1000);
				setTimeout(function () {
					$("#server-" + id + "-" + service_name).removeClass("update");
				}, 2500);
			}
		}
	});
}
function change_pos(pos, id) {
	$.ajax({
		url: "/app/service/position/" + id + "/" + pos,
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		error: function () {
			console.log(w.data_error);
		}
	});
}
function showBytes(serv) {
	$.ajax( {
		url: "/app/service/haproxy/bytes",
		data: {
			showBytes: serv
		},
		type: "POST",
		beforeSend: function() {
			$("#show_bin_bout").html('<img class="loading_small_bin_bout" src="/app/static/images/loading.gif" />');
			$("#sessions").html('<img class="loading_small_bin_bout" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript("/inc/fontawesome.min.js")
			}
		}
	} );
}
function showNginxConnections(serv) {
	$.ajax( {
		url: "/app/service/nginx/connections",
		data: {
			nginxConnections: serv
		},
		type: "POST",
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript("/inc/fontawesome.min.js")
			}
		}
	} );
}
function showApachekBytes(serv) {
	$.ajax( {
		url: "/app/service/apache/bytes",
		data: {
			apachekBytes: serv
		},
		type: "POST",
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript("/inc/fontawesome.min.js")
			}
		}
	} );
}
function keepalivedBecameMaster(serv) {
	$.ajax( {
		url: "/app/service/keepalived/become-master",
		data: {
			keepalivedBecameMaster: serv
		},
		type: "POST",
		beforeSend: function() {
			$("#bin_bout").html('<img class="loading_small_bin_bout" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript("/inc/fontawesome.min.js")
			}
		}
	} );
}
function showUsersOverview() {
	$.ajax( {
		url: "overview/users",
		// data: {
		// 	show_users_ovw: 1,
		// 	token: $('#token').val()
		// },
		type: "GET",
		beforeSend: function() {
			$("#users-table").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#users-table").html(data);
			}
		}
	} );
}
function showSubOverview() {
	$.ajax( {
		url: "/app/overview/sub",
		// data: {
		// 	show_sub_ovw: 1,
		// 	token: $('#token').val()
		// },
		type: "GET",
		beforeSend: function() {
			$("#sub-table").html('<img class="loading_small_bin_bout" style="padding-left: 40%;padding-top: 40px;padding-bottom: 40px;" src="/app/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#sub-table").html(data);
			}
		}
	} );
}
function serverSettings(id, name) {
	var cancel_word = $('#translate').attr('data-cancel');
	var save_word = $('#translate').attr('data-save');
	var settings_word = $('#translate').attr('data-settings');
	var for_word = $('#translate').attr('data-for');
	var service = $('#service').val();
	$.ajax({
		url: "/app/service/settings/" + service + "/" + id,
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#dialog-settings-service").html(data)
				$("input[type=checkbox]").checkboxradio();
				$("#dialog-settings-service").dialog({
					resizable: false,
					height: "auto",
					width: 400,
					modal: true,
					title: settings_word + " " + for_word + " " + name,
					buttons: [{
						text: save_word,
						click: function () {
							$(this).dialog("close");
							serverSettingsSave(id, name, service, $(this));
						}
					}, {
						text: cancel_word,
						click: function () {
							$(this).dialog("close");
						}
					}]
				});
			}
		}
	});
}
function serverSettingsSave(id, name, service, dialog_id) {
	var haproxy_enterprise = 0;
	var service_dockerized = 0;
	var service_restart = 0;
	if ($('#haproxy_enterprise').is(':checked')) {
		haproxy_enterprise = '1';
	}
	if ($('#haproxy_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#nginx_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#apache_dockerized').is(':checked')) {
		service_dockerized = '1';
	}
	if ($('#haproxy_restart').is(':checked')) {
		service_restart = '1';
	}
	if ($('#nginx_restart').is(':checked')) {
		service_restart = '1';
	}
	if ($('#apache_restart').is(':checked')) {
		service_restart = '1';
	}
	$.ajax({
		url: "/app/service/settings/" + service,
		data: {
			serverSettingsSave: id,
			serverSettingsEnterprise: haproxy_enterprise,
			serverSettingsDockerized: service_dockerized,
			serverSettingsRestart: service_restart,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				dialog_id.dialog('close');
				location.reload();
			}
		}
	});
}
function check_service_status(id, ip, service) {
	NProgress.configure({showSpinner: false});
	if (service == 'keepalived') return false;
	$.ajax({
		url: "/app/service/action/" + service + "/check-service",
		data: {
			server_ip: ip
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (cur_url[0] == 'service') {
				if (data.indexOf('up') != '-1') {
					$('#div-server-' + id).addClass('div-server-head-up');
					$('#div-server-' + id).removeClass('div-server-head-down');
				} else if (data.indexOf('down') != '-1') {
					$('#div-server-' + id).removeClass('div-server-head-up');
					$('#div-server-' + id).addClass('div-server-head-down');
				}
			} else if (cur_url[0] == '') {
				let span_id = $('#' + service + "_" + id);
				if (data.indexOf('up') != '-1') {
					span_id.addClass('serverUp');
					span_id.removeClass('serverDown');
					if (span_id.attr('title').indexOf('Service is down') != '-1') {
						span_id.attr('title', 'Service running')
					}
				} else if (data.indexOf('down') != '-1') {
					span_id.addClass('serverDown');
					span_id.removeClass('serverUp');
					span_id.attr('title', 'Service is down')
				}
			}
		}
	});
	NProgress.configure({showSpinner: true});
}
