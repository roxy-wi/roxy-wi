var cur_url = window.location.href.split('/').pop();
cur_url = cur_url.split('?');
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
						alert(data);
					} else {
						if (cur_url[0] == "hapservers.py") {
							location.reload()
						} else {
							setTimeout(showOverview, 2000)					
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
						alert(data);
					} else {
						setTimeout(showOverviewWaf, 2000)						
					}
				},
				error: function(){
					alert(w.data_error);
				}					
			} );
	}
$( function() {
	$('.start').click(function() {
		var id = $(this).attr('id');
		id = id.split('-')[1]
		confirmAjaxAction("start", "hap", id);
	});
	$('.stop').click(function() {
		var id = $(this).attr('id');
		id = id.split('-')[1]
		confirmAjaxAction("stop", "hap", id);
	});
	$('.restart').click(function() {
		var id = $(this).attr('id');
		id = id.split('-')[1]
		confirmAjaxAction("restart", "hap", id);
	});
	$('.start-waf').click(function() {
		var id = $(this).attr('id');
		confirmAjaxAction("start", "waf", id);
	});
	$('.stop-waf').click(function() {
		var id = $(this).attr('id');
		confirmAjaxAction("stop", "waf", id);
	});
	$('.restart-waf').click(function() {
		var id = $(this).attr('id');
		confirmAjaxAction("restart", "waf", id);
	});
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
	if (cur_url[0] == "overview.py" || cur_url[0] == "waf.py" || cur_url[0] == "metrics.py") {
		$('#secIntervals').css('display', 'none');
	}
	$('#apply_close').click( function() {
		$("#apply").css('display', 'none');
		Cookies.remove('restart', { path: '' });
	});
});
function confirmAjaxAction(action, service, id) {
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height: "auto",
		width: 400,
		modal: true,
		title: "Are you sure you want "+ action + " " + id + "?",
		buttons: {
			"Sure": function() {
				$( this ).dialog( "close" );
				if(service == "hap") {
					ajaxActionServers(action, id);
					if(action == "restart") {
						if(Cookies.get('restart')) {
							Cookies.remove('restart', { path: '' });
							$("#apply").css('display', 'none');
						}
					}
				} else if (service == "waf") {
					ajaxActionWafServers(action, id)
				}
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}