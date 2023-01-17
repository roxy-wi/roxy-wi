var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
function showHapservers(serv, hostnamea, service) {
	var i;
	for (i = 0; i < serv.length; i++) {
		showHapserversCallBack(serv[i], hostnamea[i], service)
	}
}
function showHapserversCallBack(serv, hostnamea, service) {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewHapservers",
			serv: serv,
			service: service,
			token: $('#token').val()
		},
		beforeSend: function() {
			$("#edit_date_"+hostnamea).html('<img class="loading_small_haproxyservers" src="/inc/images/loading.gif" />');
		},
		type: "POST",
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
		url: "options.py",
		data: {
			act: "overviewHapserverBackends",
			serv: serv[0],
			service: service,
			token: $('#token').val()
		},
		beforeSend: function() {
			$("#top-"+hostnamea).html('<img class="loading_small" style="padding-left: 45%;" src="/inc/images/loading.gif" />');
		},
		type: "POST",
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
}
function showOverviewCallBack(serv, hostnamea) {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overview",
			serv: serv,
			token: $('#token').val()
		},
		beforeSend: function() {
			$("#"+hostnamea).html('<img class="loading_small" src="/inc/images/loading.gif" />');
		},
		type: "POST",
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
		url: "options.py",
		data: {
			act: "overviewServices",
			token: $('#token').val()
		},
		beforeSend: function() {
			$("#services_ovw").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/inc/images/loading.gif" />');

		},
		type: "POST",
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
		url: "options.py",
		data: {
			act: "overviewServers",
			name: name,
			serv: ip,
			id: id,
			service: service,
			page: 'hapservers.py',
			token: $('#token').val()
		},
		type: "POST",
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
function ajaxActionServers(action, id) {
	var bad_ans = 'Bad config, check please';
	$.ajax( {
		url: "options.py",
		data: {
			action_hap: action,
			serv: id,
			token: $('#token').val()
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if( data ==  'Bad config, check please ' ) {
				toastr.error(data);
			} else {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (cur_url[0] == "hapservers.py") {
					if (data.indexOf('warning: ') != '-1') {
						toastr.warning(data)
					} else {
						location.reload()
					}
				} else {
					setTimeout(showOverview(ip, hostnamea), 2000);
				}
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function ajaxActionNginxServers(action, id) {
	var bad_ans = 'Bad config, check please';
	$.ajax( {
		url: "options.py",
		data: {
			action_nginx: action,
			serv: id,
			token: $('#token').val()
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if( data ==  'Bad config, check please ' ) {
				alert(data);
			} else {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (cur_url[0] == "hapservers.py") {
					if (data.indexOf('warning: ') != '-1') {
						toastr.warning(data)
					} else {
						location.reload()
					}
				} else if (cur_url[0] == "waf.py") {
					setTimeout(showOverviewWaf(ip, hostnamea), 2000)
				} else {
					setTimeout(showOverview(ip, hostnamea), 2000)
				}
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function ajaxActionKeepalivedServers(action, id) {
	var bad_ans = 'Bad config, check please';
	$.ajax( {
		url: "options.py",
		data: {
			action_keepalived: action,
			serv: id,
			token: $('#token').val()
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if( data ==  'Bad config, check please ' ) {
				alert(data);
			} else {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (cur_url[0] == "hapservers.py") {
					location.reload()
				} else {
					setTimeout(showOverview(ip, hostnamea), 2000)
				}
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function ajaxActionApacheServers(action, id) {
	var bad_ans = 'Bad config, check please';
	$.ajax( {
		url: "options.py",
		data: {
			action_apache: action,
			serv: id,
			token: $('#token').val()
		},
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if( data ==  'Bad config, check please ' ) {
				alert(data);
			} else {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if (cur_url[0] == "hapservers.py") {
					if (data.indexOf('warning: ') != '-1') {
						toastr.warning(data)
					} else {
						location.reload()
					}
				} else {
					setTimeout(showOverview(ip, hostnamea), 2000)
				}
			}
		},
		error: function(){
			alert(w.data_error);
		}
	} );
}
function ajaxActionWafServers(action, id) {
	$.ajax( {
		url: "options.py",
			data: {
				action_waf: action,
				serv: id,
				token: $('#token').val()
			},
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if( data ==  'Bad config, check please ' ) {
					toastr.error(data);
				} else {
					setTimeout(showOverviewWaf(ip, hostnamea), 2000)
				}
			},
			error: function(){
				alert(w.data_error);
			}
	} );
}
function ajaxActionWafNginxServers(action, id) {
	$.ajax( {
		url: "options.py",
			data: {
				action_waf_nginx: action,
				serv: id,
				token: $('#token').val()
			},
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else if( data ==  'Bad config, check please ' ) {
					toastr.error(data);
				} else {
					setTimeout(showOverviewWaf(ip, hostnamea), 2000)
				}
			},
			error: function(){
				alert(w.data_error);
			}
	} );
}
$( function() {
	try {
		if ((cur_url[0] == 'hapservers.py' && cur_url[1].split('&')[1].split('=')[0] == 'serv') || cur_url[0] == 'overview.py') {
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
		if (cur_url[0] == 'overview.py') {
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
		$( ".show-users" ).show("fast");
		$( "#show-all-users" ).text("Hide");
		$( "#show-all-users" ).attr("title", "Hide all users");
		$( "#show-all-users" ).attr("id", "hide-all-users");

		$("#hide-all-users").click(function() {
			$( ".show-users" ).hide("fast");
			$( "#hide-all-users" ).attr("title", "Show all users");
			$( "#hide-all-users" ).text("Show all");
			$( "#hide-all-users" ).attr("id", "show-all-users");
		});
	});

	$( "#show-all-groups" ).click( function() {
		$( ".show-groups" ).show("fast");
		$( "#show-all-groups" ).text("Hide");
		$( "#show-all-groups" ).attr("title", "Hide all groups");
		$( "#show-all-groups" ).attr("id", "hide-all-groups");

		$( "#hide-all-groups" ).click( function() {
			$( ".show-groups" ).hide("fast");
			$( "#hide-all-groups" ).attr("title", "Show all groups");
			$( "#hide-all-groups" ).text("Show all");
			$( "#hide-all-groups" ).attr("id", "show-all-groups");
		});
	});

	$( "#show-all-haproxy-wi-log" ).click( function() {
		$( ".show-haproxy-wi-log" ).show("fast");
		$( "#show-all-haproxy-wi-log" ).text("Show less");
		$( "#show-all-haproxy-wi-log" ).attr("title", "Show less");
		$( "#show-all-haproxy-wi-log" ).attr("id", "hide-all-haproxy-wi-log");

		$( "#hide-all-haproxy-wi-log" ).click( function() {
			$( ".show-haproxy-wi-log" ).hide("fast");
			$( "#hide-all-haproxy-wi-log" ).attr("title", "Show more");
			$( "#hide-all-haproxy-wi-log" ).text("Show more");
			$( "#hide-all-haproxy-wi-log" ).attr("id", "show-all-haproxy-wi-log");
		});
	});

	if (cur_url[0] == "overview.py" || cur_url[0] == "waf.py" || cur_url[0] == "metrics.py") {
		$('#secIntervals').css('display', 'none');
	}
	$('#apply_close').click( function() {
		$("#apply").css('display', 'none');
		localStorage.removeItem('restart');
	});
	$( ".server-act-links" ).change(function() {
		var id = $(this).attr('id').split('-');

		try {
			var service_name = id[2]
 		}
		catch (err) {
			var service_name = 'haproxy'
		}

		updateHapWIServer(id[1], service_name)
	});
});
function confirmAjaxAction(action, service, id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: "Are you sure you want to "+ action + " " + id + "?",
		buttons: {
			"Sure": function() {
				$( this ).dialog( "close" );
				if(service == "haproxy") {
					ajaxActionServers(action, id);
					if(action == "restart" || action == "reload") {
						if(localStorage.getItem('restart')) {
							localStorage.removeItem('restart');
							$("#apply").css('display', 'none');
						}
					}
				} else if (service == "waf") {
					ajaxActionWafServers(action, id)
				} else if (service == "nginx") {
					ajaxActionNginxServers(action, id)
				} else if (service == "keepalived") {
					ajaxActionKeepalivedServers(action, id)
				} else if (service == "apache") {
					ajaxActionApacheServers(action, id)
				} else if (service == "waf_nginx") {
					ajaxActionWafNginxServers(action, id)
				}
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}
function updateHapWIServer(id, service_name) {
	var alert_en = 0;
	var metrics = 0;
	var active = 0;
	if ($('#alert-'+id).is(':checked')) {
		alert_en = '1';
	}
	if ($('#metrics-'+id).is(':checked')) {
		metrics = '1';
	}
	if ($('#active-'+id).is(':checked')) {
		active = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			updatehapwiserver: id,
			name: $('#server-name-'+id).val(),
			metrics: metrics,
			alert_en: alert_en,
			active: active,
			service_name: service_name,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#server-"+id+"-"+service_name).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#server-"+id+"-"+service_name).removeClass( "update" );
				}, 2500 );
			}
		}
	} );
}
function change_pos(pos, id) {
	$.ajax( {
		url: "options.py",
			data: {
				change_pos: pos,
				pos_server_id: id,
				token: $('#token').val()
			},
		error: function(){
			console.log(w.data_error);
		}
	} );
}
function showBytes(serv) {
	$.ajax( {
		url: "options.py",
		data: {
			showBytes: serv,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#show_bin_bout").html('<img class="loading_small_bin_bout" src="/inc/images/loading.gif" />');
			$("#sessions").html('<img class="loading_small_bin_bout" src="/inc/images/loading.gif" />');
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
		url: "options.py",
		data: {
			nginxConnections: serv,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/inc/images/loading.gif" />');
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
		url: "options.py",
		data: {
			apachekBytes: serv,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#sessions").html('<img class="loading_small_bin_bout" src="/inc/images/loading.gif" />');
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
		url: "options.py",
		data: {
			keepalivedBecameMaster: serv,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#bin_bout").html('<img class="loading_small_bin_bout" src="/inc/images/loading.gif" />');
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
		url: "options.py",
		data: {
			show_users_ovw: 1,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#users-table").html('<img class="loading_small_bin_bout" style="padding-left: 100%;padding-top: 40px;padding-bottom: 40px;" src="/inc/images/loading.gif" />');
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
		url: "options.py",
		data: {
			show_sub_ovw: 1,
			token: $('#token').val()
		},
		type: "POST",
		beforeSend: function() {
			$("#sub-table").html('<img class="loading_small_bin_bout" style="padding-left: 40%;padding-top: 40px;padding-bottom: 40px;" src="/inc/images/loading.gif" />');
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
	var service = $('#service').val();
	$.ajax({
		url: "options.py",
		data: {
			serverSettings: id,
			serverSettingsService: service,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				$("#dialog-settings-service").html(data)
				$( "input[type=checkbox]" ).checkboxradio();
				$("#dialog-settings-service").dialog({
					resizable: false,
					height: "auto",
					width: 400,
					modal: true,
					title: "Settings for " + name,
					buttons: {
						"Save": function () {
							$(this).dialog("close");
							serverSettingsSave(id, name, service, $(this));
						},
						Cancel: function () {
							$(this).dialog("close");
						}
					}
				});
			}
		}
	});
}
function serverSettingsSave(id, name, service, dialog_id) {
	var haproxy_enterprise = 0;
	var haproxy_dockerized = 0;
	var nginx_dockerized = 0;
	var apache_dockerized = 0;
	var haproxy_restart = 0;
	var nginx_restart = 0;
	var apache_restart = 0;
	if ($('#haproxy_enterprise').is(':checked')) {
		haproxy_enterprise = '1';
	}
	if ($('#haproxy_dockerized').is(':checked')) {
		haproxy_dockerized = '1';
	}
	if ($('#nginx_dockerized').is(':checked')) {
		nginx_dockerized = '1';
	}
	if ($('#apache_dockerized').is(':checked')) {
		apache_dockerized = '1';
	}
	if ($('#haproxy_restart').is(':checked')) {
		haproxy_restart = '1';
	}
	if ($('#nginx_restart').is(':checked')) {
		nginx_restart = '1';
	}
	if ($('#apache_restart').is(':checked')) {
		apache_restart = '1';
	}
	$.ajax({
		url: "options.py",
		data: {
			serverSettingsSave: id,
			serverSettingsService: service,
			serverSettingsEnterprise: haproxy_enterprise,
			serverSettingshaproxy_dockerized: haproxy_dockerized,
			serverSettingsnginx_dockerized: nginx_dockerized,
			serverSettingsapache_dockerized: apache_dockerized,
			serverSettingsHaproxyrestart: haproxy_restart,
			serverSettingsNginxrestart: nginx_restart,
			serverSettingsApache_restart: apache_restart,
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
	$.ajax({
		url: "options.py",
		data: {
			act: 'check_service',
			service: service,
			serv: ip,
			server_id: id,
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			data = data.replace(/\s+/g, ' ');
			if (cur_url[0] == 'hapservers.py') {
				if (data.indexOf('up') != '-1') {
					$('#div-server-' + id).addClass('div-server-head-up');
					$('#div-server-' + id).removeClass('div-server-head-down');
				} else if (data.indexOf('down') != '-1') {
					$('#div-server-' + id).removeClass('div-server-head-up');
					$('#div-server-' + id).addClass('div-server-head-down');
				}
			} else if (cur_url[0] == 'overview.py') {
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
