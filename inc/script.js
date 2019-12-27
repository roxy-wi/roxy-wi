var url = "/inc/script.js";
var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
var intervalId;

$( function() {		
   $('.menu li ul li').each(function () {
       var link = $(this).find('a').attr('href');
	   var link2 = link.split('/')[2]
       if (cur_url[0] == link2) {
           $(this).parent().css('display', 'contents');
           $(this).parent().css('font-size', '13px');
           $(this).parent().css('top', '0');
           $(this).parent().css('left', '0');
           $(this).parent().children().css('margin-left', '-20px');
		   $(this).parent().find('a').css('padding-left', '20px');
		   $(this).find('a').css('padding-left', '30px');
		   $(this).find('a').css('border-left', '4px solid #5D9CEB');
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
				showMetrics();
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
		type: "POST",
		success: function( data ) {
			if(data.indexOf('ok') != '-1') {
				$("#apply").css('display', 'block');
				$("#apply_div").css('width', '850px');
				if (cur_url[0] == "hapservers.py") {
					$("#apply_div").css('width', '650px');
					$("#apply_div").html("You made changes to the server: "+ip+". Changes will take effect only after<a id='"+ip+"' class='restart' title='Restart HAproxy service' onclick=\"confirmAjaxAction('stop', 'hap', '"+ip+"')\">restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");					
				} else {
					$("#apply_div").html("You made changes to the server: "+ip+". Changes will take effect only after restart. <a href='hapservers.py' title='Overview'>Go to the HAProxy Overview page and restart</a><a href='#' title='close' id='apply_close' style='float: right'><b>X</b></a>");
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
		$('.auto-refresh').prepend('<img src=/inc/images/update.png alt="restart" class="icon">');
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
			intervalId = setInterval('showOverviewWaf()', interval);
			showOverviewWaf();
			showWafMetrics();
		} else if (cur_url[0] == "hapservers.py") {
			if(interval < 60000) {
				interval = 60000;
			}
			intervalId = setInterval('showMetrics()', interval);
			showMetrics();
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
function showOverviewWaf() {
	if (cur_url[0] == "waf.py") {
		$.getScript('/inc/chart.min.js');
		showWafMetrics()
	}
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewwaf",
			page: cur_url[0],
			token: $('#token').val()
		},
		beforeSend: function() {
			if (cur_url[0] == "waf.py") {
				var load_class = 'loading_full_page'
			} else {
				var load_class = 'loading'
			}
			$('#ajaxwafstatus').html('<img class="'+load_class+'" src="/inc/images/loading.gif" />')
		},
		type: "POST",
		success: function( data ) {
			$("#ajaxwafstatus").empty();
			$("#ajaxwafstatus").html(data);
			$.getScript('/inc/overview.js');			
			if (cur_url[0] == "waf.py") {
				$.getScript('/inc/waf.js');
				$( "input[type=submit], button" ).button();
				$( "input[type=checkbox]" ).checkboxradio();
			} else {
				$('.first-collumn-wi').css('padding', '10px');
			}
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
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);			
			window.history.pushState("Stats", "Stats", cur_url[0]+"?serv="+$("#serv").val());
			wait();
		}					
	} );
}
function openStats() {
	var serv = $("#serv").val();
	var url = "viewsttats.py?serv="+serv
	var win = window.open(url, '_blank');
	win.focus();
}
function openVersions() {
	var serv = $("#serv").val();
	var url = "versions.py?serv="+serv+"&open=open"
	var win = window.open(url,"_self");
	win.focus();
}
function showLog() {
	var waf = 0;
	if ($('#waf').is(':checked')) {
		waf = '1';
	}
	var rows = $('#rows').val()
	var grep = $('#grep').val()
	var hour = $('#time_range_out_hour').val()
	var minut = $('#time_range_out_minut').val()
	var hour1 = $('#time_range_out_hour1').val()
	var minut1 = $('#time_range_out_minut1').val()
	$.ajax( {
		url: "options.py",
		data: {
			rows: rows,
			serv: $("#serv").val(),
			waf: waf,
			grep: grep,
			hour: hour,
			minut: minut,
			hour1: hour1,
			minut1: minut1,
			token: $('#token').val()
		},
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+$("#serv").val()+
																	'&rows='+rows+
																	'&grep='+grep+
																	'&hour='+hour+
																	'&minut='+minut+
																	'&hour1='+hour1+
																	'&minut1='+minut1+
																	'&waf='+waf);
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
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Show map", "Show map", cur_url[0]+'?serv='+$("#serv").val()+'&showMap');
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
		type: "POST",
		success: function( data ) {
			$("#ajaxruntime").html(data);
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
		type: "POST",
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
		type: "POST",
		success: function( data ) {
			$("#ajax-compare").html(data);
			$( "input[type=submit], button" ).button();
			$( "select" ).selectmenu();
			window.history.pushState("Show compare config", "Show compare config", cur_url[0]+'?serv='+$("#serv").val()+'&showCompare');
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
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data);
			$.getScript('/inc/configshow.js');
			window.history.pushState("Show config", "Show config", cur_url[0]+'?serv='+$("#serv").val()+'&showConfig');
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
		type: "POST",
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
		var rows = $('#rows').val()
		var grep = $('#grep').val()
		var hour = $('#time_range_out_hour').val()
		var minut = $('#time_range_out_minut').val()
		var hour1 = $('#time_range_out_hour1').val()
		var minut1 = $('#time_range_out_minut1').val()
		$.ajax( {
			url: "options.py",
			data: {
				viewlogs: $('#viewlogs').val(),
				rows: rows,
				grep: grep,
				hour: hour,
				minut: minut,
				hour1: hour1,
				minut1: minut1,
				token: $('#token').val(),				
			},
			type: "POST",
			success: function( data ) {
				$("#ajax").html(data);
				window.history.pushState("View logs", "View logs", cur_url[0]+"?viewlogs="+$("#viewlogs").val()+
																	'&rows='+rows+
																	'&grep='+grep+
																	'&hour='+hour+
																	'&minut='+minut+
																	'&hour1='+hour1+
																	'&minut1='+minut1);
			}					
		} );
	}
}
$( function() {
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
	var autoRefresh = Cookies.get('auto-refresh');
	
	if ($('.auto-refresh')) {
		if(autoRefresh) {
			startSetInterval(autoRefresh);
			autoRefreshStyle(autoRefresh);
		}
	}
	$( "#tabs" ).tabs();
	$( "select" ).selectmenu();
		
    // var tooltips = $( "[title]" ).tooltip();
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
		Cookies.set('hide_menu', 'hide', { expires: 365 });
	});
	$( "#show_menu" ).click(function() {
		$(".top-menu").show( "drop", "fast" );
		$(".container").css("max-width", "100%");
		$(".footer").css("max-width", "100%");
		$(".container").css("margin-left", "207px");
		$(".footer").css("margin-left", "207px");
		$(".show_menu").hide();
		$("#hide_menu").show();
		Cookies.set('hide_menu', 'show', { expires: 365 });
	});
	
	var hideMenu = Cookies.get('hide_menu');
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
		var date1 = now.getHours() * 60 - 1 * 60;
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

	 $('#runtimeapiform').submit(function() {
		showRuntime();
		return false;
	}); 
	$('#auth').submit(function() {

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
			type: "POST",
			success: function( data ) {
				if (data.indexOf('ok') != '-1') {
					window.location.replace(ref);
				} else if (data.indexOf('ban') != '-1') {
					ban();				
				} 
			}
		} );
		return false;
	});
	var showUpdates = $( "#show-updates" ).dialog({
			autoOpen: false,
			resizable: false,
			height: "auto",
			width: 600,
			modal: true,
			title: 'There is a new version HAProxy-WI.',
			show: {
				effect: "fade",
				duration: 200
			},
			hide: {
				effect: "fade",
				duration: 200
			},
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
	var location = window.location.href;
    var cur_url = '/app/' + location.split('/').pop();
	cur_url = cur_url.split('?');
	cur_url = cur_url[0].split('#');
	if (cur_url[0] == "/app/users.py" || cur_url[0] == "/app/servers.py") {
		$( ".users" ).on( "click", function() {
			$('.menu li ul li').each(function () {
				$(this).find('a').css('padding-left', '20px')
				$(this).find('a').css('border-left', '0px solid #5D9CEB');
				$(this).children(".users").css('padding-left', '30px');
				$(this).children(".users").css('border-left', '4px solid #5D9CEB');
			});
			$( "#tabs" ).tabs( "option", "active", 0 );
		} );
		if (cur_url[0] == "/app/users.py") {
			$( ".group" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).children(".group").css('padding-left', '30px');
					$(this).children(".group").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );
			$( ".runtime" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );
			$( ".admin" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 3 );
			} );
			$( ".settings" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".settings").css('padding-left', '30px');
					$(this).children(".settings").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 5 );
			} );
			$( ".updatehapwi" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".updatehapwi").css('padding-left', '30px');
					$(this).children(".updatehapwi").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 6 );
			} );
		} else {
			$( ".runtime" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).children(".runtime").css('padding-left', '30px');
					$(this).children(".runtime").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 1 );
			} );					
			$( ".admin" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).find('a').css('padding-left', '20px')
					$(this).children(".admin").css('padding-left', '30px');
					$(this).children(".admin").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 2 );
			} );			
			$( ".hap" ).on( "click", function() {
				$('.menu li ul li').each(function () {
					$(this).find('a').css('padding-left', '20px')
					$(this).find('a').css('border-left', '0px solid #5D9CEB');
					$(this).children(".hap").css('padding-left', '30px');
					$(this).children(".hap").css('border-left', '4px solid #5D9CEB');
				});
				$( "#tabs" ).tabs( "option", "active", 4 );
			} );
		}
	}
	$( "#haproxyaddserv" ).on('selectmenuchange',function() {
		$.ajax( {
			url: "options.py",
			data: {
				get_hap_v: 1,
				serv: $('#haproxyaddserv option:selected').val(),
				token: $('#token').val()
			},
			type: "POST",
			success: function( data ) {	
				data = data.replace(/^\s+|\s+$/g,'');
				if(data != '') {				
					data = data+'-1';
					$('#cur_hap_ver').text(data);
					$('#install').text('Update');
					$('#install').attr('title', 'Update HAProxy');
					$('#syn_flood').checkboxradio('disable');
					$('#syn_flood').prop( "checked", false );
					$('#syn_flood').checkboxradio('refresh');
				} else {
					$('#cur_hap_ver').text('HAProxy has not installed');
					$('#install').text('Install');
					$('#install').attr('title', 'Install HAProxy');
					$('#syn_flood').checkboxradio('enable');
					$('#syn_flood').prop( "checked", true );
					$('#syn_flood').checkboxradio('refresh');
				}
			}
		} );
	});
});
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
		type: "POST",
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
		type: "POST",
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
		type: "POST",
		success: function( data ) {
			$("#ajax").html(data); 
		}
	} );	
}
function createHistroy() {
	try {
		var get_history_array = JSON.parse(Cookies.get('history'));
	}	
	catch {
		var get_history_array = ['login.py', 'login.py','login.py'];
		Cookies.set('history', JSON.stringify(get_history_array), { expires: 1, path: '/app' });
	}
}
function listHistroy() {	
	var browse_history = JSON.parse(Cookies.get('history'));
	var history_link = '';
	var title = []
	var link_text = []
	for(let i = 0; i < browse_history.length; i++){
		if (i == 0) {
			if(browse_history[0] == browse_history[1]) {
				continue
			}
			browse_history[0] = browse_history[1];
		}
		if (i == 1) {			
			if(browse_history[1] == browse_history[2]) {
				continue
			}
			browse_history[1] = browse_history[2]
		}
		if (i == 2) {
			browse_history[2] = cur_url[0]
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
	Cookies.set('history', JSON.stringify(browse_history), { expires: 1, path: '/app' });
}
createHistroy()
listHistroy()