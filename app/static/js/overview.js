var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('/');
function showHapservers(serv, hostnamea, service) {
	let i;
	for (i = 0; i < serv.length; i++) {
		showHapserversCallBack(serv[i], hostnamea[i], service)
	}
}
function showHapserversCallBack(serv, hostnamea, service) {
	$.ajax({
		url: "/service/" + service + "/" + serv + "/last-edit",
		beforeSend: function () {
			$("#edit_date_" + hostnamea).html('<img class="loading_small_haproxyservers" src="/static/images/loading.gif" />');
		},
		type: "GET",
		success: function (data) {
			if (data.indexOf('ls: cannot access') != '-1') {
				$("#edit_date_" + hostnamea).empty();
				$("#edit_date_" + hostnamea).html();
			} else {
				$("#edit_date_" + hostnamea).empty();
				$("#edit_date_" + hostnamea).html(data);
			}
		}
	});
}
function overviewHapserverBackends(serv, hostname, service) {
	let div = '';
	$.ajax( {
		url: `/service/${service}/${serv[0]}/backend`,
		beforeSend: function() {
			$("#top-"+hostname).html('<img class="loading_small" style="padding-left: 45%;" src="/static/images/loading.gif" />');
		},
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				$('.div-backends').css('height', 'auto');
				$("#top-" + hostname).empty();
				for (let i in data.data) {
					if (service === 'haproxy') {
						div = `<a href="/config/section/haproxy/${serv}/${data.data[i]}" target="_blank" style="padding-right: 10px;">${data.data[i]}</a> `
					} else if (service === 'nginx' || service === 'apache') {
						div = `<a href="/config/${service}/${serv}/show/${i}" target="_blank" style="padding-right: 10px;">${data.data[i]}</a>`;
					} else {
						div = data.data[i];
					}
					$("#top-" + hostname).append(div);
				}
			}
		}
	} );
}
function showOverview(serv, hostnamea) {
	showOverviewHapWI();
	showUsersOverview();
	let i;
	for (i = 0; i < serv.length; i++) {
		showOverviewCallBack(serv[i], hostnamea[i])
	}
	showSubOverview();
	showServicesOverview();
	updatingCpuRamCharts();
}
function showOverviewCallBack(serv, hostnamea) {
	$.ajax( {
		url: "/overview/server/"+serv,
		beforeSend: function() {
			$("#"+hostnamea).html('<img class="loading_small" src="/static/images/loading.gif" />');
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
				$("#"+hostnamea).html("");
			} else {
				$("#" + hostnamea).empty();
				$("#" + hostnamea).html(data);
			}
		}
	} );
}
function showServicesOverview() {
	$.ajax( {
		url: "/overview/services",
		beforeSend: function() {
			$("#services_ovw").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');

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
		url: "/service/cpu-ram-metrics/" + ip + "/" + id + "/" + name + "/" + service,
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#ajax-server-" + id).empty();
				$(".ajax-server").css('display', 'block');
				$(".div-server").css('clear', 'both');
				$(".div-pannel").css('clear', 'both');
				$(".div-pannel").css('display', 'block');
				$(".div-pannel").css('padding-top', '10px');
				$(".div-pannel").css('height', '70px');
				$("#div-pannel-" + id).insertBefore('#up-pannel')
				$("#ajax-server-" + id).html(data);
				$.getScript(awesome)
				getChartDataHapWiRam()
				getChartDataHapWiCpu()
			}
		}					
	} );
}
function ajaxActionServers(action, id, service) {
	$.ajax({
		url: "/service/" + service + "/" + id + "/" + action,
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				location.reload();
			}
		}
	});
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
		let id = $(this).attr('id').split('-');

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
	let action_word = translate_div.attr('data-'+action);
	let name = $('#server-name-'+id).val();
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: action_word + " " + name + "?",
		buttons: [{
			text: action_word,
			click: function () {
				$(this).dialog("close");
				if (service === "haproxy") {
					ajaxActionServers(action, id, service);
					if (action === "restart" || action === "reload") {
						if (localStorage.getItem('restart')) {
							localStorage.removeItem('restart');
							$("#apply").css('display', 'none');
						}
					}
				} else if (service === "waf") {
					ajaxActionServers(action, id, 'waf_haproxy');
				} else {
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
	let alert_en = 0;
	let metrics = 0;
	let active = 0;
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
		url: "/service/" + service_name + "/tools/update",
		data: {
			server_id: id,
			name: $('#server-name-' + id).val(),
			metrics: metrics,
			alert_en: alert_en,
			active: active
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
		url: "/service/position/" + id + "/" + pos,
		error: function () {
			console.log(w.data_error);
		}
	});
}
function showBytes(serv) {
	$.ajax( {
		url: "/service/haproxy/bytes/" + serv,
		beforeSend: function() {
			$("#show_bin_bout").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showNginxConnections(serv) {
	$.ajax( {
		url: "/service/nginx/connections/" + serv,
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showApachekBytes(serv) {
	$.ajax( {
		url: "/service/apache/bytes/" + serv,
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function keepalivedBecameMaster(serv) {
	$.ajax( {
		url: "/service/keepalived/become-master/" + serv,
		beforeSend: function() {
			$("#bin_bout").html('<img class="loading_small_bin_bout" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#bin_bout").html(data);
				$.getScript(awesome)
			}
		}
	} );
}
function showUsersOverview() {
	$.ajax( {
		url: "overview/users",
		type: "GET",
		beforeSend: function() {
			$("#users-table").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');
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
		url: "/overview/sub",
		type: "GET",
		beforeSend: function() {
			$("#sub-table").html('<img class="loading_small_bin_bout" style="padding-left: 40%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');
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
	let settings_word = translate_div.attr('data-settings');
	let for_word = translate_div.attr('data-for');
	let service = $('#service').val();
	$.ajax({
		url: "/service/settings/" + service + "/" + id,
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
	let haproxy_enterprise = 0;
	let service_dockerized = 0;
	let service_restart = 0;
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
		url: "/service/settings/" + service,
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
	if (sessionStorage.getItem('check-service-'+service+'-'+id) === '0') {
		return false;
	}
	NProgress.configure({showSpinner: false});
	let server_div = $('#div-server-' + id);
	$.ajax({
		url: "/service/" + service + "/" + id + "/status",
		contentType: "application/json; charset=utf-8",
		statusCode: {
			401: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			},
			404: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			},
			500: function (xhr) {
				sessionStorage.setItem('check-service-'+service+'-'+id, '0')
			}
		},
		success: function (data) {
			if (cur_url[0] === 'overview') {
				let span_id = $('#' + service + "_" + id);
				if (data.status === 'failed') {
					span_id.addClass('serverDown');
					span_id.removeClass('serverUp');
					span_id.attr('title', 'Service is down')
				} else {
					span_id.addClass('serverUp');
					span_id.removeClass('serverDown');
					if (span_id.attr('title').indexOf('Service is down') != '-1') {
						span_id.attr('title', 'Service running')
					}
				}
			} else {
				if (data.status === 'failed') {
					server_div.removeClass('div-server-head-unknown');
					server_div.removeClass('div-server-head-dis');
					server_div.removeClass('div-server-head-up');
					server_div.addClass('div-server-head-down');
				} else {
					if (data.Status === 'running') {
						server_div.addClass('div-server-head-up');
						server_div.removeClass('div-server-head-down');
						server_div.removeClass('div-server-head-unknown');
						server_div.removeClass('div-server-head-dis');
						$('#uptime-word-'+id).text(translate_div.attr('data-uptime'));
					} else {
						server_div.removeClass('div-server-head-up');
						server_div.removeClass('div-server-head-unknown');
						server_div.removeClass('div-server-head-dis');
						server_div.addClass('div-server-head-down');
						$('#uptime-word-'+id).text(translate_div.attr('data-downtime'));
					}
					$('#service-version-'+id).text(data.Version);
					$('#service-process_num-'+id).text(data.Process);
					$('#service-uptime-'+id).text(data.Uptime);
				}
			}
		}
	});
	NProgress.configure({showSpinner: true});
}
function ShowOverviewLogs() {
	$.ajax( {
		url: "/overview/logs",
		type: "GET",
		beforeSend: function() {
			$("#overview-logs").html('<img class="loading_small_bin_bout" style="padding-left: 40%;padding-top: 40px;padding-bottom: 40px;" src="/static/images/loading.gif" />');
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			$("#overview-logs").html(data);
			$.getScript(awesome)
			$.getScript(overview)
		}
	} );
}
