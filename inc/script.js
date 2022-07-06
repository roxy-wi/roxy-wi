var url = "/inc/script.js";
var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
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
var wait_mess = '<div class="alert alert-warning">Please do not close or refresh the page. Wait until the job is completed. This may take some time</div>'
function show_current_page(id) {
	id.parent().css('display', 'contents');
	id.parent().css('font-size', '13px');
	id.parent().css('top', '0');
	id.parent().css('left', '0');
	id.parent().children().css('margin-left', '-20px');
	id.parent().find('a').css('padding-left', '20px');
	id.find('a').css('padding-left', '30px');
	id.find('a').css('border-left', '4px solid var(--right-menu-blue-rolor)');
}
$( function() {		
   $('.menu li ul li').each(function () {
       var link = $(this).find('a').attr('href');
	   var link2 = link.split('/')[2]
	   if (cur_url[1] == null) {
		cur_url[1] = 'haproxy';
	   }
       if (cur_url[0] == link2 && cur_url[1].split('&')[0] != 'service=keepalived' && cur_url[1].split('&')[0] != 'service=nginx' && cur_url[1].split('&')[0] != 'service=apache') {
			show_current_page($(this))
		} else if(cur_url[0] == 'versions.py' && cur_url[1].split('&')[0] == 'service=keepalived' && link2 == 'versions.py?service=keepalived'){ 
			show_current_page($(this))
		} else if(cur_url[0] == 'config.py' && cur_url[1].split('&')[0] == 'service=keepalived' && link2 == 'config.py?service=keepalived'){
			show_current_page($(this))
		} else if(cur_url[0] == 'versions.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'versions.py?service=nginx'){ 
			show_current_page($(this))
		} else if(cur_url[0] == 'config.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'config.py?service=nginx'){
			show_current_page($(this))
		} else if(cur_url[0] == 'logs.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'logs.py?service=nginx'){
			show_current_page($(this))
		}  else if(cur_url[0] == 'logs.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'logs.py?service=apache'){
			show_current_page($(this))
		}  else if(cur_url[0] == 'logs.py' && cur_url[1].split('&')[0] == 'service=keepalived' && link2 == 'logs.py?service=keepalived'){
			show_current_page($(this))
		} else if(cur_url[0] == 'hapservers.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'hapservers.py?service=nginx'){
			show_current_page($(this))
		} else if(cur_url[0] == 'hapservers.py' && cur_url[1].split('&')[0] == 'service=keepalived' && link2 == 'hapservers.py?service=keepalived'){
			show_current_page($(this))
		} else if(cur_url[0] == 'viewsttats.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'viewsttats.py?service=nginx'){
			show_current_page($(this))
		} else if(cur_url[0] == 'viewsttats.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'viewsttats.py?service=apache'){
			show_current_page($(this))
		} else if(cur_url[0] == 'smon.py' && cur_url[1].split('&')[0] == 'action=view' && link2 == 'smon.py?action=view'){
		   show_current_page($(this))
	   	} else if(cur_url[0] == 'smon.py' && cur_url[1].split('&')[0] == 'action=add' && link2 == 'smon.py?action=add'){
		   show_current_page($(this))
       } else if(cur_url[0] == 'smon.py' && cur_url[1].split('&')[0] == 'action=history' && link2 == 'smon.py?action=history'){
		   show_current_page($(this))
       } else if(cur_url[0] == 'smon.py' && cur_url[1].split('&')[0] == 'action=checker_history' && link2 == 'smon.py?action=checker_history'){
		   show_current_page($(this))
	   } else if(cur_url[0] == 'add.py' && cur_url[1].split('&')[0] == 'service=nginx#ssl' && link2 == 'add.py?service=nginx#ssl'){
		   show_current_page($(this))
	   } else if(cur_url[0] == 'viewlogs.py' && cur_url[1].split('&')[0] == 'type=2' && link2 == 'viewlogs.py?type=2'){
		  	show_current_page($(this))
	   } else if(cur_url[0] == 'metrics.py' && cur_url[1].split('&')[0] == 'service=nginx' && link2 == 'metrics.py?service=nginx'){
		   show_current_page($(this))
	   } else if(cur_url[0] == 'metrics.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'metrics.py?service=apache'){
		   show_current_page($(this))
	   } else if(cur_url[0] == 'hapservers.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'hapservers.py?service=apache'){
			show_current_page($(this))
	   } else if(cur_url[0] == 'versions.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'versions.py?service=apache'){ 
			show_current_page($(this))
	   } else if(cur_url[0] == 'config.py' && cur_url[1].split('&')[0] == 'service=apache' && link2 == 'config.py?service=apache'){
			show_current_page($(this))
	   } else if(cur_url[0] == 'add.py' && cur_url[1].split('&')[0] == 'service=apache#ssl' && link2 == 'add.py?service=apache#ssl'){
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
			if (cur_url[0] == "logs.py") {
				showLog();
			} else if (cur_url[0] == "viewsttats.py") {
				showStats()
			} else if (cur_url[0] == "overview.py") {
				showOverview(); 
			} else if (cur_url[0] == "viewlogs.py") {
				viewLogs();
			} else if (cur_url[0] == "metrics.py") {
				showMetrics();
			} else if (cur_url[0] == "smon.py" && cur_url[1].split('&')[0] == "action=view") {
				showSmon('refresh')
			}
		}
	}
};
if(localStorage.getItem('restart')) {
	var ip_for_restart = localStorage.getItem('restart');
	$.ajax( {
		url: "options.py",
		data: {
			act: "checkrestart",
			serv: ip_for_restart,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if(data.indexOf('ok') != '-1') {
				var apply_div = $.find("#apply_div");
				apply_div = apply_div[0].id;
				$("#apply").css('display', 'block');
				$('#'+apply_div).css('width', '850px');
				if (cur_url[0] == "hapservers.py") {
					$('#'+apply_div).css('width', '650px');
					$('#'+apply_div).addClass("alert-one-row");
					$('#'+apply_div).html("You have made changes to the server: "+ip_for_restart+". Changes will take effect only after<a id='"+ip_for_restart+"' class='restart' title='Restart HAproxy service' onclick=\"confirmAjaxAction('restart', 'hap', '"+ip_for_restart+"')\">restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				} else {
					$('#'+apply_div).html("You have made changes to the server: "+ip_for_restart+". Changes will take effect only after restart. <a href='hapservers.py' title='Overview'>Go to the HAProxy Overview page and restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				}
				$.getScript('/inc/overview.js');
			}
		}					
	} );
}
function autoRefreshStyle(autoRefresh) {
	var margin;
	if (cur_url[0] == "overview.py" || cur_url[0] == "waf.py" || cur_url[0] == "metrics.py") {
		if(autoRefresh < 60000) {
			autoRefresh = 60000;
		}
	}
	autoRefresh = autoRefresh / 1000;
	if ( autoRefresh == 60) {
		timeRange = " minute"
		autoRefresh = autoRefresh / 60;
	} else if ( autoRefresh > 60 && autoRefresh < 3600 ) {
		timeRange = " minutes"
		autoRefresh = autoRefresh / 60;
	} else if ( autoRefresh >= 3600 && autoRefresh < 86401 ) {
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
	$('#browse_histroy').css("border-bottom", "none");
	$('.auto-refresh img').remove();
}
function setRefreshInterval(interval) {
	if (interval == "0") {
		var autoRefresh = sessionStorage.getItem('auto-refresh');
		if (autoRefresh !== undefined) {
			sessionStorage.removeItem('auto-refresh');
			pauseAutoRefresh();
			$('#0').html('<span class="auto-refresh-reload auto-refresh-reload-icon"></span> Auto-refresh');
			$('.auto-refresh').css('display', 'inline');
			$('.auto-refresh').css('font-size', '15px');
			$('#1').text('Auto-refresh');
			$('.auto-refresh-pause').css('display', 'none');
			$('.auto-refresh-resume').css('display', 'none');
			$.getScript("/inc/fontawesome.min.js");
			$.getScript("/inc/scripts.js");
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
		if (cur_url[0] == "logs.py") {
			intervalId = setInterval('showLog()', interval);
			showLog();
		} else if (cur_url[0] == "viewsttats.py") {
			intervalId = setInterval('showStats()', interval);
			showStats()
		} else if (cur_url[0] == "overview.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showOverview(ip, hostnamea)', interval);
			showOverview(ip, hostnamea); 
		} else if (cur_url[0] == "viewlogs.py") {
			intervalId = setInterval('viewLogs()', interval);
			viewLogs();
		} else if (cur_url[0] == "metrics.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showMetrics()', interval);
			showMetrics();
		} else if (cur_url[0] == "waf.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showOverviewWaf(ip, hostnamea)', interval);
			showOverviewWaf(ip, hostnamea);
			showWafMetrics();
		} else if (cur_url[0] == "hapservers.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showMetrics()', interval);
			showMetrics();
		} else if (cur_url[0] == "smon.py" && cur_url[1].split('&')[0] == "action=view") {
			intervalId = setInterval("showSmon('refresh')", interval);
			showSmon('refresh');
		}
	} else {
		pauseAutoRefresh();
	}
}
function pauseAutoRefresh() {
	clearInterval(intervalId);
	$(function() {
		$('.auto-refresh-pause').css('display', 'none');
		$('.auto-refresh-resume').css('display', 'inline');
		sessionStorage.setItem('auto-refresh-pause', '1')
	});
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
	$.ajax( {
		url: "options.py",
		data: {
			act: "stats",
			serv: $("#serv").val(),
			service: $("#service").val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' && data.indexOf('Internal error:') == '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Stats", "Stats", cur_url[0] + "?service=" + $("#service").val() + "&serv=" + $("#serv").val());
				wait();
			}
		}					
	} );
}
function openStats() {
	var serv = $("#serv").val();
	if (cur_url[1].split('&')[0] == "service=nginx") {
		var url = "viewsttats.py?service=nginx&serv="+serv+"&open=open"
	} else {	
		var url = "viewsttats.py?serv="+serv+"&open=open"
	}
	var win = window.open(url, '_blank');
	win.focus();
}
function openVersions() {
	var serv = $("#serv").val();
	if (cur_url[1].split('&')[0] == "service=keepalived") {
		var url = "versions.py?service=keepalived&serv="+serv+"&open=open"
	} else if (cur_url[1].split('&')[0] == "service=nginx") {
		var url = "versions.py?service=nginx&serv="+serv+"&open=open"
	} else if (cur_url[1].split('&')[0] == "service=apache") {
		var url = "versions.py?service=apache&serv="+serv+"&open=open"
	} else {	
		var url = "versions.py?serv="+serv+"&open=open"
	}
	var win = window.open(url,"_self");
	win.focus();
}
function showLog() {
	var waf = findGetParameter('waf');
	var file = $('#log_files').val();
	if (file === null) {
		toastr.warning('Select a log file first')
		return false;
	}
	var rows = $('#rows').val()
	var grep = $('#grep').val()
	var exgrep = $('#exgrep').val()
	var hour = $('#time_range_out_hour').val()
	var minut = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minut1 = $('#time_range_out_minut1').val()
	var service = $('#service').val()
	if (service == 'None') {
		service = 'haproxy';
	}
	$.ajax( {
		url: "options.py",
		data: {
			show_log: rows,
			serv: $("#serv").val(),
			waf: waf,
			grep: grep,
			exgrep: exgrep,
			hour: hour,
			minut: minut,
			hour1: hour1,
			minut1: minut1,
			service: service,
			file: file,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			toastr.clear();
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0] + "?service=" + service + "&serv=" + $("#serv").val() +
				'&rows=' + rows +
				'&exgrep=' + exgrep +
				'&grep=' + grep +
				'&hour=' + hour +
				'&minut=' + minut +
				'&hour1=' + hour1 +
				'&minut1=' + minut1 +
				'&file=' + file +
				'&waf=' + waf);

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
	var minut = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minut1 = $('#time_range_out_minut1').val()
	var service = $('#service').val()
	if (service == 'None') {
		service = 'haproxy';
	}
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showRemoteLogFiles",
			service: service,
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
				window.history.pushState("Logs", "Logs", cur_url[0] + "?service=" + service + "&serv=" + $("#serv").val() +
					'&rows=' + rows +
					'&exgrep=' + exgrep +
					'&grep=' + grep +
					'&hour=' + hour +
					'&minut=' + minut +
					'&hour1=' + hour1 +
					'&minut1=' + minut1 +
					'&waf=0');
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
	var unique = $.now();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showMap",
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Show map", "Show map", cur_url[0] + '?serv=' + $("#serv").val() + '&showMap');
			}
		}					
	} );
}
function showCompare() {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			left: $('#left').val(),
			right: $("#right").val(),
			service: $("#service").val(),
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
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showCompareConfigs",
			open: "open",
			service: $("#service").val(),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-compare").html(data);
				$("input[type=submit], button").button();
				$("select").selectmenu();
				window.history.pushState("Show compare config", "Show compare config", cur_url[0] + '?service=' + $("#service").val() + '&serv=' + $("#serv").val() + '&showCompare');
			}
		}
	} );
}
function showConfig() {
	var service = $('#service').val();
	var config_file_name = encodeURI($('#config_file_name').val());
	if (service == 'nginx' || service == 'apache') {
		if ($('#config_file_name').val() === undefined || $('#config_file_name').val() === null) {
			toastr.warning('Select a config file firts');
			return false;
		}
	}
	clearAllAjaxFields();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShow",
			service: service,
			config_file_name: config_file_name,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				$.getScript('/inc/configshow.js');
				window.history.pushState("Show config", "Show config", cur_url[0] + "?service=" + service + "&serv=" + $("#serv").val() + "&showConfig");
			}
		}					
	} );
}
function showConfigFiles() {
	var service = $('#service').val();
	clearAllAjaxFields();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShowFiles",
			service: service,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-config_file_name").html(data);
				if (findGetParameter('findInConfig') === null) {
					window.history.pushState("Show config", "Show config", cur_url[0] + "?service=" + service + "&serv=" + $("#serv").val() + "&showConfigFiles");
				}
			}
		}
	} );
}
function showConfigFilesForEditing() {
	var service = $('#service').val();
	var config_file_name = findGetParameter('config_file_name')
	var service = findGetParameter('service')
	if (service == 'nginx' || service == 'apache') {
		$.ajax({
			url: "options.py",
			data: {
				serv: $("#serv").val(),
				act: "configShowFiles",
				service: service,
				config_file_name: config_file_name,
				token: $('#token').val()
			},
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
		url: "options.py",
		data: {
			serv: serv,
			act: "configShow",
			configver: configver,
			service: service,
			token: $('#token').val(),
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Show config", "Show config", cur_url[0] + "?service=" + service + "&serv=" + serv + "&open=open&configver=" + configver);
				$.getScript('/inc/configshow.js');
			}
		}					
	} );
}
function showListOfVersion(for_delver) {
	var service = $('#service').val();
	var serv = $("#serv").val();
	var configver = findGetParameter('configver');
	var style = 'new'
	if (localStorage.getItem('version_style') == 'old') {
		style = 'old'
	}
	clearAllAjaxFields();
	$.ajax( {
		url: "options.py",
		data: {
			serv: serv,
			act: "showListOfVersion",
			service: service,
			configver: configver,
			for_delver: for_delver,
			style: style,
			token: $('#token').val(),
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#config_version_div").html(data);
				$( "input[type=checkbox]" ).checkboxradio();
			}
		}
	} );
}
function changeVersion(){
	if (localStorage.getItem('version_style') == 'old') {
		localStorage.setItem('version_style', 'new');
		showListOfVersion(1);
	} else {
		localStorage.setItem('version_style', 'old');
		showListOfVersion(1);
	}
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
	if($('#viewlogs').val() == 'roxy-wi.error.log' || $('#viewlogs').val() == 'roxy-wi.access.log' || $('#viewlogs').val() == 'fail2ban.log') {
		showApacheLog($('#viewlogs').val());
	} else {
		var rows = $('#rows').val()
		var grep = $('#grep').val()
		var exgrep = $('#exgrep').val()
		var hour = $('#time_range_out_hour').val()
		var minut = $('#time_range_out_minut').val()
		var hour1 = $('#time_range_out_hour1').val()
		var minut1 = $('#time_range_out_minut1').val()
		var viewlogs = $('#viewlogs').val()
		var type = findGetParameter('type')
		if (viewlogs == null){
			viewlogs = findGetParameter('viewlogs')
		}	
		$.ajax( {
			url: "options.py",
			data: {
				viewlogs: viewlogs,
				rows: rows,
				grep: grep,
				exgrep: exgrep,
				hour: hour,
				minut: minut,
				hour1: hour1,
				minut1: minut1,
				token: $('#token').val(),				
			},
			type: "POST",
			success: function( data ) {
				$("#ajax").html(data);
				window.history.pushState("View logs", "View logs", cur_url[0] + "?type=" + type +
						"&viewlogs=" + viewlogs +
						'&rows=' + rows +
						'&grep=' + grep +
						'&exgrep=' + exgrep +
						'&hour=' + hour +
						'&minut=' + minut +
						'&hour1=' + hour1 +
						'&minut1=' + minut1);
			}					
		} );
	}
}
$( function() {
	NProgress.configure({showSpinner: false});
	$.ajax( {
		url: "options.py",
		data: {
			show_versions: 1,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$('#version').html(data);
			var showUpdates = $( "#show-updates" ).dialog({
				autoOpen: false,
				width: 600,
				modal: true,
				title: 'There is a new version Roxy-WI',
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
	$('a').click(function(e) {
		try {
			var cur_path = window.location.pathname;
			var attr = $(this).attr('href');
			if (typeof attr !== typeof undefined && attr !== false) {
				$('title').text($(this).attr('title'));
				history.pushState({}, '', $(this).attr('href'));
				if ($(this).attr('href').split('#')[0] && $(this).attr('href').split('#')[0] != cur_path) {
					window.history.go()
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
		
    //$( "[title]" ).tooltip();
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
		let searchParams = new URLSearchParams(window.location.search)
		if(searchParams.has('ref')) {
			window.location = /.*ref=([^&]*).*/.exec(document.location.href)[1];
		} else {
			var ref = "overview.py";
		}
		$.ajax( {
			url: "login.py",
			data: {
				login: $('#login').val(),
				pass: $('#pass').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('ok') != '-1') {
					window.location.replace(ref);
				} else if (data.indexOf('disabled') != '-1') {
					$('.alert').show();
					$('.alert').html(data);
				} else if (data.indexOf('ban') != '-1') {
					ban();				
				} 
			}
		} );
		return false;
	});
	$('#show_log_form').submit(function() {
		if(cur_url[0] == '/app/logs.py') {
			showLog();
		} else {
			viewLogs();
		}
		return false;
	});
	var showUserSettings = $( "#show-user-settings" ).dialog({
			autoOpen: false,
			width: 600,
			modal: true,
			title: 'User settings',
			buttons: {
				Apply: function() {
					saveUserSettings();
					$( this ).dialog( "close" );
				},
				'Change password': function() {
					changePassword();
					$( this ).dialog( "close" );
				},
				Logout: function() {
					window.location.replace(window.location.origin+'/app/login.py?logout=logout');
				}
			}
		});

	$('#show-user-settings-button').click(function() {
		if (localStorage.getItem('disabled_alert') == '1') {
			$('#disable_alerting option[value="1"]').prop('selected', true);
			$('#disable_alerting').selectmenu('refresh');
		} else {
			$('#disable_alerting option[value="0"]').prop('selected', true);
			$('#disable_alerting').selectmenu('refresh');
		}
		$.ajax( {
			url: "options.py",
			data: {
				getcurrentusergroup: 1,
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				if (data.indexOf('danger') != '-1') {
					$("#ajax").html(data);
				} else {
					$('#show-user-settings-group').html(data);
					$( "select" ).selectmenu();
				}
			}
		} );
		showUserSettings.dialog('open');
	});
	var location = window.location.href;
    var cur_url = '/app/' + location.split('/').pop();
	cur_url = cur_url.split('?');
	cur_url = cur_url[0].split('#');
	if (cur_url[0] == "/app/users.py" || cur_url[0] == "/app/servers.py") {
		$( ".users" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
				$(this).children(".users").css('padding-left', '30px');
				$(this).children(".users").css('border-left', '4px solid var(--right-menu-blue-rolor)');
			});
			$( "#tabs" ).tabs( "option", "active", 0 );
		} );
		if (cur_url[0] == "/app/users.py") {
			$( ".group" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".group").css('padding-left', '30px');
					$(this).children(".group").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );
			$( ".runtime" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );
			$( ".admin" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 3 );
			} );
			$( ".checker" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".checker").css('padding-left', '30px');
					$(this).children(".checker").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				loadchecker();
				$( "#tabs" ).tabs( "option", "active", 4 );
			} );
			$( ".settings" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".settings").css('padding-left', '30px');
					$(this).children(".settings").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 6 );
			} );
			$( ".services" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".services").css('padding-left', '30px');
					$(this).children(".services").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				loadServices();
				$( "#tabs" ).tabs( "option", "active", 7 );
			} );
			$( ".updatehapwi" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".updatehapwi").css('padding-left', '30px');
					$(this).children(".updatehapwi").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 8 );
				loadupdatehapwi();
			} );
		} else {
			$( ".runtime" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );					
			$( ".admin" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );
			$( ".checker" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".checker").css('padding-left', '30px');
					$(this).children(".checker").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				loadchecker();
				$( "#tabs" ).tabs( "option", "active", 3 );
			} );
			$( ".settings" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".settings").css('padding-left', '30px');
					$(this).children(".settings").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 4 );
			} );
			$( ".installproxy" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".installproxy").css('padding-left', '30px');
					$(this).children(".installproxy").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 5 );
			} );
			$( ".installmon" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".installmon").css('padding-left', '30px');
					$(this).children(".installmon").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 6 );
			} );
			$( ".backup" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
					$(this).children(".backup").css('padding-left', '30px');
					$(this).children(".backup").css('border-left', '4px solid var(--right-menu-blue-rolor)');
				});
				$( "#tabs" ).tabs( "option", "active", 7 );
			} );
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
	if ($('#disable_alerting').val() == '0') {
		localStorage.removeItem('disabled_alert');
		sessionStorage.removeItem('disabled_alert');
	} else if ($('#disable_alerting').val() == '1') {
		sessionStorage.setItem('disabled_alert', '1');
		localStorage.removeItem('disabled_alert');
	}
	changeCurrentGroupF();
}
function sleep(ms) {
	return new Promise(resolve => setTimeout(resolve, ms));
}
async function ban() {
	$( '#login').attr('disabled', 'disabled');
	$( '#pass').attr('disabled', 'disabled');
	$( "input[type=submit], button" ).button('disable');
	$('.alert').show();
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
		var get_history_array = ['login.py', 'login.py','login.py'];
		localStorage.setItem('history', JSON.stringify(get_history_array));
	}
}
function listHistroy() {	
	var browse_history = JSON.parse(localStorage.getItem('history'));
	var history_link = '';
	var title = []
	var link_text = []
	for(let i = 0; i < browse_history.length; i++){
		if (i == 0) {
			browse_history[0] = browse_history[1];
		}
		if (i == 1) {
			browse_history[1] = browse_history[2]
		}
		if (i == 2) {
			if(cur_url[1] !== undefined) {
				browse_history[2] = cur_url[0] + '?' + cur_url[1]
			} else {
				browse_history[2] = cur_url[0]
			}
		}
		$( function() {
			$('.menu li ul li').each(function () {
				var link1 = $(this).find('a').attr('href');
				var link2 = link1.split('/')[2]
				if (browse_history[i] == link2) {
					title[i] = $(this).find('a').attr('title');
					link_text[i] = $(this).find('a').text();
					history_link = '<li><a href="'+browse_history[i]+'" title="'+title[i]+'">'+link_text[i]+'</a></li>'
					$('#browse_histroy').append(history_link);
				}
			});
		});
	}
	localStorage.setItem('history', JSON.stringify(browse_history));
}
createHistroy()
listHistroy()

function changeCurrentGroupF(){
	Cookies.remove('group');
	Cookies.set('group', $('#newCurrentGroup').val(), { expires: 365, path: '/app', samesite: 'strict', secure: 'true' });
	$.ajax( {
		url: "options.py",
		data: {
			changeUserCurrentGroupId: $('#newCurrentGroup').val(),
			changeUserGroupsUser: Cookies.get('uuid'),
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error: ') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				location.reload();
			}
		}
	} );

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
	cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('?');
	if (cur_url[0] != 'login.py' && localStorage.getItem('disabled_alert') === null) {
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
	$( "#user-change-password-table" ).dialog({
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
				"Change": function() {
					changeUserPasswordItOwn($(this));
				},
				Cancel: function() {
					$( this ).dialog( "close" );
					$('#missmatchpass').hide();
				}
			}
		});
}
function changeUserPasswordItOwn(d) {
	var pass = $('#change-password').val();
	var pass2 = $('#change2-password').val();
	if(pass != pass2) {
		$('#missmatchpass').show();
	} else {
		$('#missmatchpass').hide();
		toastr.clear();
		$.ajax( {
			url: "options.py",
			data: {
				updatepassowrd: pass,
				uuid: Cookies.get('uuid'),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('error:') != '-1') {
					toastr.error(data);
				} else {
					toastr.clear();
					d.dialog( "close" );
				}
			}
		} );
	}
}
function findInConfig(words) {
	clearAllAjaxFields();
		$.ajax( {
			url: "options.py",
			data: {
				serv: $("#serv").val(),
				act: "findInConfigs",
				service: $("#service").val(),
				words: words,
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
	var alerts = []
	alerts.push(output[0] + '\n' + output[1]);
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
		if (element.indexOf('error: ') != '-1' || element.indexOf('Fatal') != '-1' || element.indexOf('Error') != '-1' || element.indexOf('failed ') != '-1' || element.indexOf('emerg] ') != '-1' || element.indexOf('Syntax error ') != '-1') {
			toastr.error('<pre style="padding: 0; margin: 0;">' + element + '</pre>');
			toastr.info('Config not applied');
			return
		} else {
			toastr.success('<b>Configuration file is valid</b>');
		}
		if (element.indexOf('[WARNING]') != '-1' || element.indexOf('[ALER]') != '-1' || element.indexOf('[warn]') != '-1') {
			element = removeEmptyLines(element);
			toastr.warning('<pre style="padding: 0; margin: 0;">' + element + '</pre>')
		}
	})
}
