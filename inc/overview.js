var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
function showOverviewHapWI() {
	getChartDataHapWiCpu('1')
	getChartDataHapWiRam('1')
}
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
			$("#"+hostnamea).html('<img class="loading_small_haproxyservers" src="/inc/images/loading.gif" />');
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
	showOverviewHapWI()
	var i;
	for (i = 0; i < serv.length; i++) { 
		showOverviewCallBack(serv[i], hostnamea[i])
	}
	$.getScript('/inc/overview.js');
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
function showOverviewServer(name,ip,id, service) {
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
				if (cur_url[0] == "hapservers.py") {
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
				if (cur_url[0] == "hapservers.py") {
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
function ajaxActionWafServers(action, id) {
	var bad_ans = 'Bad config, check please';
	$.ajax( {
		url: "options.py",
			data: {
				action_waf: action,
				serv: id,
				token: $('#token').val()
			},
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if( data ==  'Bad config, check please ' ) {
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
	$( "#show-all-users" ).click( function() {
		$( ".show-users" ).show("fast");
		$( "#show-all-users" ).text("Hide");
		$( "#show-all-users" ).attr("title", "Hide all users"); 
		$( "#show-all-users" ).attr("id", "hide-all-users"); 
		$.getScript('/inc/overview.js');			
	});
	$( "#hide-all-users" ).click( function() {
		$( ".show-users" ).hide("fast");
		$( "#hide-all-users" ).attr("title", "Show all users");
		$( "#hide-all-users" ).text("Show all");
		$( "#hide-all-users" ).attr("id", "show-all-users");
	});
	$( "#show-all-groups" ).click( function() {
		$( ".show-groups" ).show("fast");
		$( "#show-all-groups" ).text("Hide");
		$( "#show-all-groups" ).attr("title", "Hide all groups"); 
		$( "#show-all-groups" ).attr("id", "hide-all-groups"); 
		$.getScript('/inc/overview.js');			
	});
	$( "#hide-all-groups" ).click( function() {
		$( ".show-groups" ).hide("fast");
		$( "#hide-all-groups" ).attr("title", "Show all groups");
		$( "#hide-all-groups" ).text("Show all");
		$( "#hide-all-groups" ).attr("id", "show-all-groups");
	});
	$( "#show-all-haproxy-wi-log" ).click( function() {
		$( ".show-haproxy-wi-log" ).show("fast");
		$( "#show-all-haproxy-wi-log" ).text("Show less log");
		$( "#show-all-haproxy-wi-log" ).attr("title", "Show less log"); 
		$( "#show-all-haproxy-wi-log" ).attr("id", "hide-all-haproxy-wi-log"); 
		$.getScript('/inc/overview.js');			
	});
	$( "#hide-all-haproxy-wi-log" ).click( function() {
		$( ".show-haproxy-wi-log" ).hide("fast");
		$( "#hide-all-haproxy-wi-log" ).attr("title", "Show more log");
		$( "#hide-all-haproxy-wi-log" ).text("Show more log");
		$( "#hide-all-haproxy-wi-log" ).attr("id", "show-all-haproxy-wi-log");
	});
	if (cur_url[0] == "overview.py" || cur_url[0] == "waf.py" || cur_url[0] == "metrics.py") {
		$('#secIntervals').css('display', 'none');
	}
	$('#apply_close').click( function() {
		$("#apply").css('display', 'none');
		Cookies.remove('restart', { path: '' });
	});
	$( ".server-act-links" ).change(function() {
		var id = $(this).attr('id').split('-');
		updateHapWIServer(id[1])
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
				if(service == "hap") {
					ajaxActionServers(action, id);
					if(action == "restart" || action == "reload") {
						if(Cookies.get('restart')) {
							Cookies.remove('restart', { path: '' });
							$("#apply").css('display', 'none');
						}
					}
				} else if (service == "waf") {
					ajaxActionWafServers(action, id)
				} else if (service == "nginx") {
					ajaxActionNginxServers(action, id)
				}
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}
function updateHapWIServer(id) {
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
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			data = data.replace(/\s+/g,' ');
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#server-"+id).addClass( "update", 1000 );
				setTimeout(function() {
					$( "#server-"+id ).removeClass( "update" );
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
				serv: id,
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
