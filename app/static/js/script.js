var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('/');
function validateEmail(email) {
	const re = /^(([^<>()[\]\\.,;:\s@\"]+(\.[^<>()[\]\\.,;:\s@\"]+)*)|(\".+\"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
	return re.test(email);
}
function ValidateIPaddress(ipaddress) {
	if (/^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/.test(ipaddress)) {
		return true
	}
	return false
}
var select_server = translate_div.attr('data-select_server');
function checkIsServerFiled(select_id, message = select_server) {
	if ($(select_id).val() == null || $(select_id).val() === '') {
		toastr.warning(message);
		return false;
	}
	return true;
}
function escapeHtml(unsafe) {
	return unsafe
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}
var wait_mess_word = translate_div.attr('data-wait_mess');
var wait_mess = '<div class="alert alert-warning">'+wait_mess_word+'</div>'
function show_current_page(id) {
	let theme = localStorage.getItem('theme');
	let correct_color = 'var(--color-gray-dark-alpha)';
	if (theme === 'dark') {
		correct_color = '#181818';
	}
	id.parent().css('display', 'contents');
	id.parent().css('font-size', '13px');
	id.parent().css('top', '0');
	id.parent().css('left', '0');
	id.parent().children().css('margin-left', '-20px');
	id.parent().find('a').css('padding-left', '20px');
	id.find('a').css('border-left', '4px solid var(--color-wanring) !important');
	id.find('a').css('background-color', correct_color +' !important');
}
$( function() {		
   $('.menu li ul li').each(function () {
	   let link = $(this).find('a').attr('href');
	   let full_uri = window.location.pathname
	   let full_uri1 = window.location.hash
	   let params = new URL(document.location.toString()).searchParams;
	   if (full_uri === link) {
		   show_current_page($(this))
	   } else if (link === full_uri + full_uri1) {
		   show_current_page($(this))
	   } else if (link === '/add/haproxy#ssl' && full_uri1 === '#ssl' && params.get("service") != 'nginx') {
		   show_current_page($(this))
	   } else if (link === '/add/haproxy#ssl' && full_uri1 === '#ssl' && params.get("service") === 'nginx') {
		   show_current_page($(this))
	   } else if (full_uri === 'add/haproxy?service=nginx#ssl' && cur_url[1].split('?')[1] === 'service=nginx#ssl' && full_uri1 === 'add/haproxy?service=nginx#ssl') {
		   show_current_page($(this))
	   } else if (full_uri === 'add/haproxy?service=apache#ssl' && cur_url[1].split('?')[1] === 'service=apache#ssl' && full_uri1 === 'add/haproxy?service=apache#ssl') {
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
if(localStorage.getItem('restart')) {
	let ip_for_restart = localStorage.getItem('restart');
	$.ajax({
		url: "/service/check-restart/" + ip_for_restart,
		success: function (data) {
			if (data.indexOf('ok') != '-1') {
				var apply_div = $.find("#apply_div");
				apply_div = apply_div[0].id;
				$("#apply").css('display', 'block');
				$('#' + apply_div).css('width', '850px');
				ip_for_restart = escapeHtml(ip_for_restart);
				if (cur_url[0] === "service") {
					$('#' + apply_div).css('width', '650px');
					$('#' + apply_div).addClass("alert-one-row");
					$('#' + apply_div).html("You have made changes to the server: " + ip_for_restart + ". Changes will take effect only after<a id='" + ip_for_restart + "' class='restart' title='Restart HAproxy service' onclick=\"confirmAjaxAction('restart', 'hap', '" + ip_for_restart + "')\">restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				} else {
					$('#' + apply_div).html("You have made changes to the server: " + ip_for_restart + ". Changes will take effect only after restart. <a href='service' title='Overview'>Go to the HAProxy Overview page and restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
				}
				$.getScript(overview);
			}
		}
	});
}
$( document ).ajaxSend(function( event, request, settings ) {
	NProgress.start();
});
$( document ).ajaxComplete(function( event, request, settings ) {
	NProgress.done();
});
$.ajaxSetup({
	headers: {"X-CSRF-TOKEN": csrf_token},
});
$(document).ajaxError(function myErrorHandler(event, xhr, ajaxOptions, thrownError) {
	if (xhr.status != 401 && xhr.status != 404) {
		toastr.error(xhr.responseJSON.error);
	}
});
function showStats() {
	$.ajax({
		url: "/stats/view/" + $("#service").val() + "/" + $("#serv").val(),
		success: function (data) {
			if (data.indexOf('error:') != '-1' && data.indexOf('Internal error:') == '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Stats", "Stats", "/stats/" + $("#service").val() + "/" + $("#serv").val());
				wait();
			}
		}
	});
}
function openStats() {
	let serv = $("#serv").val();
	let service_url = cur_url[4];
	let url = "/stats/"+service_url+"/"+serv
	let win = window.open(url, '_blank');
	win.focus();
}
function openVersions() {
	let serv = $("#serv").val();
	let service_url = cur_url[4];
	let url = "/config/versions/"+service_url+"/"+serv
	let win = window.open(url,"_self");
	win.focus();
}
function showLog() {
	let waf = cur_url[0].split('?')[0];
	let file = $('#log_files').val();
	if (!checkIsServerFiled('#serv')) return false;
	let serv = $("#serv").val();
	if ((file === undefined || file === null || file === 'Select a file') && (waf === '' || waf === undefined)) {
		let file_from_get = findGetParameter('file');
		if (file_from_get === undefined || file_from_get === null) {
			toastr.warning('Select a log file first')
			return false;
		} else {
			file = findGetParameter('file');
		}
	}
	if ((file === undefined || file === null) && waf === '') {
		toastr.warning('Select a log file first')
		return false;

	}
	let rows = $('#rows').val();
	let grep = $('#grep').val();
	let exgrep = $('#exgrep').val();
	let hour = $('#time_range_out_hour').val();
	let minute = $('#time_range_out_minut').val();
	let hour1 = $('#time_range_out_hour1').val();
	let minute1 = $('#time_range_out_minut1').val();
	let service = $('#service').val();
	let url = "/logs/" + service + "/" + serv + "/" + rows;
	if (service === 'None') {
		service = 'haproxy';
	}
	if (waf && waf != 'haproxy' && waf != 'apache' && waf != 'keepalived') {
		file = findGetParameter('file');
		url = "/logs/" + service + "/waf/" + serv + "/" + rows + '?file_from_get=' + file;
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
		url: "/logs/" + service + "/" + serv ,
		data: {
			serv: $("#serv").val(),
		},
		type: "POST",
		success: function( data ) {
			if (data.indexOf('error:') != '-1' || data.indexOf('ls: cannot access') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#remote_log_files").html(data);
				$.getScript(configShow);
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
	$.ajax({
		url: "/config/map/haproxy/" + $("#serv").val() + '/show',
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data);
				window.history.pushState("Show Map", "Show Map", '/config/map/' + $("#service").val() + '/' + $("#serv").val());
			}
		}
	});
}
function showCompare() {
	$.ajax({
		url: "/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/show",
		data: {
			left: $('#left').val(),
			right: $("#right").val(),
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
function showCompareConfigs() {
	clearAllAjaxFields();
	$('#ajax-config_file_name').empty();
	$.ajax({
		url: "/config/compare/" + $("#service").val() + "/" + $("#serv").val() + "/files",
		type: "GET",
		success: function (data) {
			if (data.indexOf('error:') != '-1') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax-compare").html(data);
				$("input[type=submit], button").button();
				$("select").selectmenu();
				window.history.pushState("Show compare config", "Show compare config", '/config/compare/' + $("#service").val() + '/' + $("#serv").val());
			}
		}
	});
}
function showConfig() {
	let edit_section = '';
	let service = $('#service').val();
	let config_file = $('#config_file_name').val()
	let config_file_name = encodeURI(config_file);
	if (service === 'nginx' || service === 'apache') {
		if (config_file === undefined || config_file === null) {
			config_file_name = cur_url[4]
			if (config_file_name === '') {
				toastr.warning('Select a config file first');
				return false;
			} else {
				showConfigFiles(true);
			}
		}
	}
	clearAllAjaxFields();

	if (service === 'haproxy') {
		edit_section = findGetParameter('section');
		let edit_section_uri = '?section=' + edit_section;
	}
	let json_data = {
		"serv": $("#serv").val(),
		"service": service,
		"config_file_name": config_file_name,
		"edit_section": edit_section
	}
	$.ajax({
		url: "/config/" + service + "/show",
		data: JSON.stringify(json_data),
		type: "POST",
		contentType: "application/json; charset=utf-8",
		success: function (data) {
			if (data.status === 'failed') {
				toastr.error(data);
			} else {
				toastr.clear();
				$("#ajax").html(data.data);
				$.getScript(configShow);
				window.history.pushState("Show config", "Show config", "/config/" + service + "/" + $("#serv").val() + "/show/" + config_file_name + edit_section_uri);
			}
		}
	});
}
function showConfigFiles(not_redirect=false) {
	var service = $('#service').val();
	var server_ip = $("#serv").val();
	clearAllAjaxFields();
	$.ajax( {
		url: "/config/" + service + "/show-files",
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
						window.history.pushState("Show config", "Show config", "/config/" + service + "/" + server_ip + "/show-files");
					}
				}
			}
		}
	} );
}
function showConfigFilesForEditing() {
	let service = $('#service').val();
	let server_ip = $("#serv").val();
	let config_file_name = findGetParameter('config_file_name')
	if (service === 'nginx' || service === 'apache') {
		$.ajax({
			url: "/config/" + service + "/" + server_ip + "/edit/" + config_file_name,
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
	let service = $('#service').val();
	let configver = $('#configver').val();
	let serv = $("#serv").val()
	let jsonData = {
		"serv": serv,
		"configver": configver
	}
	$.ajax( {
		url: "/config/" + service + "/show",
		data: JSON.stringify(jsonData),
		contentType: "application/json; charset=utf-8",
		type: "POST",
		success: function( data ) {
			if (data.status === 'failed') {
				toastr.error(data.error);
			} else {
				toastr.clear();
				$("#ajax").html(data.data);
				window.history.pushState("Show config", "Show config", "/config/versions/" + service + "/" + serv + "/" + configver);
				$.getScript(configShow);
			}
		}
	} );
}
function showListOfVersion(for_delver) {
	let cur_url = window.location.href.split('/').pop();
	let service = $('#service').val();
	let serv = $("#serv").val();
	let configver = cur_url;
	clearAllAjaxFields();
	$.ajax( {
		url: "/config/version/" + service + "/list",
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
				window.history.pushState("Show config", "Show config", "/config/versions/" + service + "/" + serv);
			}
		}
	} );
}
function findGetParameter(parameterName) {
    let result = null,
        tmp = [];
    let items = location.search.substr(1).split("&");
    for (let index = 0; index < items.length; index++) {
        tmp = items[index].split("=");
        if (tmp[0] === parameterName) result = decodeURIComponent(tmp[1]);
    }
    return result;
}
function viewLogs() {
	let viewlogs = $('#viewlogs').val();
	if (viewlogs === '------' || viewlogs === null) { return false; }
	if(viewlogs === 'roxy-wi.error.log' || viewlogs === 'roxy-wi.access.log' || viewlogs === 'fail2ban.log') {
		showApacheLog(viewlogs);
	} else {
		let rows = $('#rows').val();
		let grep = $('#grep').val();
		let exgrep = $('#exgrep').val();
		let hour = $('#time_range_out_hour').val();
		let minute = $('#time_range_out_minut').val();
		let hour1 = $('#time_range_out_hour1').val();
		let minute1 = $('#time_range_out_minut1').val();
		let type = findGetParameter('type')
		if (viewlogs == null){
			viewlogs = findGetParameter('viewlogs')
		}
		let url = "/logs/internal/" + viewlogs + "/" + rows;
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
			},
			type: "POST",
			success: function (data) {
				$("#ajax").html(data);
			}
		} );
	}
}
$( function() {
	checkTheme();
	$('a').click(function(e) {
		try {
			var cur_path = window.location.pathname;
			var attr = $(this).attr('href');
			if (cur_path == '/add/haproxy' || cur_path == '/add/nginx' || cur_path == '/admin' || cur_path == '/install' || cur_path == '/runtimeapi') {
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
	$('#auth').submit(function () {
		let next_url = findGetParameter('next');
		let json_data = {
			"login": $('#login').val(),
			"pass": $('#pass').val(),
			"next": next_url
		}
		$.ajax({
			url: "/login",
			data: JSON.stringify(json_data),
			contentType: "application/json; charset=utf-8",
			type: "POST",
			statusCode: {
				401: function (xhr) {
					$('.alert').show();
					if (xhr.responseText.indexOf('disabled') != '-1') {
						$('.alert').html('Your login is disabled')
					} else {
						$('.alert').html('Login or password is incorrect');
						ban();
					}
				}
			},
			success: function (data) {
				if (data.status === 'failed') {
					if (data.error.indexOf('disabled') != '-1') {
						$('.alert').show();
						$('.alert').html(data.error);
					} else {
						$('.alert').show();
						$('.alert').html(data.error);
						ban();
					}
				} else {
					sessionStorage.removeItem('check-service');
					window.location.replace(data.next_url);
				}
			}
		});
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
	let cur_url = window.location.href.split('/').pop();
	cur_url = cur_url.split('#');
	if (cur_url[0].indexOf('install') != '-1') {
		$(".installproxy").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'installproxy');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$(".installmon").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'instalmon');
			});
			$("#tabs").tabs("option", "active", 1);
		});
		$(".installgeo").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'installgeo');
			});
			$("#tabs").tabs("option", "active", 2);
		});
	}
	if (cur_url[0].indexOf('admin') != '-1') {
		$(".users").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'users');
			});
			$("#tabs").tabs("option", "active", 0);
		});
		$(".servers").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'servers');
			});
			$("#tabs").tabs("option", "active", 1);
		});
		$(".ssh").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'ssh');
			});
			$("#tabs").tabs("option", "active", 2);
		});
		$(".settings").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'settings');
			});
			$("#tabs").tabs("option", "active", 3);
			loadSettings();
		});
		$(".backup").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'backup');
			});
			$("#tabs").tabs("option", "active", 4);
			loadBackup();
		});
		$(".groups").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'groups');
			});
			$("#tabs").tabs("option", "active", 5);
		});
		$(".tools").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'tools');
			});
			$("#tabs").tabs("option", "active", 6);
			loadServices();
		});
		$(".updatehapwi").on("click", function () {
			$('.menu li ul li').each(function () {
				activeSubMenu($(this), 'updatehapwi');
			});
			$("#tabs").tabs("option", "active", 7);
			loadupdatehapwi();
		});
	}
	$('.copyToClipboard').hover(function (){
		$.getScript(overview);
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
function activeSubMenu(sub_menu, sub_menu_class) {
	sub_menu.find('a').css('padding-left', '20px');
	sub_menu.find('a').css('border-left', '0px solid var(--right-menu-blue-rolor)');
	sub_menu.find('a').css('background-color', '#48505A');
	sub_menu.children("." + sub_menu_class).css('padding-left', '30px');
	sub_menu.children("." + sub_menu_class).css('border-left', '4px solid var(--color-wanring) !important');
	sub_menu.children("." + sub_menu_class).css('background-color', 'var(--color-gray-dark-alpha) !important');
}
function saveUserSettings(user_id){
	if ($('#disable_alerting').is(':checked')) {
		localStorage.removeItem('disabled_alert');
	} else {
		localStorage.setItem('disabled_alert', '1');
	}
	changeCurrentGroupF(user_id);
	changeTheme($('#theme_select').val());
	Cookies.set('lang', $('#lang_select').val(), { expires: 365, path: '/', secure: 'true' });
}
function sleep(ms) {
	return new Promise(resolve => setTimeout(resolve, ms));
}
function changeTheme(theme) {
	localStorage.setItem('theme', theme);
	if (theme === 'dark') {
		$('#menu-overview').children().attr('src', '/static/images/roxy_icon_white.png');
		$('#menu-haproxy').children().attr('src', '/static/images/HAProxy_icon_white.png');
		$('#menu-nginx').children().attr('src', '/static/images/NGINX_icon_white.png');
		$('#menu-keepalived').children().attr('src', '/static/images/keepalived_icon_white.png');
		$('.menu-logo').attr('src', '/static/images/logo_menu_white.png');
		$('head').append('<link rel="stylesheet" href="/static/css/dark.css" type="text/css" />');
	} else {
		$('link[rel=stylesheet][href~="/static/css/dark.css"]').remove();
	}
}
function checkTheme() {
	let theme = localStorage.getItem('theme');
	changeTheme(theme);
}
function getRandomArbitrary(min, max) {
    return Math.random() * (max - min) + min;
}
async function ban() {
	$('#login').attr('disabled', 'disabled');
	$('#pass').attr('disabled', 'disabled');
	$("input[type=submit], button").button('disable');
	$('#wrong-login').show();
	$('#ban_10').show();
	$('#ban_timer').text(10);

	let i = 10;
	while (i > 0) {
		i--;
		await sleep(1000);
		$('#ban_timer').text(i);
	}

	$('#login').removeAttr('disabled');
	$('#pass').removeAttr('disabled');
	$("input[type=submit], button").button('enable');
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

function changeCurrentGroupF(user_id) {
	$.ajax({
		url: "/user/" + user_id + "/groups/" + $('#newCurrentGroup').val(),
		contentType: "application/json; charset=utf-8",
		type: "PATCH",
		success: function (data) {
			if (data.error === 'failed') {
				toastr.error(data.error);
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
		path: "/static/js/sounds/",
		preload: true
	});
});
let socket = new ReconnectingWebSocket("wss://" + window.location.host, null, {maxReconnectAttempts: 20, reconnectInterval: 3000});

socket.onopen = function(e) {
  console.log("[open] Connection is established with " + window.location.host);
  getAlerts();
};

function getAlerts() {
	socket.send("alert_group " + $('#user_group_socket').val() + " " + $('#user_id_socket').val());
}

socket.onmessage = function(event) {
	var cur_url = window.location.href.split('/').pop();
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
		buttons: [
			{
				text: $('#translate').attr('data-change'),
				click: function () {
					changeUserPasswordItOwn($(this));
				}
			}, {
				text: cancel_word,
				click: function () {
					$(this).dialog("close");
					$('#missmatchpass').hide();
				}
			}
		]
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
			url: "/user/password",
			data: JSON.stringify({'pass': pass}),
			type: "POST",
			contentType: "application/json; charset=utf-8",
			success: function (data) {
				if (data.status === 'failed') {
					toastr.error(data.error);
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
		url: "/config/" + $("#service").val() + "/find-in-config",
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
	let output = data.split('<br>')
	let alerts = [];
	let alert_warning = '';
	let alert_warning2 = '';
	let alert_error = '';
	let second_alert = false;
	alerts.push(output[0] + '\n' + output[1]);
	let server_name = output[0];
	let server_name2 = '';
	try {
		for (let i = 0; i < output.length; i++) {
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
		if (element.indexOf('error: ') != '-1' || element.indexOf('Fatal') != '-1' || element.indexOf('Error') != '-1'
			|| element.indexOf('failed ') != '-1' || element.indexOf('emerg] ') != '-1' || element.indexOf('Syntax error ') != '-1'
			|| element.indexOf('Parsing') != '-1' || element.indexOf('Unknown') != '-1' || element.indexOf('Unexpected') != '-1'
			|| element.indexOf('unknown') != '-1') {
			alert_error = alert_error + element;
			return
		}
		if (element.indexOf('[WARNING]') != '-1' || element.indexOf('[ALER]') != '-1' || element.indexOf('[warn]') != '-1') {
			element = removeEmptyLines(element);
			if (second_alert === false) {
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
		return 1;
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
	return 0;
}
function show_version() {
	NProgress.configure({showSpinner: false});
	$.ajax( {
		url: "/internal/show_version",
		contentType: "application/json; charset=utf-8",
		success: function( data ) {
			if (data.need_update) {
				$('#version').html('<span id="show-updates-button" class="new-version-exists" style="cursor: pointer;">v' + data.current_ver + '</span>');
			} else {
				$('#version').html('v' + data.current_ver);
			}
			let showUpdates = $("#show-updates").dialog({
				autoOpen: false,
				width: 600,
				modal: true,
				title: 'There is a new Roxy-WI version',
				buttons: {
					Close: function () {
						$(this).dialog("close");
						clearTips();
					}
				}
			});
			$('#show-updates-button').click(function () {
				showUpdates.dialog('open');
			});
		}
	} );
	NProgress.configure({showSpinner: true});
}
function statAgriment() {
	var cur_url = window.location.href.split('/').pop();
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
function sendGet(page) {
	let xmlHttp = new XMLHttpRequest();
	let theUrl = 'https://roxy-wi.org/' + page;
	xmlHttp.open("GET", theUrl, true); // true for asynchronous
	xmlHttp.send(null);
}
function show_pretty_ansible_error(data) {
	try {
		data = data.split('error: ');
		let p_err = JSON.parse(data[1]);
		return p_err['msg'];
	} catch (e) {
		return data;
	}
}
function openTab(tabId) {
	$( "#tabs" ).tabs( "option", "active", tabId );
}
function showPassword(input) {
	let x = document.getElementById(input);
	if (x.type === "password") {
		x.type = "text";
	} else {
		x.type = "password";
	}
}
function removeData() {
    for (let i = 0; i < charts.length; i++) {
        let chart = charts[i];
        chart.destroy();
    }
}
function common_ajax_action_after_success(dialog_id, new_group, ajax_append_id, data) {
	toastr.clear();
	$("#"+ajax_append_id).append(data);
	$( "."+new_group ).addClass( "update", 1000);
	$.getScript(awesome);
	clearTips();
	$( dialog_id ).dialog("close" );
	setTimeout(function() {
		$( "."+new_group ).removeClass( "update" );
	}, 2500 );
}
function getAllGroups() {
	let groups = '';
	$.ajax({
		url: "/server/groups",
		contentType: "application/json; charset=utf-8",
		async: false,
		success: function (data) {
			groups = data;
		}
	});
	return groups;
}
function openUserSettings(user_id) {
	if (localStorage.getItem('disabled_alert') === '1') {
		$('#disable_alerting').prop('checked', false).checkboxradio('refresh');
	} else {
		$('#disable_alerting').prop('checked', true).checkboxradio('refresh');
	}
	let theme = 'light';
	if (localStorage.getItem('theme') != null) {
		theme = localStorage.getItem('theme');
	}
	$('#theme_select').val(theme).change();
	$('#theme_select').selectmenu('refresh');
	$.ajax({
		url: "/user/group",
		success: function (data) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax").html(data);
			} else {
				$('#show-user-settings-group').html(data);
				$("select").selectmenu();
			}
		}
	});
	let user_settings_tabel_title = $("#show-user-settings-table").attr('title');
	let change_pass_word = $('#translate').attr('data-change') + ' ' + $('#translate').attr('data-password')
	let showUserSettings = $("#show-user-settings").dialog({
		autoOpen: false,
		width: 600,
		modal: true,
		title: user_settings_tabel_title,
		buttons: [{
			text: save_word,
			click: function () {
				saveUserSettings(user_id);
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
	showUserSettings.dialog('open');
}
function generateSelect(select_id, option_value, option_name, is_selected='') {
	$(select_id).append('<option value="' + option_value + '" '+is_selected+'>' + option_name + '</option>');
}
