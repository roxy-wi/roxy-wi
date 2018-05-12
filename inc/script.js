var url = "/inc/script.js";
var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
var intervalId;

function autoRefreshStyle(autoRefresh) {
	var margin;
	if (cur_url[0] == "overview.py") {
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
		$('#1').text('Auto-refresh');
		$('#0').text('Auto-refresh');
		$('.auto-refresh-pause').css('display', 'none');
		$('.auto-refresh-resume').css('display', 'none');
		hideAutoRefreshDiv();
	} else {
		clearInterval(intervalId);
		Cookies.set('auto-refresh', interval, { expires: 365 });
		startSetInterval(interval);
		hideAutoRefreshDiv();
		autoRefreshStyle(interval);
	}
}

function startSetInterval(interval) {	
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
	} else if (cur_url[0] == "apachelogs.py") {
		intervalId = setInterval('showApacheLog()', interval);
		showApacheLog();
	} 
}
function pauseAutoRefresh() {
	clearInterval(intervalId);
	$(function() {
		$('.auto-refresh-pause').css('display', 'none');
		$('.auto-refresh-resume').css('display', 'inline');
	});
}	
function pauseAutoResume(){
	var autoRefresh = Cookies.get('auto-refresh');
	setRefreshInterval(autoRefresh);
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
function showOverview() {	
	showOverviewServers();
	$.ajax( {
		url: "options.py",
		data: {
			act: "overview",
		},
		type: "GET",
		success: function( data ) {
			$("#ajaxstatus").empty();
			$("#ajaxstatus").html(data);
		}					
	} );
}

function showOverviewServers() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overviewServers",
		},
		type: "GET",
		success: function( data ) {
			$("#ajaxservers").html(data);
			$.getScript('/inc/overview.js');
		}					
	} );
}

function showStats() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "stats",
			serv: $("#serv").val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);			
			window.history.pushState("Stats", "Stats", cur_url[0]+"?serv="+$("#serv").val());
		}					
	} );
}
function showLog() {
	$.ajax( {
		url: "options.py",
		data: {
			rows: $('#rows').val(),
			serv: $("#serv").val(),
			grep: $("#grep").val(),
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Logs", "Logs", cur_url[0]+"?serv="+$("#serv").val()+"&rows="+$('#rows').val()+"&grep="+$("#grep").val());
		}					
	} );
}
function showMap() {
	var unique = $.now();
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showMap"
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
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
			save: saveCheck
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
			right: $("#right").val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			$.getScript(url);
		}					
	} );
}
function showCompareConfigs() {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "showCompareConfigs",
			open: "open"
		},
		type: "GET",
		success: function( data ) {
			$("#ajax-compare").html(data);
			$.getScript(url);
		}					
	} );
}
function showConfig() {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShow"
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			var urlConfigShowJs = '/inc/configshow.js';
			$.getScript(urlConfigShowJs);
		}					
	} );
}
function showUploadConfig() {
	$.ajax( {
		url: "options.py",
		data: {
			serv: $("#serv").val(),
			act: "configShow",
			configver: $('#configver').val()
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("Show config", "Show config", cur_url[0]+"?serv="+$("#serv").val()+"&open=open&configver="+$('#configver').val());
			var urlConfigShowJs = '/inc/configshow.js';
			$.getScript(urlConfigShowJs);
		}					
	} );
}
function viewLogs() {
	$.ajax( {
		url: "options.py",
		data: {
			viewlogs: $('#viewlogs').val(),
		},
		type: "GET",
		success: function( data ) {
			$("#ajax").html(data);
			window.history.pushState("View logs", "View logs", cur_url[0]+"?viewlogs="+$("#viewlogs").val());
		}					
	} );
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
		
    var tooltips = $( "[title]" ).tooltip({
      position: {
        my: "left top",
        at: "right+5 top-25",
        collision: "none"
      }
    });
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
			$( "#https-listen" ).prop("checked", false);
		} else {
			$( "#https-listen-span" ).show("fast");
		}
	});
	$( "#frontend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#frontend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-frontend-span" ).hide("fast");
			$( "#https-hide-frontend" ).hide("fast");
		} else {
			$( "#https-frontend-span" ).show("fast");
		}
	});
	$( "#backend-mode-select" ).on('selectmenuchange',function()  {
		if ($( "#backend-mode-select option:selected" ).val() == "tcp") {
			$( "#https-backend-span" ).hide("fast");
			$( "#https-hide-backend" ).hide("fast");
		} else {
			$( "#https-backend-span" ).show("fast");
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
			$( "#path-cert-backend" ).attr('required',true);
		} else {
			$( "#https-hide-backend" ).hide( "fast" );
			$( "#path-cert-backend" ).prop('required',false);
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
		}
	});
	$( "#cookie2" ).click( function(){
		if ($('#cookie2').is(':checked')) {
			$("#cookie_name2" ).attr('required',true);
			$("#cookie_div2").show( "fast" );
		} else {
			$("#cookie_name2" ).attr('required',false);
			$("#cookie_div2").hide( "fast" );
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
					serv: $("#serv").val()
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
					serv: $("#serv2").val()
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
					serv: $("#serv2").val()
				},
				success: function( data ) {
					response(data.split('"'));
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
	$( "#path-cert-listen" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					getcert:1,
					serv: $("#serv").val()
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
	$( "#path-cert-frontend" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					getcert:1,
					serv: $("#serv2").val()
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
	$( "#path-cert-backend" ).autocomplete({
		source: function( request, response ) {
			$.ajax( {
				url: "options.py",
				data: {
					getcert:1,
					serv: $("#serv3").val()
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
					serv: $("#master").val()
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
					serv: $("#master-add").val()
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
				ssl_name: $('#ssl_name').val()
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
				getcert: "viewcert"
			},
			type: "GET",
			success: function( data ) {
				if (data.indexOf('danger') != '-1') {
					$("#ajax-show-ssl").html(data);
				} else {
					$('.alert-danger').remove();
					$( "#ajax-show-ssl").html("<b>"+data+"</b>");					
				} 
			}
		} );
	});
});
function replace_text(id_textarea, text_var) {
	var str = $(id_textarea).val();
	var len = str.length;
	var len_var = text_var.length;
	var beg = str.indexOf(text_var);
	var end = beg + len_var
	var text_val = str.substring(0, beg) + str.substring(end, len);
	$(id_textarea).text(text_val);
}