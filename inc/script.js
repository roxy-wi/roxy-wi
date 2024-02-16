var url = "/inc/script.js";
var cur_url = window.location.href.split('/app/').pop();
cur_url = cur_url.split('/');
var intervalId;
function validateEmail(email) {
	const re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
	return re.test(email);
}
function escapeHtml(unsafe) {
	return unsafe
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}
var wait_mess_word = $('#translate').attr('data-wait_mess');
var wait_mess = '<div class="alert alert-warning">'+wait_mess_word+'</div>'
function show_current_page(id) {
	id.parent().css('display', 'contents');
	id.parent().css('font-size', '13px');
	id.parent().css('top', '0');
	id.parent().css('left', '0');
	id.parent().children().css('margin-left', '-20px');
	id.parent().find('a').css('padding-left', '20px');
	id.find('a').css('background-color', 'var(--right-menu-blue-rolor)');
}
$( function() {		
   $('.menu li ul li').each(function () {
	   var link = $(this).find('a').attr('href');
	   var link2 = link.split('/')[2];
	   var link3 = link.split('/')[3];
	   var link4 = link.split('/')[4];
	   if (cur_url[1] == null) {
		   cur_url[1] = 'haproxy';
	   }
	   var full_uri = cur_url[0] + '/' + cur_url[1]
	   var full_uri1 = link2 + '/' + link3
	   var full_uri2 = cur_url[0] + '/' + cur_url[1] + '/' + cur_url[2]
	   var full_uri3 = link2 + '/' + link3 + '/' + link4
	   if (cur_url[0] == link2 && link3 == null) {
		   show_current_page($(this))
	   } else if (full_uri == 'config/haproxy' && full_uri1 == 'config/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'config/nginx' && full_uri1 == 'config/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'config/apache' && full_uri1 == 'config/apache') {
		   show_current_page($(this))
	   } else if (full_uri == 'config/keepalived' && full_uri1 == 'config/keepalived') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/versions/haproxy' && full_uri3 == 'config/versions/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/versions/nginx' && full_uri3 == 'config/versions/nginx') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/versions/keepalived' && full_uri3 == 'config/versions/keepalived') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/versions/apache' && full_uri3 == 'config/versions/apache') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/map/haproxy' && full_uri1 == 'config/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/compare/haproxy' && full_uri1 == 'config/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/compare/nginx' && full_uri1 == 'config/nginx') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/compare/keepalived' && full_uri3 == 'config/keepalived') {
		   show_current_page($(this))
	   } else if (full_uri2 == 'config/compare/apache' && full_uri3 == 'config/apache') {
		   show_current_page($(this))
	   } else if (full_uri == 'logs/haproxy' && full_uri1 == 'logs/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'logs/nginx' && full_uri1 == 'logs/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'logs/keepalived' && full_uri1 == 'logs/keepalived') {
		   show_current_page($(this))
	   } else if (full_uri == 'logs/apache' && full_uri1 == 'logs/apache') {
		   show_current_page($(this))
	   } else if (full_uri == 'service/haproxy' && full_uri1 == 'service/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'service/nginx' && full_uri1 == 'service/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'service/keepalived' && full_uri1 == 'service/keepalived') {
		   show_current_page($(this))
	   } else if (full_uri == 'service/apache' && full_uri1 == 'service/apache') {
		   show_current_page($(this))
	   } else if (full_uri == 'stats/haproxy' && full_uri1 == 'stats/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'stats/nginx' && full_uri1 == 'stats/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'stats/apache' && full_uri1 == 'stats/apache') {
		   show_current_page($(this))
	   } else if (full_uri.indexOf('add/haproxy#') != '-1' && full_uri1.indexOf('add/haproxy#proxy') != '-1') {
		   show_current_page($(this))
	   } else if (full_uri == 'add/haproxy#ssl' && full_uri1 == 'add/haproxy#ssl') {
		   show_current_page($(this))
	   } else if (full_uri == 'add/nginx#proxy' && full_uri1 == 'add/nginx#proxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'smon/dashboard' && full_uri1 == 'smon/dashboard') {
		   show_current_page($(this))
	   } else if (full_uri == 'smon/agent' && full_uri1 == 'smon/agent') {
		   show_current_page($(this))
	   } else if (full_uri == 'smon/history' && full_uri1 == 'smon/history') {
		   show_current_page($(this))
	   } else if (full_uri == 'smon/status-page' && full_uri1 == 'smon/status-page') {
		   show_current_page($(this))
	   } else if (full_uri === 'checker/settings' && full_uri1 === 'checker/settings') {
		   show_current_page($(this))
	   } else if (full_uri == 'checker/history' && full_uri1 == 'checker/history') {
		   show_current_page($(this))
	   } else if (full_uri == 'add/haproxy?service=nginx#ssl' && cur_url[1].split('?')[1] == 'service=nginx#ssl' && full_uri1 == 'add/haproxy?service=nginx#ssl') {
		   show_current_page($(this))
	   } else if (cur_url[0] == 'app/logs' && cur_url[1].split('&')[0] == 'type=2' && link2 == 'viewlogs.py?type=2') {
		   show_current_page($(this));
		   return false;
	   } else if (full_uri == 'metrics/haproxy' && full_uri1 == 'metrics/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'metrics/nginx' && full_uri1 == 'metrics/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'metrics/apache' && full_uri1 == 'metrics/apache') {
		   show_current_page($(this))
	   } else if (full_uri == 'add/haproxy?service=apache#ssl' && cur_url[1].split('?')[1] == 'service=apache#ssl' && full_uri1 == 'add/haproxy?service=apache#ssl') {
		   show_current_page($(this))
	   } else if (full_uri == 'waf/haproxy' && full_uri1 == 'waf/haproxy') {
		   show_current_page($(this))
	   } else if (full_uri == 'waf/nginx' && full_uri1 == 'waf/nginx') {
		   show_current_page($(this))
	   } else if (full_uri == 'install/ha' && full_uri1 == 'install/ha') {
		   show_current_page($(this))
	   }
   });
});

jQuery.expr[':'].regex = function(elem, index, match) {
    var matchParams = match[3].split(','),
        validLabels = /^(data|css):/,
        attr = {
            method: matchParams[0].match(validLabels) ?
                        matchParams[0].split(':')[0] : 'attr',
            property: matchParams.shift().replace(validLabels,'')
        },
        regexFlags = 'ig',
        regex = new RegExp(matchParams.join('').replace(/^\s+|\s+$/g,''), regexFlags);
    return regex.test(jQuery(elem)[attr.method](attr.property));
}
window.onblur= function() {
	window.onfocus= function () {
		if(sessionStorage.getItem('auto-refresh-pause') == "0" && sessionStorage.getItem('auto-refresh') > 5000) {
			if (cur_url[0] == "logs") {
				showLog();
			} else if (cur_url[0] == "stats") {
				showStats()
			} else if (cur_url[0] == "/") {
				showOverview();
			} else if (cur_url[0] == "internal") {
				viewLogs();
			} else if (cur_url[0] == "metrics") {
				showMetrics();
			} else if (cur_url[0] == "smon" && cur_url[1] == "dashboard") {
				showSmon('refresh')
			}
		}
	}
};
if(localStorage.getItem('restart')) {
	var ip_for_restart = localStorage.getItem('restart');
	$.ajax({
		url: "/app/service/check-restart/" + ip_for_restart,
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		success: function (data) {
			if (data.indexOf('ok') != '-1') {
				var apply_div = $.find("#apply_div");
				apply_div = apply_div[0].id;
				$("#apply").css('display', 'block');
				$('#' + apply_div).css('width', '850px');
				ip_for_restart = escapeHtml(ip_for_restart);
				if (cur_url[0] == "service") {
					$('#' + apply_div).css('width', '650px');
					$('#' + apply_div).addClass("alert-one-row");
					$('#' + apply_div).html("You have made changes to the server: " + ip_for_restart + ". Changes will take effect only after<a id='" + ip_for_restart + "' class='restart' title='Restart HAproxy service' onclick=\"confirmAjaxAction('restart', 'hap', '" + ip_for_restart + "')\">restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				} else {
					$('#' + apply_div).html("You have made changes to the server: " + ip_for_restart + ". Changes will take effect only after restart. <a href='service' title='Overview'>Go to the HAProxy Overview page and restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				}
				$.getScript('/inc/overview.js');
			}
		}
	});
}
function autoRefreshStyle(autoRefresh) {
	var margin;
	if (cur_url[0] == "/" || cur_url[0] == "waf" || cur_url[0] == "metrics") {
		if (autoRefresh < 60000) {
			autoRefresh = 60000;
		}
	}
	autoRefresh = autoRefresh / 1000;
	if (autoRefresh == 60) {
		timeRange = " minute"
		autoRefresh = autoRefresh / 60;
	} else if (autoRefresh > 60 && autoRefresh < 3600) {
		timeRange = " minutes"
		autoRefresh = autoRefresh / 60;
	} else if (autoRefresh >= 3600 && autoRefresh < 86401) {
		timeRange = " hours"
		autoRefresh = autoRefresh / 3600;
	} else {
		timeRange = " seconds";
	}
	$('#1').text(autoRefresh + timeRange);
	$('#0').text(autoRefresh + timeRange);
	$('.auto-refresh-pause').css('display', 'inline');
	$('.auto-refresh-resume').css('display', 'none');
	$('.auto-refresh-pause').css('margin-left', "-25px");
	$('.auto-refresh-resume').css('margin-left', "-25px");
	$('#browse_history').css("border-bottom", "none");
	$('.auto-refresh img').remove();
}
function setRefreshInterval(interval) {
	if (interval == "0") {
		var autoRefresh = sessionStorage.getItem('auto-refresh');
		if (autoRefresh !== undefined) {
			var autorefresh_word = $('#translate').attr('data-autorefresh');
			sessionStorage.removeItem('auto-refresh');
			pauseAutoRefresh();
			$('#0').html('<span class="auto-refresh-reload auto-refresh-reload-icon"></span> '+autorefresh_word);
			$('.auto-refresh').css('display', 'inline');
			$('.auto-refresh').css('font-size', '15px');
			$('#1').text(autorefresh_word);
			$('.auto-refresh-resume').css('display', 'none');
			$('.auto-refresh-pause').css('display', 'none');
			$.getScript("/inc/fontawesome.min.js");
		}
		hideAutoRefreshDiv();
	} else {
		clearInterval(intervalId);
		sessionStorage.setItem('auto-refresh', interval)
		sessionStorage.setItem('auto-refresh-pause', 0)
		startSetInterval(interval);
		hideAutoRefreshDiv();
		autoRefreshStyle(interval);
	}
}
function startSetInterval(interval) {
	if(sessionStorage.getItem('auto-refresh-pause') == "0") {
		if (cur_url[0] == "logs") {
			intervalId = setInterval('showLog()', interval);
			showLog();
		} else if (cur_url[0] == "stats") {
			intervalId = setInterval('showStats()', interval);
			showStats()
		} else if (cur_url[0] == "/") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showOverview(ip, hostnamea)', interval);
			showOverview(ip, hostnamea);
		} else if (cur_url[1] == "internal") {
			intervalId = setInterval('viewLogs()', interval);
			viewLogs();
		} else if (cur_url[0] == "metrics") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showMetrics()', interval);
			showMetrics();
		} else if (cur_url[0] == "waf") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showOverviewWaf(ip, hostnamea)', interval);
			showOverviewWaf(ip, hostnamea);
			showWafMetrics();
		} else if (cur_url[0] == "service") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showMetrics()', interval);
			showMetrics();
		} else if (cur_url[0] == "smon" && cur_url[1] == "dashboard") {
			intervalId = setInterval("showSmon('refresh')", interval);
			showSmon('refresh');
		} else if (cur_url[0] == "smon" && cur_url[1] == "history") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showSmonHistory()', interval);
			showSmonHistory();
		}
	} else {
		pauseAutoRefresh();
	}
}
function pauseAutoRefresh() {
	clearInterval(intervalId);
	$('.auto-refresh-pause').css('display', 'none');
	$('.auto-refresh-resume').css('display', 'inline');
	sessionStorage.setItem('auto-refresh-pause', '1');
}
function pauseAutoResume(){
	var autoRefresh = sessionStorage.getItem('auto-refresh');
	setRefreshInterval(autoRefresh);
	sessionStorage.setItem('auto-refresh-pause', '0');
}
function hideAutoRefreshDiv() {
	$(function() {
		$('.auto-refresh-div').hide("blind", "fast");
		$('#1').css("display", "none");
		$('#0').css("display", "inline");
	});
}
$( document ).ajaxSend(function( event, request, settings ) {
	NProgress.start();
});
$( document ).ajaxComplete(function( event, request, settings ) {
	NProgress.done();
});
function showStats() {
	$.ajax({
		url: "/app/stats/view/" + $("#service").val() + "/" + $("#serv").val(),
		// data: {
		// 	token: $('#token').val()
		// },
		// type: "POST",
		success: function (data) {
			if (data.indexOf('error:') != '-1' && data.indexOf('Internal error:') == '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Stats", "Stats", "/app/stats/" + $("#service").val() + "/" + $("#serv").val());
				wait();
			}
		}
	});
}
function openStats() {
	var serv = $("#serv").val();
	var service_url = cur_url[1];
	var url = "/app/stats/"+service_url+"/"+serv
	var win = window.open(url, '_blank');
	win.focus();
}
function openVersions() {
	var serv = $("#serv").val();
	var service_url = cur_url[1];
	var url = "/app/config/versions/"+service_url+"/"+serv
	var win = window.open(url,"_self");
	win.focus();
}
function openSection() {
	var serv = $("#serv").val();
	var section = $("#section").val();
	var url = "/app/config/section/haproxy/"+serv+"/"+section;
	var win = window.open(url,"_self");
	win.focus();
}
function showLog() {
	var waf = cur_url[2];
	var file = $('#log_files').val();
	var serv = $("#serv").val();
	if ((file === undefined || file === null) && (waf == '' || waf === undefined)) {
		var file_from_get = findGetParameter('file');
		if (file_from_get === undefined || file_from_get === null) {
			toastr.warning('Select a log file first')
			return false;
		} else {
			file = file_from_get;
		}
	}
	var rows = $('#rows').val();
	var grep = $('#grep').val();
	var exgrep = $('#exgrep').val();
	var hour = $('#time_range_out_hour').val();
	var minute = $('#time_range_out_minut').val();
	var hour1 = $('#time_range_out_hour1').val();
	var minute1 = $('#time_range_out_minut1').val();
	var service = $('#service').val();
	if (service == 'None') {
		service = 'haproxy';
	}
	if (waf) {
		var url = "/app/logs/" + service + "/waf/" + serv + "/" + rows;
		waf = 1;
	} else {
		var url = "/app/logs/" + service + "/" + serv + "/" + rows;
	}
	$.ajax( {
		url: url,
		data: {
			show_log: rows,
			waf: waf,
			grep: grep,
			exgrep: exgrep,
			hour: hour,
			minute: minute,
			hour1: hour1,
			minute1: minute1,
			file: file,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			toastr.clear();
			$("#ajax").html(data);
		}
	} );
}
function showRemoteLogFiles() {
	let serv = $('#serv').val();
	if (serv === undefined || serv === null) {
		toastr.warning('Select a server firts');
		return false;
	}
	var rows = $('#rows').val()
	var grep = $('#grep').val()
	var exgrep = $('#exgrep').val()
	var hour = $('#time_range_out_hour').val()
	var minute = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minute1 = $('#time_range_out_minut1').val()
	var service = $('#service').val()
	if (service == 'None') {
		service = 'haproxy';
	}
	$.ajax( {
		url: "/app/logs/" + service + "/" + serv ,
		data: {
			serv: $("#serv").val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('ls: cannot access') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#remote_log_files").html(data);
				$.getScript('/inc/configshow.js');
			}
		}
	} );

}
function clearAllAjaxFields() {
	$("#ajax").empty();
	$('.alert').remove();
	try {
		myCodeMirror.toTextArea();
	} catch (e) {
		console.log(e)
	}
	$("#saveconfig").remove();
	$("h4").remove();
	$("#ajax-compare").empty();
	$("#config").empty();
}
function showMap() {
	clearAllAjaxFields();
	$('#ajax-config_file_name').empty();
	$.ajax( {
		url: "/app/config/map/haproxy/" + $("#serv").val() + '/show',
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Show Map", "Show Map", '/app/config/map/' + $("#service").val() + '/' + $("#serv").val());
			}
		}
	} );
}
function showCompare() {
	$.ajax( {
		url: "/app/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/show",
		data: {
			left: $('#left').val(),
			right: $("#right").val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
			}
		}
	} );
}
function showCompareConfigs() {
	clearAllAjaxFields();
	$('#ajax-config_file_name').empty();
	$.ajax( {
		url: "/app/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/files",
		type: "GET",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-compare").html(data);
				$("input[type=submit], button").button();
				$("select").selectmenu();
				window.history.pushState("Show compare config", "Show compare config", '/app/config/compare/' + $("#service").val() + '/' + $("#serv").val());
			}
		}
	} );
}
function showConfig() {
	var service = $('#service').val();
	var config_file_name = encodeURI($('#config_file_name').val());
	if (service == 'nginx' || service == 'apache') {
		if ($('#config_file_name').val() === undefined || $('#config_file_name').val() === null) {
			config_file_name = cur_url[4]
			if (config_file_name == '') {
				toastr.warning('Select a config file firts');
				return false;
			} else {
				showConfigFiles(true);
			}
		}
	}
	clearAllAjaxFields();
	$.ajax( {
		url: "/app/config/" + service + "/show",
		data: {
			serv: $("#serv").val(),
			service: service,
			config_file_name: config_file_name
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				$.getScript('/inc/configshow.js');
				window.history.pushState("Show config", "Show config", "/app/config/" + service + "/" + $("#serv").val() + "/show/" + config_file_name);
			}
		}
	} );
}
function showConfigFiles(not_redirect=false) {
	var service = $('#service').val();
	var server_ip = $("#serv").val();
	clearAllAjaxFields();
	$.ajax( {
		url: "/app/config/" + service + "/show-files",
		data: {
			serv: server_ip,
			service: service
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-config_file_name").html(data);
				if (findGetParameter('findInConfig') === null) {
					if (not_redirect) {
						window.history.pushState("Show config", "Show config", "/app/config/" + service + "/" + server_ip + "/show-files");
					}
				}
			}
		}
	} );
}
function showConfigFilesForEditing() {
	var service = $('#service').val();
	var server_ip = $("#serv").val();
	var config_file_name = findGetParameter('config_file_name')
	if (service == 'nginx' || service == 'apache') {
		$.ajax({
			url: "/app/config/" + service + "/" + server_ip + "/edit/" + config_file_name,
			type: "POST",
			success: function (data) {
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					$("#ajax-config_file_name").html(data);
				}
			}
		});
	}
}
function showUploadConfig() {
	var service = $('#service').val();
	var configver = $('#configver').val();
	var serv = $("#serv").val()
	$.ajax( {
		url: "/app/config/" + service + "/show",
		data: {
			serv: serv,
			configver: configver
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Show config", "Show config", "/app/config/versions/" + service + "/" + serv + "/" + configver);
				$.getScript('/inc/configshow.js');
			}
		}
	} );
}
function showListOfVersion(for_delver) {
	var cur_url = window.location.href.split('/app/').pop();
	cur_url = cur_url.split('/');
	var service = $('#service').val();
	var serv = $("#serv").val();
	var configver = cur_url[4];
	clearAllAjaxFields();
	$.ajax( {
		url: "/app/config/version/" + service + "/list",
		data: {
			serv: serv,
			configver: configver,
			for_delver: for_delver
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#config_version_div").html(data);
				$( "input[type=checkbox]" ).checkboxradio();
				window.history.pushState("Show config", "Show config", "/app/config/versions/" + service + "/" + serv);
			}
		}
	} );
}
function findGetParameter(parameterName) {
    var result = null,
        tmp = [];
    var items = location.search.substr(1).split("&");
    for (var index = 0; index < items.length; index++) {
        tmp = items[index].split("=");
        if (tmp[0] === parameterName) result = decodeURIComponent(tmp[1]);
    }
    return result;
}
function viewLogs() {
	var viewlogs = $('#viewlogs').val();
	if (viewlogs == '------' || viewlogs === null) { return false; }
	if(viewlogs == 'roxy-wi.error.log' || viewlogs == 'roxy-wi.access.log' || viewlogs == 'fail2ban.log') {
		showApacheLog(viewlogs);
	} else {
		var rows = $('#rows').val();
		var grep = $('#grep').val();
		var exgrep = $('#exgrep').val();
		var hour = $('#time_range_out_hour').val();
		var minute = $('#time_range_out_minut').val();
		var hour1 = $('#time_range_out_hour1').val();
		var minute1 = $('#time_range_out_minut1').val();
		var type = findGetParameter('type')
		if (viewlogs == null){
			viewlogs = findGetParameter('viewlogs')
		}
		var url = "/app/logs/internal/" + viewlogs + "/" + rows;
		$.ajax({
			url: url,
			data: {
				viewlogs: viewlogs,
				serv: viewlogs,
				rows: rows,
				grep: grep,
				exgrep: exgrep,
				hour: hour,
				minute: minute,
				hour1: hour1,
				minute1: minute1,
				token: $('#token').val(),
			},
			type: "POST",
			success: function (data) {
				$("#ajax").html(data);
			}
		} );
	}
}
$( function() {
	$('a').click(function(e) {
		try {
			var cur_path = window.location.pathname;
			var attr = $(this).attr('href');
			if (cur_path == '/app/add/haproxy' || cur_path == '/app/add/nginx' || cur_path == '/app/servers' ||
				cur_path == '/app/admin' || cur_path == '/app/install' || cur_path == '/app/runtimeapi') {
				if (typeof attr !== typeof undefined && attr !== false) {
					$('title').text($(this).attr('title'));
					history.pushState({}, '', $(this).attr('href'));
					if ($(this).attr('href').split('#')[0] && $(this).attr('href').split('#')[0] != cur_path) {
						window.history.go()
					}
				}
			}
		} catch (err) {
			console.log(err);
		}
	});
	toastr.options.closeButton = true;
	toastr.options.progressBar = true;
	toastr.options.positionClass = 'toast-bottom-full-width';
	toastr.options.timeOut = 25000;
	toastr.options.extendedTimeOut = 50000;
	$('#errorMess').click(function(){
		$('#error').remove();
	});
	$( "#serv" ).on('selectmenuchange',function()  {
		$("#show").css("pointer-events", "inherit");
		$("#show").css("cursor", "pointer");
	});
	if ($( "#serv option:selected" ).val() == "Choose server")  {
		$("#show").css("pointer-events", "none");
		$("#show").css("cursor", "not-allowed");
	}

	var pause = '<a onclick="pauseAutoRefresh()" title="Pause auto-refresh" class="auto-refresh-pause"></a>'
	var autoRefresh = sessionStorage.getItem('auto-refresh');

	if ($('.auto-refresh')) {
		if(autoRefresh) {
			startSetInterval(autoRefresh);
			autoRefreshStyle(autoRefresh);
		}
	}
	$( "#tabs" ).tabs();
	$( "select" ).selectmenu();

    $( "[title]" ).tooltip({
		"content": function(){
			return $(this).attr("data-help");
		},
		show: {"delay": 1000}
	});
	$( "input[type=submit], button" ).button();
	$( "input[type=checkbox]" ).checkboxradio();
	$( ".controlgroup" ).controlgroup();

	$( "#hide_menu" ).click(function() {
		$(".top-menu").hide( "drop", "fast" );
		$(".container").css("max-width", "100%");
		$(".footer").css("max-width", "97%");
		$(".container").css("margin-left", "1%");
		$(".footer").css("margin-left", "1%");
		$(".show_menu").show();
		$("#hide_menu").hide();
		sessionStorage.setItem('hide_menu', 'hide');
	});
	$( "#show_menu" ).click(function() {
		$(".top-menu").show( "drop", "fast" );
		$(".container").css("max-width", "100%");
		$(".footer").css("max-width", "100%");
		$(".container").css("margin-left", "207px");
		$(".footer").css("margin-left", "207px");
		$(".show_menu").hide();
		$("#hide_menu").show();
		sessionStorage.setItem('hide_menu', 'show');
	});
	var hideMenu = sessionStorage.getItem('hide_menu');
	if (hideMenu == "show") {
		$(".top-menu").show( "drop", "fast" );
		$(".container").css("max-width", "100%");
		$(".container").css("margin-left", "207px");
		$(".footer").css("margin-left", "207px");
		$(".footer").css("max-width", "100%");
		$("#hide_menu").show();
		$(".show_menu").hide();
	}
	if (hideMenu == "hide") {
		$(".top-menu").hide();
		$(".container").css("max-width", "97%");
		$(".container").css("margin-left", "1%");
		$(".footer").css("margin-left", "1%");
		$(".footer").css("max-width", "97%");
		$(".show_menu").show();
		$("#hide_menu").hide();
	}

	var now = new Date(Date.now());
	if($('#time_range_out_hour').val() != '' && $('#time_range_out_hour').val() != 'None') {
		var date1 = parseInt($('#time_range_out_hour').val(), 10) * 60 + parseInt($('#time_range_out_minut').val(), 10)
	} else {
		var date1 = now.getHours() * 60 - 3 * 60;
	}
	if($('#time_range_out_hour').val() != '' && $('#time_range_out_hour').val() != 'None') {
		var date2 = parseInt($('#time_range_out_hour1').val(), 10) * 60 + parseInt($('#time_range_out_minut1').val(), 10)
	} else {
		var date2 = now.getHours() * 60 + now.getMinutes();
	}
	$("#time-range").slider({
		range: true,
		min: 0,
		max: 1440,
		step: 15,
		values: [ date1, date2 ],
		slide: function(e, ui) {
			var hours = Math.floor(ui.values[0] / 60);
			var minutes = ui.values[0] - (hours * 60);

			if(hours.toString().length == 1) hours = '0' + hours;
			if(minutes.toString().length == 1) minutes = '0' + minutes;

			var hours1 = Math.floor(ui.values[1] / 60);
			var minutes1 = ui.values[1] - (hours1 * 60);

			if(hours1.toString().length == 1) hours1 = '0' + hours1;
			if(minutes1.toString().length == 1) minutes1 = '0' + minutes1;
			if($('#time_range_out_hour').val() != '' && $('#time_range_out_hour').val() != 'None') {
				$('#time_range_out_hour').val(hours);
			}
			if($('#time_range_out_minut').val() != '' && $('#time_range_out_minut').val() != 'None') {
				$('#time_range_out_minut').val(minutes);
			}
			if($('#time_range_out_hour1').val() != '' && $('#time_range_out_hour1').val() != 'None') {
				$('#time_range_out_hour1').val(hours1);
			}
			if($('#time_range_out_minut1').val() != '' && $('#time_range_out_minut1').val() != 'None') {
				$('#time_range_out_minut1').val(minutes1);
			}
		}
	});
        var date1_hours = Math.floor(date1/60);
        var date2_hours = date1_hours + 1;
		var date2_minute = now.getMinutes()
        if(date1_hours <= 9) date1_hours = '0' + date1_hours;
        if(date2_hours <= 9) date2_hours = '0' + date2_hours;
        if(date2_minute <= 9) date2_minute = '0' + date2_minute;
	if($('#time_range_out_hour').val() != '' && $('#time_range_out_hour').val() != 'None') {
		$('#time_range_out_hour').val($('#time_range_out_hour').val());
	} else {
		$('#time_range_out_hour').val(date1_hours);
	}
	if($('#time_range_out_minut').val() != '' && $('#time_range_out_minut').val() != 'None') {
			$('#time_range_out_minut').val($('#time_range_out_minut').val());
	} else {
		$('#time_range_out_minut').val('00');
	}
	if($('#time_range_out_hour1').val() != '' && $('#time_range_out_hour1').val() != 'None') {
		$('#time_range_out_hour1').val($('#time_range_out_hour1').val());
	} else {
		$('#time_range_out_hour1').val(date2_hours);
	}
	if($('#time_range_out_minut1').val() != '' && $('#time_range_out_minut1').val() != 'None') {
		$('#time_range_out_minut1').val($('#time_range_out_minut1').val());
	} else {
		$('#time_range_out_minut1').val(date2_minute);
	}

	$('#0').click(function() {
		$('.auto-refresh-div').show("blind", "fast");
		$('#0').css("display", "none");
		$('#1').css("display", "inline");
		});

	$('#1').click(function() {
		$('.auto-refresh-div').hide("blind", "fast");
		$('#1').css("display", "none");
		$('#0').css("display", "inline");
	});
	$('#auth').submit(function() {
		var next_url = findGetParameter('next');
		$.ajax( {
			url: "/app/login",
			data: {
				login: $('#login').val(),
				pass: $('#pass').val(),
				next: next_url
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('disabled') != '-1') {
					$('.alert').show();
					$('.alert').html(data);
				} else if (data.indexOf('ban') != '-1') {
					ban();
				} else if (data.indexOf('error') != '-1') {
					toastr.error(data);
				} else {
					sessionStorage.removeItem('check-service');
					window.location.replace(data);
				}
			}
		} );
		return false;
	});
	$('#show_log_form').submit(function() {
		showLog();
		return false;
	});
	$('#show_internal_log_form').submit(function() {
		viewLogs();
		return false;
	});

	var user_settings_tabel_title = $( "#show-user-settings-table" ).attr('title');
	var cancel_word = $('#translate').attr('data-cancel');
	var save_word = $('#translate').attr('data-save');
	var change_word = $('#translate').attr('data-change');
	var password_word = $('#translate').attr('data-password');
	var change_pass_word = change_word + ' ' + password_word
	var showUserSettings = $( "#show-user-settings" ).dialog({
		autoOpen: false,
		width: 600,
		modal: true,
		title: user_settings_tabel_title,
		buttons: [{
			text: save_word,
			click: function () {
				saveUserSettings();
				$(this).dialog("close");
			}
		}, {
			text: change_pass_word,
			click: function () {
				changePassword();
				$(this).dialog("close");
			}
		}, {
			text: cancel_word,
			click: function () {
				$(this).dialog("close");
			}
		}]
	});

	$('#show-user-settings-button').click(function() {
		if (localStorage.getItem('disabled_alert') == '1') {
			$('#disable_alerting').prop('checked', false).checkboxradio('refresh');
		} else {
			$('#disable_alerting').prop('checked', true).checkboxradio('refresh');
		}
		$.ajax({
			url: "/app/user/group/current",
			// data: {
			// 	token: $('#token').val()
			// },
			// type: "POST",
			success: function (data) {
				if (data.indexOf('danger') != '-1') {
					$("#ajax").html(data);
				} else {
					$('#show-user-settings-group').html(data);
					$("select").selectmenu();
				}
			}
		});
		showUserSettings.dialog('open');
	});
	var cur_url = window.location.href.split('/app/').pop();
	cur_url = cur_url.split('/');
	if (cur_url[0].indexOf('install') != '-1') {
		$(".installproxy").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children(".installproxy").css('padding-left', '30px');
				$(this).children(".installproxy").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				$(this).children(".installproxy").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$(".installmon").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children(".installmon").css('padding-left', '30px');
				$(this).children(".installmon").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				$(this).children(".installmon").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 1);
		});
		$(".installgeo").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children(".installgeo").css('padding-left', '30px');
				$(this).children(".installgeo").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				$(this).children(".installgeo").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 2);
		});
	}
	if (cur_url[0].indexOf('admin') != '-1' || cur_url[0].indexOf('servers') != '-1') {
		$(".users").on("click", function () {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
				$(this).find('a').css('background-color', '#48505A');
				$(this).children(".users").css('padding-left', '30px');
				$(this).children(".users").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				$(this).children(".users").css('background-color', 'var(--right-menu-blue-rolor)');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		if (cur_url[0].indexOf('admin') != '-1') {
			$(".group").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".group").css('padding-left', '30px');
					$(this).children(".group").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".group").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 1);
			});
			$(".runtime").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".runtime").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 2);
			});
			$(".admin").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".admin").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 3);
			});
			$(".settings").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".settings").css('padding-left', '30px');
					$(this).children(".settings").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".settings").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 5);
			});
			$(".services").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".services").css('padding-left', '30px');
					$(this).children(".services").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".services").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 6);
				loadServices();
			});
			$(".updatehapwi").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".updatehapwi").css('padding-left', '30px');
					$(this).children(".updatehapwi").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".updatehapwi").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 7);
				loadupdatehapwi();
			});
		} else {
			$(".runtime").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".runtime").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 1);
			});
			$(".admin").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".admin").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 2);
			});
			$(".settings").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".settings").css('padding-left', '30px');
					$(this).children(".settings").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".settings").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 4);
			});
			$(".installproxy").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".installproxy").css('padding-left', '30px');
					$(this).children(".installproxy").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".installproxy").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 5);
			});
			$(".installmon").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".installmon").css('padding-left', '30px');
					$(this).children(".installmon").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".installmon").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 6);
			});
			$(".backup").on("click", function () {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px');
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('background-color', '#48505A');
					$(this).children(".backup").css('padding-left', '30px');
					$(this).children(".backup").css('border-left', '4px solid var(--right-menu-blue-rolor)');
					$(this).children(".backup").css('background-color', 'var(--right-menu-blue-rolor)');
				});
				$("#tabs").tabs("option", "active", 7);
			});
		}
	}
	$('.copyToClipboard').hover(function (){
		$.getScript("/inc/fontawesome.min.js");
	});
	$('.copyToClipboard').click(function () {
        let str = $(this).attr('data-copy');
        const el = document.createElement('textarea');
        el.value = str;
        el.setAttribute('readonly', '');
        el.style.position = 'absolute';
        el.style.left = '-9999px';
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
    })
});
function saveUserSettings(){
	if ($('#disable_alerting').is(':checked')) {
		localStorage.removeItem('disabled_alert');
	} else {
		localStorage.setItem('disabled_alert', '1');
	}
	changeCurrentGroupF();
	Cookies.set('lang', $('#lang_select').val(), { expires: 365, path: '/', samesite: 'strict', secure: 'true' });
}
function sleep(ms) {
	return new Promise(resolve => setTimeout(resolve, ms));
}
async function ban() {
	$( '#login').attr('disabled', 'disabled');
	$( '#pass').attr('disabled', 'disabled');
	$( "input[type=submit], button" ).button('disable');
	$('#wrong-login').show();
	$('#ban_10').show();
	$( '#ban_timer').text(10);

	let i = 10;
	while (i > 0) {
		i--;
		await sleep(1000);
		$( '#ban_timer').text(i);
		}

	$( '#login').removeAttr('disabled');
	$( '#pass').removeAttr('disabled');
	$( "input[type=submit], button" ).button('enable');
	$('#ban_10').hide();
}
function replace_text(id_textarea, text_var) {
	var str = $(id_textarea).val();
	var len = str.length;
	var len_var = text_var.length;
	var beg = str.indexOf(text_var);
	var end = beg + len_var
	var text_val = str.substring(0, beg) + str.substring(end, len);
	$(id_textarea).text(text_val);
}
function createHistroy() {
	if(localStorage.getItem('history') === null) {
		var get_history_array = ['login', 'login','login'];
		localStorage.setItem('history', JSON.stringify(get_history_array));
	}
}
function listHistroy() {
	var browse_history = JSON.parse(localStorage.getItem('history'));
	var history_link = '';
	var title = []
	var link_text = []
	var cur_path = window.location.pathname;
	for(let i = 0; i < browse_history.length; i++){
		if (i == 0) {
			browse_history[0] = browse_history[1];
		}
		if (i == 1) {
			browse_history[1] = browse_history[2]
		}
		if (i == 2) {
			browse_history[2] = cur_path
		}
		$( function() {
			$('.menu li ul li').each(function () {
				var link1 = $(this).find('a').attr('href');
				if (browse_history[i].replace(/\/$/, "") == link1) {
					title[i] = $(this).find('a').attr('title');
					link_text[i] = $(this).find('a').text();
					history_link = '<li><a href="'+browse_history[i]+'" title="'+title[i]+'">'+link_text[i]+'</a></li>'
					$('#browse_history').append(history_link);
				}
			});
		});
	}
	localStorage.setItem('history', JSON.stringify(browse_history));
}
createHistroy();
listHistroy();

function changeCurrentGroupF() {
	Cookies.remove('group');
	Cookies.set('group', $('#newCurrentGroup').val(), {expires: 365, path: '/', samesite: 'strict', secure: 'true'});
	$.ajax({
		url: "/app/user/group/change",
		data: {
			changeUserCurrentGroupId: $('#newCurrentGroup').val(),
			changeUserGroupsUser: Cookies.get('uuid'),
			token: $('#token').val()
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				location.reload();
			}
		}
	});
}
function updateTips( t ) {
	var tips = $( ".validateTips" );
	tips.text( t ).addClass( "alert-warning" );
	tips.text( t ).addClass( "alert-one-row" );
}
function clearTips() {
	var tips = $( ".validateTips" );
	tips.html('Fields marked "<span class="need-field">*</span>" are required').removeClass( "alert-warning" );
	allFields = $( [] ).add( $('#new-server-add') ).add( $('#new-ip') ).add( $('#new-port')).add( $('#new-username') ).add( $('#new-password') )
	allFields.removeClass( "ui-state-error" );
}
function checkLength( o, n, min ) {
	if ( o.val().length < min ) {
		o.addClass( "ui-state-error" );
		updateTips("Field "+n+" is required");
		return false;
	} else {
		return true;
	}
}
$(function () {
	ion.sound({
		sounds: [
			{
				name: "bell_ring",
			},
			{
				name: "glass",
				volume: 1,
			},
			{
				name: "alert_sound",
				volume: 0.3,
				preload: false
			}
		],
		volume: 0.5,
		path: "/inc/sounds/",
		preload: true
	});
});
let socket = new ReconnectingWebSocket("wss://" + window.location.host, null, {maxReconnectAttempts: 20, reconnectInterval: 3000});

socket.onopen = function(e) {
  console.log("[open] Connection is established with " + window.location.host);
  getAlerts();
};

function getAlerts() {
	socket.send("alert_group " + Cookies.get('group') + ' ' + Cookies.get('uuid'));
}

socket.onmessage = function(event) {
	var cur_url = window.location.href.split('/app/').pop();
	cur_url = cur_url.split('/');
	if (cur_url != 'login' && localStorage.getItem('disabled_alert') === null) {
		data = event.data.split(";");
		for (i = 0; i < data.length; i++) {
			if (data[i].indexOf('error:') != '-1' || data[i].indexOf('alert') != '-1' || data[i].indexOf('FAILED') != '-1') {
				if (data[i].indexOf('error: database is locked') == '-1') {
					toastr.error(data[i]);
					ion.sound.play("bell_ring");
				}
			} else if (data[i].indexOf('info: ') != '-1') {
				toastr.info(data[i]);
				ion.sound.play("glass");
			} else if (data[i].indexOf('success: ') != '-1') {
				toastr.success(data[i]);
				ion.sound.play("glass");
			} else if (data[i].indexOf('warning: ') != '-1') {
				toastr.warning(data[i]);
				ion.sound.play("bell_ring");
			} else if (data[i].indexOf('critical: ') != '-1') {
				toastr.error(data[i]);
				ion.sound.play("bell_ring");
			}
		}
	}
};

socket.onclose = function(event) {
  if (event.wasClean) {
    console.log(`[close] Соединение закрыто чисто, код=${event.code} причина=${event.reason}`);
  } else {
    console.log('[close] Соединение прервано');
  }
};

socket.onerror = function(error) {
  console.log(`[error] ${error.message}`);
};
function changePassword() {
	$("#user-change-password-table").dialog({
		autoOpen: true,
		resizable: false,
		height: "auto",
		width: 600,
		modal: true,
		title: "Change password",
		show: {
			effect: "fade",
			duration: 200
		},
		hide: {
			effect: "fade",
			duration: 200
		},
		buttons: {
			"Change": function () {
				changeUserPasswordItOwn($(this));
			},
			Cancel: function () {
				$(this).dialog("close");
				$('#missmatchpass').hide();
			}
		}
	});
}
function changeUserPasswordItOwn(d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if (pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		toastr.clear();
		$.ajax({
			url: "/app/user/password",
			data: {
				updatepassowrd: pass,
				uuid: Cookies.get('uuid'),
				token: $('#token').val()
			},
			type: "POST",
			success: function (data) {
				data = data.replace(/\s+/g, ' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					d.dialog("close");
				}
			}
		});
	}
}
function findInConfig(words) {
	clearAllAjaxFields();
	$.ajax({
		url: "/app/config/" + $("#service").val() + "/find-in-config",
		data: {
			serv: $("#serv").val(),
			words: words
		},
		type: "POST",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
			}
		}
	});
}
function waitForElm(selector) {
	return new Promise(resolve => {
		if (document.querySelector(selector)) {
			return resolve(document.querySelector(selector));
		}

		const observer = new MutationObserver(mutations => {
			if (document.querySelector(selector)) {
				resolve(document.querySelector(selector));
				observer.disconnect();
			}
		});

		observer.observe(document.body, {
			childList: true,
			subtree: true
		});
	});
}
function randomIntFromInterval(min, max) {
  return Math.floor(Math.random() * (max - min + 1) + min)
}
const removeEmptyLines = str => str.split(/\r?\n/).filter(line => line.trim() !== '').join('\n');
function returnNiceCheckingConfig(data) {
	if (data.indexOf('sudo: firewall-cmd: command not found') != '-1') {
		data = data.replaceAll('sudo: firewall-cmd: command not found\n', '');
		data = data.replaceAll('sudo: firewall-cmd: command not found', '');
		toastr.warning('The Firewalld service is not enabled. You should disable this setting for this server or enable the firewalld service on the server.')
	}
	data = data.replaceAll('Configuration file is valid', '');
	data = data.replaceAll('Warnings were found.', '');
	data = data.replaceAll('nginx: the configuration file /etc/nginx/nginx.conf syntax is ok', '');
	data = data.replaceAll('nginx: configuration file /etc/nginx/nginx.conf test is successful', '');
	data = data.replaceAll('Syntax OK', '');
	output = data.split('<br>')
	var alerts = [];
	var alert_warning = '';
	var alert_warning2 = '';
	var alert_error = '';
	var second_alert = false;
	alerts.push(output[0] + '\n' + output[1]);
	var server_name = output[0];
	var server_name2 = '';
	try {
		for (var i = 0; i < output.length; i++) {
			if (i > 1) {
				if (output[i] !== undefined) {
					alerts.push(output[i])
				}
			}
		}
	} catch (err) {
		console.log(err);
	}
	alerts.forEach((element) => {
		if (element.indexOf('error: ') != '-1' || element.indexOf('Fatal') != '-1' || element.indexOf('Error') != '-1' || element.indexOf('failed ') != '-1' || element.indexOf('emerg] ') != '-1' || element.indexOf('Syntax error ') != '-1' || element.indexOf('Parsing') != '-1') {
			alert_error = alert_error + element;
			return
		}
		if (element.indexOf('[WARNING]') != '-1' || element.indexOf('[ALER]') != '-1' || element.indexOf('[warn]') != '-1') {
			element = removeEmptyLines(element);
			if (second_alert == false) {
				alert_warning = alert_warning + element;
			} else {
				alert_warning2 = alert_warning2 + element;
				server_name = 'Master server:';
				server_name2 = 'Slave server:';
			}
		}
		if (second_alert && output.length > 4 && output[1].indexOf('[NOTICE]') == '-1') {
			server_name = 'Master server:';
			server_name2 = 'Slave server:';
		}
		if (element.length === 0) {
			second_alert = true;
		}

	})
	if (alert_error) {
		toastr.error(server_name + '<pre style="padding: 0; margin: 0;">' + alert_error + '</pre>');
		toastr.info('Config not applied');
	} else if (alert_warning) {
		toastr.warning(server_name + '<pre style="padding: 0; margin: 0;">' + alert_warning + '</pre>');
		toastr.success('<b>' + server_name + ' Configuration file is valid</b>');
	} else {
		toastr.success('<b>' + server_name + ' Configuration file is valid</b>');
	}

	if (alert_warning2) {
		toastr.warning(server_name2 + '<pre style="padding: 0; margin: 0;">' + alert_warning2 + '</pre>');
		toastr.success('<b>' + server_name2 + ' Configuration file is valid</b>');
	} else if (server_name2) {
		toastr.success('<b>' + server_name2 + ' Configuration file is valid</b>');
	}
}
function show_version() {
	NProgress.configure({showSpinner: false});
	$.ajax( {
		url: "/app/internal/show_version",
		success: function( data ) {
			$('#version').html(data);
			var showUpdates = $( "#show-updates" ).dialog({
				autoOpen: false,
				width: 600,
				modal: true,
				title: 'There is a new Roxy-WI version',
				buttons: {
					Close: function() {
						$( this ).dialog( "close" );
						clearTips();
					}
				}
			});
			$('#show-updates-button').click(function() {
				showUpdates.dialog('open');
			});
		}
	} );
	NProgress.configure({showSpinner: true});
}
function statAgriment() {
	var cur_url = window.location.href.split('/app/').pop();
	cur_url = cur_url.split('/');
	if (localStorage.getItem('statistic') == null && cur_url != 'login') {
		var titles = new Map()
		var body = new Map()
		var yes_ans = new Map()
		var no_ans = new Map()
		var ver_question = randomIntFromInterval(1, 2);
		titles.set(1, 'Help us improve Roxy-WI');
		titles.set(2, 'Data collection agreement');
		body.set(1, 'We want to improve the user experience by collecting anonymous statistics. No marketing.');
		body.set(2, 'We’d like to improve your experience in Roxy-WI, so we ask for statistics collection. No personal data is collected.');
		yes_ans.set(1, 'Yes');
		yes_ans.set(2, 'Agree and help the Roxy-WI team');
		no_ans.set(1, 'No');
		no_ans.set(2, 'Disagree');
		$("#statistic").dialog({
			autoOpen: true,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: titles.get(ver_question),
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
			buttons: [{
				"id": "statYesBut",
				text: "Yes",
				click: function () {
					localStorage.setItem('statistic', '1');
					$(this).dialog("close");
					sendGet('page/ans/1/' + ver_question);
					statAgriment();
				},
			}, {
				"id": "statNoBut",
				text: "No",
				click: function () {
					localStorage.setItem('statistic', '0');
					$(this).dialog("close");
					sendGet('page/ans/0/' + ver_question);
				}
			}]
		});
		$("#statYesBut").html('<span class="ui-button-text">' + yes_ans.get(ver_question) + '</span>');
		$("#statNoBut").html('<span class="ui-button-text">' + no_ans.get(ver_question) + '</span>');
		$("#statistic-body").html(body.get(ver_question));
	}
	if (localStorage.getItem('statistic') == 1) {
		cur_url = btoa(cur_url);
		sendGet('/page/send/'+cur_url);
	}
}
function startIntro(intro) {
	intro = intro.setOptions({'exitOnOverlayClick': false});
	var intro_url = cur_url[0].split('#')[0];
	var intro_history = {};
	intro.onbeforechange(function (targetElement) {
		if (intro_url == 'users.py' && this._currentStep == 3) {
			$("#tabs").tabs("option", "active", 1);
		} else if (intro_url == 'users.py' && this._currentStep == 4) {
			$("#tabs").tabs("option", "active", 2);
		} else if (intro_url == 'users.py' && this._currentStep == 6) {
			$("#tabs").tabs("option", "active", 3);
		} else if (intro_url == 'users.py' && this._currentStep == 7) {
			$("#tabs").tabs("option", "active", 4);
		} else if (intro_url == 'users.py' && this._currentStep == 9) {
			$("#tabs").tabs("option", "active", 6);
		} else if (intro_url == 'users.py' && this._currentStep == 10) {
			$("#tabs").tabs("option", "active", 7);
		} else if (intro_url == 'users.py' && this._currentStep == 12) {
			$("#tabs").tabs("option", "active", 8);
		}
		if (intro_url == 'servers.py' && this._currentStep == 5) {
			$("#tabs").tabs("option", "active", 1);
		} else if (intro_url == 'servers.py' && this._currentStep == 13) {
			$("#tabs").tabs("option", "active", 2);
		} else if (intro_url == 'servers.py' && this._currentStep == 16) {
			$("#tabs").tabs("option", "active", 6);
		} else if (intro_url == 'servers.py' && this._currentStep == 18) {
			$("#tabs").tabs("option", "active", 7);
		}
	});
	intro.onbeforeexit(function () {
		if(localStorage.getItem('intro') === null) {
			intro_history[intro_url] = '1';
			localStorage.setItem('intro', JSON.stringify(intro_history));
		} else {
			intro_history = localStorage.getItem('intro');
			intro_history = JSON.parse(intro_history);
			intro_history[intro_url] = '1';
			localStorage.setItem('intro', JSON.stringify(intro_history));
		}
	});
	intro.onexit(function() {
		sendGet('intro/' + intro_url + '/' + this._currentStep);
	});
	if(localStorage.getItem('intro') === null) {
		if (intro_url.split('#')[0] == 'users.py' || intro_url.split('#')[0] == 'servers.py') {
			$( "#tabs" ).tabs( "option", "active", 0 );
		}
		intro.start();
	} else {
		intro_history = localStorage.getItem('intro');
		intro_history = JSON.parse(intro_history);
		if (intro_history[intro_url] != '1') {
			if (intro_url.split('#')[0] == 'users.py' || intro_url.split('#')[0] == 'servers.py') {
				$( "#tabs" ).tabs( "option", "active", 0 );
			}
			intro.start();
		}
	}
}
document.addEventListener("DOMContentLoaded", function(event){
	statAgriment();
});
function sendGet(page) {
	var xmlHttp = new XMLHttpRequest();
	var theUrl = 'https://roxy-wi.org/' + page;
	xmlHttp.open("GET", theUrl, true); // true for asynchronous
	xmlHttp.send(null);
}
function show_pretty_ansible_error(data) {
	try {
		data = data.split('error: ');
		var p_err = JSON.parse(data[1]);
		return p_err['msg'];
	} catch (e) {
		return data;
	}
}
function openTab(tabId) {
	$( "#tabs" ).tabs( "option", "active", tabId );
}
function showPassword(input) {
  var x = document.getElementById(input);
  if (x.type === "password") {
    x.type = "text";
  } else {
    x.type = "password";
  }
}
