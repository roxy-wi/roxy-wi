var url = "/inc/script.js";
var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
var intervalId;

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
		if(Cookies.get('auto-refresh-pause') == "0" && Cookies.get('auto-refresh') > 5000) {
			if (cur_url[0] == "logs.py") {
				showLog();
			} else if (cur_url[0] == "viewsttats.py") {
				showStats()
			} else if (cur_url[0] == "overview.py") {
				showOverview(); 
			} else if (cur_url[0] == "viewlogs.py") {
				viewLogs();
			}  else if (cur_url[0] == "metrics.py") {
				loadMetrics();
			}	 
		} 
	}
};
if(Cookies.get('restart')) {
	var ip = Cookies.get('restart');
	$.ajax( {
		url: "options.py",
		data: {
			act: "checkrestart",
			serv: ip,
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			if(data.indexOf('ok') != '-1') {
				$("#apply").css('display', 'block');
				$("#apply_div").css('width', '850px');
				if (cur_url[0] == "overview.py") {
					$("#apply_div").css('width', '650px');
					$("#apply_div").html("You made changes to the server: "+ip+". Changes will take effect only after<a id='"+ip+"' class='restart' title='Restart HAproxy service'>restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");					
				} else {
					$("#apply_div").html("You made changes to the server: "+ip+". Changes will take effect only after restart. <a href='overview.py' title='Overview'>Go to Overview page and restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
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
	$('.auto-refresh img').remove();
}

function setRefreshInterval(interval) {
	if (interval == "0") {
		Cookies.remove('auto-refresh');
		pauseAutoRefresh();
		$('.auto-refresh').prepend('<img src=/image/pic/update.png alt="restart" class="icon">');
		$('.auto-refresh').css('margin-top', '-3px');
		$('#1').text('Auto-refresh');
		$('#0').text('Auto-refresh');
		$('.auto-refresh-pause').css('display', 'none');
		$('.auto-refresh-resume').css('display', 'none');
		hideAutoRefreshDiv();
	} else {
		clearInterval(intervalId);
		Cookies.set('auto-refresh', interval, { expires: 365 });
		Cookies.set('auto-refresh-pause', "0", { expires: 365 });
		startSetInterval(interval);
		hideAutoRefreshDiv();
		autoRefreshStyle(interval);
	}
}

function startSetInterval(interval) {	
	if(Cookies.get('auto-refresh-pause') == "0") {
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
			intervalId = setInterval('showOverview()', interval);
			showOverview(); 
		} else if (cur_url[0] == "viewlogs.py") {
			intervalId = setInterval('viewLogs()', interval);
			viewLogs();
		} else if (cur_url[0] == "metrics.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('loadMetrics()', interval);
			loadMetrics();
		} 
		else if (cur_url[0] == "waf.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('loadMetrics()', interval);
			showOverviewWaf();
			loadMetrics();
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
		Cookies.set('auto-refresh-pause', "1", { expires: 365 });
	});
}	
function pauseAutoResume(){
	var autoRefresh = Cookies.get('auto-refresh');
	setRefreshInterval(autoRefresh);
	Cookies.set('auto-refresh-pause', "0", { expires: 365 });
}

function hideAutoRefreshDiv() {
	$(function() {
		$('.auto-refresh-div').hide("blind", "fast");
		$('#1').css("display", "none");			
		$('#0').css("display", "inline");
	});
}
$( document ).ajaxSend(function( event, request, settings ) {
	$('#cover').fadeIn('fast');
	NProgress.start();
});
$( document ).ajaxComplete(function( event, request, settings ) {
	$('#cover').fadeOut('fast');
	NProgress.done();
});

function showOverview() {
	showOverviewServers();
	showOverviewWaf()
	$.ajax( {
		url: "options.py",
		data: {
			act: "overview",
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajaxstatus").empty();
			$("#ajaxstatus").html(data);
		}					
	} );
}
function showOverviewWaf() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewwaf",
			page: cur_url[0],
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajaxwafstatus").empty();
			$("#ajaxwafstatus").html(data);
			$.getScript('/inc/overview.js');			
			if (cur_url[0] == "waf.py") {
				$.getScript('/inc/waf.js');
				$( "input[type=submit], button" ).button();
				$( "input[type=checkbox]" ).checkboxradio();
			}
		}					
	} );
}
function showOverviewServers() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewServers",
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajaxservers").html(data);
		}					
	} );
}
function showStats() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "stats",
			serv: $("#serv").val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);			
			window.history.pushState("Stats", "Stats", cur_url[0]+"?serv="+$("#serv").val());
			wait();
		}					
	} );

}
function showLog() {
	var waf = 0;
	if ($('#waf').is(':checked')) {
		waf = '1';
	}
	$.ajax( {
		url: "options.py",
		data: {
			rows: $('#rows').val(),
			serv: $("#serv").val(),
			waf: waf,
			grep: $("#grep").val(),
			hour: $('#time_range_out_hour').val(),
			minut: $('#time_range_out_minut').val(),
			hour1: $('#time_range_out_hour1').val(),
			minut1: $('#time_range_out_minut1').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+$("#serv").val()+"&rows="+$('#rows').val()+"&grep="+$("#grep").val());
		}					
	} );
}
function showMap() {
	$("#ajax").empty();
	$("#ajax-compare").empty();
	$("#config").empty();
	$(".alert-info").empty();
	var unique = $.now();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showMap",
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Show map", "Show map", cur_url[0]);
		}					
	} );
}
function showRuntime() {
	if($('#save').prop('checked')) {
		saveCheck = "on";
	} else {
		saveCheck = "";
	}
	$.ajax( {
		url: "options.py",
		data: {
			servaction: $('#servaction').val(),
			serv: $("#serv").val(),
			servbackend: $("#servbackend").val(),
			save: saveCheck,
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
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
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
		}					
	} );
}
function showCompareConfigs() {
	$("#ajax").empty();
	$("#config").empty();
	$(".alert-info").empty();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showCompareConfigs",
			open: "open",
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax-compare").html(data);
			$( "input[type=submit], button" ).button();
			$( "select" ).selectmenu();
			window.history.pushState("Compare configs", "Compare configs", cur_url[0]);
		}					
	} );
}
function showConfig() {
	$("#ajax").empty();
	$("#ajax-compare").empty();
	$("#config").empty();
	$(".alert-info").empty();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShow",
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			$.getScript('/inc/configshow.js');
			window.history.pushState("Show config", "Show config", cur_url[0]);
		}					
	} );
}
function showUploadConfig() {
	var view = $('#view').val();
	if(view != "1") {
		view = ""
	}
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShow",
			configver: $('#configver').val(),
			token: $('#token').val(),
			view: view 
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			if(view == "1") {
				window.history.pushState("Show config", "Show config", cur_url[0]+"?serv="+$("#serv").val()+"&open=open&configver="+$('#configver').val()+"&view="+$('#view').val());
			} else {
				window.history.pushState("Show config", "Show config", cur_url[0]+"?serv="+$("#serv").val()+"&open=open&configver="+$('#configver').val());
			}
			$.getScript('/inc/configshow.js');
		}					
	} );
}
function viewLogs() {
	if($('#viewlogs').val() == 'haproxy-wi.error.log' || $('#viewlogs').val() == 'haproxy-wi.access.log') {
		showApacheLog($('#viewlogs').val());
	} else {
		$.ajax( {
			url: "options.py",
			data: {
				viewlogs: $('#viewlogs').val(),
				rows2: $('#rows').val(),
				grep: $("#grep").val(),
				hour: $('#time_range_out_hour').val(),
				minut: $('#time_range_out_minut').val(),
				hour1: $('#time_range_out_hour1').val(),
				minut1: $('#time_range_out_minut1').val(),
				token: $('#token').val(),				
			},
			type: "GET",
			success: function( data ) {
				$("#ajax").html(data);
				window.history.pushState("View logs", "View logs", cur_url[0]+"?viewlogs="+$("#viewlogs").val());
			}					
		} );
	}
}
$( function() {
	$( "#serv" ).on('selectmenuchange',function()  {
		$("#show").css("pointer-events", "inherit");
		$("#show").css("cursor", "pointer");
	});
	if ($( "#serv option:selected" ).val() == "Choose server")  {
		$("#show").css("pointer-events", "none");
		$("#show").css("cursor", "not-allowed");
	}
	
	var pause = '<a onclick="pauseAutoRefresh()" title="Pause auto-refresh" class="auto-refresh-pause"></a>'
	var autoRefresh = Cookies.get('auto-refresh');
	
	if ($('.auto-refresh')) {
		if(autoRefresh) {
			startSetInterval(autoRefresh);
			autoRefreshStyle(autoRefresh);
		}
	}
	$("body").mCustomScrollbar({
		theme:"minimal-dark",
		scrollInertia:30
		});
	$(".top-link").mCustomScrollbar({
		theme:"minimal-dark",
		scrollInertia:30
		});	
	$(".diff").mCustomScrollbar({
		theme:"minimal-dark",
		scrollInertia:30
		});	
	$( "#tabs" ).tabs();
	$( "#redirectBackend" ).on( "click", function() {
		$( "#tabs" ).tabs( "option", "active", 2 );
	} );
	$( "select" ).selectmenu();
		
    var tooltips = $( "[title]" ).tooltip();
	$( "input[type=submit], button" ).button();
	$( "input[type=checkbox]" ).checkboxradio();
	$( ".controlgroup" ).controlgroup();
	
    var location = window.location.href;
    var cur_url = '/app/' + location.split('/').pop();
	cur_url = cur_url.split('?');
		
    $('.menu li').each(function () {
        var link = $(this).find('a').attr('href');

        if (cur_url[0] == link)
        {
            $(this).addClass('current');
        }
    });
	var now = new Date(Date.now());
	var date1 = now.getHours() * 60 - 1 * 60;
	var date2 = now.getHours() * 60 + now.getMinutes();
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
			$('#time_range_out_hour').val(hours);
			$('#time_range_out_minut').val(minutes);
			$('#time_range_out_hour1').val(hours1);
			$('#time_range_out_minut1').val(minutes1);
		}
	});
        var date1_hours = Math.floor(date1/60);
        var date2_hours = date1_hours + 1;
		var date2_minute = now.getMinutes()
        if(date1_hours <= 9) date1_hours = '0' + date1_hours;
        if(date2_hours <= 9) date2_hours = '0' + date2_hours;
        if(date2_minute <= 9) date2_minute = '0' + date2_minute;

	$('#time_range_out_hour').val(date1_hours);
	$('#time_range_out_minut').val('00');
	$('#time_range_out_hour1').val(date2_hours);
	$('#time_range_out_minut1').val(date2_minute);
		
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
			
	$('#select_all').click(function(){
        var checkboxes = $(this).closest('form').find(':checkbox');
        if($(this).prop('checked')) {
          $("form input[type='checkbox']").attr("checked",true).change();
		  $("#label_select_all").text("Unselect all");
        } else {
          $("form input[type='checkbox']").attr("checked",false).change();
		  $("#label_select_all").text("Select all");
        }
    });

	$( "#listen-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#listen-mode-select option:selected" ).val() == "tcp") {
			$( "#https-listen-span" ).hide("fast");
			$( "#https-hide-listen" ).hide("fast");
			$("#compression").checkboxradio( "disable" );
			$("#cache").checkboxradio( "disable" );
			$("#ssl_offloading").checkboxradio( "disable" );
			$("#cookie").checkboxradio( "disable" );
			$("#slow_atack").checkboxradio( "disable" );
			$( "#https-listen" ).prop("checked", false);
		} else {
			$( "#https-listen-span" ).show("fast");
			$("#compression").checkboxradio( "enable" );
			$("#cache").checkboxradio( "enable" );
			$("#ssl_offloading").checkboxradio( "enable" );
			$("#cookie").checkboxradio( "enable" );
			$("#slow_atack").checkboxradio( "enable" );
		}
	});
	$( "#frontend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#frontend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-frontend-span" ).hide("fast");
			$( "#https-hide-frontend" ).hide("fast");
			$("#compression2").checkboxradio( "disable" );
			$("#cache2").checkboxradio( "disable" );
			$("#ssl_offloading2").checkboxradio( "disable" );
			$("#cookie2").checkboxradio( "disable" );
			$("#slow_atack1").checkboxradio( "disable" );
		} else {
			$( "#https-frontend-span" ).show("fast");
			$("#compression2").checkboxradio( "enable" );
			$("#cache2").checkboxradio( "enable" );
			$("#ssl_offloading2").checkboxradio( "enable" );
			$("#cookie2").checkboxradio( "enable" );
			$("#slow_atack1").checkboxradio( "enable" );
		}
	});
	$( "#backend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#backend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-backend-span" ).hide("fast");
			$( "#https-hide-backend" ).hide("fast");
			$("#compression3").checkboxradio( "disable" );
			$("#cache3").checkboxradio( "disable" );
			$("#ssl_offloading3").checkboxradio( "disable" );
			$("#cookie3").checkboxradio( "disable" );
			$("#slow_atack2").checkboxradio( "disable" );
		} else {
			$( "#https-backend-span" ).show("fast");
			$("#compression3").checkboxradio( "enable" );
			$("#cache3").checkboxradio( "enable" );
			$("#ssl_offloading3").checkboxradio( "enable" );
			$("#cookie3").checkboxradio( "enable" );
			$("#slow_atack2").checkboxradio( "enable" );
		}
	});
	$( "#https-listen" ).click( function(){
		if ($('#https-listen').is(':checked')) {
			$( "#https-hide-listen" ).show( "fast" );
			$( "#path-cert-listen" ).attr('required',true);
		} else {
			$( "#https-hide-listen" ).hide( "fast" );
			$( "#path-cert-listen" ).prop('required',false);
		}
	});	
	$( "#https-frontend" ).click( function(){
		if ($('#https-frontend').is(':checked')) {
			$( "#https-hide-frontend" ).show( "fast" );
			$( "#path-cert-frontend" ).attr('required',true);
		} else {
			$( "#https-hide-frontend" ).hide( "fast" );
			$( "#path-cert-frontend" ).prop('required',false);
		}
	});	
	$( "#https-backend" ).click( function(){
		if ($('#https-backend').is(':checked')) {
			$( "#https-hide-backend" ).show( "fast" );
		} else {
			$( "#https-hide-backend" ).hide( "fast" );
		}
	});	
	$( "#options-listen-show" ).click( function(){
		if ($('#options-listen-show').is(':checked')) {
			$( "#options-listen-show-div" ).show( "fast" );
		} else {
			$( "#options-listen-show-div" ).hide( "fast" );
		}
	});	
	$( "#options-frontend-show" ).click( function(){
		if ($('#options-frontend-show').is(':checked')) {
			$( "#options-frontend-show-div" ).show( "fast" );
		} else {
			$( "#options-frontend-show-div" ).hide( "fast" );
		}
	});	
	$( "#options-backend-show" ).click( function(){
		if ($('#options-backend-show').is(':checked')) {
			$( "#options-backend-show-div" ).show( "fast" );
		} else {
			$( "#options-backend-show-div" ).hide( "fast" );
		}
	});	
	$( "#controlgroup-listen-show" ).click( function(){
		if ($('#controlgroup-listen-show').is(':checked')) {
			$( "#controlgroup-listen" ).show( "fast" );
			if ($('#check-servers-listen').is(':checked')) {
				$( "#rise-listen" ).attr('required',true);
				$( "#fall-listen" ).attr('required',true);
				$( "#inter-listen" ).attr('required',true);
				$( "#inter-listen" ).attr('disable',false);				
			}				
		} else {
			$( "#controlgroup-listen" ).hide( "fast" );			
		}
	$( "#check-servers-listen" ).click( function(){
		if ($('#check-servers-listen').is(':checked')) {
			$( "#rise-listen" ).attr('required',true);
			$( "#fall-listen" ).attr('required',true);
			$( "#inter-listen" ).attr('required',true);
			$( "#inter-listen" ).selectmenu( "option", "disabled", false );
			$( "#fall-listen" ).selectmenu( "option", "disabled", false );
			$( "#rise-listen" ).selectmenu( "option", "disabled", false );
		} else {
			$( "#rise-listen" ).attr('required',false);
			$( "#fall-listen" ).attr('required',false);
			$( "#inter-listen" ).attr('required',false);
			$( "#inter-listen" ).selectmenu( "option", "disabled", true );
			$( "#fall-listen" ).selectmenu( "option", "disabled", true );
			$( "#rise-listen" ).selectmenu( "option", "disabled", true );
		}
	});
	
	});
	$( "#controlgroup-backend-show" ).click( function(){
		if ($('#controlgroup-backend-show').is(':checked')) {
			$( "#controlgroup-backend" ).show( "fast" );
			if ($('#check-servers-backend').is(':checked')) {
				$( "#rise-backend" ).attr('required',true);
				$( "#fall-backend" ).attr('required',true);
				$( "#inter-backend" ).attr('required',true);
			}
		} else {
			$( "#controlgroup-backend" ).hide( "fast" );			
		}
	});
	$( "#cookie" ).click( function(){
		if ($('#cookie').is(':checked')) {
			$("#cookie_name" ).attr('required',true);
			$("#cookie_div").show( "fast" );
		} else {
			$("#cookie_name" ).attr('required',false);
			$("#cookie_div").hide( "fast" );
			$("#dynamic-cookie-key" ).attr('required',false);
		}
	});
	$( "#cookie2" ).click( function(){
		if ($('#cookie2').is(':checked')) {
			$("#cookie_name2" ).attr('required',true);
			$("#cookie_div2").show( "fast" );
		} else {
			$("#cookie_name2" ).attr('required',false);
			$("#cookie_div2").hide( "fast" );
			$("#dynamic-cookie-key2" ).attr('required',false);
		}
	});
	$( "#rewrite" ).on('selectmenuchange',function()  {
		if ($( "#rewrite option:selected" ).val() == "insert" || $( "#rewrite option:selected" ).val() == "rewrite") {
			$( "#prefix" ).checkboxradio( "disable" );
		} else {
			$( "#prefix" ).checkboxradio( "enable" );
		}
	});
	$( "#rewrite2" ).on('selectmenuchange',function()  {
		if ($( "#rewrite2 option:selected" ).val() == "insert" || $( "#rewrite2 option:selected" ).val() == "rewrite") {
			$( "#prefix2" ).checkboxradio( "disable" );
		} else {
			$( "#prefix2" ).checkboxradio( "enable" );
		}
	});
	$( "#dynamic" ).click( function(){
		if ($('#dynamic').is(':checked')) {
			$("#dynamic-cookie-key" ).attr('required',true);
			$("#dynamic_div").show("slide", "fast" );
		} else {
			$("#dynamic-cookie-key" ).attr('required',false);
			$("#dynamic_div").hide("slide", "fast" );
		}
	});
	$( "#dynamic2" ).click( function(){
		if ($('#dynamic2').is(':checked')) {
			$("#dynamic-cookie-key2" ).attr('required',true);
			$("#dynamic_div2").show("slide", "fast" );
		} else {
			$("#dynamic-cookie-key2" ).attr('required',false);
			$("#dynamic_div2").hide("slide", "fast" );
		}
	});
	$( "#check-servers-backend" ).click( function(){
		if ($('#check-servers-backend').is(':checked')) {
			$( "#rise-backend" ).attr('required',true);
			$( "#fall-backend" ).attr('required',true);
			$( "#inter-backend" ).attr('required',true);
			$( "#inter-backend" ).selectmenu( "option", "disabled", false );
			$( "#fall-backend" ).selectmenu( "option", "disabled", false );
			$( "#rise-backend" ).selectmenu( "option", "disabled", false );
		} else {
			$( "#rise-backend" ).attr('required',false);
			$( "#fall-backend" ).attr('required',false);
			$( "#inter-backend" ).attr('required',false);
			$( "#inter-backend" ).selectmenu( "option", "disabled", true );
			$( "#fall-backend" ).selectmenu( "option", "disabled", true );
			$( "#rise-backend" ).selectmenu( "option", "disabled", true );
		}
	});
	$( "#hide_menu" ).click(function() {
		$(".top-menu").hide( "drop", "fast" );
		$(".container").css("max-width", "98%");
		$(".container").css("margin-left", "1%");
		$(".show_menu").show();
		Cookies.set('hide_menu', 'hide', { expires: 365 });
	});
	$( "#show_menu" ).click(function() {
		$(".top-menu").show( "drop", "fast" );
		$(".container").css("max-width", "91%");
		$(".container").css("margin-left", "207px");
		$(".show_menu").hide();
		Cookies.set('hide_menu', 'show', { expires: 365 });
	});
	
	var hideMenu = Cookies.get('hide_menu');
	if (hideMenu == "show") {
		$(".top-menu").show( "drop", "fast" );
		$(".container").css("max-width", "91%");
		$(".container").css("margin-left", "207px");
	}
	if (hideMenu == "hide") {
		$(".top-menu").hide();
		$(".container").css("max-width", "98%");
		$(".container").css("margin-left", "1%");
		$(".show_menu").show();
	}	
	
	var availableTags = [
		"acl", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "set cookie", "dynamic-cookie-key", "mysql-check", "tcpka", "tcplog", "forwardfor", "option"
	];
			
	$( "#ip" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					ip: request.term,
					serv: $("#serv").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));				
				}					
			} );
		},
		autoFocus: true,
		minLength: -1,
		select: function( event, ui ) {
			$('#listen-port').focus();				
		}
	});
	$( "#ip1" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					ip: request.term,
					serv: $("#serv2").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
					}					
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#backends" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					backend: request.term,
					serv: $("#serv2").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					response(data.split('<br>'));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#blacklist-hide-input" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "black",
					group: $("#group").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#blacklist-hide-input1" ).autocomplete({
		source: function( request, response ) {
			if ( request.term == "" ) {
				request.term = 1
			}
			$.ajax( {
				url: "options.py",
				data: {
					get_lists: request.term,
					color: "black",
					group: $("#group").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#options" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput").append(ui.item.value + " ");
			$("#options").empty();
		}
	});
	$( "#options1" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput1").append(ui.item.value + " ");				
		}
	});
	$( "#options2" ).autocomplete({
		source: availableTags,
		autoFocus: true,
	    minLength: -1,
		select: function( event, ui ) {
			$("#optionsInput2").append(ui.item.value + " ")
		}
	});
	
	var ssl_offloading_var = "http-request set-header X-Forwarded-Port %[dst_port] \n"+
						"http-request add-header X-Forwarded-Proto https if { ssl_fc } \n"+
						"redirect scheme https if !{ ssl_fc } \n"
	$('#ssl_offloading').click(function() {
		if($('#optionsInput').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput", ssl_offloading_var);
		}
	});
	$('#ssl_offloading1').click(function() {
		if($('#optionsInput1').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput1").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput1", ssl_offloading_var);
		}

	});
	$('#ssl_offloading2').click(function() {
		if($('#optionsInput2').val().indexOf('ssl_fc ') == '-1') {
			$("#optionsInput2").append(ssl_offloading_var)
		} else {
			replace_text("#optionsInput2", ssl_offloading_var);
		}
	});
	var forward_for_var = "option forwardfor if-none\n";
	$('#forward_for').click(function() {
		if($('#optionsInput').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput").append(forward_for_var)
		} else {
			replace_text("#optionsInput", forward_for_var);
		}	
	});
	$('#forward_for1').click(function() {
		if($('#optionsInput1').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput1").append(forward_for_var)
		} else {
			replace_text("#optionsInput1", forward_for_var);
		}	
	});
	$('#forward_for2').click(function() {
		if($('#optionsInput2').val().indexOf(forward_for_var) == '-1') {
			$("#optionsInput2").append(forward_for_var)
		} else {
			replace_text("#optionsInput2", forward_for_var);
		}	
	});
	var redispatch_var = "option redispatch\n";
	$('#redispatch').click(function() {
		if($('#optionsInput').val().indexOf(redispatch_var) == '-1') {
			$("#optionsInput").append(redispatch_var)
		} else {
			replace_text("#optionsInput", redispatch_var);
		}	
	});
	$('#redispatch2').click(function() {
		if($('#optionsInput2').val().indexOf(redispatch_var) == '-1') {
			$("#optionsInput2").append(redispatch_var)
		} else {
			replace_text("#optionsInput2", redispatch_var);
		}	
	});
	var slow_atack = "option http-buffer-request\ntimeout http-request 10s\n"
	$('#slow_atack').click(function() {
		if($('#optionsInput').val().indexOf(slow_atack) == '-1') {
			$("#optionsInput").append(slow_atack)
		} else {
			replace_text("#optionsInput", slow_atack);
		}	
	});
	$('#slow_atack1').click(function() {
		if($('#optionsInput1').val().indexOf(slow_atack) == '-1') {
			$("#optionsInput1").append(slow_atack)
		} else {
			replace_text("#optionsInput1", slow_atack);
		}	
	});
	$("#ddos").checkboxradio( "disable" );
	$("#ddos1").checkboxradio( "disable" );
	$("#ddos2").checkboxradio( "disable" );
	$( "#name" ).change(function() {
		table_name = $('#name').val();
		table_name = $.trim(table_name)
		if($('#name').val() != "") {
			$("#ddos").checkboxradio( "enable" );
		} else {
			$("#ddos").checkboxradio( "disable" );
		}
	});
	$( "#new_frontend" ).change(function() {
		table_name = $('#new_frontend').val();
		table_name = $.trim(table_name)
		if($('#new_frontend').val() != "") {
			$("#ddos1").checkboxradio( "enable" );
		} else {
			$("#ddos1").checkboxradio( "disable" );
		}
	});
	
	$('#ddos').click(function() {
		if($('#name').val() == "") {
			$("#optionsInput").append(ddos_var)
		}
		var ddos_var = "#Start config for DDOS atack protecte\n"+
								  "stick-table type ip size 1m expire 1m store gpc0,http_req_rate(10s),http_err_rate(10s)\n"+
								  "tcp-request connection track-sc1 src\n"+
								  "tcp-request connection reject if { sc1_get_gpc0 gt 0 }\n"+
								  "# Abuser means more than 100reqs/10s\n"+
								  "acl abuse sc1_http_req_rate("+table_name+") ge 100\n"+
								  "acl flag_abuser sc1_inc_gpc0("+table_name+")\n"+
								  "tcp-request content reject if abuse flag_abuser\n"+
								  "#End config for DDOS\n";
		if($('#optionsInput').val().indexOf(ddos_var) == '-1') {			
			if($('#name').val() == "") {
				alert("First set Listen name")
			} else {
				$("#optionsInput").append(ddos_var);
			}
		} else {
			replace_text("#optionsInput", ddos_var);
		}	
	});
	$('#ddos1').click(function() {
		if($('#new_frontend').val() == "") {
			$("#optionsInput1").append(ddos_var)
		}
		var ddos_var = "#Start config for DDOS atack protecte\n"+
								  "stick-table type ip size 1m expire 1m store gpc0,http_req_rate(10s),http_err_rate(10s)\n"+
								  "tcp-request connection track-sc1 src\n"+
								  "tcp-request connection reject if { sc1_get_gpc0 gt 0 }\n"+
								  "# Abuser means more than 100reqs/10s\n"+
								  "acl abuse sc1_http_req_rate("+table_name+") ge 100\n"+
								  "acl flag_abuser sc1_inc_gpc0("+table_name+")\n"+
								  "tcp-request content reject if abuse flag_abuser\n"+
								  "#End config for DDOS\n";
		if($('#optionsInput1').val().indexOf(ddos_var) == '-1') {
			if($('#new_frontend').val() == "") {
				alert("First set Frontend name")
			} else {
				$("#optionsInput1").append(ddos_var)
			}
		} else {
			replace_text("#optionsInput1", ddos_var);
		}	
	});

	$( "#blacklist_checkbox" ).click( function(){
		if ($('#blacklist_checkbox').is(':checked')) {
			$( "#blacklist-hide" ).show( "fast" );
			$( "#blacklist-hide-input" ).attr('required',true);
		} else {
			$( "#blacklist-hide" ).hide( "fast" );
			$( "#blacklist-hide-input" ).prop('required',false);
		}
	});
	$( "#blacklist_checkbox1" ).click( function(){
		if ($('#blacklist_checkbox1').is(':checked')) {
			$( "#blacklist-hide1" ).show( "fast" );
			$( "#blacklist-hide-input1" ).attr('required',true);
		} else {
			$( "#blacklist-hide1" ).hide( "fast" );
			$( "#blacklist-hide-input1" ).prop('required',false);
		}
	});
	cur_url = cur_url[0].split('#');
	if (cur_url[0] == "/app/add.py") {
		$("#cache").checkboxradio( "disable" );
		$("#waf").checkboxradio( "disable" );
		$( "#serv" ).on('selectmenuchange',function() {
			change_select_acceleration("");
			change_select_waf("");
		});
		
		$("#cache2").checkboxradio( "disable" );
		$("#waf2").checkboxradio( "disable" );
		$( "#serv2" ).on('selectmenuchange',function() {
			change_select_acceleration("2");
			change_select_waf("2");
		});
			
		$("#cache3").checkboxradio( "disable" );
		$( "#serv3" ).on('selectmenuchange',function() {
			change_select_acceleration("3");
		});
		$( "#add1" ).on( "click", function() {
			 $('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 0 );
		} );
		$( "#add2" ).on( "click", function() {
			 $('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 1 );
		} );
		$( "#add3" ).on( "click", function() {
			 $('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 2 );
		} );
		$( "#add4" ).on( "click", function() {
			 $('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 3 );
		} );
	}
	if (cur_url[0] == "/app/users.py" || cur_url[0] == "/app/servers.py") {
		$( ".users" ).on( "click", function() {
			 $('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 0 );
		} );
		if (cur_url[0] == "/app/users.py") {
			$( ".group" ).on( "click", function() {
				$('.menu li').each(function () {
				$(this).removeClass('current');
			});
				$(this).parent().addClass('current');
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );
		} else {
			$( ".runtime" ).on( "click", function() {
				$('.menu li').each(function () {
				$(this).removeClass('current');
			});
				$(this).parent().addClass('current');
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );
		}
		if (cur_url[0] == "/app/servers.py") {
			$( ".admin" ).on( "click", function() {
				$('.menu li').each(function () {
				$(this).removeClass('current');
			});
				$(this).parent().addClass('current');
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );
		}
		if (cur_url[0] == "/app/users.py") {
			$( ".runtime" ).on( "click", function() {
				$('.menu li').each(function () {
				$(this).removeClass('current');
			});
				$(this).parent().addClass('current');
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );
		}
		$( ".role" ).on( "click", function() {
			$('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 3 );
		} );
		$( ".admin" ).on( "click", function() {
			$('.menu li').each(function () {
				$(this).removeClass('current');
			});
			$(this).parent().addClass('current');
			$( "#tabs" ).tabs( "option", "active", 4 );
		} );
	}
	$( "#path-cert-listen" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					getcerts:1,
					serv: $("#serv").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#path-cert-frontend" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					getcerts:1,
					serv: $("#serv2").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#interface" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#master").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#interface-add" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					showif:1,
					serv: $("#master-add").val(),
					token: $('#token').val()
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					response(data.split(" "));
				}						
			} );
		},
		autoFocus: true,
		minLength: -1
	});
	$( "#ssl_key_upload" ).click(function() {
		$('.alert-danger').remove();
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#serv4').val(),
				ssl_cert: $('#ssl_cert').val(),
				ssl_name: $('#ssl_name').val(),
				token: $('#token').val()
			},
			type: "GET",
			success: function( data ) {
				data = data.replace(/\s+/g,' ');
				if (data.indexOf('danger') != '-1') {
					$("#ajax-ssl").html(data);
				} else if (data.indexOf('success') != '-1') {
					$('.alert-danger').remove();
					$( "#ajax-ssl").html(data);
					setTimeout(function() {
						$( "#ajax-ssl").html("");
					}, 2500 );
				} else {
					$("#ajax-ssl").html('<div class="alert alert-danger">Something wrong, check and try again</div>');
				}
			}
		} );
	});
	$('#ssl_key_view').click(function() {
		$.ajax( {
			url: "options.py",
			data: {
				serv: $('#serv5').val(),
				getcerts: "viewcert",
				token: $('#token').val()
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('danger') != '-1') {
					$("#ajax-show-ssl").html(data);
				} else {
					$('.alert-danger').remove();
					var i;
					var new_data = "";
					data = data.split("\n");
					
					for (i = 0; i < data.length; i++) {
						
						new_data += ' <a onclick="view_ssl(\''+data[i]+'\')" style="cursor: pointer;" title="View this cert">'+data[i]+'</a> '
					}
					$("#ajax-show-ssl").html("<b>"+new_data+"</b>");					
				} 
			}
		} );
	});
	var add_server_var = '<br /><input name="servers" title="Backend port" size=14 placeholder="xxx.xxx.xxx.xxx" class="form-control">: <input name="server_port" title="Backend port" size=1 placeholder="yyy" class="form-control">'
	$('#add-server-input').click(function() {
		$('#servers').append(add_server_var);		
	});
	$('#add-server-input2').click(function() {
		$('#servers2').append(add_server_var);		
	});
	$('.advance-show').click(function() {
		$('.advance-show').fadeOut();
		$('.advance').fadeIn();
	});
	$('#auth').submit(function() {
		$('.alert-danger').remove();
		let searchParams = new URLSearchParams(window.location.search)
		if(searchParams.has('ref')) {
			var ref = searchParams.get('ref');
		} else {
			var ref = "overview.py";
		}
		$.ajax( {
			url: "login.py",
			data: {
				login: $('#login').val(),
				pass: $('#pass').val()
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('ok') != '-1') {
					$( "#dialog-confirm" ).dialog({
						resizable: false,
						height: "auto",
						width: 400,
						modal: true,
						title: "Support the project!",
						buttons: {
						"Ok": function() {
								window.location.replace(ref);
							}
						  }
					});
				} else {
					$('.alert-danger').remove();
					$("#ajax").html(data);					
				} 
			}
		} );
		return false;
	});
});
function change_select_acceleration(id) {
	$.ajax( {
		url: "options.py",
		data: {
			get_hap_v: 1,
			serv: $('#serv'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {	
			console.log(data)
			if(parseFloat(data) < parseFloat('1.8')) {	
				$("#cache"+id).checkboxradio( "disable" );
			} else {
				$("#cache"+id).checkboxradio( "enable" );
			}
		}
	} );
}
function change_select_waf(id) {
	$.ajax( {
		url: "options.py",
		data: {
			get_hap_v: 1,
			serv: $('#serv'+id+' option:selected').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {	
			console.log(data)
			if(parseFloat(data) < parseFloat('1.8')) {	
				$("#waf"+id).checkboxradio( "disable" );
			} else {
				$("#waf"+id).checkboxradio( "enable" );
			}
		}
	} );
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

function view_ssl(id) {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $('#serv5').val(),
			getcert: id,
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax-show-ssl").html(data);
			} else {
				$('.alert-danger').remove();
				$('#dialog-confirm-body').text(data);
				$( "#dialog-confirm" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Certificate from "+$('#serv5').val()+", name: "+id,
					buttons: {
						Ok: function() {
							$( this ).dialog( "close" );
						}
					  }
				});					
			} 
		}
	} );
}

function createList(color) {
	if(color == 'white') {
		list = $('#new_whitelist_name').val() 
	} else {
		list = $('#new_blacklist_name').val()
	}
	$.ajax( {
		url: "options.py",
		data: {
			bwlists_create: list,
			color: color,
			group: $('#group').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data); 
			setTimeout(function() {
						location.reload();
					}, 2500 );			 
		}
	} );	
}
function editList(list, color) {
	$.ajax( {
		url: "options.py",
		data: {
			bwlists: list,
			color: color,
			group: $('#group').val(),
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			if (data.indexOf('danger') != '-1') {
				$("#ajax").html(data);
			} else {
				$('.alert-danger').remove();
				$('#edit_lists').text(data);
				$( "#dialog-confirm" ).dialog({
					resizable: false,
					height: "auto",
					width: 650,
					modal: true,
					title: "Edit "+color+" list "+list,
					buttons: {
						"Just save": function() {
							$( this ).dialog( "close" );	
							saveList('save', list, color);
						},
						"Save and restart": function() {
							$( this ).dialog( "close" );	
							saveList('restart', list, color);
						},
						Cancel: function() {
							$( this ).dialog( "close" );
						}
					  }
				});					
			} 
		}
	} );	
}
function saveList(action, list, color) {
	$.ajax( {
		url: "options.py",
		data: {
			bwlists_save: list,
			bwlists_content: $('#edit_lists').val(),
			color: color,
			group: $('#group').val(),
			bwlists_restart: action,
			token: $('#token').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data); 
		}
	} );	
}