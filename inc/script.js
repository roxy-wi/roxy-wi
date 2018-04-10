function autoRefreshStyle(autoRefresh) {
	var margin;
	autoRefresh = autoRefresh / 1000;
	if ( autoRefresh == 60) {
		timeRange = " minute"
		autoRefresh = autoRefresh / 60;
		margin = '-80px';
	} else if ( autoRefresh > 60 && autoRefresh < 3600 ) {
		timeRange = " minutes"
		autoRefresh = autoRefresh / 60;
		margin = '-93px';
	} else if ( autoRefresh >= 3600 && autoRefresh < 86401 ) {
		timeRange = " hours"
		autoRefresh = autoRefresh / 3600;
		margin = '-80px';				
	} else {
		timeRange = " seconds";
		margin = '-100px';
	}
	$('#1').text(autoRefresh + timeRange);
	$('#0').text(autoRefresh + timeRange);
	$('.auto-refresh-pause').css('display', 'inline');		
	$('.auto-refresh-pause').css('margin-left', margin);	
	$('.auto-refresh img').remove();
}

function setRefreshInterval(interval) {
	if (interval == "0") {
		Cookies.remove('auto-refresh');
		pauseAutoRefresh();
		$('.auto-refresh').append('<img style="margin-top: 10px; margin-left: -110px; position: fixed;" src=/image/pic/update.png alt="restart" class="icon">');
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

var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
var intervalId;
function startSetInterval(interval) {	
	if (cur_url[0] == "logs.py") {
		intervalId = setInterval('showLog()', interval);
		showLog();
	} else if (cur_url[0] == "viewsttats.py") {
		intervalId = setInterval('showStats()', interval);
		showStats()
	} else if (cur_url[0] == "overview.py") {
		intervalId = setInterval('showOverview()', interval);
		showOverview();
	}  else {
		intervalId = setInterval('document.location.reload()', interval);
	}
}
function pauseAutoRefresh() {
	clearInterval(intervalId);
	$(function() {
		$('.auto-refresh-pause').attr('onclick', 'pauseAutoResume()');
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
function showOverview() {
	$.ajax( {
		url: "options.py",
		data: {
			act: "overview",
		},
		type: "GET",
		beforeSend: function () {
			NProgress.start();
		},
		complete: function () {
			NProgress.done();
		},
		success: function( data ) {
			var form = $("#ajax").html();
			$("#ajax").html(data);
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
		beforeSend: function () {
			NProgress.start();
		},
		complete: function () {
			NProgress.done();
		},
		success: function( data ) {
			var form = $("#ajax").html();
			$("#ajax").html(data);
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
		beforeSend: function () {
			NProgress.start();
		},
		complete: function () {
			NProgress.done();
		},
		success: function( data ) {
			var form = $("#ajax").html();
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
		beforeSend: function () {
			NProgress.start();
		},
		complete: function () {
			NProgress.done();
		},
		success: function( data ) {
			var form = $("#ajax").html();
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
		beforeSend: function () {
			NProgress.start();
		},
		complete: function () {
			NProgress.done();
		},
		success: function( data ) {
			var form = $("#ajax").html();
			$("#ajax").html(data);
		}					
	} );
}

$( function() {
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
	$( "#number" ).spinner();
	$( ".controlgroup" ).controlgroup();
	$( ".configShow" ).accordion({
      collapsible: true,
	  heightStyle: "content",
	  icons: { "header": "ui-icon-plus", "activeHeader": "ui-icon-minus" }
    });
	var headers = $('.configShow .accordion-header');
	var contentAreas = $('.configShow .ui-accordion-content ').hide()
	.first().show().end();
	var expandLink = $('.accordion-expand-all');

	// add the accordion functionality
	headers.click(function() {
		// close all panels
		contentAreas.slideUp();
		// open the appropriate panel
		$(this).next().slideDown();
		// reset Expand all button
		expandLink.text('Expand all')
			.data('isAllOpen', false);
		// stop page scroll
		return false;
	});

	// hook up the expand/collapse all
	expandLink.click(function(){
		var isAllOpen = !$(this).data('isAllOpen');
		console.log({isAllOpen: isAllOpen, contentAreas: contentAreas})
		contentAreas[isAllOpen? 'slideDown': 'slideUp']();
		
		expandLink.text(isAllOpen? 'Collapse All': 'Expand all')
					.data('isAllOpen', isAllOpen);    
	});
	
	function ajaxActionServers(action, id) {
		var bad_ans = 'Bad config, check please';
		$.ajax( {
				url: "options.py",
				data: {
					action: action,
					serv: id
				},
				success: function( data ) {
					data = data.replace(/\s+/g,' ');
					if( data ==  'Bad config, check please ' ) {
						alert(data);
					} else {
						document.location.reload();
					}
				},
				error: function(){
					alert(w.data_error);
				}					
			} );
	}
	
	$('.start').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("start", id);
	});
	$('.stop').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("stop", id);
	});
	$('.restart').click(function() {
		var id = $(this).attr('id');
		ajaxActionServers("restart", id);
	});

    var location = window.location.href;
    var cur_url = '/cgi-bin/' + location.split('/').pop();
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
	$ ( "#show-all-users" ).click( function() {
		if($( "#show-all-users" ).text() == "Show all") {
			$( ".show-users" ).show("fast");
			$( "#show-all-users" ).text("Hide");
			$( "show-all-users" ).attr("title") = "Hide all users";
		} else {
			$( ".show-users" ).hide("fast");
			$( "#show-all-users" ).attr("title", "Show all users");
			$( "#show-all-users" ).text("Show all");
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
		"acl", "http-request", "http-response", "set-uri", "set-url", "set-header", "add-header", "del-header", "replace-header", "path_beg", "url_beg()", "urlp_sub()", "tcpka", "tcplog", "forwardfor", "option"
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
					response(data.split("\n"));
				}					
			} );
		},
		autoFocus: true,
		minLength: -1
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
					serv: $("#serv").val()
				},
				success: function( data ) {
					response(data.split("\n"));
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
	input = $('<tr><td><input type="text" name="login-add" value="" class="form-control"></td>	<td><input type="passwrod" name="passwrod-add" value="" class="form-control"></td> <td><input type="text" name="role-add" value="" class="form-control"></td><td><input type="text" name="groups-add" value="" class="form-control"></td></tr>');
	$( "#add-user" ).click( function(){
		$( "#users-table" ).append(input);
	});
} );

function removeUser(id) {
	document.getElementById(id).parentNode.removeChild(document.getElementById(id));
    return false;
}